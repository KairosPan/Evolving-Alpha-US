"""D4: canonical sha256 of HarnessState; optional h_digest on DecisionPackage; eval never reads it."""
import subprocess
from datetime import date
from pathlib import Path

from alpha.eval.decision import DecisionPackage
from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.snapshot import harness_digest
from alpha.harness.state import HarnessState

REPO_ROOT = Path(__file__).resolve().parents[2]


def _state(lesson_text: str = "x") -> HarnessState:
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons(
        [Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson=lesson_text)])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def test_digest_stable_and_content_sensitive():
    # equal content -> equal digest; mutate one lesson -> digest changes; 64 hex chars.
    d1 = harness_digest(_state())
    d2 = harness_digest(_state())
    assert d1 == d2
    assert len(d1) == 64
    assert all(c in "0123456789abcdef" for c in d1)

    d3 = harness_digest(_state(lesson_text="y"))
    assert d3 != d1


def test_decision_package_h_digest_optional_and_eval_neutral():
    # DecisionPackage() without h_digest still validates (default None) — additive field.
    pkg = DecisionPackage(date=date(2026, 1, 5))
    assert pkg.h_digest is None

    pkg2 = pkg.model_copy(update={"h_digest": harness_digest(_state())})
    assert pkg2.h_digest is not None and len(pkg2.h_digest) == 64

    # grep-level neutrality pin: eval scoring / loop drivers never READ h_digest. The field must be
    # DECLARED in alpha/eval/decision.py (that's where DecisionPackage itself lives, per
    # `grep -rn "class DecisionPackage" alpha/`) — so that one declaration line is the sole
    # permitted hit; every other file under alpha/eval (scorer/walk_forward/contribution/metrics/
    # oracle/...) and all of alpha/loop must have zero hits.
    result = subprocess.run(
        ["grep", "-rln", "h_digest", "alpha/eval", "alpha/loop"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    hit_files = {f for f in result.stdout.splitlines() if not f.endswith(".pyc")}
    assert hit_files == {"alpha/eval/decision.py"}, f"h_digest leaked beyond its own model file: {hit_files}"
