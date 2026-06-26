# spikes/2026-06-26-hermes-vendor-feasibility/conftest.py
import os, sys
sys.path.insert(0, os.path.dirname(__file__))  # so spike tests can `import spike_loop`, etc.

# The vendored Hermes clone (_hermes/, gitignored) ships its own test suite that
# errors on uninstalled deps (e.g. `acp`); never collect it as part of the spike.
collect_ignore = ["_hermes"]
collect_ignore_glob = ["_hermes/*"]
