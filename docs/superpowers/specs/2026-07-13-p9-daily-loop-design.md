# P9 — Live daily production loop (design)

Status: drafted 2026-07-13. Source: DEVELOPMENT-PLAN.md §1 P9 + the Activation-ledger row
("Daily production loop"; the point-of-ON for the dormant capabilities). Charter posture:
warn-the-human co-pilot — an **unattended** loop must never lie about completeness, and must never
run guard-blind silently.

## What exists (the three on-demand producers)

Today the console reads whatever three operator-invoked scripts happen to have written:

| Producer (library fn) | Writes | Checksum posture | Corp-blind note |
|---|---|---|---|
| `scripts/save_decisions.py::save_decisions` | `DecisionStore` dir (`<date>.json` + `<date>.prompt.json`) | `verify_checksums(fail_closed=True)` in `main` | lands in `pkg.key_risks` via `screen_decision` |
| `scripts/run_verdict.py::run_verdict` + `comparison_to_view` | `VerdictStore` dir (`<label>.json`) | `verify_checksums(fail_closed=True)` in `main` | n/a (aggregate) |
| `scripts/save_evolution.py::run_evolution` | single evolution JSON (`ALPHA_WEB_EVOLUTION`) | `verify_checksums(fail_closed=False)` in `main` — **warn only** | n/a |

Each `main()` verifies checksums independently, each writes to its own destination independently, and
nothing coordinates them. Three failure modes an unattended cron inherits:

1. **Partial day that looks complete.** `save_decisions` succeeds and writes a decision file; the
   verdict step then fails. The console now shows a decision for the day with no matching verdict — a
   half-written day indistinguishable from a real one.
2. **Silent guard-blind.** `save_evolution` verifies **warn-only**; a mid-window corp-actions gap
   (P3's `CORP_BLIND_NOTE`) is buried inside one `DecisionPackage.key_risks` entry no operator reads.
3. **Drift tolerated per-artifact.** The three producers verify the pinned window separately; there is
   no single fail-closed gate for "this run ran on pinned data".

## The orchestration model

One module — `scripts/daily_loop.py` (sibling of the three producers; imports their library fns, does
not shell out) — turns "one logical production date + one captured PIT window" into **all three
artifacts or none**. Signature mirrors the siblings: `daily_loop <pit_root> <start> <end> <out_root>`,
where **`end` is the logical production date** and `[start, end]` is the window all three producers run
over (decisions get their in-window trailing history exactly as `save_decisions` threads it today; the
verdict/evolution get the comparison window). `out_root` is a fixed layout:

```
out_root/
  decisions/            # DecisionStore   -> ALPHA_WEB_DECISIONS_DIR
  verdicts/             # VerdictStore     -> ALPHA_WEB_VERDICTS_DIR
  evolution.json        # single file      -> ALPHA_WEB_EVOLUTION   (no dir variant in Settings)
  manifests/<end>.json  # the loop's own run record (completion marker + summary)
```

(Evolution has no `*_dir` browse variant in `Settings`, so it stays a single overwritten file — the
console's living "latest trajectory".) Individual paths + the trailing window override via flags; in
`main()` they default from the frozen `Settings.from_env()` (`web_decisions_dir` / `web_verdicts_dir` /
`web_evolution` / `episodes_db` / `pit_root`), constructed **once** and threaded down — the producer-tier
consumption pattern `alpha/settings.py` documents.

## The loud-failure contract (the core requirement)

**Stage-then-finalize, all-or-nothing.** No producer writes to a real destination. Instead:

1. **Verify once, fail closed.** `verify_checksums(pit_root, fail_closed=True)` before any work — the
   single gate that replaces the three per-producer checks (and upgrades evolution's warn-only posture).
   A mismatch raises → the run aborts before staging exists → destinations untouched.
2. **Preconditions, before producing** (review round — every *discoverable* failure moved ahead of the
   first irreversible `os.replace`): (a) the window carries **≥1 trading day** in the captured calendar —
   an empty window (holiday range / scheduler misfire / range outside the capture) would otherwise let the
   verdict + evolution finalize with *no* decision (a partial day); it raises loudly instead. (b) all four
   destination roots share the **staging filesystem** (`os.stat().st_dev` of each root's nearest existing
   ancestor == staging's) — a cross-device destination would make a finalize `os.replace` raise `EXDEV`
   *mid-move*, stranding already-moved files; it raises before producing instead. Both run before any LLM
   call or staged write.
3. **Produce into a private staging dir** (`out_root/.daily_loop.<end>.<pid>.tmp/`, same filesystem as
   `out_root` so the finalize renames are atomic). Decisions → `staging/decisions/`, verdict →
   `staging/verdicts/`, evolution → `staging/evolution.json`. Any producer raising propagates out; the
   `finally` unlinks the staging tree; **nothing was ever moved to a destination**. A post-produce invariant
   (`#staged decision packages == #trading days`) refuses a decision shortfall before finalize.
4. **Finalize** only after all three succeed. The full move list — including *iterating the staged
   decisions* — is **planned before the first `os.replace`**, so a missing/short stage surfaces at plan
   time (nothing moved), never mid-move. The plan executes in a deliberate order: **verdict, then
   evolution, then the decision file(s) + prompt sidecars, then the manifest last.** The decision file is
   what makes a day *appear* in the console's date picker (`DecisionStore.dates()`), so publishing it last
   means a crash mid-finalize can only ever leave a day that is *not yet visible* — never a visible
   decision missing its siblings (failure mode 1, closed). The manifest is the durable "run completed"
   record, written last.

The guarantee: every *discoverable* failure (empty window, cross-fs layout, decision shortfall, any
producer raising) aborts with **zero** finalized output (the acceptance-gate core). The only residual
partial state is a hard crash *between* the atomic renames — a window of a few syscalls with no
computation — and even then the ordering prevents a lone "looks-complete" decision, and the absent
manifest flags it for a clean re-run.

**No silent guard-blind.** After producing, the loop reads each staged `DecisionPackage` back and scans
`key_risks` for `CORP_BLIND_NOTE` (imported from `alpha.guard.screen`). If any day ran blind it:
(a) records `corp_blind: {blind: true, dates: [...]}` in the manifest (the persisted record), and
(b) prints a prominent `WARNING: corp-actions guard ran blind on N day(s): ...` to the run log. It does
**not** fail by default — P3's posture is warn-the-human, not veto — but `--fail-on-corp-blind` makes an
unattended operator's loop hard-stop (loud, non-zero exit) when strict. Either way the note reaches the
persisted record; it is never swallowed.

**Loud exit.** `main()` wraps `run_daily_loop`; any exception prints `daily-loop FAILED for <end>:
<self-describing message>` to stderr and exits non-zero. Success prints a one-line summary
(`daily-loop OK <end>: N decisions, verdict <label>, K edits[, CORP-BLIND N days]`).

## Idempotency / re-run semantics

**Overwrite cleanly** (chosen over refuse-unless-forced — an unattended cron re-run after a fixed data
issue must Just Work, and the atomic finalize guarantees a re-run never interleaves old and new). Every
finalize step is an `os.replace` over the prior file; the manifest, verdict label, evolution file, and
per-date decision file all key on `end`/window, so re-running a date fully replaces that date's outputs.
A crashed partial run finalized nothing, so the next run starts clean; its orphaned staging dir (named by
pid) is inert and swept by the `finally` on the crashing run when the process survives the exception
(a hard kill leaves an inert `.daily_loop.*.tmp/` that never shadows a destination). `--force` is not
needed; there is no refuse path to document around.

## Offline-buildable vs needs-the-machine

**Buildable + tested offline (this task):** the whole orchestration + loud-failure contract. Tests drive
`run_daily_loop` with a `FakeSource` + injected `MockLLM` factories (the sibling producers' own test
idiom) and assert: (a) a full run finalizes all three artifacts + a manifest; (b) an injected failing
step finalizes **nothing** (destinations empty) and raises — the acceptance-gate core; (c) a
`corp_actions_available=False` source surfaces `CORP_BLIND_NOTE` into the manifest + (with the flag)
fails; (d) a re-run overwrites cleanly; (e) a fail-closed checksum stub aborts before any artifact;
(f) an empty/holiday window aborts loudly, finalizing nothing and leaving a prior good `evolution.json`
intact; (g) a cross-filesystem destination aborts at the precondition **before** any LLM call (zero
producing), finalizing nothing.

**Needs-the-machine (documented, out of scope):** the real run needs `pip install -e ".[live]"` +
`APCA_*` + the per-role LLM keys + a captured window (`capture_window` → CHECKSUMS). The **scheduling
wrapper** (cron/systemd timer invoking `python scripts/daily_loop.py $PIT $START $END $OUT` once per
trading afternoon, env-file-sourced) is a deployment concern, not code — a runbook step, not this module.
The loop is *invocable and idempotent*; wiring a scheduler around an idempotent invocable command is the
machine step.

## Non-goals / deliberately not done

- **Not a new store.** Reuses `DecisionStore` / `VerdictStore` / the evolution JSON verbatim; adds only
  the run-manifest (the loop's own record — not consumed by the console, which is untouched per footprint).
- **No producer edits.** The three library fns are imported and called as-is; the corp-blind note is read
  back from the produced packages, never re-plumbed through the producers.
- **Single-comparison verdict.** The daily verdict is `windows=1` (`comparison_to_view` needs a single
  comparison); the multi-window diagnostic stays a manual `run_verdict --windows N` concern.
- **TCB.** Nothing here is in `tcb.lock`; `scripts/daily_loop.py` is a new orchestration script, not a
  TCB file, and touches no TCB file.
