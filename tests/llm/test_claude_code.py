import json

import pytest

from alpha.llm.chat import ChatMessage
from alpha.llm.claude_code import ClaudeCodeClient


class _FakeRunner:
    """Records (argv, stdin) and returns a canned `claude -p --output-format json` envelope; fails
    the first `fail_n` calls to exercise retry/backoff."""

    def __init__(self, result="{\"ok\": 1}", usage=None, fail_n=0):
        env = {"type": "result", "subtype": "success", "result": result}
        if usage is not None:
            env["usage"] = usage
        self._stdout = json.dumps(env)
        self._fail_n = fail_n
        self.calls: list[tuple[list, str]] = []

    def __call__(self, argv, stdin):
        self.calls.append((list(argv), stdin))
        if len(self.calls) <= self._fail_n:
            raise RuntimeError("spawn failed")
        return self._stdout


def _client(runner, sleeps=None, **kw):
    return ClaudeCodeClient(model="claude-fable-5", backoff=0.0,
                            sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
                            runner=runner, **kw)


def test_returns_result_text():
    assert _client(_FakeRunner('{"ok": 1}')).complete("s", "u") == '{"ok": 1}'


def test_prompt_goes_to_stdin_not_argv():
    r = _FakeRunner()
    _client(r).complete("SYS", "the user prompt")
    argv, stdin = r.calls[0]
    assert stdin == "the user prompt"           # user prompt piped via stdin, never an argv token
    assert "the user prompt" not in argv


def test_argv_carries_model_system_and_json_format():
    r = _FakeRunner()
    _client(r).complete("SYS PROMPT", "u")
    argv = r.calls[0][0]
    assert argv[:2] == ["claude", "-p"]
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "--model" in argv and argv[argv.index("--model") + 1] == "claude-fable-5"
    assert "--append-system-prompt" in argv and argv[argv.index("--append-system-prompt") + 1] == "SYS PROMPT"


def test_no_system_prompt_omits_append_flag():
    r = _FakeRunner()
    _client(r).complete("", "u")
    assert "--append-system-prompt" not in r.calls[0][0]


def test_temperature_is_not_sent():
    r = _FakeRunner()
    ClaudeCodeClient(model="claude-fable-5", temperature=0.7, runner=r).complete("s", "u")
    assert "--temperature" not in r.calls[0][0]      # Claude Code owns sampling; Fable 5 rejects it


def test_captures_provider_usage_when_present():
    from alpha.llm.metering import Usage
    c = _client(_FakeRunner('{"ok": 1}', usage={"input_tokens": 20, "output_tokens": 8}))
    c.complete("s", "u")
    assert c.last_usage == Usage(tokens_in=20, tokens_out=8)


def test_usage_folds_cache_tokens_into_input():
    from alpha.llm.metering import Usage
    c = _client(_FakeRunner('{"ok": 1}', usage={
        "input_tokens": 20, "output_tokens": 8,
        "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5}))
    c.complete("s", "u")
    assert c.last_usage == Usage(tokens_in=125, tokens_out=8)


def test_last_usage_none_when_envelope_omits_usage():
    c = _client(_FakeRunner('{"ok": 1}'))          # no usage field
    c.complete("s", "u")
    assert c.last_usage is None


def test_retries_then_succeeds():
    r = _FakeRunner('{"ok": 1}', fail_n=2)
    sleeps: list = []
    assert _client(r, sleeps).complete("s", "u") == '{"ok": 1}'
    assert len(r.calls) == 3 and len(sleeps) == 2


def test_raises_after_exhaustion():
    with pytest.raises(RuntimeError):
        _client(_FakeRunner(fail_n=99)).complete("s", "u")


def test_missing_result_field_raises():
    def runner(argv, stdin):
        return json.dumps({"type": "result", "subtype": "error_max_turns"})   # no `result`
    with pytest.raises(RuntimeError):
        _client(runner).complete("s", "u")


def test_chat_flattens_history_into_one_prompt():
    r = _FakeRunner("the reply")
    out = _client(r).chat("SYS", [ChatMessage(role="user", text="hello"),
                                  ChatMessage(role="assistant", text="hi"),
                                  ChatMessage(role="user", text="more")])
    assert out == "the reply"
    stdin = r.calls[0][1]
    assert stdin == "User: hello\n\nAssistant: hi\n\nUser: more"
    assert r.calls[0][0][argv_i := r.calls[0][0].index("--append-system-prompt") + 1] == "SYS"


def test_missing_cli_raises_on_call(monkeypatch):
    import alpha.llm.claude_code as mod
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)   # simulate `claude` not installed
    c = ClaudeCodeClient(model="claude-fable-5")                   # runner=None -> _run stays None
    assert c._run is None
    with pytest.raises(RuntimeError, match="claude CLI not installed"):
        c.complete("s", "u")


def test_exposes_model_and_temperature():
    c = ClaudeCodeClient(model="claude-fable-5", temperature=0.0, runner=_FakeRunner())
    assert c.model == "claude-fable-5" and c.temperature == 0.0


def test_argv_disallows_the_tool_surface():
    # Neutral execution surface: a pure-completion call must not expose Claude Code's headless
    # tool surface (auto-allowed read-only tools could pull local files into the prompt).
    r = _FakeRunner()
    _client(r).complete("s", "u")
    argv = r.calls[0][0]
    assert "--disallowedTools" in argv
    spec = argv[argv.index("--disallowedTools") + 1]
    for tool in ("Read", "Glob", "Grep", "Bash", "Edit", "Write", "WebFetch", "WebSearch", "Task"):
        assert tool in spec


def test_extra_args_come_after_the_default_hardening():
    # extra_args stays the operator override seam: later flags win in the claude CLI.
    r = _FakeRunner()
    ClaudeCodeClient(model="claude-fable-5", runner=r,
                     extra_args=["--allowedTools", "WebSearch"]).complete("s", "u")
    argv = r.calls[0][0]
    assert argv.index("--disallowedTools") < argv.index("--allowedTools")


def test_default_runner_accepts_cwd(tmp_path):
    from alpha.llm.claude_code import _default_runner
    out = _default_runner(["pwd"], "", timeout=10, cwd=str(tmp_path))
    assert out.strip() == str(tmp_path)


def test_neutral_cwd_bound_into_default_runner(monkeypatch, tmp_path):
    # The spawn must NOT inherit the service's cwd (the repo root), or `claude -p` loads this
    # repo's CLAUDE.md + .claude/settings.json into every LLM call.
    import alpha.llm.claude_code as mod
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/claude")
    seen = {}
    def fake_runner(argv, stdin, timeout=None, cwd=None):
        seen["cwd"] = cwd
        return '{"result": "ok"}'
    monkeypatch.setattr(mod, "_default_runner", fake_runner)
    mod.ClaudeCodeClient(model="claude-fable-5").complete("s", "u")
    import os
    assert seen["cwd"] is not None and os.path.isdir(seen["cwd"])
    assert os.path.realpath(seen["cwd"]) != os.path.realpath(os.getcwd())
    assert not os.path.exists(os.path.join(seen["cwd"], "CLAUDE.md"))


def test_neutral_cwd_is_private_unpredictable_and_cached():
    # Security (commit review finding): a PREDICTABLE shared tmp path (/tmp/alpha-claude-neutral)
    # can be pre-created by another local user with a hostile CLAUDE.md inside — reopening the
    # injection surface the neutral cwd exists to close. Must be mkdtemp-style: unpredictable
    # name, owner-only mode, empty by construction, and cached per process (no per-call litter).
    import os
    import stat
    import tempfile
    from alpha.llm.claude_code import _neutral_cwd
    d = _neutral_cwd()
    assert d == _neutral_cwd()                                     # cached: one dir per process
    assert os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()))
    assert os.path.basename(d) != "alpha-claude-neutral"           # not the predictable fixed name
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700               # owner-only (mkdtemp default)
    assert os.listdir(d) == []                                     # empty — nothing to load


def test_default_runner_times_out():
    import subprocess
    from alpha.llm.claude_code import _default_runner
    with pytest.raises(subprocess.TimeoutExpired):
        _default_runner(["sleep", "5"], "", timeout=0.1)   # offline: no claude needed


def test_timeout_is_bound_into_default_runner(monkeypatch):
    import alpha.llm.claude_code as mod
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/claude")
    seen = {}
    def fake_runner(argv, stdin, timeout=None, cwd=None):
        seen["timeout"] = timeout
        return '{"result": "ok"}'
    monkeypatch.setattr(mod, "_default_runner", fake_runner)
    c = mod.ClaudeCodeClient(model="claude-fable-5", timeout=42.0)
    assert c.complete("s", "u") == "ok"
    assert seen["timeout"] == 42.0
