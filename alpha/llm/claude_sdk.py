from __future__ import annotations

import asyncio
import time

from alpha.llm.claude_code import _flatten_chat, _usage_from_claude_code


class ClaudeSdkClient:
    """Claude via the Claude Agent SDK (`claude-agent-sdk`), drawing on your Pro/Max SUBSCRIPTION
    quota — the officially-sanctioned personal-use path, same as the `claude -p` provider it
    supersedes as the default. The SDK spawns the same Claude Code runtime, but Anthropic
    maintains the isolation defaults for us: `setting_sources=None` loads NO filesystem settings
    (no repo CLAUDE.md / .claude/settings.json in the prompt — no neutral-cwd hack needed), and
    `tools=[]` + `max_turns=1` make each call a pure, loop-free completion.

    Auth is ambient: the Claude Code credential store (`claude /login`) or a `claude setup-token`
    → CLAUDE_CODE_OAUTH_TOKEN. This client stores no key. GOTCHA: a set ANTHROPIC_API_KEY
    silently overrides the subscription login and bills the metered API — unset it.

    Sync-seam adapter: `query()` is async-only, so each call runs under its own event loop via
    asyncio.run (the FastAPI faces call from sync handlers on worker threads — no running loop).
    `timeout` (seconds) caps a call via asyncio.wait_for; TimeoutError enters the retry path.
    No OpenAI-style json_object mode: the caller's system prompt asks for raw JSON and the
    agent's extractor pulls the balanced object. `model`/`temperature` are public for the cache
    key; `temperature` is NOT sent (the runtime owns sampling; Fable 5 / Opus 4.7+ reject it)."""

    def __init__(self, model: str = "claude-fable-5", temperature: float = 0.0,
                 max_tokens: int = 4096, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None, timeout: float = 600.0, query_fn=None) -> None:
        self.model = model
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep
        self._timeout = timeout
        if query_fn is not None:
            self._query = query_fn
        else:
            try:
                from claude_agent_sdk import query  # lazy
                self._query = query
            except ImportError:
                self._query = None      # sdk not installed (offline tests inject query_fn)
        self.last_usage = None          # A6 metering side-channel: provider tokens of the last call

    def _options(self, system: str):
        from claude_agent_sdk import ClaudeAgentOptions  # lazy — reached only with the sdk present
        return ClaudeAgentOptions(
            system_prompt=system or None,
            model=self.model,
            tools=[],                    # disable ALL built-in tools: pure completion
            max_turns=1,                 # no agent loop
            setting_sources=None,        # SDK default, pinned: load NO CLAUDE.md / settings
        )

    async def _acall(self, system: str, prompt: str) -> str:
        async def _collect() -> str:
            result = None
            async for message in self._query(prompt=prompt, options=self._options(system)):
                if type(message).__name__ == "ResultMessage":
                    result = message
            if result is None:
                raise RuntimeError("claude-agent-sdk stream ended with no ResultMessage")
            self.last_usage = _usage_from_claude_code({"usage": result.usage})
            if result.is_error:
                raise RuntimeError(
                    f"claude-agent-sdk error result ({result.subtype}): {str(result.result)[:300]}")
            if result.result is None:
                raise RuntimeError("claude-agent-sdk ResultMessage carries no result text")
            return result.result
        return await asyncio.wait_for(_collect(), timeout=self._timeout)

    def _invoke(self, system: str, prompt: str) -> str:
        if self._query is None:
            raise RuntimeError("claude-agent-sdk not installed (pip install claude-agent-sdk; "
                               "then `claude /login` or CLAUDE_CODE_OAUTH_TOKEN)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return asyncio.run(self._acall(system, prompt))
            except Exception as e:           # noqa: BLE001 — transient (spawn/timeout/rate): back off
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
