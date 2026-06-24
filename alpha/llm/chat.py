from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """One turn in a multi-turn chat. Text-only (Sonia's copilot has no vision)."""
    role: str  # "user" | "assistant"
    text: str = ""


@runtime_checkable
class ChatLLMClient(Protocol):
    """Multi-turn chat: given a system prompt and prior turns, return the reply text."""
    def chat(self, system: str, messages: list[ChatMessage]) -> str: ...
