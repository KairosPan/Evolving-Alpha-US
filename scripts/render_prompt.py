"""Render a day's D3 prompt-audit sidecar for human inspection: the exact system prompt the agent
saw, then the offered/dropped table (every drop names its reason).

  python scripts/render_prompt.py decisions 2026-01-05

reads `decisions/2026-01-05.prompt.json` (written by scripts/save_decisions.py beside the day's
decision file) and prints the assembled prompt text followed by one line per audited record —
`kind`, `id`, `status`, and the drop reason (depends_on-unmet / budget-cut / weight-cut).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Print a day's assembled system prompt + audit table.")
    ap.add_argument("decisions_dir", help="DecisionStore directory holding <date>.prompt.json sidecars")
    ap.add_argument("date", help="ISO date of the sidecar to render, e.g. 2026-01-05")
    args = ap.parse_args(argv)

    path = Path(args.decisions_dir) / f"{args.date}.prompt.json"
    side = json.loads(path.read_text(encoding="utf-8"))

    print(f"=== ASSEMBLED SYSTEM PROMPT ({side.get('date', args.date)}) ===")
    print(side.get("assembled", ""))
    print()
    print("=== PROMPT AUDIT (offered / dropped) ===")
    records = side.get("records", [])
    if not records:
        print("(no records)")
        return
    for r in records:
        line = f"{r.get('kind', '?'):8} {r.get('id', '?'):40} {r.get('status', '?'):8}"
        if r.get("reason"):
            line += f" {r['reason']}"
        print(line)


if __name__ == "__main__":
    main()
