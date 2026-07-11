"""Read-only PIT episode inspector: print the SAME summarize()/is_episode_taboo() numbers the L4
guard's episode-taboo veto sees (alpha/guard/screen.py), so a human can audit *why* the veto did
(or didn't) fire on a given day. Imports summarize()/is_episode_taboo() straight from their
production home (alpha.memory.aggregate) and reads via the identical `for_asof(asof, limit=None)`
call the veto makes (default kind="trade", full PIT-masked history, no 50-row display cap) — no
re-derivation, so this can never silently drift from what the veto actually saw.

  python scripts/inspect_episodes.py brain.db 2026-06-10
  python scripts/inspect_episodes.py brain.db 2026-06-10 --symbol RUN
"""
from __future__ import annotations

import argparse
from datetime import date as Date

from alpha.memory.aggregate import is_episode_taboo, summarize
from alpha.memory.store import EpisodeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Print PIT-masked episodes + the same taboo numbers the L4 guard sees.")
    ap.add_argument("db", help="EpisodeStore sqlite path (brain.db)")
    ap.add_argument("asof", type=Date.fromisoformat, help="PIT cutoff date, e.g. 2026-06-10")
    ap.add_argument("--symbol", help="restrict to one symbol (rows + stats)")
    args = ap.parse_args(argv)

    store = EpisodeStore.open(args.db, create_if_missing=False)
    try:
        # Mirrors alpha/guard/screen.py's read exactly: for_asof(as_of, limit=None), trade-kind
        # default, full PIT history (past the 50-row display cap).
        episodes = store.for_asof(args.asof, limit=None)
    finally:
        store.close()
    if args.symbol:
        episodes = [e for e in episodes if e.symbol == args.symbol]

    print(f"=== EPISODES as-of {args.asof.isoformat()} ({len(episodes)} rows) ===")
    for e in sorted(episodes, key=lambda e: (e.symbol, e.exit_date)):
        print(f"{e.exit_date.isoformat()} {e.symbol:8} {e.skill_id:20} {e.outcome:10} "
              f"adv={e.advantage:+.2f} score={e.score:.2f}")

    # Same aggregator + same taboo predicate the L4 guard calls (alpha/guard/screen.py).
    stats = summarize(episodes, key=lambda e: e.symbol)
    print()
    print("=== SUMMARY (same summarize()/is_episode_taboo() the L4 guard uses) ===")
    if not stats:
        print("(no episodes)")
        return
    for symbol in sorted(stats):
        s = stats[symbol]
        taboo = is_episode_taboo(s)
        print(f"{symbol:8} n={s.n} nuked={s.nuked} continued={s.continued} faded={s.faded} "
              f"nuke_rate={s.nuke_rate:.2f} win_rate={s.win_rate:.2f} mean_adv={s.mean_advantage:+.2f} "
              f"taboo={'YES' if taboo else 'no'}")


if __name__ == "__main__":
    main()
