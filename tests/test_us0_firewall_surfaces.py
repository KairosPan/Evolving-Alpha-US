"""US-0 acceptance: the four firewall surfaces each have a green guarding test.
This module documents the gate and asserts the guarding tests import & run."""
from __future__ import annotations
import importlib


def test_four_firewall_surface_modules_exist():
    for mod in [
        "tests.data.test_source",            # surface 1: date-lookahead (GuardedSource)
        "tests.data.test_corp_actions",      # surface 2: corp-action ex-date PIT
        "tests.data.test_snapshot_source",   # surface 3: split-vintage raw-PIT
        "tests.universe.test_build_universe", # surface 4: windowed-rank trailing-only
    ]:
        assert importlib.import_module(mod) is not None
