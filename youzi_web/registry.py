# youzi_web/registry.py
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class SubNavItem:
    label: str
    path: str
    enabled: bool = True          # False → 灰显占位("以后"的子页)


@dataclass(frozen=True)
class Feature:
    id: str                       # "research"
    label: str                    # "研究"
    icon: str                     # "📊"
    router: APIRouter
    subnav: list[SubNavItem] = field(default_factory=list)
