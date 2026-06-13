from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """最小 LLM 接口:给系统/用户提示,返回文本(期望是 JSON 字符串)。"""
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """离线测试用:返回脚本化响应,并记录每次 (system, user) 调用。"""

    def __init__(self, scripted: "str | list[str]") -> None:
        self._responses: list[str] = [scripted] if isinstance(scripted, str) else list(scripted)
        if not self._responses:
            raise ValueError("scripted 不能为空")
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r


class DeepSeekClient:
    """DeepSeek(OpenAI 兼容)。lazy import openai;实盘/smoke 用,测试不触达。

    带 retry/backoff:网络/限流/5xx 等异常时指数退避重试;耗尽仍失败则向上抛
    (由 1b-3 编排或 LLMAgentPolicy 决定空仓兜底,本类不吞异常)。sleep 可注入便于测试。
    """

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com", temperature: float = 0.3,
                 max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        import time
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        try:
            from openai import OpenAI  # lazy
            self._client = OpenAI(api_key=key, base_url=base_url)
        except ImportError:
            self._client = None  # openai 未安装(离线测试会注入 _client)
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        if self._client is None:                 # openai 未安装:立即清晰报错,不浪费重试退避
            raise RuntimeError("openai 未安装(pip install openai),无法调用 DeepSeek")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=self._temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:           # noqa: BLE001 — 网络/限流/5xx 皆重试
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover — 循环必 return 或 raise
