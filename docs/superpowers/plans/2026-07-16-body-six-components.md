# Completing the Body: H=(p,K,M,C,W,A) + Sonia observe loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three declared-but-stubbed Brain components — connector (C), workflow (W), subagent (A) — as real, gated parts of H, plus a fail-closed observe-tier tool loop for Sonia (market visibility gated by the alpaca connector + two-tier disclosure over the brain).

**Architecture:** One shared integration pattern stamped three times: a Pydantic entry model + a plain-dict registry, an additive defaulted `HarnessState` field (serialized inside brain.json's `harness` sub-dict via `to_dict`/`from_dict`), three write-waist ops under new PASS_TOOLS passes with structural lints, the `extract_ops` vocabulary + `render_brain_summary` index, a real console page, and a seed. Then Sonia's `respond()` reroutes through the existing `run_conversation` loop with a T0-only `ActivityPolicy`.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI+Jinja2 (`web`/`sonia` extras), pytest (offline).

**Spec:** `docs/superpowers/specs/2026-07-16-body-six-components-design.md`. **Grounding (exact current code):** `.superpowers/sdd/grounding-six-components.md` — the implementer should read the relevant grounding facts named in each task.

## Global Constraints

- **House style** for all three entry models: `model_config = ConfigDict(extra="forbid", validate_assignment=True)`; `Literal` enums; `Field(default_factory=...)` for collections; `domain: Literal["trading","operational"]`; `scope: Scope = DEFAULT_SCOPE` (import from `alpha.harness.scope`). Mirror `alpha/harness/skill.py`.
- **`HarnessState` is a `@dataclass`, NOT Pydantic.** New fields MUST be defaulted (`field(default_factory=Registry.empty)`) and come after `vocabulary` — 54 test files construct `HarnessState(doctrine=..., skills=..., memory=...)` kwargs-only.
- **brain.json shape choke point is `HarnessState.to_dict`/`from_dict` only.** New lists dump `model_dump(mode="json")`; read via `d.get("connectors", [])` (legacy/corrupt dumps → empty registry, never KeyError). LiveBrainStore / SnapshotStore / GitBodyStore need ZERO changes.
- **One waist:** every C/W/A edit goes through `alpha/refine/apply.py::try_apply_op` with the SAME provenance/governance (worker-propose refusal, user_direct handling, conflict holds). No second gate.
- **New PASS_TOOLS passes:** add `PassKind` values `"C"`,`"W"`,`"A"`; `PASS_ORDER = ("p","G","K","M","C","W","A")`; `PASS_TOOLS["G"]` stays `frozenset()` (test-pinned reserved). `PASS_TOOLS["C"]={"write_connector","patch_connector","disable_connector"}`, `["W"]={"write_workflow","patch_workflow","retire_workflow"}`, `["A"]={"write_subagent","patch_subagent","retire_subagent"}`. `ALL_TOOLS` derives from `PASS_TOOLS`, and `teach_scope("sonia")==ALL_TOOLS`, so the teach chain gains the ops for free.
- **No delete ops** (mirrors doctrine's no-destroy bias): create=`write_*`, mutate=`patch_*`, soft-remove=`disable_connector`/`retire_workflow`/`retire_subagent`.
- **Entries carry NO URLs, NO credential values, NO executable content.** `impl_ref` is a registry key; `env_keys` are env-var NAMES only (value-shaped strings refused at the waist).
- **Subagent execution stays deferred** — `PASS_TOOLS["G"]` reserved-empty; entries are dispatch-READY state, dispatch is a later arc. `PASS_ORDER`/`PASS_TOOLS["G"]` pins in `tests/refine/test_ops.py` change WITH this plan.
- **Seed files `connectors.json`/`workflows.json`/`subagents.json` are OPTIONAL** — the loader returns `[]` on a missing file (do NOT make them required, or 54 fixtures + test_loader break).
- **Verdict symmetry untouched:** `decide()`'s prompt (`alpha/agent/prompt.py`) keeps its full always-in-prompt render. Two-tier disclosure is Sonia-chat only. `extract_ops` keeps full render (the op-writer must diff against exact current text).
- **Offline tests only.** Face-touching tests outside `tests/web|sonia|workbench` must request `brain_session_isolation` explicitly.
- **Commits:** message to a file, `git commit -F <file>` (never `-m` with backticks/parens).

---

### Task 1: ConnectorEntry + ConnectorRegistry + HarnessState integration

**Files:**
- Create: `alpha/harness/connectors.py`
- Modify: `alpha/harness/state.py` (imports, `connectors` field, `to_dict`, `from_dict`)
- Test: `tests/harness/test_connectors.py`, and extend `tests/harness/test_state.py`

**Interfaces:**
- Consumes: `alpha.harness.scope.{Scope, DEFAULT_SCOPE}` (existing); `HarnessState` (`@dataclass`).
- Produces (Tasks 2/3/8 rely on these exact names):
  - `ConnectorEntry` (Pydantic) fields: `connector_id, name, kind: Literal["data_source","llm_role","mcp"], impl_ref, capabilities: list[str], env_keys: list[str], instructions, pit_key: str = "", enabled: bool = True, required: bool = False, tier: str = "T0_OBSERVE", domain: Literal["trading","operational"] = "trading", scope: Scope = DEFAULT_SCOPE, notes: str = ""`
  - `ConnectorRegistry`: `empty()` classmethod, `from_connectors(list)` (dup-id ValueError), `get(connector_id) -> ConnectorEntry | None`, `all() -> list[ConnectorEntry]`, `upsert(entry)`, `__len__`, `__bool__` (always True)
  - `HarnessState.connectors: ConnectorRegistry`

- [ ] **Step 1: Write the failing tests** — create `tests/harness/test_connectors.py`:

```python
import pytest
from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry


def _entry(cid="alpaca", **kw):
    base = dict(connector_id=cid, name="Alpaca", kind="data_source", impl_ref="alpaca",
                capabilities=["bars", "snapshots"], env_keys=["APCA_API_KEY_ID"],
                instructions="US equities bars/snapshots.", pit_key="announce_date:=process_date")
    base.update(kw)
    return ConnectorEntry(**base)


def test_entry_rejects_unknown_field():
    with pytest.raises(Exception):
        ConnectorEntry(connector_id="x", name="X", kind="data_source", impl_ref="alpaca",
                       capabilities=[], env_keys=[], instructions="", bogus=1)


def test_entry_defaults():
    e = _entry()
    assert e.enabled is True and e.required is False and e.tier == "T0_OBSERVE"
    assert e.domain == "trading" and e.notes == ""


def test_registry_dup_id_raises():
    with pytest.raises(ValueError):
        ConnectorRegistry.from_connectors([_entry(), _entry()])


def test_registry_get_all_len_bool():
    r = ConnectorRegistry.from_connectors([_entry()])
    assert r.get("alpaca").name == "Alpaca" and r.get("absent") is None
    assert len(r) == 1 and r.all()[0].connector_id == "alpaca"
    assert bool(ConnectorRegistry.empty()) is True and len(ConnectorRegistry.empty()) == 0


def test_registry_upsert_replaces():
    r = ConnectorRegistry.empty()
    r.upsert(_entry())
    r.upsert(_entry(name="Alpaca v2"))
    assert len(r) == 1 and r.get("alpaca").name == "Alpaca v2"


def _minimal_h(**kw):
    return HarnessState(doctrine=Doctrine.empty(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), **kw)


def test_harness_roundtrip_carries_connectors():
    h = _minimal_h(connectors=ConnectorRegistry.from_connectors([_entry()]))
    d = h.to_dict()
    assert d["connectors"][0]["connector_id"] == "alpaca"
    h2 = HarnessState.from_dict(d)
    assert h2.connectors.get("alpaca").pit_key == "announce_date:=process_date"


def test_legacy_dump_without_connectors_yields_empty():
    h = _minimal_h()
    d = h.to_dict()
    d.pop("connectors")
    h2 = HarnessState.from_dict(d)
    assert len(h2.connectors) == 0
```

> Confirm `Doctrine.empty()` exists (grounding: doctrine.py). If the minimal-doctrine factory is named differently, mirror the pattern in `tests/harness/test_state.py:30-74` (grounding report 0 / 4).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/harness/test_connectors.py -q`
Expected: ERROR — `No module named 'alpha.harness.connectors'`.

- [ ] **Step 3: Implement `alpha/harness/connectors.py`**

```python
"""Connector (C) — the fourth Body component: a DECLARATION of an external data/tool connection
the agent may draw on. An entry references an operator-registered implementation by key (impl_ref
into alpha.data.registry) and names required env vars — it carries NO URL, NO credential value,
NO executable content, so editing an entry can never grant a capability (data rung R1/R2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.scope import DEFAULT_SCOPE, Scope


class ConnectorEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    connector_id: str
    name: str
    kind: Literal["data_source", "llm_role", "mcp"]
    impl_ref: str                                   # registry key (make_source / make_client / MCP id)
    capabilities: list[str] = Field(default_factory=list)
    env_keys: list[str] = Field(default_factory=list)   # env-var NAMES only, never values
    instructions: str = ""                          # the ONLY field ever prompt-rendered
    pit_key: str = ""                               # per-connector PIT contract note
    enabled: bool = True
    required: bool = False
    tier: str = "T0_OBSERVE"
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    notes: str = ""


class ConnectorRegistry:
    """Id-keyed registry (house style: mirrors SkillRegistry/MemoryStore). Always truthy."""

    def __init__(self, entries: dict[str, ConnectorEntry]) -> None:
        self._entries = entries

    @classmethod
    def empty(cls) -> "ConnectorRegistry":
        return cls({})

    @classmethod
    def from_connectors(cls, entries: list[ConnectorEntry]) -> "ConnectorRegistry":
        d: dict[str, ConnectorEntry] = {}
        for e in entries:
            if e.connector_id in d:
                raise ValueError(f"duplicate connector_id: {e.connector_id}")
            d[e.connector_id] = e
        return cls(d)

    def get(self, connector_id: str) -> "ConnectorEntry | None":
        return self._entries.get(connector_id)

    def all(self) -> list[ConnectorEntry]:
        return list(self._entries.values())

    def upsert(self, entry: ConnectorEntry) -> None:
        self._entries[entry.connector_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Wire `HarnessState`** (`alpha/harness/state.py`)

Add import: `from alpha.harness.connectors import ConnectorRegistry`. Add `from dataclasses import dataclass, field`. Add the field after `vocabulary`:

```python
    connectors: ConnectorRegistry = field(default_factory=ConnectorRegistry.empty)
```

In `to_dict`'s returned dict add: `"connectors": [c.model_dump(mode="json") for c in self.connectors.all()],`
In `from_dict`'s `cls(...)` call add:
```python
        connectors=ConnectorRegistry.from_connectors(
            [ConnectorEntry.model_validate(x) for x in d.get("connectors", [])]),
```
and import `ConnectorEntry` in `from_dict`'s module scope.

- [ ] **Step 5: Extend `tests/harness/test_state.py`** — add the vocabulary-pair clone for connectors (a roundtrip + a legacy-pop test) mirroring `test_state.py:58-74` (grounding report 0). Two asserts: populated registry survives `to_dict`/`from_dict`; `d.pop("connectors")` → empty registry.

- [ ] **Step 6: Run tests to verify they pass, then the harness slice + full suite**

Run: `python -m pytest tests/harness/test_connectors.py tests/harness/test_state.py -q` → all pass.
Run: `python -m pytest -q` → all pass (snapshot/digest/serialization tests inherit the additive key with no change; if a test pins a specific brain HASH value it will shift — update it to recompute, do not delete).

- [ ] **Step 7: Commit**

```bash
git add alpha/harness/connectors.py alpha/harness/state.py tests/harness/test_connectors.py tests/harness/test_state.py
git commit -F <msg>   # "feat(harness): ConnectorEntry + ConnectorRegistry as H's fourth component"
```

---

### Task 2: Connector write-waist ops (write/patch/disable) + lints + conflict wiring

**Files:**
- Modify: `alpha/harness/metatools.py` (three methods), `alpha/refine/ops.py` (PASS_TOOLS/PassKind/PASS_ORDER), `alpha/refine/apply.py` (dispatch, lints, `_target_id`), `alpha/refine/conflict.py` (`_KIND`, `_CONTEST_VERBS`), `alpha/meta/agent.py` (`_KIND`), `alpha/data/registry.py` (public `source_names()`)
- Test: `tests/refine/test_connector_ops.py`, extend `tests/refine/test_ops.py`

**Interfaces:**
- Consumes: `ConnectorEntry`/`ConnectorRegistry` (Task 1); `try_apply_op(tools, h, op, *, allowed, provenance, ...) -> (record, None) | (None, reason)`; `RefineOp{tool,args,rationale}`; `MetaTools` (mutate-registry-first then one `log.append`).
- Produces (Tasks 3/5/7 mirror the pattern): ops `write_connector`/`patch_connector`/`disable_connector`; `alpha.data.registry.source_names() -> set[str]`; PASS `"C"`.

- [ ] **Step 1: Write the failing tests** — `tests/refine/test_connector_ops.py`:

```python
import pytest
from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.apply import try_apply_op


def _h():
    return HarnessState(doctrine=Doctrine.empty(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), connectors=ConnectorRegistry.empty())


def _args(**kw):
    a = dict(connector_id="alpaca", name="Alpaca", kind="data_source", impl_ref="alpaca",
             capabilities=["bars"], env_keys=["APCA_API_KEY_ID"], instructions="bars.")
    a.update(kw)
    return a


def _apply(h, log, tool, args, rationale="because"):
    return try_apply_op(MetaTools(h, log), h, RefineOp(tool=tool, args=args, rationale=rationale),
                        allowed=PASS_TOOLS["C"])


def test_write_connector_creates_entry():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args())
    assert reason is None and rec is not None
    assert h.connectors.get("alpaca").impl_ref == "alpaca"


def test_write_connector_rejects_unresolvable_impl_ref():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(impl_ref="not_a_real_source"))
    assert rec is None and "impl_ref" in reason


def test_write_connector_rejects_value_shaped_env_key():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(env_keys=["APCA_KEY=sk-secret-value"]))
    assert rec is None and "env_keys" in reason


def test_write_connector_rejects_overlong_instructions():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(instructions="x" * 2001))
    assert rec is None and "instructions" in reason


def test_patch_connector_updates_fields():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "patch_connector", {"connector_id": "alpaca", "notes": "note"})
    assert reason is None and h.connectors.get("alpaca").notes == "note"


def test_disable_connector_sets_enabled_false():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "disable_connector", {"connector_id": "alpaca"})
    assert reason is None and h.connectors.get("alpaca").enabled is False


def test_connector_op_refused_for_worker_proposer():
    from alpha.refine.edit_log_provenance import EditProvenance  # adjust import to real location
    h, log = _h(), EditLog()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_connector", args=_args(), rationale="x"),
                               allowed=PASS_TOOLS["C"],
                               provenance=EditProvenance(path="self_study", proposer="kairos"))
    assert rec is None and reason  # worker-propose refusal fires first
```

> The provenance import path + `EditProvenance` constructor: read grounding report 1 (`edit_log.py:10-24`) and match the real module. If the default `try_apply_op` provenance already refuses `kairos`, keep this test; otherwise adapt to the real refusal trigger.

- [ ] **Step 2: Run tests → fail**

Run: `python -m pytest tests/refine/test_connector_ops.py -q`
Expected: FAIL — `write_connector` not in `PASS_TOOLS["C"]` (KeyError on the pass) / unknown tool at the waist.

- [ ] **Step 3: Add PASS `"C"`** (`alpha/refine/ops.py`, grounding report 1 ops.py:10-19)

Extend `PassKind` Literal with `"C"`,`"W"`,`"A"`; set `PASS_ORDER = ("p","G","K","M","C","W","A")`; add to `PASS_TOOLS`:
```python
    "C": frozenset({"write_connector", "patch_connector", "disable_connector"}),
    "W": frozenset({"write_workflow", "patch_workflow", "retire_workflow"}),
    "A": frozenset({"write_subagent", "patch_subagent", "retire_subagent"}),
```
(All three added now so later tasks touch only their handlers, not this table.)

- [ ] **Step 4: Add `source_names()`** (`alpha/data/registry.py`, grounding report 5 registry.py:100-111)

```python
def source_names() -> set[str]:
    """Public accessor for the registered data-source keys (waist impl_ref lint; never import the
    private _SOURCES dict)."""
    return set(_SOURCES)
```

- [ ] **Step 5: Add the lints + MetaTools methods + dispatch**

In `alpha/refine/apply.py` add module-level lint predicates (mirror the taboo-lint template, grounding report 1 apply.py:92-98):
```python
_MAX_INSTRUCTIONS = 2000

def _connector_impl_resolves(entry) -> bool:
    from alpha.data.registry import source_names
    if entry.kind == "data_source":
        return entry.impl_ref in source_names()
    if entry.kind == "llm_role":
        return entry.impl_ref in {"agent", "refiner", "sonia", "converse"}
    return True  # mcp: no registry to resolve against yet

def _env_keys_are_names(entry) -> str | None:
    for k in entry.env_keys:
        if "=" in k or len(k) > 64:
            return f"env_keys must be env-var NAMES only (offending: {k[:20]}...)"
    return None
```
Add a `_check_connector(entry) -> str | None` returning the first failing reason (`impl_ref` unresolvable, `_env_keys_are_names`, `len(instructions) > _MAX_INSTRUCTIONS`), and call it inside the `write_connector`/`patch_connector` handlers before committing.

In `alpha/harness/metatools.py` (grounding report 1 metatools.py:32-112) add:
```python
def write_connector(self, entry, rationale):
    self.h.connectors.upsert(entry)
    return self.log.append("write_connector", "connector", entry.connector_id, "create",
                           entry.name, payload={"before": None, "after": entry.model_dump(mode="json")},
                           rationale=rationale)

def patch_connector(self, connector_id, fields, rationale):
    cur = self.h.connectors.get(connector_id)
    if cur is None:
        raise KeyError(f"unknown connector: {connector_id}")
    before = cur.model_dump(mode="json")
    updated = cur.model_copy(update=fields)
    self.h.connectors.upsert(updated)
    return self.log.append("patch_connector", "connector", connector_id, "update",
                           ",".join(fields), payload={"before": before, "after": updated.model_dump(mode="json")},
                           rationale=rationale)

def disable_connector(self, connector_id, rationale):
    return self.patch_connector(connector_id, {"enabled": False}, rationale)
```
> Match `log.append`'s real positional/keyword signature (grounding report 1 edit_log.py:61). If `append` differs, adapt these three calls to it.

In `alpha/refine/apply.py`'s dispatch (grounding report 1 apply.py:25-61) add the three op branches:
```python
    elif op.tool == "write_connector":
        entry = ConnectorEntry.model_validate(op.args)
        bad = _check_connector(entry)
        if bad:
            return None, bad
        rec = tools.write_connector(entry, rationale=op.rationale)
    elif op.tool == "patch_connector":
        cid = op.args["connector_id"]
        fields = {k: v for k, v in op.args.items() if k != "connector_id"}
        cur = h.connectors.get(cid)
        if cur is not None:
            bad = _check_connector(cur.model_copy(update=fields))
            if bad:
                return None, bad
        rec = tools.patch_connector(cid, fields, rationale=op.rationale)
    elif op.tool == "disable_connector":
        rec = tools.disable_connector(op.args["connector_id"], rationale=op.rationale)
```
(Follow the file's existing branch style — errors from `_DISPATCH_ERRORS` become clean reject reasons.)

- [ ] **Step 6: Wire `_target_id` + both `_KIND` maps + `_CONTEST_VERBS`**

`alpha/refine/apply.py::_target_id` (apply.py:124-133): add `connector` branch → `op.args.get("connector_id")`.
`alpha/refine/conflict.py::_KIND` (conflict.py:8-13) AND `alpha/meta/agent.py::_KIND` (agent.py:14-19): add the three tools → `"connector"`.
`alpha/refine/conflict.py::_CONTEST_VERBS`: add `"patch_connector"`,`"disable_connector"` (creates excluded by design).

- [ ] **Step 7: Update `tests/refine/test_ops.py`** — the PASS_ORDER / PASS_TOOLS["G"] pins (grounding report 4 test_ops.py:4-14): set expected `PASS_ORDER == ("p","G","K","M","C","W","A")`, keep `PASS_TOOLS["G"] == frozenset()`, add `PASS_TOOLS["C"]` exact-set assert.

- [ ] **Step 8: Run tests → pass, then full suite**

Run: `python -m pytest tests/refine -q` → all pass.
Run: `python -m pytest -q` → all pass.

- [ ] **Step 9: Commit**

```bash
git add alpha/harness/metatools.py alpha/refine/ops.py alpha/refine/apply.py alpha/refine/conflict.py alpha/meta/agent.py alpha/data/registry.py tests/refine/test_connector_ops.py tests/refine/test_ops.py
git commit -F <msg>   # "feat(refine): connector write-waist ops (write/patch/disable) + impl_ref/env_keys lints + PASS C/W/A"
```

---

### Task 3: Connector extract_ops vocabulary + brain-summary index + alpaca seed

**Files:**
- Modify: `alpha/meta/prompts.py` (`_TOOLS_DOC`, `_EXTRACTION_INSTRUCTION`, `render_brain_summary`), `alpha/harness/loader.py` (optional connectors.json load), `seeds/momo/` + `seeds/growth/` (new `connectors.json`)
- Test: `tests/meta/test_connector_extract.py`, extend `tests/harness/test_seed_packs.py`, `tests/harness/test_loader.py`

**Interfaces:**
- Consumes: `extract_ops` chain (unchanged — vocabulary lives in `prompts._TOOLS_DOC`); `load_seeds`/`load_pack` (grounding report 4 loader.py:17-76).
- Produces: an `alpaca` connector in both seed packs; `render_brain_summary` gains a `CONNECTORS:` section.

- [ ] **Step 1: Write the failing tests** — `tests/meta/test_connector_extract.py`:

```python
from alpha.meta import prompts
from alpha.harness.loader import load_seeds
from pathlib import Path

SEEDS_MOMO = Path(__file__).resolve().parents[2] / "seeds" / "momo"


def test_tools_doc_advertises_connector_ops():
    assert "write_connector" in prompts._TOOLS_DOC
    assert "disable_connector" in prompts._TOOLS_DOC


def test_extraction_instruction_lists_connector_target():
    assert "connector" in prompts._EXTRACTION_INSTRUCTION


def test_brain_summary_renders_connectors_section():
    h = load_seeds(SEEDS_MOMO)
    s = prompts.render_brain_summary(h)
    assert "CONNECTORS:" in s and "alpaca" in s


def test_momo_seed_has_alpaca_connector():
    h = load_seeds(SEEDS_MOMO)
    c = h.connectors.get("alpaca")
    assert c is not None and c.impl_ref == "alpaca"
    assert "bars" in c.capabilities and c.pit_key == "announce_date:=process_date"
```

Add to `tests/harness/test_loader.py` a test that a seed dir WITHOUT connectors.json still loads (empty registry) — the optional-file guarantee.

- [ ] **Step 2: Run → fail** (`ImportError`/`KeyError`/assert): `python -m pytest tests/meta/test_connector_extract.py -q`

- [ ] **Step 3: Seed files** — create `seeds/momo/connectors.json` and `seeds/growth/connectors.json` (identical):

```json
[
  {
    "connector_id": "alpaca",
    "name": "Alpaca US Equities",
    "kind": "data_source",
    "impl_ref": "alpaca",
    "capabilities": ["bars", "snapshots", "corp_actions", "calendar"],
    "env_keys": ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"],
    "instructions": "US equities daily bars, snapshots, corporate actions and the market calendar. IEX feed on free/paper keys.",
    "pit_key": "announce_date:=process_date",
    "enabled": true,
    "required": false,
    "tier": "T0_OBSERVE",
    "domain": "trading",
    "notes": "Seeded connector; credentials live in .env.alpaca (env-var names above)."
  }
]
```

- [ ] **Step 4: Optional-load in `alpha/harness/loader.py`** (grounding report 4 loader.py:17-76)

`_read_json_list` raises `FileNotFoundError` on a missing file. Add a connectors read that tolerates absence:
```python
    connectors_path = seeds_dir / "connectors.json"
    connector_rows = _read_json_list(connectors_path) if connectors_path.exists() else []
```
Build `ConnectorRegistry.from_connectors([ConnectorEntry.model_validate(r) for r in connector_rows])` and pass `connectors=...` into the `HarnessState(...)` construction. Import both. Keep skills/memory/doctrine reads REQUIRED (don't touch the pinned read order). `load_pack` inherits this via `load_seeds`.

- [ ] **Step 5: `_TOOLS_DOC` + `_EXTRACTION_INSTRUCTION` + `render_brain_summary`** (`alpha/meta/prompts.py`, grounding report 2 prompts.py:10-34)

Append to `_TOOLS_DOC` (one line each, matching existing style):
```
- write_connector(args: connector_id, name, kind[data_source|llm_role|mcp], impl_ref, capabilities[], env_keys[], instructions[, pit_key])
- patch_connector(args: connector_id, + any fields to change)
- disable_connector(args: connector_id)
```
Extend `_EXTRACTION_INSTRUCTION`'s missing-target enumeration to include `connector` and name `write_connector` as its create op.
In `render_brain_summary`, after the MEMORY section append:
```python
    parts.append("\nCONNECTORS (id [kind, status]):")
    for c in h.connectors.all():
        parts.append(f"- {c.connector_id} [{c.kind}, {'on' if c.enabled else 'off'}] {c.instructions[:80]}")
```

- [ ] **Step 6: Seed-count pins** — extend `tests/harness/test_seed_packs.py` (grounding report 4 test_seed_packs.py:14-56): assert exactly one connector `alpaca` in each pack; workflows/subagents will be asserted empty in Tasks 4/6. Confirm `test_seed_packs_v2.py`'s byte-identity gate still passes (all load paths gain the key identically).

- [ ] **Step 7: Run → pass, full suite**

Run: `python -m pytest tests/meta/test_connector_extract.py tests/harness/test_seed_packs.py tests/harness/test_loader.py -q` → pass.
Run: `python -m pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add alpha/meta/prompts.py alpha/harness/loader.py seeds/momo/connectors.json seeds/growth/connectors.json tests/meta/test_connector_extract.py tests/harness/test_seed_packs.py tests/harness/test_loader.py
git commit -F <msg>   # "feat(harness): connector extract_ops vocabulary + brain-summary index + alpaca seed"
```

---

### Task 4: WorkflowEntry + WorkflowRegistry + HarnessState integration

**Files:**
- Create: `alpha/harness/workflows.py`
- Modify: `alpha/harness/state.py` (import, `workflows` field, `to_dict`, `from_dict`)
- Test: `tests/harness/test_workflows.py`, extend `tests/harness/test_state.py`

**Interfaces:**
- Consumes: Task 1's HarnessState wiring pattern.
- Produces: `WorkflowStep{ref: str, note: str = ""}`; `WorkflowEntry{workflow_id, name, description, steps: list[WorkflowStep], arg_hints: list[str] = [], user_only: bool = True, phases: list[str] = [], domain, scope, status: Literal["active","retired"] = "active", content_hash: str = ""}`; `WorkflowRegistry` (same methods as ConnectorRegistry: `empty`/`from_workflows`/`get`/`all`/`upsert`/`__len__`/`__bool__`); `HarnessState.workflows`.

- [ ] **Step 1: Write failing tests** — `tests/harness/test_workflows.py` mirroring `test_connectors.py` (Task 1) with workflow fields: entry rejects unknown field; defaults (`user_only is True`, `status == "active"`, `content_hash == ""`); registry dup-id ValueError, get/all/len/bool, upsert-replaces; `_minimal_h(workflows=...)` roundtrip carries workflows; legacy `d.pop("workflows")` → empty registry. Build a step: `WorkflowStep(ref="skill_x", note="first")`.

- [ ] **Step 2: Run → fail**: `python -m pytest tests/harness/test_workflows.py -q` → `No module named 'alpha.harness.workflows'`.

- [ ] **Step 3: Implement `alpha/harness/workflows.py`**

```python
"""Workflow (W) — a named multi-step playbook, SKILL-SHAPED per the unanimous mainstream verdict
(no first-class workflow type in Claude Code / Codex / Hermes). Steps reference skills by id (or
free-prose actions); side-effectful flows are human-triggered by default. Declarative this arc —
no executor; the entry is prompt-visible and teachable/evolvable through the write-waist."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.scope import DEFAULT_SCOPE, Scope


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    note: str = ""


class WorkflowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    workflow_id: str
    name: str
    description: str = ""                            # <=200 chars — the index line
    steps: list[WorkflowStep] = Field(default_factory=list)
    arg_hints: list[str] = Field(default_factory=list)
    user_only: bool = True
    phases: list[str] = Field(default_factory=list)
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    status: Literal["active", "retired"] = "active"
    content_hash: str = ""


class WorkflowRegistry:
    def __init__(self, entries: dict[str, WorkflowEntry]) -> None:
        self._entries = entries

    @classmethod
    def empty(cls) -> "WorkflowRegistry":
        return cls({})

    @classmethod
    def from_workflows(cls, entries: list[WorkflowEntry]) -> "WorkflowRegistry":
        d: dict[str, WorkflowEntry] = {}
        for e in entries:
            if e.workflow_id in d:
                raise ValueError(f"duplicate workflow_id: {e.workflow_id}")
            d[e.workflow_id] = e
        return cls(d)

    def get(self, workflow_id: str) -> "WorkflowEntry | None":
        return self._entries.get(workflow_id)

    def all(self) -> list[WorkflowEntry]:
        return list(self._entries.values())

    def upsert(self, entry: WorkflowEntry) -> None:
        self._entries[entry.workflow_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Wire HarnessState** — same as Task 1 Step 4: import `WorkflowRegistry` (+ `WorkflowEntry` in from_dict scope), field `workflows: WorkflowRegistry = field(default_factory=WorkflowRegistry.empty)` after `connectors`; `to_dict` add `"workflows": [w.model_dump(mode="json") for w in self.workflows.all()]`; `from_dict` add `workflows=WorkflowRegistry.from_workflows([WorkflowEntry.model_validate(x) for x in d.get("workflows", [])])`.

- [ ] **Step 5: Extend `tests/harness/test_state.py`** — workflow roundtrip + legacy-pop pair.

- [ ] **Step 6: Run → pass, full suite**: `python -m pytest tests/harness -q` then `python -m pytest -q`.

- [ ] **Step 7: Commit** — `git add alpha/harness/workflows.py alpha/harness/state.py tests/harness/test_workflows.py tests/harness/test_state.py` → `git commit -F <msg>` ("feat(harness): WorkflowEntry + WorkflowRegistry as H's fifth component").

---

### Task 5: Workflow write-waist ops + step-referential-integrity lint + extract vocabulary + render

**Files:**
- Modify: `alpha/harness/metatools.py`, `alpha/refine/apply.py`, `alpha/refine/conflict.py`, `alpha/meta/agent.py`, `alpha/meta/prompts.py`
- Test: `tests/refine/test_workflow_ops.py`

**Interfaces:**
- Consumes: Task 4's models; PASS `"W"` (already in `PASS_TOOLS` from Task 2).
- Produces: ops `write_workflow`/`patch_workflow`/`retire_workflow`; step-ref lint.

- [ ] **Step 1: Write failing tests** — `tests/refine/test_workflow_ops.py` mirroring `test_connector_ops.py` (Task 2) with `allowed=PASS_TOOLS["W"]`:
  - `write_workflow` creates an entry (args: workflow_id, name, description, steps=[{"ref":"...","note":""}]);
  - **step-referential-integrity lint**: a step whose `ref` looks like a skill id (matches an existing skill-id shape) but is absent/retired → refused with `"step"` in reason; a step with a free-prose `ref` (contains a space / not id-shaped) → allowed;
  - `patch_workflow` updates fields; `retire_workflow` sets `status="retired"`;
  - a `content_hash` is populated on apply and CHANGES after `patch_workflow`.
  Seed one real skill into `_h()` (via `SkillRegistry.from_skills([...])`) so a valid step ref resolves.

- [ ] **Step 2: Run → fail**: `python -m pytest tests/refine/test_workflow_ops.py -q`.

- [ ] **Step 3: Lint + content_hash helper** (`alpha/refine/apply.py`)

```python
import re as _re
_SKILL_ID_SHAPE = _re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")   # id-shaped ref (no spaces)

def _check_workflow(entry, h) -> str | None:
    if len(entry.description) > 200:
        return "description exceeds 200 chars (the index budget)"
    for st in entry.steps:
        if _SKILL_ID_SHAPE.match(st.ref):                # looks like a skill id → must resolve, active
            sk = h.skills.get(st.ref)
            if sk is not None and sk.status == "retired":
                return f"step ref {st.ref} is a retired skill"
            # id-shaped but unknown = treated as free action ref (allowed) unless it collides retired
    return None

def _workflow_hash(entry) -> str:
    from alpha.integrity import sha256_canonical_json    # match the repo's canonicalizer (grounding)
    body = entry.model_dump(mode="json")
    body.pop("content_hash", None)
    return sha256_canonical_json(body)
```
> Use the repo's real canonicalizer import (grounding report 0 snapshot.py uses `sha256_canonical_json` from `alpha.integrity`). If a skill-id-shaped ref must be a HARD error when unknown, tighten `_check_workflow` — but the spec says referential-integrity lint for skill refs; keep unknown-id-shaped refs permissive (they may be future skills) and only block retired ones, matching taboo-lint's "block known-bad" posture.

- [ ] **Step 4: MetaTools methods** (`alpha/harness/metatools.py`) — `write_workflow(entry, rationale)`, `patch_workflow(workflow_id, fields, rationale)`, `retire_workflow(workflow_id, rationale)` mirroring the connector trio, logging `target_kind="workflow"`. In the handlers (apply.py dispatch), compute `entry.content_hash = _workflow_hash(entry)` before upsert for create AND for patch (recompute on the updated entry).

- [ ] **Step 5: Dispatch + `_target_id` + `_KIND`×2 + `_CONTEST_VERBS`** — add the three workflow branches to apply.py dispatch (validate `WorkflowEntry`, run `_check_workflow(entry, h)`, set content_hash); `_target_id` → `op.args.get("workflow_id")`; both `_KIND` maps → three tools `"workflow"`; `_CONTEST_VERBS` add `patch_workflow`,`retire_workflow`.

- [ ] **Step 6: prompts** — `_TOOLS_DOC` append `write_workflow(args: workflow_id, name, description, steps[{ref,note}][, user_only, phases])`, `patch_workflow`, `retire_workflow`; `_EXTRACTION_INSTRUCTION` add `workflow`/`write_workflow`; `render_brain_summary` append a `WORKFLOWS (id [status]):` section (`f"- {w.workflow_id} [{w.status}] {w.description[:80]}"`).

- [ ] **Step 7: Run → pass, full suite**: `python -m pytest tests/refine -q` then `python -m pytest -q`.

- [ ] **Step 8: Commit** — `git commit -F <msg>` ("feat(refine): workflow write-waist ops + step-ref lint + content_hash + extract vocabulary").

---

### Task 6: SubagentEntry + SubagentRegistry + HarnessState integration

**Files:**
- Create: `alpha/harness/subagents.py`
- Modify: `alpha/harness/state.py`
- Test: `tests/harness/test_subagents.py`, extend `tests/harness/test_state.py`

**Interfaces:**
- Produces: `SubagentEntry{subagent_id, name, description, system_prompt: str = "", llm_role: str = "inherit", tools: list[str] = [], max_tier: str = "T0_OBSERVE", skills_preload: list[str] = [], max_turns: int = 8, domain, scope, status: Literal["active","retired"] = "active", notes: str = ""}`; `SubagentRegistry` (same method set); `HarnessState.subagents`.

- [ ] **Step 1: Write failing tests** — `tests/harness/test_subagents.py` mirroring Task 1/4: unknown-field reject; defaults (`llm_role == "inherit"`, `max_tier == "T0_OBSERVE"`, `max_turns == 8`, `status == "active"`); registry dup/get/all/len/bool/upsert; H roundtrip carries subagents; legacy-pop → empty.

- [ ] **Step 2: Run → fail**: `python -m pytest tests/harness/test_subagents.py -q`.

- [ ] **Step 3: Implement `alpha/harness/subagents.py`**

```python
"""Subagent (A) — a specialized dispatch persona. STATE ONLY this arc: description is the dispatch
routing signal, system_prompt the body, tools/max_tier the restriction surface. Dispatch mechanics
(the G pass) stay deferred — PASS_TOOLS["G"] is reserved-empty; these entries are dispatch-READY."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.scope import DEFAULT_SCOPE, Scope


class SubagentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    subagent_id: str
    name: str
    description: str = ""                            # <=1536 chars — the ONLY dispatch-routing signal
    system_prompt: str = ""
    llm_role: str = "inherit"
    tools: list[str] = Field(default_factory=list)
    max_tier: str = "T0_OBSERVE"
    skills_preload: list[str] = Field(default_factory=list)
    max_turns: int = 8
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    status: Literal["active", "retired"] = "active"
    notes: str = ""


class SubagentRegistry:
    def __init__(self, entries: dict[str, SubagentEntry]) -> None:
        self._entries = entries

    @classmethod
    def empty(cls) -> "SubagentRegistry":
        return cls({})

    @classmethod
    def from_subagents(cls, entries: list[SubagentEntry]) -> "SubagentRegistry":
        d: dict[str, SubagentEntry] = {}
        for e in entries:
            if e.subagent_id in d:
                raise ValueError(f"duplicate subagent_id: {e.subagent_id}")
            d[e.subagent_id] = e
        return cls(d)

    def get(self, subagent_id: str) -> "SubagentEntry | None":
        return self._entries.get(subagent_id)

    def all(self) -> list[SubagentEntry]:
        return list(self._entries.values())

    def upsert(self, entry: SubagentEntry) -> None:
        self._entries[entry.subagent_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Wire HarnessState** — import; field `subagents: SubagentRegistry = field(default_factory=SubagentRegistry.empty)` after `workflows`; `to_dict` + `from_dict` with `d.get("subagents", [])`.

- [ ] **Step 5: Extend `tests/harness/test_state.py`** — subagent roundtrip + legacy-pop pair.

- [ ] **Step 6: Run → pass, full suite**.

- [ ] **Step 7: Commit** — ("feat(harness): SubagentEntry + SubagentRegistry as H's sixth component").

---

### Task 7: Subagent write-waist ops + tools-subset lint + extract vocabulary + render

**Files:** Modify `alpha/harness/metatools.py`, `alpha/refine/apply.py`, `alpha/refine/conflict.py`, `alpha/meta/agent.py`, `alpha/meta/prompts.py`. Test `tests/refine/test_subagent_ops.py`.

**Interfaces:** ops `write_subagent`/`patch_subagent`/`retire_subagent` under PASS `"A"`; tools-subset + description-cap lint.

- [ ] **Step 1: Write failing tests** — `tests/refine/test_subagent_ops.py`, `allowed=PASS_TOOLS["A"]`: create; **tools-subset lint** — a `tools` list containing a name not in the registerable parent tool set → refused with `"tools"` in reason (use a small known allowlist constant, see Step 3); **description cap** — >1536 chars refused; patch updates; retire sets `status="retired"`.

- [ ] **Step 2: Run → fail**.

- [ ] **Step 3: Lint** (`alpha/refine/apply.py`)

```python
# The parent tool surface a subagent entry may name (this arc: the observe-tier vocabulary).
_REGISTERABLE_TOOLS = frozenset({
    "market_snapshot", "daily_bars", "latest_decisions",
    "view_doctrine", "view_skill", "view_lesson", "view_workflow", "view_connector",
    "view_subagent", "search_episodes", "decide",
})

def _check_subagent(entry) -> str | None:
    if len(entry.description) > 1536:
        return "description exceeds 1536 chars (the dispatch-index budget)"
    extra = set(entry.tools) - _REGISTERABLE_TOOLS
    if extra:
        return f"tools not in the registerable parent set: {sorted(extra)}"
    return None
```
> If Tasks 9/10 name the observe tools differently, keep `_REGISTERABLE_TOOLS` in sync — it is the single source for the subset lint. Grounding note: this constant is the code-level home of the spec's "child ⊆ parent" rule until the dispatch layer lands.

- [ ] **Step 4: MetaTools + dispatch + `_target_id` + `_KIND`×2 + `_CONTEST_VERBS`** — `write_subagent`/`patch_subagent`/`retire_subagent` (target_kind `"subagent"`); dispatch validates `SubagentEntry` + runs `_check_subagent`; `_target_id` → `op.args.get("subagent_id")`; `_KIND`×2 add three tools; `_CONTEST_VERBS` add `patch_subagent`,`retire_subagent`.

- [ ] **Step 5: prompts** — `_TOOLS_DOC` add the three subagent ops (`write_subagent(args: subagent_id, name, description, system_prompt[, llm_role, tools[], max_tier, skills_preload[], max_turns])`, patch, retire); `_EXTRACTION_INSTRUCTION` add `subagent`/`write_subagent`; `render_brain_summary` append `SUBAGENTS (id [status]):` section.

- [ ] **Step 6: Run → pass, full suite**.

- [ ] **Step 7: Commit** — ("feat(refine): subagent write-waist ops + tools-subset lint + extract vocabulary").

---

### Task 8: Three real console pages (/connector, /workflow, /subagent)

**Files:**
- Modify: `alpha_web/app.py` (replace the three stub routes; can delete `_BRAIN_STUBS`/`_brain_stub` once unused), `alpha_web/data_access.py` (three list helpers)
- Create: `alpha_web/templates/connector.html`, `workflow.html`, `subagent.html`
- Delete (once no route references it): `alpha_web/templates/brain_stub.html`
- Test: rewrite the stub test in `tests/web/test_app.py`

**Interfaces:**
- Consumes: `da.load_brain()` → `HarnessState` with `.connectors`/`.workflows`/`.subagents` (Tasks 1/4/6); the `render(request, name, ctx)` closure + `active` nav key (grounding report 5 app.py:277-281).
- Produces: three real read-only pages; `da.list_connectors(h)`, `da.list_workflows(h)`, `da.list_subagents(h)`.

- [ ] **Step 1: Write failing tests** — rewrite `tests/web/test_app.py::test_brain_stub_pages_render_readonly` (grounding report 5 test_app.py:426-438) into three tests mirroring `test_doctrine_page_shows_a_real_redline` (test_app.py:11-14): `GET /connector` is 200, contains the seeded `alpaca` id/instructions, and the Brain drawer group is open (`active in brain_keys`); `GET /workflow` and `GET /subagent` are 200 and render an **empty-state** message (seeds are empty). Keep the existing nav-order test `test_brain_group_lists_six_children_in_order` untouched.

- [ ] **Step 2: Run → fail**: `python -m pytest tests/web/test_app.py -q -k "connector or workflow or subagent"`.

- [ ] **Step 3: `data_access.py` helpers** (mirror `split_doctrine`, grounding report 5 data_access.py:189-191)

```python
def list_connectors(h) -> list:
    return h.connectors.all()

def list_workflows(h) -> list:
    return h.workflows.all()

def list_subagents(h) -> list:
    return h.subagents.all()
```

- [ ] **Step 4: Replace the three routes** (`alpha_web/app.py`, grounding report 5 app.py:411-425)

```python
    @app.get("/connector")
    def connector(request: Request):
        h = da.load_brain()
        return render(request, "connector.html",
                      {"active": "connector", "connectors": da.list_connectors(h)})

    @app.get("/workflow")
    def workflow(request: Request):
        h = da.load_brain()
        return render(request, "workflow.html",
                      {"active": "workflow", "workflows": da.list_workflows(h)})

    @app.get("/subagent")
    def subagent(request: Request):
        h = da.load_brain()
        return render(request, "subagent.html",
                      {"active": "subagent", "subagents": da.list_subagents(h)})
```
Delete `_BRAIN_STUBS`, `_brain_stub`, and the two remaining stub-route wrappers if `/connector`/`/workflow`/`/subagent` were the only callers.

- [ ] **Step 5: Templates** — create the three, each extending `base.html` mirroring `doctrine.html` (grounding report 5 doctrine.html:1-47): page-head (eyebrow/title/lede) + a cardlist. `connector.html` cards show id, kind, enabled badge, capabilities, instructions, pit_key, env_keys (names). `workflow.html`/`subagent.html` cards show id/name/status/description (+ steps for workflow), and an empty-state block (`{% if not workflows %}<p class="lede">No workflows yet — teach one in the cockpit.</p>{% endif %}`).

Example `connector.html`:
```html
{% extends "base.html" %}
{% block title %}Connectors{% endblock %}
{% block content %}
<section class="panel">
  <header class="page-head"><span class="eyebrow">Body · C</span>
    <h1 class="page-title">Connectors</h1>
    <p class="page-lede">External data/tool connections H may draw on. Declarations only — no URLs, no secrets.</p></header>
  {% if not connectors %}<p class="lede">No connectors yet.</p>{% endif %}
  <div class="cardlist">
  {% for c in connectors %}
    <article class="card {% if not c.enabled %}sealed{% endif %}">
      <div class="top"><span class="section">{{ c.connector_id }}</span>
        <span class="tag">{{ c.kind }}</span>
        <span class="tag {{ 'fam' if c.enabled else '' }}">{{ 'enabled' if c.enabled else 'disabled' }}</span></div>
      <div class="body">{{ c.instructions }}</div>
      <div class="meta">impl: {{ c.impl_ref }} · caps: {{ c.capabilities|join(', ') }} · env: {{ c.env_keys|join(', ') }}
        {% if c.pit_key %}· PIT: {{ c.pit_key }}{% endif %}</div>
    </article>
  {% endfor %}
  </div>
</section>
{% endblock %}
```
(Reuse existing CSS classes; confirm names against `doctrine.html`.)

- [ ] **Step 6: Run → pass, web slice + full suite**: `python -m pytest tests/web -q` then `python -m pytest -q`.

- [ ] **Step 7: Commit** — `git add alpha_web/app.py alpha_web/data_access.py alpha_web/templates/{connector,workflow,subagent}.html tests/web/test_app.py` (+ `git rm alpha_web/templates/brain_stub.html` if unused) → ("feat(web): real Connector/Workflow/Subagent brain pages").

---

### Task 9: Sonia observe loop — reroute respond() through run_conversation + brain view_* tools

**Files:**
- Create: `alpha/meta/sonia_tools.py` (registry+policy builder; may import `alpha.arena` — the AST guard only walks `alpha/converse`)
- Modify: `alpha/meta/sonia_agent.py` (`respond` reroute + two-tier index), `sonia/app.py` (thread the registry/policy into `SoniaAgent`)
- Test: `tests/meta/test_sonia_loop.py`

**Interfaces:**
- Consumes: `run_conversation(registry, chat, system, messages, *, max_iters, dispatch) -> ConversationResult` (grounding report 3 loop.py:36-74); `ToolRegistry.register(name, schema, fn)` (registry.py:6-27); `ActivityPolicy(reg, tiers)` + `CapabilityTier.T0_OBSERVE` (policy.py / contract.py); `HarnessState` view accessors.
- Produces: `build_sonia_registry(h) -> (ToolRegistry, ActivityPolicy)` with the seven `view_*`/`search_episodes` tools (market tools added in Task 10); `SoniaAgent` accepting an optional `registry_factory`.

- [ ] **Step 1: Write failing tests** — `tests/meta/test_sonia_loop.py` (offline, uses the scripted `_Chat` pattern from grounding report 3 test_policy.py:13-35):

```python
import json
from alpha.meta.sonia_tools import build_sonia_registry
from alpha.meta.sonia_agent import SoniaAgent
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.meta.models import Session, Message, new_message_id, now_iso
from pathlib import Path

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "momo"


class _Chat:
    def __init__(self, replies): self._r = list(replies)
    def chat(self, system, messages): return self._r.pop(0)


def _sess():
    return Session(session_id="s1", created_at=now_iso())


def _umsg(text):
    return Message(message_id=new_message_id(), role="user", created_at=now_iso(), text=text, origin="user")


def test_registry_registers_view_tools_at_t0():
    h = load_seeds(SEEDS)
    reg, pol = build_sonia_registry(h)
    assert "view_connector" in reg.names()          # adjust to the real registry introspection method
    # every registered tool is T0-tiered (fail-closed policy)
    for name in reg.names():
        assert pol.tier_of(name).name == "T0_OBSERVE"  # adjust to the real policy accessor


def test_respond_uses_a_tool_then_finishes():
    h = load_seeds(SEEDS)
    # turn 1: model asks to view the alpaca connector; turn 2: prose answer
    chat = _Chat([json.dumps({"tool": "view_connector", "args": {"connector_id": "alpaca"}}),
                  "Alpaca is your data connector."])
    agent = SoniaAgent(MetaTools(h, EditLog()), chat, registry_factory=build_sonia_registry)
    msg = agent.respond(_sess(), _umsg("what data do we have?"))
    assert "Alpaca" in msg.text                       # final prose after the tool turn


def test_respond_still_parses_directions_without_tools():
    h = load_seeds(SEEDS)
    chat = _Chat(['Here is a thought.\n{"directions": [{"title": "T", "summary": "S"}]}'])
    agent = SoniaAgent(MetaTools(h, EditLog()), chat, registry_factory=build_sonia_registry)
    msg = agent.respond(_sess(), _umsg("ideas?"))
    assert msg.directions and msg.directions[0].title == "T"
```
> Adjust `reg.names()` / `pol.tier_of()` to the real `ToolRegistry`/`ActivityPolicy` introspection (read grounding report 3 registry.py:6-27, policy.py:11-26). The directions test pins the CRITICAL interplay (grounding report 3 loop.py:9-33): a reply with only a `{"directions"}` block is NOT a tool call, so the loop ends and `parse_directions(final_text)` still works.

- [ ] **Step 2: Run → fail**: `python -m pytest tests/meta/test_sonia_loop.py -q`.

- [ ] **Step 3: `alpha/meta/sonia_tools.py`** — seven read tools over H, T0-tiered:

```python
"""Sonia's observe-tier tool registry: read-only brain browse (two-tier disclosure) + (Task 10)
market snapshot tools. All tools are T0_OBSERVE under a fail-closed ActivityPolicy — Sonia's hands
still only touch the brain-edit door (via the separate teach/propose chain), never write here."""
from __future__ import annotations

import json

from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry


def _schema(name, desc, props=None, required=None):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


def build_sonia_registry(h):
    reg = ToolRegistry()
    tiers = {}

    def _add(name, desc, fn, props=None, required=None):
        reg.register(name, _schema(name, desc, props, required), fn)
        tiers[name] = CapabilityTier.T0_OBSERVE

    _add("view_doctrine", "Full text of one doctrine section.",
         lambda section: {"ok": True, "entry": next((e.model_dump() for e in
             h.doctrine.all_entries() if e.section == section), None)},
         {"section": {"type": "string"}}, ["section"])
    _add("view_skill", "Full detail of one skill by id.",
         lambda skill_id: {"ok": True, "skill": (h.skills.get(skill_id).model_dump()
             if h.skills.get(skill_id) else None)},
         {"skill_id": {"type": "string"}}, ["skill_id"])
    _add("view_lesson", "Full text of one memory lesson by id.",
         lambda lesson_id: {"ok": True, "lesson": (h.memory.get(lesson_id).model_dump()
             if h.memory.get(lesson_id) else None)},
         {"lesson_id": {"type": "string"}}, ["lesson_id"])
    _add("view_workflow", "Full detail of one workflow by id.",
         lambda workflow_id: {"ok": True, "workflow": (h.workflows.get(workflow_id).model_dump()
             if h.workflows.get(workflow_id) else None)},
         {"workflow_id": {"type": "string"}}, ["workflow_id"])
    _add("view_connector", "Full detail of one connector by id.",
         lambda connector_id: {"ok": True, "connector": (h.connectors.get(connector_id).model_dump()
             if h.connectors.get(connector_id) else None)},
         {"connector_id": {"type": "string"}}, ["connector_id"])
    _add("view_subagent", "Full detail of one subagent by id.",
         lambda subagent_id: {"ok": True, "subagent": (h.subagents.get(subagent_id).model_dump()
             if h.subagents.get(subagent_id) else None)},
         {"subagent_id": {"type": "string"}}, ["subagent_id"])
    _add("search_episodes", "Search PIT episodic memory (returns matching lesson summaries).",
         lambda query: {"ok": True, "hits": []},   # wired to EpisodeStore when a brain db is present
         {"query": {"type": "string"}}, ["query"])

    return reg, ActivityPolicy(reg, tiers)
```
> Match the real accessor names: `h.doctrine.all_entries()`/`.all()`, `h.skills.get`, `h.memory.get`, `ActivityPolicy(reg, tiers)` constructor (grounding report 0/3). If `ToolRegistry.register` fn-signature binds args positionally vs by kwargs, adapt the lambdas — the loop's `_parse_tool_call` passes the JSON `args` dict; check how existing arena tools receive them (grounding report 3 tools.py:20-31, `fn(**args)` vs `fn(args)`).

- [ ] **Step 4: Reroute `SoniaAgent.respond`** (`alpha/meta/sonia_agent.py`, grounding report 3 sonia_agent.py:9-48)

Add `registry_factory=None` to `__init__`. In `respond`, if a factory is present:
```python
        if self._registry_factory is not None:
            reg, pol = self._registry_factory(self.h)
            res = run_conversation(reg, self.copilot, self._system(),
                                   self._history(session, user_message),
                                   max_iters=6, dispatch=pol.dispatch)
            reply = res.final_text
        else:
            reply = self.copilot.chat(self._system(), self._history(session, user_message))
```
then keep the EXISTING `extract_json_object`/`parse_directions` post-processing on `reply` (works because a directions-only reply ends the loop as `final_text`). Import `run_conversation` from `alpha.converse.loop`.

- [ ] **Step 5: Two-tier index in `_system`** — change `render_brain_summary` usage so the chat system prompt shows the budgeted INDEX (already index-shaped after Tasks 3/5/7 added one-line sections). Confirm `_system()` still calls `render_brain_summary(self.h) + _INSTRUCTIONS` and that the `_INSTRUCTIONS` text now mentions the view_* tools are available for detail (append one sentence). No change to `extract_ops`/decide render.

- [ ] **Step 6: Thread into `sonia/app.py`** (grounding report 3 app.py:153-174) — build the registry factory at the `SoniaAgent(...)` construction site inside `/chat`:
```python
            from alpha.meta.sonia_tools import build_sonia_registry
            agent = SoniaAgent(MetaTools(h, log), make_client("sonia"),
                               registry_factory=build_sonia_registry)
```

- [ ] **Step 7: Run → pass, sonia slice + full suite**: `python -m pytest tests/meta/test_sonia_loop.py tests/sonia -q` then `python -m pytest -q`.

- [ ] **Step 8: Commit** — ("feat(sonia): observe loop — respond() through run_conversation + T0 brain view_* tools").

---

### Task 10: Sonia market tools gated by the alpaca connector (lazy, fail-soft)

**Files:**
- Modify: `alpha/meta/sonia_tools.py` (add market tools, connector-gated), `sonia/app.py` (lazy source construction)
- Test: extend `tests/meta/test_sonia_loop.py`

**Interfaces:**
- Consumes: `make_source()` (raw; wrap per-call in `GuardedSource(source, AsOfGuard(day))` — grounding report 3 tools.py:32-49); the alpaca `ConnectorEntry` (`enabled` + `env_keys` present) gates registration.
- Produces: `build_sonia_registry(h, *, source_factory=None)` adds `market_snapshot`/`daily_bars`/`latest_decisions` only when the alpaca connector is enabled and its env keys are set.

- [ ] **Step 1: Write failing tests** — extend `tests/meta/test_sonia_loop.py`:
  - with a `FakeSource` injected via `source_factory` AND the alpaca connector enabled + env keys present (monkeypatch `os.environ`), `market_snapshot` IS registered and returns `{"ok": True, ...}`;
  - with the alpaca connector `disable_connector`'d (or env keys absent), `market_snapshot` is NOT registered (gated off);
  - a market tool whose source raises returns `{"ok": False, "error": ...}` (fail-soft, never raises into the loop).
  Use the repo's `FakeSource` (grounding: offline source used across tests).

- [ ] **Step 2: Run → fail**.

- [ ] **Step 3: Add connector-gated market tools** to `build_sonia_registry`:

```python
def build_sonia_registry(h, *, source_factory=None):
    reg = ToolRegistry()
    tiers = {}
    # ... the seven view_* tools from Task 9 ...

    conn = h.connectors.get("alpaca")
    import os
    keys_present = conn is not None and all(os.environ.get(k) for k in conn.env_keys)
    if conn is not None and conn.enabled and keys_present:
        src_factory = source_factory if source_factory is not None else _default_source_factory
        _add("market_snapshot", "Latest snapshot (price/volume) for one or more symbols.",
             _market_snapshot_fn(src_factory),
             {"symbols": {"type": "array", "items": {"type": "string"}}}, ["symbols"])
        _add("daily_bars", "Recent daily bars for one symbol.",
             _daily_bars_fn(src_factory),
             {"symbol": {"type": "string"}, "days": {"type": "integer"}}, ["symbol"])
        _add("latest_decisions", "Today's DecisionPackage if one has been produced.",
             _latest_decisions_fn(),
             {}, [])
    return reg, ActivityPolicy(reg, tiers)
```
Implement `_market_snapshot_fn`/`_daily_bars_fn` as fail-soft closures (mirror `make_decide_for_date_tool`, grounding report 3 tools.py:32-49 — wrap the raw source in `GuardedSource(src, AsOfGuard(today))` per call; catch exceptions → `{"ok": False, "error": str(e)}`). `_default_source_factory` lazily `from alpha.data.registry import make_source; return make_source()`. `_latest_decisions_fn` reads a `DecisionStore` if `ALPHA_WEB_DECISIONS_DIR`/its env is set, else `{"ok": True, "decisions": None}`.

- [ ] **Step 4: Lazy source in `sonia/app.py`** — pass `source_factory=None` (the default lazy `make_source`); construction stays inside the `/chat` never-500 boundary so a missing `.env.alpaca` fails soft (tool absent), never boot-blocking. `sonia/__main__.py` stays untouched (grounding report 5 __main__.py:1-14).

- [ ] **Step 5: Run → pass, full suite**: `python -m pytest tests/meta tests/sonia -q` then `python -m pytest -q`.

- [ ] **Step 6: Commit** — ("feat(sonia): connector-gated market tools (snapshot/bars/decisions), lazy + fail-soft").

---

### Task 11: Docs + service recipe + ROADMAP built-log & deferrals

**Files:** Modify `CLAUDE.md` (Map row + a Gotcha), `ROADMAP.md` (Part II built-log + deferrals), and the `run-workbench-live-face` memory (sonia recipe gains `.env.alpaca`).

- [ ] **Step 1: CLAUDE.md** — update the `alpha/harness` Map row to `H = (p, K, M, C, W, A)` (doctrine/skills/memory/connectors/workflows/subagents); update the `**\`H\` in code is \`(p, K, M)\`**` gotcha to note C/W/A are now real components (declarative; W/A executors deferred, G pass still reserved-empty). Add one line: Sonia now has a T0 observe loop (market tools gated by the alpaca connector).

- [ ] **Step 2: ROADMAP.md Part II** — append a dated 2026-07-16 entry (blockquote format, matching the file): the six-component Body completion, one shared pattern, connector-gated Sonia observe loop, executors/dispatch/hooks-cron explicitly deferred. Spec + plan paths.

- [ ] **Step 3: Update the `run-workbench-live-face` memory** — sonia start line gains `. ./.env.alpaca` (fail-soft), note market tools appear only when the alpaca connector is enabled + keys present.

- [ ] **Step 4: Full suite green** — `python -m pytest -q`.

- [ ] **Step 5: Commit** — ("docs: Body six-component completion — CLAUDE.md map + ROADMAP built log + deferrals").

---

## Self-Review

**1. Spec coverage:** ConnectorEntry/WorkflowEntry/SubagentEntry field lists (T1/4/6) ✓; shared integration pattern — HarnessState registries, brain.json serialization, EditRecord target_kinds, extract_ops vocabulary, render index, console pages, seeds (T1-8) ✓; waist ops + lints (impl_ref resolve, env_keys value-refusal, description/instructions caps, step referential integrity, tools-subset) (T2/5/7) ✓; no-URL/credential/executable constraint (T1 model + T2 lint) ✓; PASS G reserved-empty + PASS_ORDER pin (T2 + Global Constraints) ✓; Sonia observe loop — run_conversation reroute, T0 fail-closed policy, connector-gated market tools, two-tier disclosure, full render retained for decide()/extract_ops (T9/10) ✓; deferrals recorded (T11) ✓; alpaca seed (T3) ✓; fail-soft + never-boot-block + offline tests (T9/10 + Global Constraints) ✓.

**2. Placeholder scan:** every code step shows code; every lint has a concrete predicate; no TBD/TODO. Adaptation notes (real accessor names, log.append signature, provenance import) are explicit "read grounding X / match the real Y" instructions, not placeholders — the grounding file carries the verbatim source.

**3. Type consistency:** `ConnectorRegistry.from_connectors` / `WorkflowRegistry.from_workflows` / `SubagentRegistry.from_subagents` (distinct classmethod names, matching `HarnessState.from_dict` calls); ops names identical across Global Constraints / PASS_TOOLS / MetaTools / dispatch / `_KIND` / prompts (`write_connector` etc.); `_REGISTERABLE_TOOLS` (T7) lists exactly the tool names built in T9/T10 (`market_snapshot`,`daily_bars`,`latest_decisions`,`view_*`,`search_episodes`,`decide`) — the subset lint's source of truth; `build_sonia_registry(h, *, source_factory=None)` signature consistent T9→T10.
