# Completing the Body: H = (p, K, M, C, W, A) + Sonia's observe loop (design)

Date: 2026-07-16 · Status: approved by user (brainstorm session) · Calibrated against a
4-system comparison study (Claude Code / Codex / Hermes / this repo — see Appendix).

## Goal

Build the three declared-but-stubbed Brain components — **connector (C)**, **workflow (W)**,
**subagent (A)** — as real, gated parts of H (the Body), in one arc, using one shared
integration pattern; and give **Sonia a bounded observe-tier tool loop** (market visibility
granted by the alpaca connector entry, plus two-tier progressive disclosure over the brain).

## User-confirmed decisions

| Question | Decision |
|---|---|
| Sonia's market visibility | Full tool loop (observe tier), not prompt injection |
| Connector placement | Inside gated H — H is the Body; (p,K,M) is current shape, not a ceiling |
| Scope | One shot: all three components (C/W/A) — the Brain drawer's six slots become real |
| W/A effect level this arc | Declarative: stored, editable, evolvable, prompt-visible; **executors deferred** |
| Format calibration | Follow the mainstream convergent patterns (comparison study, Appendix) |

## Charter / TCB constraints (binding)

- **Data rung only (R1/R2).** All three new components are declarative data. A connector
  entry references only operator-registered implementations; entries carry **no URLs, no
  credential values, no executable content** — an entry edit can never be a capability grant.
  Credentials stay in env (entries may name env **keys**); code stays in the operator-owned
  registries (`make_source` / `make_client`).
- **One waist.** All edits to C/W/A go through `alpha/refine/apply.py::try_apply_op` with the
  same provenance/governance machinery (worker-propose refusal, user_direct floors, conflict
  holds). No second gate, no per-component style.
- **Subagent execution stays deferred** — `PASS_TOOLS["G"]` remains a reserved empty pass;
  entries are dispatch-READY state, dispatch mechanics are a later arc (US-2/R3 boundary).
- **Verdict symmetry untouched.** decide() keeps its full always-in-prompt render (byte-identical
  across arms). Two-tier disclosure applies to the conversational faces only.

## Entry models (field-level; all Pydantic, `extra='forbid'`, house style)

### ConnectorEntry (`alpha/harness/connectors.py`)

```python
connector_id: str                 # unique key, lowercase-hyphen
name: str
kind: Literal["data_source", "llm_role", "mcp"]
impl_ref: str                     # registry key: make_source name | make_client role | future MCP id
capabilities: list[str]           # e.g. ["bars", "snapshots", "corp_actions", "calendar"]
env_keys: list[str]               # required env-var NAMES only (e.g. "APCA_API_KEY_ID")
instructions: str                 # <=2000 chars — the ONLY part prompt-rendered
pit_key: str = ""                 # documents the per-connector PIT contract (e.g. "announce_date:=process_date")
enabled: bool = True
required: bool = False
tier: str = "T0_OBSERVE"          # capability tier ceiling for tools this connector grants
domain: str; scope: str; notes: str = ""
```

Waist ops: `write_connector` (upsert) / `patch_connector` / `disable_connector` — **no delete**
(mirrors doctrine's no-destroy bias). Lints at the waist: `impl_ref` must resolve in the live
registry for its `kind`; `env_keys` entries that look like values (contain `=`, length > 64,
key-shaped secrets) are refused; `instructions` char-cap enforced.

### WorkflowEntry (`alpha/harness/workflows.py`) — skill-SHAPED, per the unanimous mainstream verdict

```python
workflow_id: str
name: str
description: str                  # <=200 chars — the always-in-prompt index line
steps: list[WorkflowStep]         # WorkflowStep{ref: str, note: str = ""} — ref = skill_id or free prose
arg_hints: list[str] = []
user_only: bool = True            # side-effectful flows are HUMAN-triggered by default
phases: list[str] = []; domain: str; scope: str
status: Literal["active", "retired"] = "active"
content_hash: str = ""            # computed at apply time; patch = new hash (frozen versions referenceable)
```

Waist ops: `write_workflow` / `patch_workflow` / `retire_workflow`. Lint: every `steps[].ref`
that matches an existing-skill id pattern must exist and be non-retired (referential-integrity
lint, the taboo-lint analog); description char-cap.

### SubagentEntry (`alpha/harness/subagents.py`) — persona STATE only; dispatch mechanics stay in code

```python
subagent_id: str                  # lowercase-hyphen
name: str
description: str                  # <=1536 chars — the ONLY dispatch-routing signal ("use when ...")
system_prompt: str                # the body
llm_role: str = "inherit"         # maps to make_client roles; "inherit" allowed
tools: list[str] = []             # allowlist; lint: subset of the parent-registerable tool names
max_tier: str = "T0_OBSERVE"      # hard ceiling; tighten-only vs dispatching parent
skills_preload: list[str] = []    # skill_ids rendered IN FULL into the child prompt (child has no index loop)
max_turns: int = 8
domain: str; scope: str
status: Literal["active", "retired"] = "active"
notes: str = ""
```

Waist ops: `write_subagent` / `patch_subagent` / `retire_subagent`. Hard-coded (never
per-entry): children never get T3/T4 tools, never delegate (depth=1), child episodes are
tagged `source="subagent"` and excluded from verdict recall by default. (These bind at the
future dispatch layer; the constants and lints land now so entries are dispatch-ready.)

## Shared integration pattern (stamped three times)

1. `HarnessState` gains `connectors` / `workflows` / `subagents` registries — additive fields
   with empty defaults (legacy-dump compatible, the `vocabulary` precedent).
2. brain.json gains one list per component; dumps/loads/snapshots/edit-log follow existing
   serialization paths; US-0 shape-pin tests updated.
3. `EditRecord` gains target_kinds `connector|workflow|subagent`; `try_apply_op` gains the
   op vocabulary + lints above under the SAME provenance rules.
4. `extract_ops`' tool vocabulary gains the new ops → the existing chat → Propose → preview →
   Accept → apply chain works for all three immediately (Sonia can teach a workflow into H).
5. `render_brain_summary` gains budgeted index lines per component (chars-capped).
6. alpha_web: `/connector`, `/workflow`, `/subagent` stub routes become real read-only pages
   rendering the live brain (same pattern as /doctrine).
7. Seeds: C seeds one `alpaca` entry (kind=data_source, impl_ref=alpaca, capabilities
   bars/snapshots/corp_actions/calendar, env_keys APCA_API_KEY_ID/APCA_API_SECRET_KEY,
   pit_key "announce_date:=process_date"); W and A seed EMPTY (grown through teaching).

## Sonia's observe loop

- `SoniaAgent.respond` routes through the existing `run_conversation` dispatch seam with a
  Sonia-scoped ToolRegistry under a fail-closed `ActivityPolicy` (T0 entries only).
- **Market tools, granted by the connector entry** (registered only when the `alpaca` entry is
  `enabled` and its `env_keys` are present in the env — the Body's declaration actually gates
  her perception): `market_snapshot(symbols)`, `daily_bars(symbol, days)`, `latest_decisions()`.
  Missing keys / disabled entry → tool absent or fail-soft error result; chat always works.
- **Brain browse tools (two-tier disclosure, the mainstream convergent pattern)**:
  `view_doctrine(section)`, `view_skill(skill_id)`, `view_lesson(lesson_id)`,
  `view_workflow(workflow_id)`, `view_connector(connector_id)`, `view_subagent(subagent_id)`,
  `search_episodes(query)` — full bodies on demand; the always-in-prompt summary becomes a
  budgeted INDEX (per component: id + one description/trigger line, chars-capped).
- **Full render stays where load-bearing**: `extract_ops` (the op-writer must see exact current
  text) and `decide()` (verdict symmetry) are unchanged.
- Tool turns surface in the cockpit via the existing `origin="tool"` channel.
- sonia service start recipe gains `.env.alpaca` (lazy source construction; absent keys are
  fail-soft, never boot-blocking).
- Live market pulls are teaching context only; no verdict/eval path touches SoniaAgent.

## Explicit deferrals (recorded in ROADMAP)

- Workflow EXECUTOR (engine stepping through steps) and subagent DISPATCH (G pass) — R3/US-2.
- Hooks/cron analog (deterministic lifecycle triggers): today's deterministic layer covers
  pre-action blocking (L4 veto, ActivityPolicy tiers, sizing decorators) but not post-action
  or scheduled events — noted as a gap, not built now.
- Sonia editing brain components other than through the existing propose→accept chain.
- MCP-kind connectors (schema supports the kind; no MCP wiring this arc).

## Error handling

- Corrupt/legacy brain.json (missing new lists) → empty registries, never a load failure.
- Waist lint failures → structured refusal (same shape as existing op refusals).
- Market tool failures (no keys, network, bad symbol) → fail-soft error result into the loop;
  bounded by `run_conversation`'s existing max_iters; chat never 500s (existing boundary).

## Testing (all offline)

- Per-component: model validation (extra='forbid', char caps), registry round-trip through
  dumps/loads/snapshots, waist op happy/refusal paths (impl_ref resolution, env_keys value
  refusal, step referential integrity, tools-subset lint), shape-pin updates.
- extract_ops vocabulary: new ops crystallize + preview + apply through the existing chain.
- Sonia loop: FakeSource-backed market tools; connector-gating (disabled entry → no tool);
  fail-soft on missing keys; two-tier index render budgets; origin="tool" turns.
- UI: three new pages render live-brain entries; empty-state rendering.
- Meta: brain_session_isolation covers all faces (already); full suite stays offline.

## Appendix: comparison-study conclusions that calibrated this design

1. **Workflow is not a first-class type anywhere** (Claude Code merged commands into skills;
   Codex deprecated its separate object; Hermes refuses the type) → WorkflowEntry is
   skill-shaped, `user_only` default, composition-by-reference.
2. **Connector convergent shape = MCP-config-style declarative entry**: impl reference, env-var
   NAMES only, enable flags, short instructions as prompt surface → ConnectorEntry mirrors it,
   plus our `pit_key` (no mainstream analog; our PIT firewall is a deliberate divergence).
3. **Skill/persona triggering = description-as-contract under hard char budgets** (1536ch /
   8k / 60ch across the three) → char-cap lints at the waist; two-tier disclosure for the
   conversational faces; full render retained only for decide()/extract_ops.
4. **Subagent = persona state + description routing + tool restriction (child ⊆ parent,
   depth-bounded, summary-only return)** → SubagentEntry stores state; restrictions land as
   code constants now, dispatch later.
5. **Our gated write-waist + provenance has no mainstream analog** — and Codex independently
   re-invented its essentials for the one component its agent self-writes (memory: proposer →
   consolidator → usage credit → git baseline). Keep the waist; extend it uniformly.
