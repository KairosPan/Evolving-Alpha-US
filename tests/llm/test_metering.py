"""Unit tests for the A6 spend meter (alpha/llm/metering.py).

Charter: *Resources as Security* — a reported scalar is not a governed one. Offline, keyless,
deterministic (MockLLMClient meters via token estimation).
"""
import math

import pytest

from alpha.llm.client import MockLLMClient
from alpha.llm.metering import (
    Budget,
    BudgetExceeded,
    CostRecord,
    DEFAULT_PRICE,
    MeteredClient,
    ModelPrice,
    PRICES,
    SpendMeter,
    Usage,
    budget_from_env,
    estimate_tokens,
    format_summary,
    metered_factory,
    price_of,
)

# A fixed table so exact-cost assertions don't ride the (updatable) real rates.
_FIXED = {"m": ModelPrice(in_per_1m=1_000_000.0, out_per_1m=2_000_000.0)}  # $1/tok in, $2/tok out


class _UsageClient:
    """A stub real client: republishes provider usage on `last_usage` every call (as the real
    openai_compat/anthropic clients do), returns fixed text, exposes a `.model`."""

    def __init__(self, text, usage, model="m"):
        self._text, self._usage, self.model = text, usage, model
        self.last_usage = usage

    def complete(self, system, user):
        self.last_usage = self._usage          # real clients set usage on every successful call
        return self._text


# --------------------------------------------------------------------------- cost model

def test_estimate_tokens_deterministic():
    assert estimate_tokens("") == 1                    # floor 1, never zero
    assert estimate_tokens("abcd") == 1                # 4 chars -> 1
    assert estimate_tokens("a" * 10) == math.ceil(10 / 4)  # 3


def test_price_of_uses_table_and_default():
    # known model in a fixed table: 2 in + 3 out at $1/$2 per token
    assert price_of("m", 2, 3, _FIXED) == pytest.approx(2 * 1.0 + 3 * 2.0)
    # unknown model -> DEFAULT_PRICE, and it is NON-ZERO (fail-toward-metering)
    unknown = price_of("no-such-model", 1000, 1000, PRICES)
    assert unknown > 0.0
    assert DEFAULT_PRICE.in_per_1m > 0 and DEFAULT_PRICE.out_per_1m > 0


def test_default_role_models_are_priced_nonzero():
    # the live default id (deepseek-v4-pro) is in the table so a real run is never silently free
    assert "deepseek-v4-pro" in PRICES


# --------------------------------------------------------------------------- (a) every call records

def test_mock_call_produces_estimated_cost_record():
    meter = SpendMeter()
    client = meter.wrap(MockLLMClient('{"ok": 1}'), role="agent")
    out = client.complete("system here", "user here")
    assert out == '{"ok": 1}'                          # delegates unchanged (byte-identical text)
    assert len(meter.records) == 1
    rec = meter.records[0]
    assert rec.role == "agent" and rec.model == "mock"
    assert rec.estimated is True                       # MockLLMClient has no provider usage
    assert rec.tokens_in == estimate_tokens("system here") + estimate_tokens("user here")
    assert rec.tokens_out == estimate_tokens('{"ok": 1}')
    assert rec.cost_usd > 0.0                           # priced at DEFAULT_PRICE (non-zero)


def test_provider_usage_is_used_when_present():
    meter = SpendMeter()
    client = MeteredClient(_UsageClient("resp", Usage(tokens_in=100, tokens_out=40)),
                           role="refiner", meter=meter, prices=_FIXED)
    client.complete("s", "u")
    rec = meter.records[0]
    assert rec.estimated is False                       # real provider counts, not estimated
    assert (rec.tokens_in, rec.tokens_out) == (100, 40)
    assert rec.cost_usd == pytest.approx(100 * 1.0 + 40 * 2.0)


def test_usage_is_cleared_after_read_no_stale_reuse():
    class _OneShot:                                     # publishes usage ONCE, then stops (never again)
        model = "m"

        def __init__(self):
            self.last_usage = Usage(tokens_in=10, tokens_out=5)

        def complete(self, system, user):
            return "resp"                               # does NOT re-set last_usage

    inner = _OneShot()
    meter = SpendMeter()
    client = MeteredClient(inner, role="agent", meter=meter, prices=_FIXED)
    client.complete("s", "u")
    assert meter.records[0].estimated is False          # first call used the published usage
    assert inner.last_usage is None                     # wrapper cleared it -> no stale reuse
    client.complete("s2", "u2")
    assert meter.records[1].estimated is True            # second call estimates (usage gone)


def test_metered_client_is_transparent_proxy():
    inner = _UsageClient("x", None, model="deepseek-chat")
    client = MeteredClient(inner, role="agent", meter=SpendMeter())
    assert client.model == "deepseek-chat"              # __getattr__ delegates non-call attributes


# --------------------------------------------------------------------------- (b) hard breach halts

def test_hard_usd_breach_raises_budget_exceeded():
    meter = SpendMeter(Budget(usd=5.0))
    client = MeteredClient(_UsageClient("r", Usage(3, 0)), role="agent", meter=meter, prices=_FIXED)
    client.complete("s", "u")                           # $3 spent, under ceiling -> ok
    with pytest.raises(BudgetExceeded) as ei:
        client.complete("s", "u")                       # +$3 -> $6 > $5 -> halt
    err = ei.value
    assert err.dimension == "usd" and err.limit == 5.0
    assert err.spent == pytest.approx(6.0) and err.n_calls == 2
    msg = str(err)
    assert "BudgetExceeded" in msg and "5" in msg and "agent" in msg   # self-describing + loud


def test_breach_stops_the_loop_subsequent_calls_do_not_run():
    """A breach must STOP the loop, not just log: the caller sees the raise and aborts."""
    meter = SpendMeter(Budget(usd=1.0))
    calls = {"n": 0}

    class _Counting:
        model = "m"
        last_usage = None

        def complete(self, system, user):
            calls["n"] += 1
            return "x" * 40                             # ~10 tokens out

    client = MeteredClient(_Counting(), role="agent", meter=meter, prices=_FIXED)
    # a single call already blows a $1 ceiling (40 chars out = 10 tok * $2 = $20)
    with pytest.raises(BudgetExceeded):
        for _ in range(5):
            client.complete("s", "u")
    assert calls["n"] == 1                               # loop aborted at the first breach


def test_token_dimension_budget_breach():
    meter = SpendMeter(Budget(tokens=150))
    client = MeteredClient(_UsageClient("r", Usage(100, 40)), role="agent", meter=meter, prices=_FIXED)
    client.complete("s", "u")                           # 140 tok, under 150
    with pytest.raises(BudgetExceeded) as ei:
        client.complete("s", "u")                       # 280 tok > 150
    assert ei.value.dimension == "tokens"


# --------------------------------------------------------------------------- (c) soft warns, no halt

def test_soft_threshold_warns_once_without_halting():
    warns: list[str] = []
    meter = SpendMeter(Budget(usd=10.0, soft_ratio=0.5), on_warn=warns.append)
    client = MeteredClient(_UsageClient("r", Usage(3, 0)), role="agent", meter=meter, prices=_FIXED)
    client.complete("s", "u")                           # $3 < $5 soft line -> no warn
    assert warns == []
    client.complete("s", "u")                           # $6 >= $5 soft line -> warn once, no raise
    assert len(warns) == 1
    client.complete("s", "u")                           # $9 still < $10 hard -> no second warn (once)
    assert len(warns) == 1
    assert meter.total_usd == pytest.approx(9.0)        # never raised


def test_hard_beats_soft_when_both_cross_on_one_call():
    warns: list[str] = []
    meter = SpendMeter(Budget(usd=2.0, soft_ratio=0.5), on_warn=warns.append)
    client = MeteredClient(_UsageClient("r", Usage(3, 0)), role="agent", meter=meter, prices=_FIXED)
    with pytest.raises(BudgetExceeded):                 # $3 crosses both soft($1) and hard($2) -> raise
        client.complete("s", "u")
    assert warns == []                                  # hard checked first: it raised, never warned


# --------------------------------------------------------------------------- (d) unlimited / summary

def test_no_budget_records_but_never_raises():
    meter = SpendMeter()                                # unlimited
    client = MeteredClient(_UsageClient("r", Usage(10 ** 9, 10 ** 9)), role="agent",
                           meter=meter, prices=_FIXED)
    for _ in range(3):
        client.complete("s", "u")                       # astronomically expensive, no budget -> fine
    assert len(meter.records) == 3 and meter.budget is None


def test_summary_aggregates_by_role_and_model():
    meter = SpendMeter(Budget(usd=100.0))
    MeteredClient(_UsageClient("r", Usage(10, 10), model="m"), role="agent",
                  meter=meter, prices=_FIXED).complete("s", "u")
    MeteredClient(_UsageClient("r", Usage(20, 0), model="m2"), role="refiner",
                  meter=meter, prices={"m2": ModelPrice(0.0, 0.0)}).complete("s", "u")
    summ = meter.summary()
    assert summ["n_calls"] == 2
    assert summ["total_tokens"] == 40
    assert set(summ["by_role"]) == {"agent", "refiner"}
    assert set(summ["by_model"]) == {"m", "m2"}
    assert summ["budget"] == {"usd": 100.0, "tokens": None, "soft_ratio": 0.8}
    assert isinstance(format_summary(summ), str) and "total" in format_summary(summ).lower()


# --------------------------------------------------------------------------- budget construction

def test_budget_requires_a_ceiling():
    with pytest.raises(ValueError):
        Budget()
    with pytest.raises(ValueError):
        Budget(usd=1.0, soft_ratio=1.5)                 # ratio out of (0,1]


def test_budget_rejects_non_positive_ceiling():
    """A 0/negative ceiling is a config error — refused at construction (both env + CLI funnel here),
    not left to breach on the first paid call with a nonsensical "spent $X exceeded $-5" message."""
    for bad in (lambda: Budget(usd=0.0), lambda: Budget(usd=-5.0),
                lambda: Budget(tokens=0), lambda: Budget(tokens=-1)):
        with pytest.raises(ValueError):
            bad()
    assert Budget(usd=0.00001).usd == 0.00001            # a legit tiny positive ceiling still constructs
    assert Budget(tokens=1).tokens == 1


def test_budget_from_env_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("ALPHA_SPEND_BUDGET_USD", "5.0")
    monkeypatch.setenv("ALPHA_SPEND_SOFT_RATIO", "0.7")
    b = budget_from_env()
    assert b is not None and b.usd == 5.0 and b.soft_ratio == 0.7
    b2 = budget_from_env(usd=9.0)                        # CLI wins
    assert b2.usd == 9.0


def test_budget_from_env_none_when_unset(monkeypatch):
    monkeypatch.delenv("ALPHA_SPEND_BUDGET_USD", raising=False)
    monkeypatch.delenv("ALPHA_SPEND_BUDGET_TOKENS", raising=False)
    assert budget_from_env() is None                    # no ceiling -> unlimited (None)


def test_metered_factory_none_is_identity_else_wraps():
    base = lambda: MockLLMClient("{}")
    assert metered_factory(base, "agent", None) is base   # meter=None -> byte-identical (same factory)
    meter = SpendMeter()
    wrapped = metered_factory(base, "agent", meter)
    client = wrapped()
    assert isinstance(client, MeteredClient)
    client.complete("s", "u")
    assert len(meter.records) == 1 and meter.records[0].role == "agent"


def test_cost_record_is_a_plain_value():
    rec = CostRecord(role="agent", model="m", tokens_in=1, tokens_out=2, cost_usd=0.5, estimated=True)
    assert (rec.role, rec.model, rec.tokens_in, rec.tokens_out, rec.cost_usd, rec.estimated) == \
        ("agent", "m", 1, 2, 0.5, True)
