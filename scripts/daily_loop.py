"""P9 — the scheduled daily production loop: one logical date + one captured PIT window -> all three
console artifacts at once, atomically (all-or-nothing), replacing the three on-demand producers
(`save_decisions` / `run_verdict --json` / `save_evolution`) so the console reads a living record.

Design + the loud-failure contract: docs/superpowers/specs/2026-07-13-p9-daily-loop-design.md.

  # 1. capture + pin a PIT window (needs the `live` extra + APCA keys):
  python scripts/capture_window.py 2026-01-02 2026-01-31 snap AAPL MSFT NVDA TSLA AMD

  # 2. produce all three artifacts for the day (needs the agent + refiner LLM keys):
  export ALPHA_AGENT_PROVIDER=openai_compat ALPHA_AGENT_MODEL=deepseek-chat   # + DEEPSEEK_API_KEY
  python scripts/daily_loop.py snap 2026-01-02 2026-01-31 prod   # end (=2026-01-31) is the logical date

  # 3. browse the living record in the console:
  ALPHA_WEB_DECISIONS_DIR=prod/decisions ALPHA_WEB_VERDICTS_DIR=prod/verdicts \
  ALPHA_WEB_EVOLUTION=prod/evolution.json python -m alpha_web

Scheduling (cron/systemd firing this once per trading afternoon) is a deployment concern, not code — the
loop is invocable + idempotent; wiring a scheduler around it is the needs-the-machine step (spec §"machine").

The loud-failure contract (why this exists, vs running the three producers by hand): every artifact is
produced into a private staging tree and only os.replace-finalized into its destination AFTER all three
succeed — a failed step leaves NO partial day (never a visible decision missing its verdict). The pinned
window is verified ONCE fail-closed (upgrading save_evolution's warn-only posture), and P3's corp-blind
note is surfaced into the run manifest + log, never swallowed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date as Date, datetime, timezone
from pathlib import Path

from alpha.data.integrity_check import verify_checksums
from alpha.data.pit_store import PITStore
from alpha.data.calendar import trading_days_between
from alpha.data.snapshot_source import SnapshotSource
from alpha.eval.decision_store import DecisionStore
from alpha.eval.verdict_store import VerdictStore
from alpha.guard.screen import CORP_BLIND_NOTE
from alpha.harness.loader import load_pack
from alpha.llm.config import make_client
from alpha.memory.store import EpisodeStore
from alpha.settings import Settings
from alpha.universe import resolve_universe_screen

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:                       # import the sibling producers by name (never shell out)
    sys.path.insert(0, str(_HERE))

import run_verdict            # noqa: E402  sibling producers (library fns reused, not shelled out)
import save_decisions         # noqa: E402
import save_evolution         # noqa: E402


def _fs_device(path: Path) -> int:
    """st_dev of `path`'s nearest EXISTING ancestor. A not-yet-created destination lands on the
    filesystem of the first directory that already exists above it, so that ancestor's device is where
    its finalized file will be written — the value the same-filesystem precondition must compare."""
    p = Path(path).resolve()
    while not p.exists():
        if p.parent == p:                                # reached the filesystem root
            break
        p = p.parent
    return os.stat(p).st_dev


def _atomic_write_json(path: Path, data: dict) -> Path:
    """Write `data` as JSON to `path` atomically (temp-in-dir + os.replace; the store idiom). default=str
    so date/enum payloads round-trip; never leaves a truncated final file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def run_daily_loop(source, start: Date, end: Date, *,
                   decisions_dir, verdicts_dir, evolution_path, manifests_dir,
                   agent_llm_factory=None, refiner_llm_factory=None,
                   screen: bool = True, size: bool = True, horizon: int = 2,
                   episode_store=None, recall_store=None,
                   universe_screen: str | None = None, seed_pack: str | None = None,
                   pit_root=None, verify=None,
                   fail_on_corp_blind: bool = False) -> dict:
    """Produce + finalize the day's DecisionStore / VerdictStore / evolution artifacts atomically over the
    window [start, end] (end = the logical production date). Returns the run manifest (also persisted).

    All-or-nothing: everything is produced into a private staging tree and only os.replace-finalized into
    the destinations after all three succeed (finalize order verdict -> evolution -> decisions -> manifest,
    so the console-visible decision is published LAST — a mid-finalize crash can never leave a lone
    "looks-complete" decision). A producer raising propagates out with NOTHING finalized; the staging tree
    is always swept in `finally`.

    Every DISCOVERABLE failure is moved ahead of the first irreversible os.replace: two preconditions run
    BEFORE producing — the window has >=1 trading day in the captured calendar (else a holiday/misfire range
    would finalize a verdict/evolution with no decision), and all four destination roots share the staging
    filesystem (else a cross-device os.replace would strand already-moved files mid-finalize). The finalize
    move list (including iterating the staged decisions) is planned in full before any move executes, so a
    missing stage surfaces at plan time, not mid-move.

    Loud failure: `verify(pit_root, fail_closed=True)` gates the whole run on pinned data (one gate for all
    three artifacts; None pit_root skips it — a manifest-less offline window). P3's `CORP_BLIND_NOTE` is
    scanned out of the freshly-produced packages and surfaced into the manifest + a WARNING log line; with
    `fail_on_corp_blind` it hard-stops the run (unattended-strict) instead of warning.

    Factories default to this module's `make_client` (the single monkey-point); tests inject MockLLM. The
    verdict is a single comparison (windows=1) — the shape `comparison_to_view` / the console consume."""
    decisions_dir, verdicts_dir = Path(decisions_dir), Path(verdicts_dir)
    evolution_path, manifests_dir = Path(evolution_path), Path(manifests_dir)
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))

    # 1. one fail-closed gate over the pinned window (replaces + upgrades the per-producer checks) —
    #    BEFORE any staging exists, so a drift mismatch aborts with the destinations untouched.
    checksums_verified = pit_root is not None
    if checksums_verified:
        (verify or verify_checksums)(Path(pit_root), fail_closed=True)   # call-time bind honors a monkeypatch

    # PRECONDITION (a): the window must carry >=1 trading day in the captured calendar. An empty window
    # (holiday range / scheduler misfire / range outside the capture) would otherwise finalize a degenerate
    # verdict + evolution with NO decision — a partial day. Refuse loudly, before producing anything.
    n_days = len(trading_days_between(source.trading_calendar(), start, end))
    if n_days == 0:
        raise RuntimeError(f"no trading days in [{start.isoformat()}, {end.isoformat()}] — nothing to "
                           f"produce (holiday range / scheduler misfire / range outside the captured "
                           f"calendar); refusing to finalize a partial day")

    # run provenance resolved once (rides the verdict view AND the manifest so a browsed run is unambiguous)
    universe_screen = resolve_universe_screen() if universe_screen is None else universe_screen
    seed_pack = load_pack().vocabulary if seed_pack is None else seed_pack
    label = f"{start.isoformat()}_{end.isoformat()}"

    # a private staging tree under out_root (== manifests_dir.parent in the standard layout) so every
    # finalize move is a same-filesystem atomic rename; pid in the name keeps concurrent runs disjoint.
    staging = manifests_dir.parent / f".daily_loop.{end.isoformat()}.{os.getpid()}.tmp"
    stage_dec, stage_ver = staging / "decisions", staging / "verdicts"
    stage_evo = staging / "evolution.json"
    try:
        staging.mkdir(parents=True, exist_ok=True)

        # PRECONDITION (b): every destination must land on the staging filesystem, else a finalize os.replace
        # raises EXDEV mid-move (already-moved files stranded). Assert same-device BEFORE producing, so a
        # cross-fs layout aborts with nothing produced or finalized (matches the spec's same-fs assumption).
        staging_dev = _fs_device(staging)
        for name, root in (("decisions_dir", decisions_dir), ("verdicts_dir", verdicts_dir),
                           ("evolution_path", evolution_path.parent), ("manifests_dir", manifests_dir)):
            if _fs_device(root) != staging_dev:
                raise RuntimeError(f"destinations must be on the same filesystem as out_root "
                                   f"(got cross-device: {name}={root})")

        # --- produce (decisions FIRST so the corp-blind scan runs before anything is finalized) ---
        dec_store = DecisionStore(stage_dec)
        n_dec = save_decisions.save_decisions(source, start, end, dec_store,
                                              agent_llm_factory=agent_llm_factory, screen=screen,
                                              size=size, episode_store=episode_store)
        decision_dates = dec_store.dates()
        if len(decision_dates) != n_days:                 # save_decisions writes one package per trading day;
            raise RuntimeError(f"staged {len(decision_dates)} daily package(s) but the window "   # a shortfall
                               f"[{start.isoformat()}, {end.isoformat()}] has {n_days} trading day(s) — "
                               f"refusing to finalize a partial day")   # would be a partial day -> refuse pre-finalize
        blind_dates = [d.isoformat() for d in decision_dates
                       if (pkg := dec_store.get(d)) is not None and CORP_BLIND_NOTE in pkg.key_risks]
        if blind_dates:                                   # never swallowed — reaches the log AND the manifest
            print(f"WARNING: corp-actions guard ran blind on {len(blind_dates)} day(s): "
                  f"{', '.join(blind_dates)} — an unflagged split or dilution may have passed")
        if blind_dates and fail_on_corp_blind:
            raise RuntimeError(f"corp-actions guard ran blind on {len(blind_dates)} day(s) "
                               f"({', '.join(blind_dates)}) and --fail-on-corp-blind is set")

        cr = run_verdict.run_verdict(source, start, end, horizon=horizon, windows=1, screen=screen,
                                     agent_llm_factory=agent_llm_factory,
                                     refiner_llm_factory=refiner_llm_factory, recall_store=recall_store)
        view = run_verdict.comparison_to_view(cr, start=start, end=end, horizon=horizon, screen=screen,
                                              universe_screen=universe_screen, seed_pack=seed_pack)
        VerdictStore(stage_ver).put(label, view)

        evo = save_evolution.run_evolution(source, start, end, horizon=horizon,
                                           agent_llm_factory=agent_llm_factory,
                                           refiner_llm_factory=refiner_llm_factory)
        _atomic_write_json(stage_evo, evo)

        manifest = {
            "logical_date": end.isoformat(),
            "window": {"start": start.isoformat(), "end": end.isoformat(), "horizon": horizon},
            "status": "ok",
            "checksums_verified": checksums_verified,
            "corp_blind": {"blind": bool(blind_dates), "dates": blind_dates},
            "screen": screen, "size": size,
            "seed_pack": seed_pack, "universe_screen": universe_screen,
            "artifacts": {
                "decisions_dir": str(decisions_dir),
                "n_decisions": n_dec,
                "decision_dates": [d.isoformat() for d in decision_dates],
                "verdict_dir": str(verdicts_dir),
                "verdict_label": label,
                "evolution_path": str(evolution_path),
                "n_edits": evo["summary"]["n_edits"],
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # --- finalize: PLAN the full move list (incl. iterating the staged decisions) BEFORE the first
        #     os.replace, so a missing/short stage surfaces here — not stranded mid-move. Order is verdict,
        #     evolution, then decisions LAST (the console-visible commit); the manifest lands last of all. ---
        moves = [(stage_ver / f"{label}.json", verdicts_dir / f"{label}.json"), (stage_evo, evolution_path)]
        moves += [(f, decisions_dir / f.name) for f in sorted(stage_dec.iterdir()) if f.is_file()]
        for _src, dst in moves:                           # same-fs already asserted -> these renames are atomic
            dst.parent.mkdir(parents=True, exist_ok=True)
        for src, dst in moves:
            os.replace(src, dst)
        _atomic_write_json(manifests_dir / f"{end.isoformat()}.json", manifest)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)        # sweep on success (empty) AND failure (partial)


def main() -> None:
    ap = argparse.ArgumentParser(description="Daily production loop: one PIT window -> DecisionStore + "
                                 "VerdictStore + evolution artifact, atomically (all-or-nothing).")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat, help="the logical production date (window end)")
    ap.add_argument("out_root", help="output root: writes decisions/ verdicts/ evolution.json manifests/")
    ap.add_argument("--horizon", type=int, default=2)
    ap.add_argument("--no-screen", action="store_true", help="skip the L4 guard veto")
    ap.add_argument("--no-size", action="store_true", help="emit unsized decisions (skip L3 sizing)")
    ap.add_argument("--brain", metavar="PATH", help="read-only EpisodeStore (brain.db) for recall+taboo; "
                    "defaults to $ALPHA_EPISODES_DB if set")
    ap.add_argument("--fail-on-corp-blind", action="store_true",
                    help="hard-stop (non-zero exit) if any day's corp-actions guard ran blind")
    ap.add_argument("--decisions-dir", help="override out_root/decisions")
    ap.add_argument("--verdicts-dir", help="override out_root/verdicts")
    ap.add_argument("--evolution-path", help="override out_root/evolution.json")
    ap.add_argument("--manifests-dir", help="override out_root/manifests")
    args = ap.parse_args()

    s = Settings.from_env()                              # frozen settings, once, threaded down (mining §2.7)
    out_root = Path(args.out_root)
    decisions_dir = Path(args.decisions_dir or s.web_decisions_dir or (out_root / "decisions"))
    verdicts_dir = Path(args.verdicts_dir or s.web_verdicts_dir or (out_root / "verdicts"))
    evolution_path = Path(args.evolution_path or s.web_evolution or (out_root / "evolution.json"))
    manifests_dir = Path(args.manifests_dir or (out_root / "manifests"))

    pit_root = Path(args.pit_root)
    source = SnapshotSource(PITStore(pit_root))
    brain = args.brain or s.episodes_db
    episode_store = EpisodeStore.open(brain, create_if_missing=False) if brain else None

    try:
        manifest = run_daily_loop(
            source, args.start, args.end,
            decisions_dir=decisions_dir, verdicts_dir=verdicts_dir,
            evolution_path=evolution_path, manifests_dir=manifests_dir,
            agent_llm_factory=lambda: make_client("agent"),
            refiner_llm_factory=lambda: make_client("refiner"),
            screen=not args.no_screen, size=not args.no_size, horizon=args.horizon,
            episode_store=episode_store, recall_store=episode_store,   # verdict gets it read-only (never episode_store=)
            pit_root=pit_root, fail_on_corp_blind=args.fail_on_corp_blind)
    except Exception as e:
        print(f"daily-loop FAILED for {args.end.isoformat()}: {e}", file=sys.stderr)
        raise SystemExit(1)

    a, cb = manifest["artifacts"], manifest["corp_blind"]
    extra = f"  CORP-BLIND {len(cb['dates'])} days" if cb["blind"] else ""
    print(f"daily-loop OK {args.end.isoformat()}: {a['n_decisions']} decisions, "
          f"verdict {a['verdict_label']}, {a['n_edits']} edits{extra}")


if __name__ == "__main__":
    main()
