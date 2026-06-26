import subprocess
from datetime import date

import pytest

from alpha.eval.decision import DecisionPackage
from alpha.converse.workspace import Workspace


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def test_init_and_commit_artifact(tmp_path):
    ws = Workspace(tmp_path)
    ws.init()
    assert (tmp_path / ".git").exists()
    ws.init()  # idempotent: second init is a no-op
    sha = ws.commit_artifact("note.md", "hello", "add note")
    assert sha and "note.md" in _git(["ls-files"], tmp_path)


def test_put_decision_writes_and_commits_typed_artifact(tmp_path):
    ws = Workspace(tmp_path)
    ws.init()
    pkg = DecisionPackage(date=date(2026, 6, 12), regime_read="trend frontside")
    ws.put_decision(pkg)
    written = (tmp_path / "2026-06-12.json").read_text()
    assert DecisionPackage.model_validate_json(written) == pkg
    assert "2026-06-12.json" in _git(["ls-files"], tmp_path)


def test_traversal_guard(tmp_path):
    ws = Workspace(tmp_path)
    ws.init()
    with pytest.raises(ValueError):
        ws.commit_artifact("../escape.txt", "x", "m")
