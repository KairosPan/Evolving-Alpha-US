from __future__ import annotations

import json
import shutil
import subprocess
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


def _default_runner(argv: "list[str]", stdin: str) -> str:
    """Shell out to the installed `claude` binary; return stdout, raise on non-zero exit."""
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}")
    return proc.stdout


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
                 sleep=None, runner=None, extra_args: "list[str] | None" = None) -> None:
        self.model = model
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep
        self._extra_args = list(extra_args) if extra_args else []
        if runner is not None:
            self._run = runner
        elif shutil.which("claude") is not None:
            self._run = _default_runner
        else:
            self._run = None            # claude CLI not installed (offline tests inject a runner)
        self.last_usage = None          # A6 metering side-channel: provider tokens of the last call

    def _argv(self, system: str) -> "list[str]":
        argv = ["claude", "-p", "--output-format", "json", "--model", self.model]
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
