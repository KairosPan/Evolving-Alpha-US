# Phase 0 Spike — Hermes vendor feasibility

Pinned Hermes commit: 5add283ec8e7a33110a9051179208bd50bda427c
Clone (gitignored): ./_hermes/

Clone method: git clone --depth 1 (network confirmed working; full clone succeeded)

Target file paths verified at expected locations:
- _hermes/tools/registry.py
- _hermes/hermes_state.py
- _hermes/agent/conversation_loop.py

Run the integration proof:   python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/ -v
Run the coupling analysis:   python spikes/2026-06-26-hermes-vendor-feasibility/coupling.py

GO/NO-GO and the §8 vendor-tracking recommendation live in FINDINGS.md.
