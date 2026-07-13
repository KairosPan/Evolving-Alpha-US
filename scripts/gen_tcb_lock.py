#!/usr/bin/env python3
"""Generate/check tcb.lock — content hashes of the TCB file set (modification-ladder §3).

Usage: python scripts/gen_tcb_lock.py [--check]
The manifest set is TCB_FILES below; ADDITIONS ARE HUMAN-ONLY (the list is a red-line).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha.integrity import sha256_file

TCB_FILES = [
    "alpha/refine/apply.py",        # the gate (try_apply_op) — one-write-waist
    "alpha/refine/ops.py",          # PASS_TOOLS whitelist / RefineOp vocabulary
    "alpha/refine/conflict.py",     # two-loop conflict -> held_for_review
    "alpha/harness/metatools.py",   # the only edit facade; rationale floor
    "alpha/harness/edit_log.py",    # append-only audit + provenance stamping
    "alpha/harness/snapshot.py",    # atomic checkpoint (the version authority)
    "alpha/harness/manager.py",     # rollback + handle rebinding
    "alpha/harness/doctrine.py",    # red-line immutability
    "alpha/loop/floor_breaker.py",  # capability-floor breaker
    "alpha/data/firewall.py",       # PIT firewall (AsOfGuard/GuardedSource)
    "alpha/memory/store.py",        # recall PIT-mask: for_asof (spec §3 row 11, corrected)
    "alpha/agent/retrieval.py",     # recall PIT-mask: select_for_prompt (row 11, corrected)
    "alpha/arena/policy.py",        # single dispatch choke point + tiers
    "alpha/meta/evolution.py",      # adopt-time red-line/prefix validation (added 2026-07-10, user-approved)
    "alpha/meta/proposal_store.py", # brain_hash staleness pin (added 2026-07-10, user-approved)
    "alpha/meta/body_git.py",       # A5 Body-Store-as-git audit mirror (added 2026-07-13, user-approved)
    "alpha/meta/netguard.py",       # A9 SSRF/egress trust root (added 2026-07-13, user-approved)
]

def generate(repo: Path) -> str:
    lines = [f"{sha256_file(repo / f)}  {f}" for f in sorted(TCB_FILES)]
    header = ("# tcb.lock — TCB content hashes (modification-ladder spec §3; additions human-only)\n"
              "# Row 13 (red-line lint / try_promote_body / verifier harness): declared, not yet built.\n"
              "# alpha/meta/{evolution,proposal_store}.py added 2026-07-10 (user-approved, backend-design round).\n"
              "# alpha/meta/{body_git,netguard}.py added 2026-07-13 (user-approved; A5 Body-git audit, A9 SSRF trust root).\n")
    return header + "\n".join(lines) + "\n"

def read_lock(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            out[name] = digest
    return out

def check(repo: Path) -> list[str]:
    lock = read_lock(repo / "tcb.lock")
    problems = [f"listed-but-absent: {f}" for f in lock if not (repo / f).exists()]
    problems += [f"unlisted: {f}" for f in TCB_FILES if f not in lock]
    problems += [f"drift: {f}" for f, d in lock.items()
                 if (repo / f).exists() and sha256_file(repo / f) != d]
    return problems

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(__file__).resolve().parents[1]
    if "--check" in argv:
        problems = check(repo)
        for p in problems: print(p)
        return 1 if problems else 0
    (repo / "tcb.lock").write_text(generate(repo))
    print("tcb.lock written")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
