# Vendored Hermes — provenance

- **Upstream:** NousResearch/hermes-agent (MIT).
- **Pinned commit:** `5add283ec8e7a33110a9051179208bd50bda427c`
- **What is vendored:** ONLY `tools/registry.py` (the central tool registry — an eager
  leaf: 1 file / 589 LOC, no `agent/` package drag, measured by the Phase-0 spike
  `spikes/2026-06-26-hermes-vendor-feasibility/COUPLING.md`).
- **Why reference-only:** the active tool-registry code path is
  `alpha/converse/registry.py` (a 28-LOC reimplementation). This committed copy is the
  audit / provenance anchor and the schema source-of-truth that the parity test
  (`tests/converse/test_registry_parity.py`) checks the reimpl against. We do NOT import
  this file in production.
- **Upstream-tracking policy (parent spec §8):** **hard-pin this SHA; do not track upstream.**
  Hermes is a ~2 579-file daily-moving monolith; the narrow waist we depend on
  is the tool-calling *schema contract*, not the code. Only bump deliberately, and when you
  do, re-run the Phase-0 coupling measurement
  (`spikes/2026-06-26-hermes-vendor-feasibility/coupling.py`) as a gating check.
