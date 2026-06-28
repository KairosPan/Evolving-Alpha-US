from alpha.arena.contract import ExecResult
from alpha.arena.environment import InProcessEnv, ToolEnvironment


def test_inprocess_is_a_tool_environment():
    env = InProcessEnv()
    assert isinstance(env, ToolEnvironment)


def test_inprocess_refuses_to_execute():
    env = InProcessEnv()
    r = env.run(["echo", "hi"])
    assert isinstance(r, ExecResult)
    assert r.ok is False
    assert "disabled" in r.stderr.lower()
