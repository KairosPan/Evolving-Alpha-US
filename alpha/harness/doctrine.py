# alpha/harness/doctrine.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.errors import ImmutableDoctrineError
from alpha.harness.regime import is_family, normalize_phases


class DoctrineEntry(BaseModel):
    """A p doctrine entry (mutable; immutable=True = a discipline red-line, write-protected)."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    section: str
    phases: list[str] = Field(default_factory=list)
    applies_all_phases: bool = False
    family: str | None = None
    immutable: bool = False
    guidance: str

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        phases, applies_all = normalize_phases(d.get("phases", d.get("regime", [])))
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)

    def __setattr__(self, name: str, value: object) -> None:
        # Construction writes __dict__ directly (not via this path); this only blocks
        # post-construction edits to a discipline red-line.
        if self.__dict__.get("immutable", False):
            raise ImmutableDoctrineError(f"immutable doctrine entry cannot be modified (field {name})")
        super().__setattr__(name, value)


class Doctrine(BaseModel):
    """Doctrine container (read/query only here; CRUD is US-1b)."""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "Doctrine":
        return cls(entries=[DoctrineEntry.from_seed(d) for d in items])

    def get(self, section: str) -> DoctrineEntry | None:
        return next((e for e in self.entries if e.section == section), None)

    def for_phase(self, phase: str) -> list[DoctrineEntry]:
        return [e for e in self.entries if phase in e.phases or e.applies_all_phases]

    def immutable_core(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if e.immutable]

    def mutable_entries(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if not e.immutable]

    # ── CRUD (US-1b; immutable-protected) ─────────────────────────────────
    def add(self, entry: DoctrineEntry) -> None:
        if self.get(entry.section) is not None:
            raise ValueError(f"duplicate section: {entry.section}")
        self.entries.append(entry)

    def rewrite(self, section: str, new_guidance: str) -> DoctrineEntry:
        e = self.get(section)
        if e is None:
            raise KeyError(f"no such section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"immutable doctrine cannot be rewritten: {section}")
        e.guidance = new_guidance
        return e

    def remove(self, section: str) -> None:
        e = self.get(section)
        if e is None:
            raise KeyError(f"no such section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"immutable doctrine cannot be removed: {section}")
        self.entries.remove(e)
