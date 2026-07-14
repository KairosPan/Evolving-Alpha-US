from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from alpha.llm.client import LLMClient, MockLLMClient

if TYPE_CHECKING:
    from alpha.llm.metering import SpendMeter

Role = Literal["agent", "refiner", "sonia", "converse"]

# (provider, model) defaults per role: ALL roles on Claude Fable 5 via the Claude Code CLI
# (`claude_code`), drawing on the operator's Pro/Max SUBSCRIPTION quota, not a metered API key.
# NOTE (time-sensitive): Fable 5 on subscription is a promotion capped at 50% of the weekly limit and
# scheduled to end 2026-07-19 — after that set ALPHA_<ROLE>_MODEL=claude-opus-4-8 (the durable
# subscription model) or point a role back at DeepSeek (ALPHA_<ROLE>_PROVIDER=openai_compat).
# Auth is ambient (Claude Code login / `claude setup-token`); the heavy batch roles (agent/refiner)
# burn subscription credit fastest, so dial them to openai_compat if quota is tight.
_DEFAULTS: dict[str, tuple[str, str]] = {
    "agent": ("claude_code", "claude-fable-5"),
    "refiner": ("claude_code", "claude-fable-5"),
    "sonia": ("claude_code", "claude-fable-5"),
    "converse": ("claude_code", "claude-fable-5"),
}


def make_client(role: Role, *, meter: "SpendMeter | None" = None) -> LLMClient:
    """Build the LLM client for a role from env (ALPHA_<ROLE>_PROVIDER / _MODEL). The console's
    entity switch (state/llm_stack.json, see alpha/llm/stack.py) sits between env and the defaults.

    providers: 'mock' (offline), 'claude_code' (ClaudeCodeClient — subscription quota via the Claude
    Code CLI, the default), 'anthropic' (ClaudeClient — metered API key), 'openai_compat'
    (OpenAICompatClient — DeepSeek etc.).
    temperature defaults to 0.0 (eval determinism); override with ALPHA_LLM_TEMPERATURE.

    meter (A6, charter *Resources as Security*): when a SpendMeter is passed, the raw client is wrapped
    so every call meters (token count × price) into it and a budget breach halts the run loudly.
    meter=None (the default) returns the raw client UNCHANGED — byte-identical, unmetered.
    """
    if role not in _DEFAULTS:
        raise ValueError(f"unknown role: {role!r} (expected one of {sorted(_DEFAULTS)})")
    def_provider, def_model = _DEFAULTS[role]
    # Three layers, resolved PER FIELD: explicit role env (expert escape hatch) > the entity's
    # named stack from the shared state file (the console switch) > _DEFAULTS.
    from alpha.llm.stack import resolve_stack
    stacked = resolve_stack(role)
    if stacked is not None:
        def_provider, def_model = stacked
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
    temperature = float(os.environ.get("ALPHA_LLM_TEMPERATURE", "0"))

    if provider == "mock":
        raw: LLMClient = MockLLMClient(os.environ.get("ALPHA_MOCK_RESPONSE", "{}"))
    elif provider == "claude_code":
        from alpha.llm.claude_code import ClaudeCodeClient
        raw = ClaudeCodeClient(model=model, temperature=temperature)
    elif provider == "anthropic":
        from alpha.llm.anthropic import ClaudeClient
        raw = ClaudeClient(model=model, temperature=temperature)
    elif provider == "openai_compat":
        from alpha.llm.openai_compat import OpenAICompatClient
        raw = OpenAICompatClient(model=model, temperature=temperature)
    else:
        raise ValueError(
            f"unknown provider: {provider!r} (expected mock|claude_code|anthropic|openai_compat)")
    return raw if meter is None else meter.wrap(raw, role=role)
