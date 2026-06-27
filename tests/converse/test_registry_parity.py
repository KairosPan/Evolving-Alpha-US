import pathlib

ROOT = pathlib.Path(__file__).parents[2]
VENDOR = ROOT / "third_party" / "hermes"
PINNED_SHA = "5add283ec8e7a33110a9051179208bd50bda427c"


def test_vendored_tree_present_and_provenanced():
    assert (VENDOR / "tools" / "registry.py").is_file()
    license_text = (VENDOR / "LICENSE").read_text()
    assert "MIT" in license_text
    prov = (VENDOR / "PROVENANCE.md").read_text()
    assert PINNED_SHA in prov                      # exact pinned commit recorded
    assert "do not track upstream" in prov.lower() # §8 policy recorded
