# A6 — Spend metering (design)

> Arc: DEVELOPMENT-PLAN §2 A6 · closes Backend-Design G5 · charter: *Resources as Security: Cost Is
> Also the Adversary's Weapon* (added 2026-07-06, resolves review §4.3). Drafted 2026-07-13.

## Why (charter)

Cost enters the charter as a virtue — "the only objectively measurable scalar" on every packet — but
**"a *reported* scalar is not a *governed* one"**: nothing thresholds it, and the watchdog watches
*failure*, not *spend*. Both §4.3 adversaries are **live today** on the single-user machine: a
prompt-injected activity session and a buggy/looping Body can each burn a four-digit bill with every
call succeeding and **no failure signature firing** (economic denial-of-service). This arc adds the
money dimension the compute quotas never had — a new *watched signal under the authority that already
exists*, not a second authority.

The charter's spine (Resources as Security → Decisions):
- The watched signal is **the kernel's own metering of every model call it dispatches** (token count
  × price), so a **pure-inference loop with no tool calls is still metered** — exactly the all-success
  runaway that fires no failure signature.
- Money is denominated by a **versioned price list** (per-model-id rates), a governed data row whose
  real home is the third-party lockfile. Honest limit: no external price feed → a silent vendor
  repricing is caught only at pin-reconcile.
- Enforcement is **keyed to scope**: an unattended batch that breaches its ceiling is **halted** (the
  bounded detect-and-kill); a foreground interactive session would pause-and-prompt; the cross-session
  daily accumulator halts admission. This arc implements the **run-batch (unattended) scope → halt**,
  which is the correct action for the metered producers (refine_live / verdict / decisions batches).
- Accepted risks carried verbatim: (1) the attack's own bill **up to the cap is still paid**; (2)
  **granularity is one call** — the signal is checked *between* calls, so a single call larger than the
  remaining budget overshoots by that much (sub-call metering not built); (3) a wrong/stale price list
  makes the ceiling wrong.

A6's own acceptance gate (DEVELOPMENT-PLAN): every LLM call carries a cost record; a budget breach
halts the run loudly; per-refinement/per-run cost appears on the run output (feeds A8).

## Scope of this arc

Footprint-isolated to the LLM seam + the run entry points:
- `alpha/llm/metering.py` (NEW) — the meter, the cost model + price table, the Budget, the watchdog.
- `alpha/llm/config.py::make_client` — an additive `meter=` kwarg (the metering seam).
- `alpha/llm/openai_compat.py` / `alpha/llm/anthropic.py` — additive `last_usage` capture (real
  provider token counts when the API returns them; absent → the wrapper estimates).
- `scripts/refine_live.py` / `scripts/run_verdict.py` / `scripts/save_decisions.py` — thread an
  optional `meter=`, surface the run's spend on output, exit non-zero on breach.

**Deliberately NOT in this arc** (reported, not done): putting per-refinement cost **on the
`EvolutionProposal` packet object** requires editing TCB `alpha/meta/evolution.py` — out of footprint
and out of the immutable-TCB carve-out. A6 surfaces run cost on the **run summary** (printed + on
`run_refine_live`'s returned dict); the packet-object field is A8's natural home (packet counsel). The
richer charter ladder — foreground **pause-and-prompt**, the cross-session **daily accumulator**, the
egress-call meter, per-party rate limiting — is out of this run-batch scope (noted below).

## The meter seam

One wrapping primitive, `MeteredClient`, wraps any `LLMClient`/`ChatLLMClient` (structural — reads
`.complete`/`.chat`, delegates everything else via `__getattr__`). On each call it:
1. delegates to the inner client (the call happens; its cost is already incurred);
2. reads the inner client's `last_usage` side-channel (real provider tokens) if present, else
   **estimates** tokens from text length (`ceil(len/4)`, floor 1) and marks the record `estimated`;
3. prices it against the price table keyed by the inner client's `.model` (unknown model →
   `DEFAULT_PRICE`, non-zero — **fail-toward-metering**, never silently free);
4. appends a `CostRecord` to the `SpendMeter` and lets the meter **enforce** (may raise).

Two ways to attach it, both using the same primitive:
- **`make_client(role, *, meter=None)`** — `meter=None` returns the raw client **unchanged**
  (byte-identical seam; existing `isinstance(make_client(role), MockLLMClient)` holds); `meter` set
  returns `meter.wrap(raw, role=role)`.
- **Run entry points** wrap the factory *output* (`meter.wrap(factory(), role=...)`), so even a
  test-injected `MockLLMClient` factory is metered when a meter is threaded.

`MockLLMClient` has no `.model` and no `last_usage` → model `"mock"`, estimated tokens — deterministic,
offline. This is what makes the offline test suite able to prove metering with no keys.

## The cost model + price table

```
Usage(tokens_in, tokens_out)           # normalized provider usage (side-channel on real clients)
ModelPrice(in_per_1m, out_per_1m)      # USD per 1M tokens
PRICES: dict[model_id -> ModelPrice]   # APPROXIMATE 2026-07 public rates, updatable in place
DEFAULT_PRICE                          # unknown model -> non-zero fallback
price_of(model, tin, tout, prices) = tin/1e6*in_per_1m + tout/1e6*out_per_1m
estimate_tokens(text) = max(1, ceil(len(text)/4))
```

The table is **approximate and updatable**, documented as such in the module. Per the charter its real
home is the versioned vendor price list folded into the third-party lockfile (a governed, agent-
unwritable data row); until that lockfile lands, the in-module table is the interim pin. Silent vendor
repricing is the charter's accepted risk (3). Cost computation takes an overridable `prices=` so tests
assert exact cost against a fixed table, decoupled from the (updatable) real rates.

## The budget object

```
Budget(usd: float|None = None, tokens: int|None = None, soft_ratio: float = 0.8)
```
At least one hard ceiling (usd or tokens) required. `soft_ratio` in (0,1] sets the warn line. Money is
the charter's primary unit; a token ceiling is offered for when the price table isn't trusted. A breach
of **either** hard ceiling halts. Budget values are the **user's declaration** (charter: user-direct
records) — supplied by CLI (`--budget-usd`/`--budget-tokens`/`--soft-ratio`) or env
(`ALPHA_SPEND_BUDGET_USD` / `ALPHA_SPEND_BUDGET_TOKENS` / `ALPHA_SPEND_SOFT_RATIO`); CLI overrides env;
`budget_from_env(...)` returns `Budget | None` (None when neither ceiling set).

## The watchdog ladder (governed, not reported)

`SpendMeter.record(rec)` appends, accumulates totals, then — only if a budget is attached:
- **hard ceiling breached** (total_usd > usd, or total_tokens > tokens) → **raise `BudgetExceeded`**, a
  self-describing exception (dimension, spent, limit, n_calls, the tripping record). This propagates
  through the run function, aborting the loop; the script's `main()` prints it loudly to stderr and
  **exits non-zero** (`sys.exit(1)`). *A breach stops the loop, it does not just log* — this is the
  governed-not-reported core.
- else **soft threshold crossed** (total ≥ soft_ratio × ceiling) → **warn once** via an injectable
  `on_warn` (default `logging.warning`); the run continues.

Hard is checked before soft, so an over-hard call raises rather than warns. Enforcement is **between
calls** (the just-completed call is already paid — charter accepted risk 1 & 2). No budget attached →
records only, never raises (unlimited).

## What's enforced vs advisory

| Signal | Behavior |
|---|---|
| No budget attached | Advisory — every call recorded, nothing enforced, unlimited (byte-identical to today) |
| Soft threshold (soft_ratio × ceiling) | Advisory — warn once, run continues |
| Hard ceiling (usd or tokens) | **Enforced** — `BudgetExceeded` raised, run aborts, non-zero exit |

## Surfacing (feeds A8)

`SpendMeter.summary()` → a dict: `total_usd`, `total_tokens`, `n_calls`, `estimated_calls`, per-role
and per-model breakdown, the budget, `soft_warned`. `format_summary(summary)` renders it. Each metered
`main()` prints it at the end (and on breach, the partial summary). `run_refine_live` additionally
carries `spend=meter.summary()` on its returned dict **when a meter is threaded** (the packet-producing
run — closest to the charter's per-refinement scalar; the None path's dict is unchanged). Putting the
scalar on the `EvolutionProposal` object itself is A8 (TCB seam, reported).

## Byte-identity when unset (the additive proof)

- `make_client(role)` with no `meter` returns the identical raw client (unchanged `isinstance`).
- Run functions with `meter=None` leave the factories untouched → no wrapping → identical decisions,
  proposals, verdicts, and return shapes. Existing script tests (which inject their own factories and
  pass no meter) are unchanged.
- The real clients' `last_usage` is a new attribute set to `None`/`Usage`; return values are byte-
  identical, so `test_openai_compat.py` / `test_anthropic.py` stay green.

## TCB accounting

`tcb.lock` TCB_FILES: `alpha/agent/retrieval.py`, `alpha/arena/policy.py`, `alpha/data/firewall.py`,
`alpha/harness/{doctrine,edit_log,manager,metatools,snapshot}.py`, `alpha/loop/floor_breaker.py`,
`alpha/memory/store.py`, `alpha/meta/{evolution,proposal_store}.py`,
`alpha/refine/{apply,conflict,ops}.py`. **None touched.** The whole footprint (`alpha/llm/*`,
`alpha/llm/metering.py` NEW, the three scripts) is outside the TCB. The one place A6 would want a TCB
seam — the per-refinement scalar on `EvolutionProposal` — is deliberately deferred to A8 rather than
touched here.

## Test plan (TDD)

`tests/llm/test_metering.py` (unit):
- (a) every LLM call produces a cost record — `MeteredClient` over a `MockLLMClient` records role /
  model / tokens / estimated=True; a stub client exposing `last_usage` records estimated=False with the
  provider counts; unknown model prices at `DEFAULT_PRICE` (non-zero).
- (b) a hard breach raises `BudgetExceeded` loudly (message names spent/limit/last call); the run stops
  at the breaching call (subsequent calls don't run).
- (c) a soft crossing warns once (injected `on_warn` list) without raising; hard beats soft.
- (d) no-budget meter records but never raises (unlimited); `make_client(role)` with no meter is the
  raw client (byte-identity seam); `make_client(role, meter=m)` wraps.
- price_of / estimate_tokens determinism; token-dimension budget; `budget_from_env` CLI-over-env.

`tests/llm/test_openai_compat.py` / `test_anthropic.py` (additive): `last_usage` populated from a fake
`resp.usage`; absent usage → `last_usage is None`; returned text unchanged.

`tests/scripts/test_*_metering.py` (wiring), for at least refine_live + save_decisions + run_verdict:
- meter threaded → records accumulate and reach `meter.summary()`;
- a tight budget → `BudgetExceeded` propagates out of the run function;
- `meter=None` → byte-identical (existing behavior; a spot re-assert).

All offline, keyless (`MockLLMClient` / mocked provider), no new deps.
