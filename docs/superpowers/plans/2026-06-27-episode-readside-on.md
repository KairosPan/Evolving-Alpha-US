# Episode Read-Side ON (§6 recall + taboo into the live/verdict decide path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip the §6 read-side ON — wire the live `EpisodeStore` into the production decide path (act-only + evolving) and the verdict harness's **symmetric** arms, turning the already-built recall + episode-taboo capabilities (today default-off via `episode_store=None`) into live behavior.

**Architecture:** Three additive moves. (1) Uncap `EpisodeStore.for_asof(limit=None)` and use it at the two aggregation read sites (taboo, recall) so they see full PIT-masked history. (2) **Decouple read from write** in `InnerLoop`: a new read-only `recall_store` (feeds the policy stack's recall + taboo) distinct from `episode_store` (the `apply_credit` write handle) — so the verdict can give both arms the SAME fixed pool while the HCH arm does NOT self-write mid-verdict (symmetric, like the `screen` flag). (3) Thread the store through the three live entry points (`save_decisions`, `refine_live`, `run_verdict`) — defaulting to inert (`None` / no brain → byte-identical) and turning ON only when a brain is present.

**Tech Stack:** Python 3, pydantic v2, sqlite3 (EpisodeStore), pytest. No new dependencies.

## Global Constraints

- **Additive / default-off invariant:** every new parameter defaults to `None`. With no store wired, every touched path is **byte-identical** to today and all 680 existing tests stay green. Verify with the full suite at the end of each task.
- **PIT-safety (non-negotiable):** all episode reads go through `EpisodeStore.for_asof(asof, …)`, which masks `learned_asof <= asof` and `superseded = 0`. Recall uses `asof = state.as_of`; taboo uses `as_of = state.date`. No episode whose outcome became knowable after the decision date may surface. Every read-path test must include a future-`learned_asof` exclusion assertion or rely on a fixture that already enforces it.
- **Verdict symmetry:** in `compare_harnesses`, `recall_store` is **read-only** for both arms. The HCH arm's `InnerLoop` receives it as `recall_store=` (read), NEVER as `episode_store=` (write). A verdict run must not mutate the supplied store.
- **Style:** match the surrounding dense-comment idiom (one-line rationale on the load-bearing line). Keep diffs minimal — these are wiring changes, not refactors.
- **Scope exclusion:** the conversational face (`alpha/converse/tools.py`) is OUT of scope (different phase boundary; no guard/sizing wrapping yet; phase-1B plan defers recall).
- **Commands:** run tests with `python -m pytest`. Do NOT push (push needs explicit user authorization per project rule).

---

### Task 1: `EpisodeStore.for_asof(limit=None)` — uncapped full-history read

The default `limit=50` is a GLOBAL cap (latest-50 by `exit_date` across ALL symbols). The aggregation callers (taboo, recall) need full PIT-masked history; the forge already passes an explicit large limit. Add a clean `limit=None` → no-cap mode (keeps `50` as the ad-hoc-caller safety default).

**Files:**
- Modify: `alpha/memory/store.py:66-77` (`EpisodeStore.for_asof`)
- Test: `tests/memory/test_episode_store_query.py`

**Interfaces:**
- Produces: `EpisodeStore.for_asof(asof, *, phase=None, narrative=None, limit: int | None = 50) -> list[Episode]` — `limit=None` returns the full PIT-masked, non-superseded history (newest `exit_date` first).

- [ ] **Step 1: Write the failing test** (append to `tests/memory/test_episode_store_query.py`)

```python
def test_for_asof_limit_none_returns_full_history():
    """limit=None bypasses the default-50 cap; default still caps at 50 (the recurring-cap fix)."""
    from datetime import date
    from alpha.memory.store import EpisodeStore
    from alpha.memory.episodes import Episode
    store = EpisodeStore(__import__("sqlite3").connect(":memory:"))
    for i in range(60):  # 60 PIT-visible episodes, exit_date ascending
        store.add(Episode(episode_id=f"e{i}", symbol="AAA", skill_id="s1",
                          entry_date=date(2026, 1, 1), exit_date=date(2026, 2, 1) + __import__("datetime").timedelta(days=i),
                          outcome="faded", learned_asof=date(2026, 2, 1) + __import__("datetime").timedelta(days=i)))
    asof = date(2026, 6, 1)
    assert len(store.for_asof(asof)) == 50            # default cap unchanged
    assert len(store.for_asof(asof, limit=None)) == 60  # full history
```

> NOTE to implementer: confirm the real write method name on `EpisodeStore` (likely `add`/`put`/`record`) by reading `alpha/memory/store.py`; use the actual one. Confirm `Episode`'s required fields from `alpha/memory/episodes.py` and adjust the constructor kwargs to match (the fixture only needs `outcome`/`learned_asof`/`exit_date` to be meaningful).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/memory/test_episode_store_query.py::test_for_asof_limit_none_returns_full_history -v`
Expected: FAIL (today `limit` is `int`, `for_asof(asof, limit=None)` would append `None` as a SQL param / behave wrong).

- [ ] **Step 3: Implement** — replace the body of `for_asof` in `alpha/memory/store.py`:

```python
def for_asof(self, asof: Date, *, phase: str | None = None, narrative: str | None = None,
             limit: int | None = 50) -> list[Episode]:
    """PIT-safe recall: non-superseded episodes knowable by `asof` (learned_asof <= asof), newest first.
    `limit=None` -> the FULL PIT-masked history (no cap) — the aggregation callers (taboo/recall) need it;
    the default 50 stays the safety cap for ad-hoc callers."""
    clauses = ["superseded = 0", "learned_asof <= ?"]
    params: list = [asof.isoformat()]
    if phase is not None:
        clauses.append("phase = ?"); params.append(phase)
    if narrative is not None:
        clauses.append("narrative = ?"); params.append(narrative)
    where = " AND ".join(clauses)
    if limit is None:
        sql = f"SELECT * FROM episodes WHERE {where} ORDER BY exit_date DESC"
    else:
        params.append(limit)
        sql = f"SELECT * FROM episodes WHERE {where} ORDER BY exit_date DESC LIMIT ?"
    return [_row_to_episode(r) for r in self._conn.execute(sql, params)]
```

- [ ] **Step 4: Run tests to verify green** — `python -m pytest tests/memory/ -v`  → PASS
- [ ] **Step 5: Commit** — `git add alpha/memory/store.py tests/memory/test_episode_store_query.py && git commit -m "feat(memory): for_asof(limit=None) -> full PIT-masked history (uncap the aggregation read sites)"`

---

### Task 2: Taboo aggregation reads full history (`screen.py`)

Today `screen_decision` aggregates `for_asof(as_of)` (default-50). With other symbols' recent episodes filling the top-50, a target symbol's nuke history can fall outside it → per-symbol `n < min_samples=3` → taboo never fires. Use `limit=None`.

**Files:**
- Modify: `alpha/guard/screen.py:89` (the `taboo_stats` line)
- Test: `tests/guard/test_screen_episode_taboo.py`

**Interfaces:**
- Consumes: `EpisodeStore.for_asof(asof, limit=None)` (Task 1).

- [ ] **Step 1: Write the failing test** (append to `tests/guard/test_screen_episode_taboo.py`) — prove the cap was hiding the taboo:

```python
def test_taboo_sees_full_history_past_the_50_cap():
    """A symbol nuked 3x is taboo even when 50 more-recent OTHER-symbol episodes would crowd it out of
    the default-50 window (the for_asof cap fix)."""
    from datetime import date, timedelta
    import sqlite3
    from alpha.memory.store import EpisodeStore
    from alpha.memory.episodes import Episode
    store = EpisodeStore(sqlite3.connect(":memory:"))
    # 3 OLDER nuked episodes for RUN
    for i in range(3):
        store.add(Episode(episode_id=f"run{i}", symbol="RUN", skill_id="s",
                          entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2) + timedelta(days=i),
                          outcome="nuked", learned_asof=date(2026, 1, 2) + timedelta(days=i)))
    # 50 MORE-RECENT episodes for other symbols (would fill the default-50 window)
    for i in range(50):
        store.add(Episode(episode_id=f"oth{i}", symbol=f"X{i}", skill_id="s",
                          entry_date=date(2026, 1, 1), exit_date=date(2026, 3, 1) + timedelta(days=i),
                          outcome="continued", learned_asof=date(2026, 3, 1) + timedelta(days=i)))
    # Build a decision whose candidate is RUN at a frontside/risk-on regime; assert RUN is dropped (taboo).
    # Reuse this test module's existing helpers (a frontside MarketState + a single-RUN-candidate
    # DecisionPackage + a FakeSource). Mirror the existing test_episode_taboo_drops_the_candidate setup.
    out = _screen_run_candidate(store, asof=date(2026, 6, 1))   # helper analogous to the existing taboo test
    assert "RUN" not in [c.symbol for c in out.candidates]
    assert any("episode taboo" in r for r in out.key_risks)
```

> NOTE: read `tests/guard/test_screen_episode_taboo.py` first and REUSE its existing fixtures/helpers (it already builds a frontside regime + a RUN candidate + calls `screen_decision`). The new test differs only by adding the 50 crowding episodes. If no reusable helper exists, inline the same setup the existing `test_episode_taboo_drops_the_candidate` uses.

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/guard/test_screen_episode_taboo.py::test_taboo_sees_full_history_past_the_50_cap -v` → FAIL (RUN survives: its 3 nukes are outside the default-50 window).
- [ ] **Step 3: Implement** — in `alpha/guard/screen.py:89` change:

```python
    taboo_stats = (summarize(episode_store.for_asof(as_of, limit=None), key=lambda e: e.symbol)
                   if episode_store is not None else {})
```

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/guard/ -v` → PASS
- [ ] **Step 5: Commit** — `git add alpha/guard/screen.py tests/guard/test_screen_episode_taboo.py && git commit -m "fix(guard): taboo aggregates full PIT history (for_asof limit=None, past the 50 cap)"`

---

### Task 3: Recall pool reads full history (`retrieval.py`)

`select_episodes_for_prompt` pulls `for_asof(asof)` (default-50) then ranks (phase-match, recency, |adv|) and takes top-`budget`. An older but phase-matching high-|adv| episode can be excluded by the 50-cap. Use `limit=None` so ranking sees the full pool.

**Files:**
- Modify: `alpha/agent/retrieval.py:71` (the `pool =` line)
- Test: `tests/agent/test_select_episodes.py`

**Interfaces:**
- Consumes: `EpisodeStore.for_asof(asof, limit=None)` (Task 1).

- [ ] **Step 1: Write the failing test** (append to `tests/agent/test_select_episodes.py`):

```python
def test_recall_pool_sees_full_history_past_the_50_cap():
    """An older phase-matching high-|advantage| episode is recalled (ranked first) even behind 50
    more-recent off-phase episodes that would crowd the default-50 window."""
    from datetime import date, timedelta
    import sqlite3
    from alpha.memory.store import EpisodeStore
    from alpha.memory.episodes import Episode
    from alpha.agent.retrieval import select_episodes_for_prompt
    store = EpisodeStore(sqlite3.connect(":memory:"))
    store.add(Episode(episode_id="gold", symbol="AAA", skill_id="s", phase="trend",
                      entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2),
                      outcome="continued", advantage=9.0, learned_asof=date(2026, 1, 2)))
    for i in range(50):  # off-phase, more recent
        store.add(Episode(episode_id=f"n{i}", symbol="BBB", skill_id="s", phase="chop",
                          entry_date=date(2026, 1, 1), exit_date=date(2026, 3, 1) + timedelta(days=i),
                          outcome="faded", advantage=0.1, learned_asof=date(2026, 3, 1) + timedelta(days=i)))
    got = select_episodes_for_prompt(store, phase_prior="trend", asof=date(2026, 6, 1), budget=8)
    assert any(e.episode_id == "gold" for e in got)   # behind the 50-cap, but full pool sees it
```

> NOTE: confirm the canonical phase token the regime uses (`phase_from_read("trend") == "trend"` per the recall design) so the phase-match boost applies; adjust `phase=`/`phase_prior=` to a real canonical token if "trend" is not one.

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/agent/test_select_episodes.py::test_recall_pool_sees_full_history_past_the_50_cap -v` → FAIL ("gold" outside the default-50 pool).
- [ ] **Step 3: Implement** — in `alpha/agent/retrieval.py:71` change `pool = episode_store.for_asof(asof)` to:

```python
    pool = episode_store.for_asof(asof, limit=None)             # full PIT-masked pool; rank then top-budget
```

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/agent/ -v` → PASS
- [ ] **Step 5: Commit** — `git add alpha/agent/retrieval.py tests/agent/test_select_episodes.py && git commit -m "fix(agent): recall ranks the full PIT pool (for_asof limit=None)"`

---

### Task 4: Decouple read (`recall_store`) from write (`episode_store`) in `InnerLoop`

`InnerLoop._episode_store` is the `apply_credit` WRITE handle (line 181). Add a separate read-only `recall_store` that `_rebind` threads into the policy stack (recall via `LLMAgentPolicy`, taboo via `GuardedPolicy`). This lets the verdict supply a fixed read pool to both arms WITHOUT the HCH arm self-writing during the run.

**Files:**
- Modify: `alpha/loop/inner_loop.py` (`InnerLoop.__init__` ~89-108, `_rebind` 110-119)
- Test: `tests/loop/test_inner_loop.py` (or the existing inner-loop test module — read the dir first)

**Interfaces:**
- Consumes: `LLMAgentPolicy(h, llm, episode_store=…)`, `GuardedPolicy(inner, source, episode_store=…)` (already built).
- Produces: `InnerLoop(…, episode_store=None, conflict_queue=None, recall_store=None)` — `recall_store` is read-only (recall + taboo); `episode_store` remains the `apply_credit` write handle. The two are independent.

- [ ] **Step 1: Write the failing tests** (append to the inner-loop test module). Two assertions: read works, and read≠write (decoupled).

```python
def test_recall_store_is_read_only_and_drives_taboo(monkeypatch):
    """recall_store feeds taboo (a seeded nuke history drops the candidate) and is NEVER written to."""
    # Build a tiny offline source + MockLLM that always picks 'RUN', seed recall_store so RUN is taboo.
    # Reuse the inner-loop test harness's existing builders (FakeSource/MockLLM/seed harness).
    store_R = _seed_taboo_store("RUN")            # 3 PIT-old nuked RUN episodes (helper; see Task 2 fixture)
    n_before = _count_episodes(store_R)
    loop = _make_inner_loop(agent_picks=["RUN"], recall_store=store_R, episode_store=None)
    report = loop.run()
    assert _count_episodes(store_R) == n_before    # read-only: the run did not write to recall_store
    # RUN was vetoed -> never entered -> absent from scored entries
    assert all("RUN" not in step.entries for step in report.trajectory.scored_steps())


def test_episode_store_is_write_only_independent_of_recall(monkeypatch):
    """episode_store still records episodes at apply_credit; recall_store=None means no recall block."""
    store_W = _empty_store()
    loop = _make_inner_loop(agent_picks=["AAA"], recall_store=None, episode_store=store_W)
    loop.run()
    assert _count_episodes(store_W) > 0            # write path intact, independent of recall_store
```

> NOTE: the helpers (`_seed_taboo_store`, `_count_episodes`, `_make_inner_loop`, `_empty_store`) should be thin wrappers over the inner-loop test module's EXISTING fixtures. Read `tests/loop/` to find them. `_count_episodes(store)` = `len(store.for_asof(date(2099,1,1), limit=None))`. If the existing tests already construct an `InnerLoop` with a MockLLM + FakeSource, copy that construction and add the `recall_store`/`episode_store` kwargs.

- [ ] **Step 2: Run to verify they fail** — `python -m pytest tests/loop/ -k "recall_store or write_only" -v` → FAIL (`InnerLoop` has no `recall_store` kwarg).
- [ ] **Step 3: Implement** — in `alpha/loop/inner_loop.py`:

(a) add the kwarg to `__init__` (after `conflict_queue=None`):
```python
                 episode_store=None, conflict_queue=None, recall_store=None) -> None:
```
and store it (next to `self._episode_store = episode_store`):
```python
        self._recall_store = recall_store     # READ-only: recall + taboo into the policy stack (NOT the
        #   apply_credit WRITE handle above) — lets the verdict feed both arms a fixed pool, no self-write
```

(b) thread it in `_rebind` (lines 114-117):
```python
    def _rebind(self) -> None:
        """(Re)build agent + refiner from the CURRENT mgr.harness/mgr.tools. Call at startup and after
        EVERY rollback (rollback_to rebinds mgr.harness/mgr.tools to the restored objects)."""
        h = self._mgr.harness
        base = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm, episode_store=self._recall_store)
        policy = GuardedPolicy(base, self._source, episode_store=self._recall_store) if self._cfg.screen else base
        self._agent = SizingPolicy(policy) if self._cfg.size else policy   # size OUTSIDE guard (post-veto)
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg,
                                conflict_queue=self._conflict_queue)
```
(Leave `apply_credit(..., episode_store=self._episode_store)` at line 181 unchanged — the write path.)

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/loop/ -v` → PASS
- [ ] **Step 5: Commit** — `git add alpha/loop/inner_loop.py tests/loop/ && git commit -m "feat(loop): InnerLoop recall_store (read) decoupled from episode_store (write)"`

---

### Task 5: Symmetric `recall_store` across verdict arms (`compare.py`)

Thread a read-only `recall_store` into `compare_harnesses` (and `multi_window`): the Hexpert/Hmin arms via `_wrap`'s `GuardedPolicy` + the Hexpert `LLMAgentPolicy` (recall); the HCH arm via `InnerLoop(recall_store=…)` (NOT `episode_store=` — no self-write). Default `None` → byte-identical verdict.

**Files:**
- Modify: `alpha/loop/compare.py` (`compare_harnesses` 63-133: `_wrap` 86-88, Hexpert LLMAgentPolicy 91 & 103, InnerLoop 95-97; `multi_window` 152-180)
- Test: the compare test module (read `tests/loop/` for `test_compare*.py`)

**Interfaces:**
- Consumes: `InnerLoop(…, recall_store=…)` (Task 4); `GuardedPolicy(…, episode_store=…)`, `LLMAgentPolicy(…, episode_store=…)`.
- Produces: `compare_harnesses(…, recall_store=None)` and `multi_window(…, recall_store=None)` — read-only; never mutated by a verdict.

- [ ] **Step 1: Write the failing tests** (append to the compare test module):

```python
def test_verdict_recall_store_not_written_during_run():
    """A verdict reads the supplied pool but never writes to it (HCH uses recall_store, not episode_store)."""
    store = _seed_taboo_store("RUN")                       # reuse a shared helper / inline the seed
    n_before = len(store.for_asof(date(2099, 1, 1), limit=None))
    _run_compare(recall_store=store)                       # thin wrapper over compare_harnesses w/ MockLLM
    assert len(store.for_asof(date(2099, 1, 1), limit=None)) == n_before   # unchanged -> read-only


def test_verdict_recall_store_none_byte_identical():
    """recall_store=None reproduces today's headline numbers (additive default-off)."""
    a = _run_compare(recall_store=None)
    b = _run_compare()                                    # no kwarg -> same default
    assert a.hch_minus_hexpert_mean_excess == b.hch_minus_hexpert_mean_excess
```

> NOTE: build `_run_compare` from the EXISTING compare test's `compare_harnesses(...)` call (it already wires `harness_factory`, MockLLM factories, `store_factory`, `loop_config`). Add `recall_store=` as a passthrough. For the symmetric-read intent, if the existing test infra can capture per-arm decisions, add a third test asserting RUN is dropped from BOTH the HCH and Hexpert arm reports (taboo applied symmetrically); otherwise the two tests above plus Task 4's read-only proof cover the contract.

- [ ] **Step 2: Run to verify they fail** — `python -m pytest tests/loop/ -k "verdict_recall" -v` → FAIL (`compare_harnesses` has no `recall_store`).
- [ ] **Step 3: Implement** — in `alpha/loop/compare.py`:

(a) add `recall_store=None` to `compare_harnesses` signature (after `shadow: bool = False`):
```python
                      shadow: bool = False, recall_store=None) -> ComparisonReport:
```
(b) `_wrap` (86-88) — taboo for every guarded arm:
```python
    def _wrap(policy):
        p = GuardedPolicy(policy, source, episode_store=recall_store) if cfg.screen else policy
        return SizingPolicy(p) if cfg.size else p
```
(c) Hexpert recall — both constructions (line 91 shadow pre-run AND line 103 reuse path):
```python
    hexpert_traj = wf.walk(_wrap(LLMAgentPolicy(harness_factory(), agent_llm_factory(),
                                                episode_store=recall_store))) if shadow else None
```
```python
        hexpert_traj = wf.walk(_wrap(LLMAgentPolicy(harness_factory(), agent_llm_factory(),
                                                    episode_store=recall_store)))
```
(d) HCH — read-only into the loop (line 95-97), as `recall_store=` NOT `episode_store=`:
```python
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                     config=cfg, refiner_config=refiner_config, scorer=scorer_factory(),
                     shadow_daily=(daily_advantage(hexpert_traj) if shadow else None),
                     recall_store=recall_store)
```
(e) `multi_window` — add `recall_store=None` to the signature (after `shadow: bool = False`) and pass it in the `compare_harnesses(...)` call (line 166-169): add `recall_store=recall_store`.

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/loop/ -v` → PASS
- [ ] **Step 5: Commit** — `git add alpha/loop/compare.py tests/loop/ && git commit -m "feat(loop): symmetric read-only recall_store across verdict arms (compare/multi_window)"`

---

### Task 6: `run_verdict.py` threads `recall_store` + optional `--brain` (default None)

Wire the verdict CLI to optionally open a read-only brain and pass it as `recall_store`. Default (no `--brain`, no env) → `None` → today's verdict is byte-identical (preserves the rendered findings doc).

**Files:**
- Modify: `scripts/run_verdict.py` (imports; `run_verdict` 61-80; `main` 174-214)
- Test: the run_verdict test module (read `tests/` for it; likely `tests/scripts/test_run_verdict.py`)

**Interfaces:**
- Consumes: `compare_harnesses(…, recall_store=…)`, `multi_window(…, recall_store=…)` (Task 5); `EpisodeStore.open(path, create_if_missing=False)`.
- Produces: `run_verdict(…, recall_store=None)`.

- [ ] **Step 1: Write the failing test** (append to the run_verdict test module):

```python
def test_run_verdict_threads_recall_store():
    """recall_store passes through run_verdict into the comparison (read-only; not mutated)."""
    store = _seed_taboo_store("RUN")
    n_before = len(store.for_asof(date(2099, 1, 1), limit=None))
    result = _run_verdict_offline(recall_store=store)     # wrapper over run_verdict w/ MockLLM factories
    assert len(store.for_asof(date(2099, 1, 1), limit=None)) == n_before   # read-only
```

> NOTE: model `_run_verdict_offline` on the existing run_verdict test (it injects `agent_llm_factory`/`refiner_llm_factory` MockLLMs + a captured/synthetic source). Add `recall_store=` passthrough.

- [ ] **Step 2: Run to verify it fails** — FAIL (`run_verdict` has no `recall_store`).
- [ ] **Step 3: Implement** — in `scripts/run_verdict.py`:

(a) import: add `from alpha.memory.store import EpisodeStore`.
(b) `run_verdict` signature: add `recall_store=None` (after `refiner_llm_factory=None`); add to `kw`:
```python
    kw = dict(agent_llm_factory=agent_llm_factory, refiner_llm_factory=refiner_llm_factory,
              store_factory=store_factory, loop_config=cfg, shadow=shadow, recall_store=recall_store)
```
(c) `main`: add the CLI flag (next to `--no-screen`):
```python
    ap.add_argument("--brain", metavar="PATH", help="read-only EpisodeStore (brain.db) for §6 recall+taboo "
                    "into BOTH arms (symmetric); omit for the no-memory verdict")
```
and open it read-only + thread it (before the `run_verdict(...)` call at line 202):
```python
    recall_store = EpisodeStore.open(args.brain, create_if_missing=False) if args.brain else None
    print(f"  recall_store={'(brain) ' + args.brain if args.brain else '(none)'}")
    result = run_verdict(source, args.start, args.end, horizon=args.horizon,
                         windows=args.windows, shadow=args.shadow, screen=screen,
                         recall_store=recall_store)
```

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/ -k run_verdict -v` → PASS
- [ ] **Step 5: Commit** — `git add scripts/run_verdict.py tests/ && git commit -m "feat(verdict): run_verdict --brain feeds a read-only recall_store to both arms"`

---

### Task 7: `save_decisions.py` opens + threads the store (live act-only path)

The act-only producer builds `LLMAgentPolicy → GuardedPolicy → SizingPolicy` with no store. Add an `episode_store` param (recall + taboo, read-only here — no scoring/write) and an `ALPHA_EPISODES_DB`/`--brain` opener. Default absent → inert.

**Files:**
- Modify: `scripts/save_decisions.py` (imports; `produce_decisions` 42-66; `main` 78-92)
- Test: the save_decisions test module (read `tests/` for it)

**Interfaces:**
- Consumes: `LLMAgentPolicy(…, episode_store=…)`, `GuardedPolicy(…, episode_store=…)`; `EpisodeStore.open(path, create_if_missing=False)`.
- Produces: `produce_decisions(…, episode_store=None)`.

- [ ] **Step 1: Write the failing test** (append to the save_decisions test module):

```python
def test_produce_decisions_taboo_drops_candidate():
    """With a seeded brain, the act-only path drops a taboo symbol from the daily packages."""
    store = _seed_taboo_store("RUN")
    pkgs = list(_produce_offline(agent_picks=["RUN"], episode_store=store))   # MockLLM picks RUN
    assert all("RUN" not in [c.symbol for c in p.candidates] for p in pkgs)
    pkgs_off = list(_produce_offline(agent_picks=["RUN"], episode_store=None))
    assert any("RUN" in [c.symbol for c in p.candidates] for p in pkgs_off)   # off -> not dropped
```

> NOTE: build `_produce_offline` from the EXISTING save_decisions test (it already injects a MockLLM via `agent_llm_factory` + a synthetic source). Thread `episode_store=` through `produce_decisions`. Ensure the seeded RUN regime is frontside/risk-on so ONLY taboo (not the regime veto) drops it.

- [ ] **Step 2: Run to verify it fails** — FAIL (`produce_decisions` has no `episode_store`).
- [ ] **Step 3: Implement** — in `scripts/save_decisions.py`:

(a) import: add `from alpha.memory.store import EpisodeStore`.
(b) `produce_decisions` signature: add `episode_store=None` (after `size: bool = True`); thread it:
```python
    policy = LLMAgentPolicy(h, agent_llm_factory(), episode_store=episode_store)
    if screen:
        policy = GuardedPolicy(policy, source, episode_store=episode_store)   # L4 veto (+ §6 taboo)
    if size:
        policy = SizingPolicy(policy)
```
(c) `main`: add `--brain` (next to `--no-size`) and open read-only, pass via the `save_decisions(...)` kwargs:
```python
    ap.add_argument("--brain", metavar="PATH", help="read-only EpisodeStore (brain.db) for §6 recall+taboo; "
                    "defaults to $ALPHA_EPISODES_DB if set")
    ...
    brain = args.brain or os.environ.get("ALPHA_EPISODES_DB")
    episode_store = EpisodeStore.open(brain, create_if_missing=False) if brain else None
    n = save_decisions(source, args.start, args.end, store,
                       screen=not args.no_screen, size=not args.no_size, episode_store=episode_store)
```
(add `import os` if absent.)

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/ -k save_decision -v` → PASS
- [ ] **Step 5: Commit** — `git add scripts/save_decisions.py tests/ && git commit -m "feat(save_decisions): optional read-only brain -> §6 recall+taboo on the act path"`

---

### Task 8: `refine_live.py` flips the live-evolving read ON

`refine_live` already opens `episode_store` from `ALPHA_EPISODES_DB` (default `./state/brain.db`) and passes it to `InnerLoop` as the WRITE handle. Flip the read on by ALSO passing `recall_store=episode_store` — the live evolving loop reads its own growing, PIT-masked brain. (In a single forward run, read==write is correct; the asymmetry only mattered for the paired verdict, handled in Task 5.)

**Files:**
- Modify: `scripts/refine_live.py:44-46` (the `InnerLoop(...)` call)
- Test: the refine_live test module (read `tests/` for it)

**Interfaces:**
- Consumes: `InnerLoop(…, episode_store=…, recall_store=…)` (Task 4).

- [ ] **Step 1: Write the failing test** (append to the refine_live test module) — observable taboo behavior: a vetoed symbol is never entered, so no NEW episode is written for it:

```python
def test_refine_live_recalls_own_brain_and_vetoes_taboo(tmp_path):
    """Seed the brain so RUN is taboo; the live loop recalls it -> vetoes RUN -> writes NO new RUN episode."""
    db = str(tmp_path / "brain.db")
    _seed_taboo_db(db, "RUN")                              # 3 PIT-old nuked RUN episodes (helper opens EpisodeStore.open(db))
    from alpha.memory.store import EpisodeStore
    before = len(EpisodeStore.open(db).for_asof(date(2099, 1, 1), limit=None))
    _run_refine_live_offline(db, agent_picks=["RUN"])     # MockLLM picks RUN every day; frontside regime
    after_run = [e for e in EpisodeStore.open(db).for_asof(date(2099, 1, 1), limit=None) if e.symbol == "RUN"]
    assert len(after_run) == 3                            # no NEW RUN episode: taboo vetoed it before entry
```

> NOTE: build `_run_refine_live_offline` from the EXISTING refine_live test (it injects MockLLM factories + tmp brain/conflict dirs + a synthetic source). It must pass `episodes_db=db`. Without Task 8's wiring this test FAILS (RUN gets entered + scored -> a 4th RUN episode appears).

- [ ] **Step 2: Run to verify it fails** — FAIL (today RUN is not vetoed → a new RUN episode is written → count 4).
- [ ] **Step 3: Implement** — in `scripts/refine_live.py:44-46`:

```python
        loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                         config=cfg, conflict_queue=cq, episode_store=episode_store,
                         recall_store=episode_store,        # §6 read ON: recall+taboo from the live brain
                         agent_factory=agent_factory)
```

- [ ] **Step 4: Run to verify green** — `python -m pytest tests/ -k refine_live -v` → PASS
- [ ] **Step 5: Commit** — `git add scripts/refine_live.py tests/ && git commit -m "feat(refine_live): live-evolving loop recalls its own brain (§6 read ON)"`

---

### Task 9: Full-suite gate + docs

- [ ] **Step 1: Full suite** — `python -m pytest` → all green (≥ 680 + the new tests). Investigate any regression as a real failure (systematic-debugging), not by deleting the test.
- [ ] **Step 2: Update the specs' out-of-scope notes** — in `docs/superpowers/specs/2026-06-26-episode-recall-design.md` and `docs/superpowers/specs/2026-06-27-episode-taboo-veto-design.md`, mark the "wire the live/verdict path ON" deferred item as DONE (it shipped here), pointing at this plan.
- [ ] **Step 3: Record in `docs/PROJECT_STATE.md`** — append a what's-built entry (the §6 read-side is ON: recall+taboo wired into save_decisions/refine_live/run_verdict, symmetric verdict via read-only `recall_store`, for_asof cap fixed at the read sites). Note remaining follow-ups stay in `ROADMAP.md` (the for_asof broader audit, hit_max_iters, conftest fragility, §8/Phase-1 Hermes).
- [ ] **Step 4: Commit docs** — `git add docs/ && git commit -m "docs: §6 read-side ON — update specs + PROJECT_STATE"`

---

## Self-Review

- **Spec coverage:** recall on-switch (recall design §"Out of scope" wire-on) → Tasks 3,5,6,7,8; taboo on-switch (taboo design §"Out of scope" wire-on) → Tasks 2,5,6,7,8; symmetric arms → Tasks 4,5; for_asof cap fold-in → Tasks 1,2,3. Converse face intentionally excluded (Global Constraints).
- **Decoupling correctness:** Task 4 keeps `apply_credit(episode_store=self._episode_store)` (write) untouched and reads via `self._recall_store`; Task 5 passes the verdict pool as `recall_store=` (read) NEVER `episode_store=` (write) → no HCH self-write (the `not_written_during_run` test enforces it).
- **Additive default-off:** every new param defaults `None`; Tasks 5/6/7 include explicit byte-identical / off-path assertions; the Task 9 full suite is the global regression gate.
- **Type consistency:** `recall_store` (read) vs `episode_store` (write) used consistently; `for_asof(…, limit: int | None = 50)` matches all three call sites (store, screen, retrieval) and the test helper `for_asof(date(2099,1,1), limit=None)`.
- **Helper caveat:** every test references thin wrappers (`_seed_taboo_store`, `_make_inner_loop`, `_run_compare`, `_produce_offline`, `_run_refine_live_offline`) that MUST be built from each test module's existing fixtures — the implementer reads the module first and reuses its real builders/MockLLM, rather than inventing infra.
