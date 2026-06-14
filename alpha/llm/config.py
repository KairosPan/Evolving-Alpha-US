from __future__ import annotations

import os
from typing import Literal

from alpha.llm.client import LLMClient, MockLLMClient

Role = Literal["agent", "refiner"]

# (provider, model) defaults per role: agent cheap (many rollouts), refiner Claude (edits H).
_DEFAULTS: dict[str, tuple[str, str]] = {
    "agent": ("openai_compat", "deepseek-chat"),
    "refiner": ("anthropic", "claude-sonnet-4-6"),
}


def make_client(role: Role) -> LLMClient:
    """Build the LLM client for a role from env (ALPHA_<ROLE>_PROVIDER / _MODEL).

    providers: 'mock' (offline), 'anthropic' (ClaudeClient), 'openai_compat' (OpenAICompatClient).
    temperature defaults to 0.0 (eval determinism); override with ALPHA_LLM_TEMPERATURE.
    """
    if role not in _DEFAULTS:
        raise ValueError(f"unknown role: {role!r} (expected one of {sorted(_DEFAULTS)})")
    def_provider, def_model = _DEFAULTS[role]
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
    temperature = float(os.environ.get("ALPHA_LLM_TEMPERATURE", "0"))

    if provider == "mock":
        return MockLLMClient(os.environ.get("ALPHA_MOCK_RESPONSE", "{}"))
    if provider == "anthropic":
        from alpha.llm.anthropic import ClaudeClient
        return ClaudeClient(model=model, temperature=temperature)
    if provider == "openai_compat":
        from alpha.llm.openai_compat import OpenAICompatClient
        return OpenAICompatClient(model=model, temperature=temperature)
    raise ValueError(f"unknown provider: {provider!r} (expected mock|anthropic|openai_compat)")
