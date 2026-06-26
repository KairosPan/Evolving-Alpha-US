from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    schema: dict
    fn: Callable[..., Any]


@dataclass
class ToolRegistry:
    """Name -> tool. Mirrors an OpenAI-function-calling registry; the B-WIDE loop dispatches by name."""
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, name: str, schema: dict, fn: Callable[..., Any]) -> None:
        self._tools[name] = Tool(name, schema, fn)

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name].fn(**kwargs)

    def specs(self) -> list[dict]:
        return [t.schema for t in self._tools.values()]
