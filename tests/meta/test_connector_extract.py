from pathlib import Path

from alpha.harness.loader import load_seeds
from alpha.meta import prompts

# Real momo pack lives directly under seeds/ (the growth pack is seeds_v2/); the brief's
# seeds/momo path does not exist in this tree — adapted to the actual layout.
SEEDS_MOMO = Path(__file__).resolve().parents[2] / "seeds"


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
