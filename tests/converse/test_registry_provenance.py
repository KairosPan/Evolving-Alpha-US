"""A7 (charter First Founding Principle: "Kairos does not propose at all"): the worker face
registers NO H-mutation tool — the staging tool was retired (as live-landing was in 2026-07-09).
write_mode="apply" still raises (never silently downgrade); any other mode registers only compute
tools."""
import pytest

import alpha.converse.agent as agent_mod
from alpha.harness.loader import load_seeds


def test_apply_mode_is_retired_and_raises():
    with pytest.raises(ValueError, match="retired"):
        agent_mod.build_converse_registry(load_seeds("seeds"), None, None, write_mode="apply")


def test_default_mode_registers_no_propose_tool():
    # A7: "stage" no longer registers a brain-edit tool — the worker only decides.
    reg = agent_mod.build_converse_registry(load_seeds("seeds"), None, None)
    assert {s["name"] for s in reg.specs()} == {"decide"}


def test_read_only_registers_only_decide():
    reg = agent_mod.build_converse_registry(load_seeds("seeds"), None, None, read_only=True)
    assert {s["name"] for s in reg.specs()} == {"decide"}
