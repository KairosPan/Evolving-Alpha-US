# P3 — Corp-actions tri-state guard-blind fix (design)

Status: drafted 2026-07-13. Source: DEVELOPMENT-PLAN.md §1 P3; kairos-mining §2.2 (CONFIRMED) + §4.2.
Charter posture: warn-the-human co-pilot — surface the data gap, never add a veto.

## The verified hole

When a captured window has **no `corp_actions.parquet`**, the read path collapses "artifact absent"
into "checked, nothing announced":

```
PITStore.get_corp_actions()            -> None            (file absent)   ── the ONLY place absence is known
SnapshotSource.corporate_actions_known -> known_corporate_actions(None, as_of) -> EMPTY frame
screen_decision: corp = guarded.corporate_actions_known(as_of)  -> EMPTY frame
has_reverse_split_pending(corp, ...)   -> known.empty -> False
has_dilution_filing(corp, ...)         -> known.empty -> False
```

An **empty** `corp_actions.parquet` (checked, nothing announced — a legitimate clean state) yields the
*same* empty frame and the *same* `False`. The two are byte-indistinguishable, so on a missing artifact
the reverse-split / dilution guard silently runs blind. This is real on the snapshot-store path
(hand-built captures, or any window whose capture pre-dated corp-action persistence); the live Alpaca
path already fails loud (network fetch raises; a successful fetch with zero actions is a true empty).

Post-pivot this matters more: dilution-after-runup is a core growth-universe hazard (the manuscript's
减持就跑 analog), and P9's unattended daily loop cannot be trusted while the blindness is silent.

## Flag inventory — corp-data-dependent vs tape-derived

`screen_decision` builds one `CandidateContext` per enter candidate. Classifying every flag by its data
source (only the corp-data-dependent ones are in scope for this fix):

| Flag | Source expression | Class | In scope? |
|---|---|---|---|
| `reverse_split_pending` | `has_reverse_split_pending(corp, …)` over `corporate_actions_known` | **corp-data-dependent** | **YES** |
| `dilution` | `has_dilution_filing(corp, …)` over `corporate_actions_known` | **corp-data-dependent** | **YES** |
| `ssr` | `ssr_active(guarded, …)` → prior-day close-to-close over `daily_bars` | tape-derived | no |
| `halt_then_dump` | `halt_then_dump_proxy(rows.get(sym))` over `daily_snapshot` OHLC | tape-derived | no |
| `episode_taboo` | `is_episode_taboo(...)` over `episode_store` | episode-derived | no |
| `panic_state` | `detect_panic_state(history, state)` | history-derived | no |
| `going_concern`, `regulatory` | hardcoded `False` (no feed yet) | no data source | no |

Notes on the not-in-scope tape flags (kairos-mining §2.2 named "ssr_active/halt_then_dump mapping
missing rows → False" as the sibling silent seam, but they are **not** corp-artifact-dependent):
- `halt_then_dump`: `screen_decision` calls `guarded.daily_snapshot(as_of)` unconditionally, and
  `SnapshotSource.daily_snapshot` **raises `SnapshotMissingError`** on an absent day — so a missing
  snapshot fails loud (never silently blind). A per-name absent row (`rows.get(sym) is None`) is a
  legitimate "no OHLC for this name" and correctly yields `False`.
- `ssr`: missing bars → `_prior_day_pct` returns `None` → `False`. That is a *bars*-missing blindness,
  a separate seam from the corp-actions artifact, and out of this task's scope (recorded below).

So the fix is scoped precisely to the corp-actions artifact feeding `reverse_split_pending` + `dilution`.

## The seam

Add a **boolean availability probe** at the source contract:

```python
def corp_actions_available(self) -> bool: ...   # True = frame present (checkable); False = artifact MISSING
```

The three semantic states (AVAILABLE with rows / PRESENT-BUT-EMPTY / MISSING) already exist at the
store level as `get_corp_actions()`'s three returns (non-empty frame / empty frame / `None`). The
load-bearing partition for the guard is 2-way — *checkable* (AVAILABLE + PRESENT-BUT-EMPTY, both
legitimate "we looked") vs *not checkable* (MISSING) — so a boolean exposes exactly the distinction the
consumer needs without overloading pandas emptiness. Date-independent (the parquet is the whole PIT
snapshot captured at window end), so no `as_of` argument and no `AsOfGuard.check`.

Implementations:
- **`PITStore.has_corp_actions() -> bool`** — `self._snap_path`-style existence check on
  `corp_actions.parquet` (mirrors the existing `has_snapshot`).
- **`SnapshotSource.corp_actions_available()`** — `return self._store.has_corp_actions()`.
- **`FakeSource`** — new constructor kwarg `corp_actions_available: bool = True` (in-memory sources are
  always checkable; the flag lets tests simulate MISSING); method returns it.
- **`AlpacaSource.corp_actions_available()`** — `return True` (fetch-or-raise; never silently blind).
- **`GuardedSource.corp_actions_available()`** — passthrough via
  `getattr(self._inner, "corp_actions_available", None)`, returning `True` when the inner predates the
  capability. This keeps any minimal stub source byte-identical (same graceful-degradation posture as
  `GuardedPolicy`'s optional `collect` forwarding).
- **`MarketDataSource` Protocol** — declare the method (documents the contract; the getattr tolerance in
  `GuardedSource` covers structural doubles that don't carry it).

## Consumer change — `screen_decision`

Compute availability **once per package** from the same `guarded` source both verdict arms share (so the
availability view is symmetric by construction — the screen-flag pattern), then after the veto loop
append a single self-describing note to `key_risks` only when the artifact is MISSING *and* the blind
guard was actually consulted for an entry (≥1 `enter` candidate):

```python
corp_available = guarded.corp_actions_available()
...
if not corp_available and any(candidate_action(c) == "enter" for c in decision.candidates):
    notes.append(CORP_BLIND_NOTE)   # module constant, once per package
```

`CORP_BLIND_NOTE = "corp-actions guard ran blind: artifact missing — reverse-split-pending / dilution "`
`"checks did not run (an unflagged split or dilution overhang may have passed)"`.

Why gate on an `enter` candidate: a `trim`/`exit` is a derisk on a held name (P0.6) that the new-entry
corp veto never touches, and a no-candidate package made no entry to distrust — so the blindness is only
material when it could have cleared a new entry. This keeps the note honest and low-noise.

## Invariants (acceptance gate)

- **Additive / default-preserving.** Every in-repo source constructed with a present corp frame (all
  `FakeSource` defaults `corp_actions_available=True`; every captured `SnapshotSource` with a written
  parquet — including an empty one) reports available → **no note** → byte-identical to today. Pinned by
  a regression asserting a present-but-empty corp yields the exact key_risks of the pre-fix path.
- **Distinguishes MISSING from PRESENT-BUT-EMPTY** (both directions) — the core gate: missing artifact →
  note present; present-but-empty artifact → note absent, veto results unchanged.
- **Verdict symmetry + neutrality.** Availability is source-derived and `compare_harnesses` passes one
  `source` to every arm's `GuardedPolicy`, so both arms see the same availability view. The note lives
  in `key_risks`, which eval/verdict scoring never reads → verdict-neutral (pinned: a missing-corp
  source keeps `hch_minus_hexpert_mean_excess ≈ 0`).
- **Persistence + console.** The note round-trips through `DecisionStore` (it is a plain `key_risks`
  string) and renders in `alpha_web/templates/decisions.html`'s `{% for r in pkg.key_risks %}` list
  without error.

## TCB accounting

**No TCB file is touched.** Files changed — `alpha/data/pit_store.py`, `alpha/data/snapshot_source.py`,
`alpha/data/source.py`, `alpha/data/alpaca.py`, `alpha/guard/screen.py` — are **none** of the 15
`TCB_FILES` in `scripts/gen_tcb_lock.py`. The TCB member on the data path, `alpha/data/firewall.py`
(`AsOfGuard`/`GuardedSource`-the-firewall), is **untouched**; the availability probe is date-independent
and adds no firewall surface. `tcb.lock` needs no regeneration; `gen_tcb_lock.py --check` stays 0.

## Deliberately not done

- **Bars-missing blindness in `ssr` / per-name snapshot gaps** — a distinct seam (tape data, not the
  corp artifact); left as-is. A `daily_bars`/snapshot tri-state would be a separate task.
- **Live EDGAR dilution lifecycle** (withdrawal/expiry) — P5; the veto-forever default is unchanged.
- **Turning availability into a veto** — out of charter posture; this is warn-the-human only.
