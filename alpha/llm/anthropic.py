from __future__ import annotations

import os
import time


class ClaudeClient:
    """Anthropic Claude client. Smoke-only for real calls; retry/backoff; injectable transport.

    Claude has no OpenAI-style json_object mode, so the system prompt asks for raw JSON and the
    agent's extractor pulls the balanced object. `model`/`temperature` are public for the cache key.
    """

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None,
                 api_key_env: str = "ANTHROPIC_API_KEY", temperature: float = 0.0,
                 max_tokens: int = 4096, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"missing {api_key_env}")
        try:
            import anthropic  # lazy
            self._client = anthropic.Anthropic(api_key=key)
        except ImportError:
            self._client = None        # anthropic not installed (offline tests inject _client)
        except Exception as e:         # SDK present but init failed (bad config) -> surface cleanly
            raise RuntimeError(f"anthropic SDK init failed: {e}") from e
        self.model = model
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("anthropic not installed (pip install anthropic)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                msg = self._client.messages.create(
                    model=self.model, max_tokens=self._max_tokens, temperature=self.temperature,
                    system=system, messages=[{"role": "user", "content": user}],
                )
                parts = [b.text for b in msg.content if getattr(b, "text", None)]
                return "".join(parts)
            except Exception as e:           # noqa: BLE001 — transient: back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover
