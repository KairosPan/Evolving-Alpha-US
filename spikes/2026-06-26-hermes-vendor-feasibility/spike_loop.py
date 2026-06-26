# spikes/2026-06-26-hermes-vendor-feasibility/spike_loop.py
"""A ~40-line tool registry + single-turn dispatch loop, mirroring Hermes's OpenAI-function-calling
contract (register a tool with a JSON schema; the model returns one tool call; dispatch it). This is
deliberately tiny: if Hermes's real tools/registry.py lifts cleanly (Task 2), swap this for it; if it
drags the monolith, this IS the fallback reimplementation."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Tool:
    name: str
    schema: dict
    fn: Callable[..., Any]

@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)
    def register(self, name: str, schema: dict, fn: Callable[..., Any]) -> None:
        self.tools[name] = Tool(name, schema, fn)
    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        return self.tools[name].fn(**kwargs)

def run_turn(registry: Registry, llm) -> Any:
    """One tool-calling turn. `llm.complete(system, user)` returns JSON {"tool": name, "args": {...}}."""
    call = json.loads(llm.complete("You may call one registered tool.", ""))
    return registry.call(call["tool"], **call.get("args", {}))
