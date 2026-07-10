# alpha/arena/ — the activity space (Kairos's tiered tool surface)

A tool catalog with capability tiers + ONE enforcement point. Data rungs R1/R2 only; code-level
self-modification (R3+, the "body axis") is deferred behind a kernel sandbox + immutable-TCB
carve-out — do not add it here.

- **`ActivityPolicy.dispatch` is the single choke point** — fail-closed on any untiered tool,
  blocks autonomous T4. Callers MUST drive the loop via
  `run_conversation(dispatch=policy.dispatch)`; passing the bare registry silently skips ALL
  tier/membrane enforcement (the builder's return comment repeats this — it is load-bearing).
- Tiers (`contract.py`): T0_OBSERVE (`decide`, `read_file`) · T1 (`write_file`) · T2 (`shell`) ·
  T3_BRAIN_EDIT (`propose_memory_edit`, stage-only) · T4 (human-confirm class). `build_arena`
  registers **no order tool** — by design, never add one.
- **`LocalEnv` is NOT a kernel boundary** (stated in its code): the path guard is
  TOCTOU-bypassable, `net` is advisory. The real line is structural — brain dir outside the
  workspace, enforced by the workbench boot assert.
- **Layer spine:** `converse` never imports `arena` (AST-guard test pins it). Injection flows
  the other way: an apps-layer caller passes `registry_factory` into `converse_project`.
- `experience.py` task episodes are **observation-only** (`Episode.kind="task"`): never gated,
  never in `to_dict()`/rollback, never touch `SkillStats`; injected via `experience_writer`.

```bash
python -m pytest tests/arena -q          # scoped tests (offline)
```

*Owner: KairosPan · reviewed 2026-07-10.*
