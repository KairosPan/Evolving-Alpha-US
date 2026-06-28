# tests/arena/test_environment_local.py
from pathlib import Path
from alpha.arena.environment import LocalEnv


def test_local_runs_harmless_command(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["python", "-c", "print('hello')"])
    assert r.ok and "hello" in r.stdout and r.exit_code == 0


def test_local_blocks_hardline_command(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["rm", "-rf", "/"])
    assert r.ok is False
    assert "blocked" in r.stderr.lower()


def test_local_blocks_path_escape_above_workspace(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    # an absolute path operand outside the workspace is refused before exec
    r = env.run(["cat", "/etc/passwd"])
    assert r.ok is False
    assert "outside workspace" in r.stderr.lower()


def test_local_times_out(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["python", "-c", "import time; time.sleep(5)"], timeout=0.3)
    assert r.ok is False
    assert "timeout" in r.stderr.lower()
