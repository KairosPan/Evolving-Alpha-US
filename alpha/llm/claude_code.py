from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time

from alpha.llm.metering import Usage


def _usage_from_claude_code(env) -> "Usage | None":
    """Normalize the `usage` object of a `claude -p --output-format json` envelope → Usage, or None.

    Claude Code reports subscription usage as input_tokens/output_tokens (+ cache fields we fold into
    input, matching how the API bills them). Metering is only a NOTIONAL ceiling here — subscription
    calls are not billed per-token — but keeping last_usage populated keeps the SpendMeter wrapper
    working unchanged (charter *Resources as Security*)."""
    if not isinstance(env, dict):
        return None
    u = env.get("usage")
    if not isinstance(u, dict):
        return None
    tin, tout = u.get("input_tokens"), u.get("output_tokens")
    if tin is None or tout is None:
        return None
    tin = int(tin) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
    return Usage(tokens_in=tin, tokens_out=int(tout))


def _default_runner(argv: "list[str]", stdin: str, timeout: "float | None" = None,
                    cwd: "str | None" = None) -> str:
    """Shell out to the installed `claude` binary; return stdout, raise on non-zero exit.

    `timeout` (seconds) caps the spawn so a hung `claude` cannot block the role forever —
    subprocess.run raises subprocess.TimeoutExpired, which _invoke's broad except turns into a
    retry/backoff and finally a raise. None = no cap (only injected runners pass None).
    `cwd` is the NEUTRAL execution surface (see _neutral_cwd): never the service's repo root."""
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout,
                          cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}")
    return proc.stdout


# Neutral execution surface. A pure-completion call must not carry Claude Code's ambient repo
# context (CLAUDE.md, .claude/settings.json — quota burn + prompt contamination) nor its headless
# tool surface (auto-allowed read-only tools could pull local files into the prompt under
# injection). extra_args stays the operator override seam — it is appended AFTER these, and later
# flags win in the claude CLI.
_NEUTRAL_DISALLOWED_TOOLS = ("Bash,Edit,Write,NotebookEdit,Read,Glob,Grep,"
                             "WebFetch,WebSearch,Task,TodoWrite")


_NEUTRAL_CWD: "str | None" = None


def _neutral_cwd() -> str:
    """An empty, PRIVATE directory for the `claude -p` spawn, so no project CLAUDE.md or
    .claude/settings.json is loaded (the CLI walks cwd upward; tmp's parents carry none).

    mkdtemp (unpredictable name, mode 0700, empty by construction), cached per process — a fixed
    shared path like /tmp/alpha-claude-neutral would be squattable by another local user, who
    could pre-seed it with a hostile CLAUDE.md and reopen the very injection surface this closes
    (commit security-review finding). One dir per process; OS tmp reapers collect them."""
    global _NEUTRAL_CWD
    if _NEUTRAL_CWD is None or not os.path.isdir(_NEUTRAL_CWD):
        _NEUTRAL_CWD = tempfile.mkdtemp(prefix="alpha-claude-neutral-")
    return _NEUTRAL_CWD


def _flatten_chat(messages) -> str:
    """Serialize a multi-turn history into one prompt. `claude -p` is single-shot (stateless), so —
    like the openai_compat client resending the full message list — each call carries the whole
    conversation, here as labeled turns."""
    lines = []
    for m in messages:
        label = "Assistant" if getattr(m, "role", "") == "assistant" else "User"
        lines.append(f"{label}: {getattr(m, 'text', '')}")
    return "\n\n".join(lines)


class ClaudeCodeClient:
    """Claude via the headless Claude Code CLI (`claude -p`), drawing on your Pro/Max SUBSCRIPTION
    quota rather than a metered API key — the officially-sanctioned personal-use path for running a
    harness on subscription credit (Agent SDK / `claude -p`, NOT the raw Messages API, which rejects
    subscription OAuth tokens). Smoke-only for real calls; retry/backoff; injectable runner.

    Auth is ambient: Claude Code owns the credentials (interactive `claude /login`, or a
    `claude setup-token` → CLAUDE_CODE_OAUTH_TOKEN). This client stores no key; it shells out.
    GOTCHA: a set ANTHROPIC_API_KEY silently overrides the subscription login and bills the API —
    unset it to stay on subscription quota.

    No OpenAI-style json_object mode: the caller's system prompt asks for raw JSON and the agent's
    extractor pulls the balanced object (same contract as the other providers). `model`/`temperature`
    are public for the cache key; `temperature` is NOT sent (Claude Code owns sampling, and
    Fable 5 / Opus 4.7+ reject an explicit temperature)."""

    def __init__(self, model: str = "claude-fable-5", temperature: float = 0.0,
                 max_tokens: int = 4096, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None, runner=None, extra_args: "list[str] | None" = None,
                 timeout: float = 600.0) -> None:
        self.model = model
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep
        self._extra_args = list(extra_args) if extra_args else []
        if runner is not None:
            self._run = runner          # injected runner owns its own timeout semantics
        elif shutil.which("claude") is not None:
            # Bind the per-call timeout (default 600s, matching the Anthropic SDK) so a hung `claude`
            # spawn can't block the role forever, and the neutral cwd so the spawn never inherits the
            # service's repo root. `_default_runner` is looked up as a module global at CALL time, so
            # tests may monkeypatch it.
            cwd = _neutral_cwd()
            self._run = lambda argv, stdin: _default_runner(argv, stdin, timeout=timeout, cwd=cwd)
        else:
            self._run = None            # claude CLI not installed (offline tests inject a runner)
        self.last_usage = None          # A6 metering side-channel: provider tokens of the last call

    def _argv(self, system: str) -> "list[str]":
        argv = ["claude", "-p", "--output-format", "json", "--model", self.model,
                "--disallowedTools", _NEUTRAL_DISALLOWED_TOOLS]
        if system:
            argv += ["--append-system-prompt", system]
        return argv + self._extra_args

    def _invoke(self, system: str, prompt: str) -> str:
        if self._run is None:
            raise RuntimeError(
                "claude CLI not installed (npm i -g @anthropic-ai/claude-code; then `claude /login` "
                "or `claude setup-token` for CLAUDE_CODE_OAUTH_TOKEN)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                raw = self._run(self._argv(system), prompt)
                env = json.loads(raw) if raw else {}
                self.last_usage = _usage_from_claude_code(env)
                text = env.get("result")
                if text is None:
                    raise RuntimeError(f"claude -p returned no `result` field: {str(env)[:300]}")
                return text
            except Exception as e:           # noqa: BLE001 — transient (spawn/parse/rate): back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover

    def complete(self, system: str, user: str) -> str:
        return self._invoke(system, user)

    def chat(self, system: str, messages: list) -> str:
        return self._invoke(system, _flatten_chat(messages))
