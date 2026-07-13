"""Spend metering for the LLM seam — A6, charter *Resources as Security: Cost Is Also the Adversary's
Weapon*.

"A *reported* scalar is not a *governed* one." The watchdog watches failure; this module makes **spend**
a watched signal beside it. Every model call the system dispatches is metered (token count × price) —
so a pure-inference loop with no tool calls, the all-success economic-DoS runaway that fires no failure
signature, is still counted. A `Budget` turns the count into an enforced ceiling: a soft threshold
warns, a hard ceiling raises `BudgetExceeded` and the run aborts loudly (governed, not merely reported).

Additive by construction: no `Budget` attached → records only, unlimited, byte-identical to an unmetered
run. `make_client(role)` with no `meter=` returns the raw client unchanged.

Scope (this arc): the run-batch (unattended) enforcement — halt on breach — which is the correct action
for the metered producers (refine_live / verdict / decisions batches; charter: *Machine authority
boundary* bounded detect-and-kill). The richer charter ladder — foreground pause-and-prompt, the
cross-session daily accumulator, the egress-call meter, per-party rate limiting — is out of scope here.

Accepted risks carried from the charter: (1) the bill up to the cap is still paid (the ceiling bounds,
does not refund); (2) granularity is one call — the signal is checked *between* calls, so a single call
over the remaining budget overshoots by that much; (3) a wrong/stale price list makes the ceiling wrong.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

_log = logging.getLogger("alpha.metering")


# --------------------------------------------------------------------------- cost model

@dataclass(frozen=True)
class Usage:
    """Normalized provider token usage, published by a real client on its `last_usage` attribute."""
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 tokens (input, output). Approximate list prices — see PRICES."""
    in_per_1m: float
    out_per_1m: float


# APPROXIMATE public list prices (USD / 1M tokens), 2026-07 snapshot — updatable IN PLACE. Per the
# charter (*Resources as Security* → "Money is denominated by a versioned price list") the real home is
# the versioned vendor price list folded into the third-party lockfile as a governed, agent-unwritable
# data row; until that lockfile lands this table is the interim pin. Honest limit (charter accepted risk
# 3): there is no external price feed, so a silent vendor repricing is caught only when this pin is
# reconciled, not in the moment it takes effect.
PRICES: dict[str, ModelPrice] = {
    "deepseek-chat": ModelPrice(0.27, 1.10),
    "deepseek-reasoner": ModelPrice(0.55, 2.19),
    "deepseek-v4-pro": ModelPrice(0.55, 2.19),      # the intended default id (see llm/config.py)
    "claude-sonnet-4-6": ModelPrice(3.00, 15.00),
    "claude-opus-4-8": ModelPrice(15.00, 75.00),
}
# Unknown model → non-zero fallback: fail-toward-metering, so an unrecognized id is never silently free
# (a silent $0 would let an adversary evade the ceiling by naming an untabled model).
DEFAULT_PRICE = ModelPrice(1.00, 3.00)


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate for offline metering when a provider returns no usage: ~4 chars per
    token, floored at 1 so a call is never counted as zero cost."""
    return max(1, math.ceil(len(text or "") / 4))


def price_of(model: str, tokens_in: int, tokens_out: int,
             prices: "dict[str, ModelPrice] | None" = None) -> float:
    """USD cost of a call. Unknown model → DEFAULT_PRICE (non-zero)."""
    table = PRICES if prices is None else prices
    p = table.get(model, DEFAULT_PRICE)
    return tokens_in / 1_000_000 * p.in_per_1m + tokens_out / 1_000_000 * p.out_per_1m


# --------------------------------------------------------------------------- records + budget

@dataclass(frozen=True)
class CostRecord:
    """One metered LLM call. `estimated` is True when tokens came from text-length estimation rather
    than provider-reported usage (accuracy caveat rides the record)."""
    role: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    estimated: bool


@dataclass(frozen=True)
class Budget:
    """A user-declared spend ceiling (charter: user-direct records). At least one hard ceiling (usd or
    tokens) is required; a breach of either halts. `soft_ratio` in (0,1] sets the warn line."""
    usd: "float | None" = None
    tokens: "int | None" = None
    soft_ratio: float = 0.8

    def __post_init__(self) -> None:
        if self.usd is None and self.tokens is None:
            raise ValueError("Budget needs at least one hard ceiling (usd= or tokens=)")
        # A non-positive ceiling is a config error (a 0/negative cap breaches on the first paid call with
        # a confusing "spent $X exceeded $-5" message). Refuse it at construction — None-safe, per
        # dimension — so both the CLI and env paths (which funnel through here) fail before any client.
        if self.usd is not None and self.usd <= 0:
            raise ValueError(f"budget usd ceiling must be positive, got {self.usd}")
        if self.tokens is not None and self.tokens <= 0:
            raise ValueError(f"budget tokens ceiling must be positive, got {self.tokens}")
        if not (0.0 < self.soft_ratio <= 1.0):
            raise ValueError(f"soft_ratio must be in (0, 1], got {self.soft_ratio}")


class BudgetExceeded(RuntimeError):
    """Raised when a metered call pushes cumulative spend past a hard ceiling. Self-describing and loud:
    the message names the breached dimension, the spend, the ceiling, and the tripping call. Propagates
    out of the run function so the loop ABORTS (governed halt) rather than logging and continuing."""

    def __init__(self, *, dimension: str, spent: float, limit: float, n_calls: int,
                 last: CostRecord) -> None:
        self.dimension = dimension          # "usd" | "tokens"
        self.spent = spent
        self.limit = limit
        self.n_calls = n_calls
        self.last = last
        shown = f"${spent:.4f}" if dimension == "usd" else f"{int(spent)} tokens"
        cap = f"${limit:.4f}" if dimension == "usd" else f"{int(limit)} tokens"
        super().__init__(
            f"BudgetExceeded: {dimension} spend {shown} exceeded the ceiling {cap} after {n_calls} "
            f"LLM call(s). Last call: role={last.role} model={last.model} "
            f"cost=${last.cost_usd:.4f} ({last.tokens_in}+{last.tokens_out} tok"
            f"{', estimated' if last.estimated else ''}). Run halted — governed spend ceiling "
            f"(charter: Resources as Security)."
        )


def _default_warn(msg: str) -> None:
    _log.warning(msg)


# --------------------------------------------------------------------------- the meter (watchdog)

class SpendMeter:
    """Accumulates CostRecords and enforces a Budget as a watched signal beside failure.

    `record()` appends, updates totals, then (only if a budget is attached) applies the ladder: a hard
    ceiling breach raises BudgetExceeded (checked FIRST, so it wins over soft); else a soft-threshold
    crossing warns ONCE via `on_warn` (default logging.warning) and the run continues. Enforcement is
    between calls — the just-completed call is already paid (charter accepted risks 1 & 2). No budget →
    records only, never raises (unlimited)."""

    def __init__(self, budget: "Budget | None" = None, *, on_warn=None) -> None:
        self.budget = budget
        self.records: list[CostRecord] = []
        self.total_usd = 0.0
        self.total_tokens = 0
        self._on_warn = on_warn or _default_warn
        self._soft_warned = False

    def wrap(self, client, *, role: str) -> "MeteredClient":
        """Wrap a client so its every call meters into this ledger. The one metering primitive; also
        used by make_client(role, meter=…) and by the run entry points to wrap injected factories."""
        return MeteredClient(client, role=role, meter=self)

    def record(self, rec: CostRecord) -> None:
        self.records.append(rec)
        self.total_usd += rec.cost_usd
        self.total_tokens += rec.tokens_in + rec.tokens_out
        if self.budget is None:
            return
        b = self.budget
        if b.usd is not None and self.total_usd > b.usd:
            raise BudgetExceeded(dimension="usd", spent=self.total_usd, limit=b.usd,
                                 n_calls=len(self.records), last=rec)
        if b.tokens is not None and self.total_tokens > b.tokens:
            raise BudgetExceeded(dimension="tokens", spent=self.total_tokens, limit=float(b.tokens),
                                 n_calls=len(self.records), last=rec)
        self._maybe_soft_warn()

    def _maybe_soft_warn(self) -> None:
        if self._soft_warned:
            return
        b = self.budget
        crossed = ((b.usd is not None and self.total_usd >= b.soft_ratio * b.usd) or
                   (b.tokens is not None and self.total_tokens >= b.soft_ratio * b.tokens))
        if crossed:
            self._soft_warned = True
            pct = int(round(b.soft_ratio * 100))
            self._on_warn(
                f"spend watchdog: crossed {pct}% soft threshold — spent ${self.total_usd:.4f} / "
                f"{self.total_tokens} tok across {len(self.records)} call(s); ceiling "
                f"usd={b.usd} tokens={b.tokens}."
            )

    def summary(self) -> dict:
        """Additive run-output payload (feeds A8): totals, per-role/per-model breakdown, the budget."""
        by_role: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        for r in self.records:
            for key, bucket in ((r.role, by_role), (r.model, by_model)):
                slot = bucket.setdefault(key, {"n": 0, "tokens": 0, "cost_usd": 0.0})
                slot["n"] += 1
                slot["tokens"] += r.tokens_in + r.tokens_out
                slot["cost_usd"] = round(slot["cost_usd"] + r.cost_usd, 6)
        return {
            "total_usd": round(self.total_usd, 6),
            "total_tokens": self.total_tokens,
            "n_calls": len(self.records),
            "estimated_calls": sum(1 for r in self.records if r.estimated),
            "by_role": by_role,
            "by_model": by_model,
            "budget": (None if self.budget is None else
                       {"usd": self.budget.usd, "tokens": self.budget.tokens,
                        "soft_ratio": self.budget.soft_ratio}),
            "soft_warned": self._soft_warned,
        }


# --------------------------------------------------------------------------- the metered client

class MeteredClient:
    """Transparent proxy over any LLMClient/ChatLLMClient that meters every complete()/chat() call into
    a SpendMeter. Non-call attributes (`.model`, `.temperature`, …) delegate via __getattr__, so the
    wrapper is a drop-in for the raw client. Uses provider usage (the inner client's `last_usage`
    side-channel) when present, else estimates tokens from text length."""

    def __init__(self, inner, *, role: str, meter: SpendMeter,
                 prices: "dict[str, ModelPrice] | None" = None) -> None:
        self._inner = inner
        self._role = role
        self._meter = meter
        self._prices = prices

    def complete(self, system: str, user: str) -> str:
        text = self._inner.complete(system, user)
        self._meter_call(estimate_in=lambda: estimate_tokens(system) + estimate_tokens(user),
                         text=text)
        return text

    def chat(self, system: str, messages: list) -> str:
        text = self._inner.chat(system, messages)
        self._meter_call(
            estimate_in=lambda: estimate_tokens(system) + sum(
                estimate_tokens(getattr(m, "text", "")) for m in messages),
            text=text)
        return text

    def _meter_call(self, *, estimate_in, text: str) -> None:
        usage = self._read_usage()
        if usage is not None:
            tokens_in, tokens_out, estimated = usage.tokens_in, usage.tokens_out, False
        else:
            tokens_in, tokens_out, estimated = estimate_in(), estimate_tokens(text), True
        model = getattr(self._inner, "model", "mock")
        rec = CostRecord(role=self._role, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                         cost_usd=price_of(model, tokens_in, tokens_out, self._prices),
                         estimated=estimated)
        self._meter.record(rec)             # may raise BudgetExceeded -> the run aborts

    def _read_usage(self) -> "Usage | None":
        usage = getattr(self._inner, "last_usage", None)
        if hasattr(self._inner, "last_usage"):
            try:
                self._inner.last_usage = None            # clear so a next call without usage estimates
            except Exception:                            # noqa: BLE001 — read-only attr: ignore
                pass
        return usage

    def __getattr__(self, name):                         # transparent proxy for everything else
        return getattr(self._inner, name)


# --------------------------------------------------------------------------- budget construction

def _env_float(name: str) -> "float | None":
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else None


def _env_int(name: str) -> "int | None":
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else None


def metered_factory(base, role: str, meter: "SpendMeter | None"):
    """Wrap an LLM-client factory so each client it builds meters into `meter`. meter=None returns the
    base factory UNCHANGED (byte-identical) — the additive seam the run entry points use so a threaded
    meter also covers a test-injected factory, not only make_client's own clients."""
    if meter is None:
        return base
    return lambda: meter.wrap(base(), role=role)


def budget_from_env(*, usd: "float | None" = None, tokens: "int | None" = None,
                    soft_ratio: "float | None" = None) -> "Budget | None":
    """Build a Budget from CLI args (passed here) over env fallbacks — the user's ceiling declaration:
    ALPHA_SPEND_BUDGET_USD / ALPHA_SPEND_BUDGET_TOKENS / ALPHA_SPEND_SOFT_RATIO. Returns None when
    neither hard ceiling is set (→ unlimited, byte-identical to an unmetered run)."""
    usd = usd if usd is not None else _env_float("ALPHA_SPEND_BUDGET_USD")
    tokens = tokens if tokens is not None else _env_int("ALPHA_SPEND_BUDGET_TOKENS")
    soft = soft_ratio if soft_ratio is not None else _env_float("ALPHA_SPEND_SOFT_RATIO")
    if usd is None and tokens is None:
        return None
    kw: dict = {}
    if soft is not None:
        kw["soft_ratio"] = soft
    return Budget(usd=usd, tokens=tokens, **kw)


def add_budget_args(parser) -> None:
    """Add the shared A6 spend-ceiling CLI flags to an argparse parser (the user's ceiling declaration;
    each also falls back to its ALPHA_SPEND_* env var via budget_from_env)."""
    g = parser.add_argument_group("spend metering (A6)")
    g.add_argument("--budget-usd", type=float, default=None, metavar="USD",
                   help="hard money ceiling for this run; a breach HALTS loudly (env ALPHA_SPEND_BUDGET_USD)")
    g.add_argument("--budget-tokens", type=int, default=None, metavar="N",
                   help="hard token ceiling for this run (env ALPHA_SPEND_BUDGET_TOKENS)")
    g.add_argument("--soft-ratio", type=float, default=None, metavar="R",
                   help="warn once when spend crosses R×ceiling (0<R<=1, default 0.8; env ALPHA_SPEND_SOFT_RATIO)")


def format_summary(summary: dict) -> str:
    """Render SpendMeter.summary() as a readable block for a run's stdout."""
    lines = [
        f"SPEND  total=${summary['total_usd']:.4f}  tokens={summary['total_tokens']}  "
        f"calls={summary['n_calls']} (estimated={summary['estimated_calls']})"
    ]
    b = summary.get("budget")
    if b is not None:
        lines.append(f"  budget: usd={b['usd']} tokens={b['tokens']} soft_ratio={b['soft_ratio']} "
                     f"soft_warned={summary['soft_warned']}")
    for role, s in sorted(summary.get("by_role", {}).items()):
        lines.append(f"  role {role:<9} n={s['n']:<4} tokens={s['tokens']:<8} cost=${s['cost_usd']:.4f}")
    for model, s in sorted(summary.get("by_model", {}).items()):
        lines.append(f"  model {model:<16} n={s['n']:<4} tokens={s['tokens']:<8} cost=${s['cost_usd']:.4f}")
    return "\n".join(lines)
