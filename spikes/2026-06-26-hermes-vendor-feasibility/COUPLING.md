# Hermes coupling measurement

> **EAGER** = imports that execute on `import` (module top-level only); **TOTAL** = full static footprint including lazy/function-level imports that only fire when those code paths run. Vendor feasibility is driven by the EAGER metric.

## `tools/registry.py`

| Metric | file_count | loc | drags_agent_pkg |
|--------|-----------|-----|-----------------|
| EAGER  | **1** | 589 | **False** |
| TOTAL  | **503** | 432055 | **True** |

- verdict: **liftable (eager leaf)** — candidate for Strategy C vendoring

## `hermes_state.py`

| Metric | file_count | loc | drags_agent_pkg |
|--------|-----------|-----|-----------------|
| EAGER  | **7** | 8825 | **True** |
| TOTAL  | **503** | 432055 | **True** |

- verdict: **eager-coupled** — investigate/sever agent dependency or reimplement

## `agent/conversation_loop.py`

| Metric | file_count | loc | drags_agent_pkg |
|--------|-----------|-----|-----------------|
| EAGER  | **28** | 20906 | **True** |
| TOTAL  | **503** | 432055 | **True** |

- verdict: **eager-coupled** — investigate/sever agent dependency or reimplement
