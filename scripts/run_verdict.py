"""Render the empirical HCH-vs-Hexpert verdict (spec §9/§10) on captured Alpaca PIT data.

This is the orthogonal closeout of US-2/US-3: the offline test suite validates the *apparatus*
(MockLLM ignores prompts), so the actual pass/fail verdict needs a live, deterministic (temperature=0)
LLM run over real market windows. This script wires the captured PIT source through `compare_harnesses`
/ `multi_window` with per-role temp=0 clients and prints the StatVerdict + contribution split + per-arm
report. The honest expectation is **parity** (HCH ~= Hexpert); beating frozen seeds is the frontier.

Two-step user run (needs the `live` extra + APCA_API_KEY_ID/SECRET + LLM keys):

  # 1. Build the offline PIT DB once (no LLM, just market data):
  python scripts/capture_window.py 2026-01-02 2026-03-31 verdict_pit AAPL MSFT NVDA TSLA AMD ...

  # 2. Render the verdict at temperature=0 (agent=DeepSeek/cheap, refiner=Claude by default):
  export ALPHA_AGENT_PROVIDER=openai_compat ALPHA_AGENT_MODEL=deepseek-chat   # + DEEPSEEK key
  export ALPHA_REFINER_PROVIDER=anthropic   ALPHA_REFINER_MODEL=claude-sonnet-4-6  # + ANTHROPIC key
  python scripts/run_verdict.py verdict_pit 2026-01-02 2026-03-31 --windows 3

`screen` defaults ON (the L4 guard is live + symmetric across arms; richer-state wiring 2026-06-16), so
this measures the production posture. Determinism: `make_client` reads ALPHA_LLM_TEMPERATURE (default 0).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date as Date
from pathlib import Path

from alpha.data.calendar import trading_days_between
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.eval.contribution import ContributionBucket, ContributionReport
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.loop.compare import ComparisonReport, MultiWindowReport, compare_harnesses, multi_window
from alpha.loop.inner_loop import LoopConfig
from alpha.llm.config import make_client

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"


def split_windows(calendar: list[Date], start: Date, end: Date, n: int, *, horizon: int) -> list[tuple[Date, Date]]:
    """Partition the trading days in [start, end] into `n` contiguous windows, each long enough to score
    (> horizon days). The temp=0 multi-window tally is the deterministic surrogate for multi-seed (spec
    §10/US-2e): with temperature=0 you cannot vary the seed, so independent windows stand in for trials."""
    days = trading_days_between(calendar, start, end)
    if n <= 1 or len(days) < 2 * (horizon + 1):
        return [(start, end)]
    n = min(n, len(days) // (horizon + 1))            # never make a window shorter than horizon+1 days
    size = len(days) // n
    out: list[tuple[Date, Date]] = []
    for i in range(n):
        lo = i * size
        hi = (len(days) - 1) if i == n - 1 else (lo + size - 1)   # last window absorbs the remainder
        out.append((days[lo], days[hi]))
    return out


def run_verdict(source, start: Date, end: Date, *, seeds_dir: Path = SEEDS_DIR, horizon: int = 2,
                windows: int = 1, shadow: bool = False, agent_llm_factory=None, refiner_llm_factory=None):
    """Run the §9/§10 comparison over the captured `source`. Returns a ComparisonReport (windows<=1) or a
    MultiWindowReport (windows>1). Factories default to temp=0 `make_client` clients; tests inject MockLLM.

    All arms get a FRESH H / LLM client / store (factory injection — no cross-arm pollution). `screen`
    defaults ON via LoopConfig(), so HCH and the Hexpert/Hmin arms are guarded symmetrically."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))
    harness_factory = lambda: load_seeds(seeds_dir)
    store_factory = lambda: SnapshotStore(tempfile.mkdtemp())
    cfg = LoopConfig(horizon=horizon)                 # screen defaults ON (production posture)
    kw = dict(agent_llm_factory=agent_llm_factory, refiner_llm_factory=refiner_llm_factory,
              store_factory=store_factory, loop_config=cfg, shadow=shadow)
    wins = split_windows(source.trading_calendar(), start, end, windows, horizon=horizon)
    if len(wins) > 1:
        return multi_window(harness_factory, source, wins, **kw)
    return compare_harnesses(harness_factory, source, wins[0][0], wins[0][1], **kw)


def _fmt_arm(label: str, arm) -> str:
    r = arm.report
    extra = ""
    if arm.n_refines is not None:
        extra = f"  refines={arm.n_refines} trips={arm.n_breaker_trips} frozen={arm.frozen_from}"
    return (f"  {label:<13} n_dec={r.n_decisions:<4} cand={r.n_candidates:<4} "
            f"mean_excess={r.mean_excess:+.4f} hit={r.hit_rate:.2f} nuke={r.nuke_rate:.2f}{extra}")


def _fmt_bucket(label: str, b: ContributionBucket) -> str:
    return (f"    {label:<10} n={b.n:<4} hit={b.hit_rate:.2f} nuke={b.nuke_rate:.2f} "
            f"exp={b.expectancy:+.4f} exp_raw={b.expectancy_raw:+.4f}")


def _fmt_contribution(c: ContributionReport) -> str:
    lines = ["CONTRIBUTION (HCH, resolved vs the evolved H)",
             _fmt_bucket("offense", c.offense), _fmt_bucket("defense", c.defense),
             _fmt_bucket("unknown", c.unknown)]
    if c.by_family:
        fam = "  ".join(f"{k}(n={v.n}, exp={v.expectancy:+.3f})" for k, v in sorted(c.by_family.items()))
        lines.append(f"    by_family: {fam}")
    return "\n".join(lines)


def format_comparison(cr: ComparisonReport, *, header: str = "") -> str:
    lines = [header] if header else []
    lines.append("ARMS")
    for name in ("HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"):
        if name in cr.arms:
            lines.append(_fmt_arm(name, cr.arms[name]))
    lines.append("")
    lines.append(f"HEADLINE  HCH - Hexpert mean_excess = {cr.hch_minus_hexpert_mean_excess:+.4f}"
                 f"  ->  HCH beats Hexpert: {cr.hch_beats_hexpert}")
    if cr.stat_verdict is not None:
        v = cr.stat_verdict
        ci = (f"[{v.ci_low:+.4f}, {v.ci_high:+.4f}]" if v.ci_low is not None else "n/a")
        p = (f"{v.p_value:.3f}" if v.p_value is not None else "n/a")
        mde = (f"{v.mde:.3f}" if v.mde is not None else "n/a")
        lines.append(f"STAT VERDICT (paired day-level)  verdict={v.verdict}  n_days={v.n_days}  "
                     f"mean_diff={v.mean_diff:+.4f}  CI={ci}  p={p}  MDE={mde}")
    if cr.contribution is not None:
        lines.append(_fmt_contribution(cr.contribution))
    return "\n".join(lines)


def comparison_to_view(cr: ComparisonReport, *, start: Date, end: Date, horizon: int,
                       screen: bool) -> dict:
    """Map a ComparisonReport to the flat UI dict the web console's verdict page consumes (the shape of
    `alpha_web.sample.sample_verdict()`, NOT ComparisonReport's own shape). Write this with `--json` and
    point `ALPHA_WEB_VERDICT` (or drop several into `ALPHA_WEB_VERDICTS_DIR`) at it to browse a real run."""
    def arm(a) -> dict:
        r = a.report
        d = {"n_decisions": r.n_decisions, "n_candidates": r.n_candidates,
             "mean_excess": r.mean_excess, "hit_rate": r.hit_rate, "nuke_rate": r.nuke_rate}
        if a.n_refines is not None:                       # HCH-only evolution counters
            d.update(refines=a.n_refines, trips=a.n_breaker_trips,
                     frozen_from=a.frozen_from.isoformat() if a.frozen_from is not None else None)
        return d

    v = cr.stat_verdict
    stat = ({"verdict": v.verdict, "n_days": v.n_days, "mean_diff": v.mean_diff, "ci_low": v.ci_low,
             "ci_high": v.ci_high, "p_value": v.p_value, "mde": v.mde} if v is not None else
            {"verdict": "insufficient", "n_days": 0, "mean_diff": 0.0,
             "ci_low": None, "ci_high": None, "p_value": None, "mde": None})

    c = cr.contribution
    def bucket(b) -> dict:
        return {"n": b.n, "hit_rate": b.hit_rate, "nuke_rate": b.nuke_rate, "expectancy": b.expectancy}
    contribution = ({"offense": bucket(c.offense), "defense": bucket(c.defense),
                     "unknown": bucket(c.unknown)} if c is not None else None)

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "horizon": horizon,
                   "windows": 1, "screen": screen},
        "arms": {name: arm(a) for name, a in cr.arms.items()},
        "headline": {"hch_minus_hexpert": cr.hch_minus_hexpert_mean_excess,
                     "hch_beats_hexpert": cr.hch_beats_hexpert},
        "stat_verdict": stat,
        "contribution": contribution,
    }


def format_multi(mw: MultiWindowReport) -> str:
    lines = [f"MULTI-WINDOW ({mw.n_windows} windows; temp=0 multi-seed surrogate)",
             f"  deltas      = {[round(d, 4) for d in mw.deltas]}",
             f"  mean_delta  = {mw.mean_delta:+.4f}",
             f"  win_rate    = {mw.win_rate:.2f}   sign_consistent = {mw.sign_consistent}",
             f"  verdict_tally = {dict(sorted(mw.verdict_tally.items()))}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the HCH-vs-Hexpert verdict on captured PIT data.")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat)
    ap.add_argument("--windows", type=int, default=1, help="split into N independent windows (multi-seed surrogate)")
    ap.add_argument("--horizon", type=int, default=2, help="hold horizon (>=2; no same-day round-trip)")
    ap.add_argument("--shadow", action="store_true", help="seed HCH's paired breaker with the Hexpert series")
    ap.add_argument("--json", metavar="PATH", help="also write the console JSON (web verdict view) to PATH "
                    "(single comparison; pair with --windows 1, the default)")
    args = ap.parse_args()

    source = SnapshotSource(PITStore(Path(args.pit_root)))
    temp = os.environ.get("ALPHA_LLM_TEMPERATURE", "0")
    print("=== Evolving-Alpha-US verdict run ===")
    print(f"window: {args.start} .. {args.end}   horizon={args.horizon}  windows={args.windows}  "
          f"screen={LoopConfig().screen}  shadow={args.shadow}")
    for role in ("agent", "refiner"):
        prov = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", "(default)")
        model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", "(default)")
        print(f"  {role:<8} provider={prov} model={model} temp={temp}")
    if temp != "0":
        print("  WARNING: ALPHA_LLM_TEMPERATURE != 0 — the verdict will not be deterministic.")
    print()

    result = run_verdict(source, args.start, args.end, horizon=args.horizon,
                         windows=args.windows, shadow=args.shadow)
    if isinstance(result, MultiWindowReport):
        print(format_multi(result))
        if args.json:
            print(f"  NOTE: --json needs a single comparison; re-run with --windows 1 to emit {args.json} (skipped).")
    else:
        print(format_comparison(result))
        if args.json:
            view = comparison_to_view(result, start=args.start, end=args.end,
                                      horizon=args.horizon, screen=LoopConfig().screen)
            Path(args.json).write_text(json.dumps(view, indent=2), encoding="utf-8")
            print(f"  wrote console JSON -> {args.json}  (ALPHA_WEB_VERDICT={args.json} python -m alpha_web)")


if __name__ == "__main__":
    main()
