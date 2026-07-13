from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from alpha.llm.client import LLMClient, MockLLMClient

if TYPE_CHECKING:
    from alpha.llm.metering import SpendMeter

Role = Literal["agent", "refiner", "sonia", "converse"]

# (provider, model) defaults per role: ALL roles on DeepSeek deepseek-v4-pro (openai_compat).
# NOTE: `deepseek-v4-pro` is the intended model NAME; if the live API rejects it as an unknown id,
# override per role at runtime (e.g. ALPHA_AGENT_MODEL=deepseek-chat) — any OpenAI-compatible id works.
_DEFAULTS: dict[str, tuple[str, str]] = {
    "agent": ("openai_compat", "deepseek-v4-pro"),
    "refiner": ("openai_compat", "deepseek-v4-pro"),
    "sonia": ("openai_compat", "deepseek-v4-pro"),
    "converse": ("openai_compat", "deepseek-v4-pro"),
}


def make_client(role: Role, *, meter: "SpendMeter | None" = None) -> LLMClient:
    """Build the LLM client for a role from env (ALPHA_<ROLE>_PROVIDER / _MODEL).

    providers: 'mock' (offline), 'anthropic' (ClaudeClient), 'openai_compat' (OpenAICompatClient).
    temperature defaults to 0.0 (eval determinism); override with ALPHA_LLM_TEMPERATURE.

    meter (A6, charter *Resources as Security*): when a SpendMeter is passed, the raw client is wrapped
    so every call meters (token count × price) into it and a budget breach halts the run loudly.
    meter=None (the default) returns the raw client UNCHANGED — byte-identical, unmetered.
    """
    if role not in _DEFAULTS:
        raise ValueError(f"unknown role: {role!r} (expected one of {sorted(_DEFAULTS)})")
    def_provider, def_model = _DEFAULTS[role]
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
    temperature = float(os.environ.get("ALPHA_LLM_TEMPERATURE", "0"))

    if provider == "mock":
        raw: LLMClient = MockLLMClient(os.environ.get("ALPHA_MOCK_RESPONSE", "{}"))
    elif provider == "anthropic":
        from alpha.llm.anthropic import ClaudeClient
        raw = ClaudeClient(model=model, temperature=temperature)
    elif provider == "openai_compat":
        from alpha.llm.openai_compat import OpenAICompatClient
        raw = OpenAICompatClient(model=model, temperature=temperature)
    else:
        raise ValueError(f"unknown provider: {provider!r} (expected mock|anthropic|openai_compat)")
    return raw if meter is None else meter.wrap(raw, role=role)
