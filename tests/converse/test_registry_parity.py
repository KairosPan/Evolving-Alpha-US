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


import ast
import sys
import importlib.util
from alpha.converse.registry import ToolRegistry as OurRegistry

VENDORED_FILE = VENDOR / "tools" / "registry.py"


def _load_vendored():
    spec = importlib.util.spec_from_file_location("hermes_vendored_registry", VENDORED_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vendored_leaf_imports_clean_no_monolith():
    """§8 narrow-waist claim: the leaf's top-level (module-level) imports are all stdlib — so
    importing it eagerly drags in NO hermes/agent module (eager footprint = 1, per the Phase-0
    spike). The file's only non-stdlib references (model_tools / tools.budget_config) are LAZY
    imports inside method bodies that fire on hot-path dispatch, never on import — which is why
    `_load_vendored()` below succeeds standalone. We therefore scan only module-level statements
    (tree.body), matching that claim, rather than ast.walk (which would also flag the lazy ones)."""
    tree = ast.parse(VENDORED_FILE.read_text())
    roots = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    nonstd = {r for r in roots if r not in sys.stdlib_module_names}
    assert nonstd == set(), f"vendored leaf has non-stdlib top-level imports: {nonstd}"
    # And it genuinely imports standalone (eager footprint is clean):
    assert _load_vendored() is not None


def test_reimpl_matches_vendored_schema_contract():
    """Our 28-LOC reimpl honors the same tool-calling contract the vendored registry exposes:
    a tool is (name, schema, callable); registration is name-keyed; the provider-facing schema
    is retrievable by name; dispatch is by name."""
    vend = _load_vendored()
    schema = {"name": "ping", "description": "demo",
              "parameters": {"type": "object", "properties": {}}}

    # Vendored: register -> name is known -> schema retrievable by name.
    vr = vend.ToolRegistry()
    vr.register(name="ping", toolset="demo", schema=schema,
                handler=lambda args, **k: "pong", check_fn=None)
    assert "ping" in vr.get_all_tool_names()
    assert vr.get_schema("ping") == schema

    # Our reimpl: same essential contract, narrower surface.
    our = OurRegistry()
    our.register("ping", schema, lambda: "pong")
    assert our.specs() == [schema]      # provider-facing schema list == the registered schema
    assert our.call("ping") == "pong"   # dispatch by name invokes the callable
