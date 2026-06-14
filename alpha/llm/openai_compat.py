from __future__ import annotations

import os
import time


class OpenAICompatClient:
    """OpenAI-compatible client (DeepSeek by default; any base_url). Smoke-only for real calls.

    Retry/backoff on transient errors; re-raises after exhaustion (the caller/loop decides the
    no-trade fallback — this class does not swallow). `sleep` is injectable for offline tests.
    `model`/`temperature` are public for the (future) cache key.
    """

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 api_key_env: str = "DEEPSEEK_API_KEY", base_url: str = "https://api.deepseek.com",
                 temperature: float = 0.0, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"missing {api_key_env}")
        try:
            from openai import OpenAI  # lazy
            self._client = OpenAI(api_key=key, base_url=base_url)
        except ImportError:
            self._client = None        # openai not installed (offline tests inject _client)
        except Exception as e:         # SDK present but init failed (bad config) -> surface cleanly
            raise RuntimeError(f"OpenAI SDK init failed: {e}") from e
        self.model = model
        self.temperature = temperature
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("openai not installed (pip install openai)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=self.temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:           # noqa: BLE001 — transient (network/rate/5xx): back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover
