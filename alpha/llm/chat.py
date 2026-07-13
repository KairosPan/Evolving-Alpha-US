from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from alpha.trace import MessageOrigin


class ChatMessage(BaseModel):
    """One turn in a multi-turn chat. Text-only (Sonia's copilot has no vision)."""
    role: str  # "user" | "assistant"
    text: str = ""
    # Principal-origin stamp (A4): set from the physical entry path, never inferred from content.
    # None = legacy/unstamped. A tool result re-injected as role="user" carries origin="tool", so it
    # is distinguishable from a model-authored "[tool:…]" string (which carries origin="model").
    origin: MessageOrigin | None = None


@runtime_checkable
class ChatLLMClient(Protocol):
    """Multi-turn chat: given a system prompt and prior turns, return the reply text."""
    def chat(self, system: str, messages: list[ChatMessage]) -> str: ...
