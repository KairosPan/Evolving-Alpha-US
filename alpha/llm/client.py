from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal LLM interface: given system/user prompts, return text (expected to be a JSON string)."""
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """Offline test client: replays scripted responses and records every (system, user) call."""

    def __init__(self, scripted: "str | list[str]") -> None:
        self._responses: list[str] = [scripted] if isinstance(scripted, str) else list(scripted)
        if not self._responses:
            raise ValueError("scripted must be non-empty")
        self._i = 0
        self.calls: list[tuple[str, str]] = []
        self.chat_calls: list = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r

    def chat(self, system: str, messages: list) -> str:
        self.chat_calls.append((system, list(messages)))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r
