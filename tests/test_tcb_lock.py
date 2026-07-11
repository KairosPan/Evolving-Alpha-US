"""tcb.lock drift gate (modification-ladder §3: 'defining the manifest is a NOW deliverable').

REGEN RITUAL: a legitimate TCB edit re-runs `python scripts/gen_tcb_lock.py` and commits
the updated tcb.lock IN THE SAME CHANGE — this test staying red is the reminder.
Additions to TCB_FILES are highest-approval, human-only (spec §3 red-line rule).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import gen_tcb_lock


def test_manifest_is_non_empty_and_complete():
    entries = gen_tcb_lock.read_lock(REPO / "tcb.lock")
    assert len(entries) >= 15                              # non-vacuous
    assert set(entries) == set(gen_tcb_lock.TCB_FILES)     # lockfile matches the declared set


def test_every_tcb_file_exists_and_matches():
    problems = gen_tcb_lock.check(REPO)
    assert problems == [], "TCB drift — re-run scripts/gen_tcb_lock.py in the same change:\n" + "\n".join(problems)
