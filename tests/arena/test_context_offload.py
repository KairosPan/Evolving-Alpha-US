"""A3 PART 1 — content-addressed offload store + T0 recall tool through the choke point."""
from __future__ import annotations

from alpha.arena.context import OffloadStore, make_recall_tool
from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry


def test_offload_round_trip_content_addressed(tmp_path):
    store = OffloadStore(tmp_path)
    h1 = store.put("hello world")
    h2 = store.put("hello world")
    assert h1 == h2                                  # content-addressed: same content, same hash
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)
    assert store.get(h1) == "hello world"


def test_offload_blobs_live_inside_workspace(tmp_path):
    store = OffloadStore(tmp_path)
    h = store.put("payload")
    blob = tmp_path / ".offload" / f"{h}.txt"
    assert blob.exists()
    assert blob.resolve().is_relative_to(tmp_path.resolve())   # rooted INSIDE the workspace


def test_offload_get_rejects_path_escape(tmp_path):
    """The recall tool feeds a MODEL-supplied hash — a traversal / non-hex hash must NOT read
    outside the store (path-guard, no escape)."""
    store = OffloadStore(tmp_path)
    # plant a secret outside the .offload root
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    assert store.get("../secret") is None
    assert store.get("../../etc/passwd") is None
    assert store.get("not-a-hash") is None
    assert store.get("") is None
    assert store.get("A" * 64) is None               # uppercase is not the [0-9a-f] alphabet


def test_offload_get_unknown_hash_is_none(tmp_path):
    store = OffloadStore(tmp_path)
    assert store.get("0" * 64) is None


def test_recall_tool_is_t0_and_flows_through_choke_point(tmp_path):
    store = OffloadStore(tmp_path)
    h = store.put("the elided span")
    schema, fn, tier = make_recall_tool(store)
    assert tier == CapabilityTier.T0_OBSERVE
    assert schema["name"] == "recall"

    reg = ToolRegistry()
    reg.register("recall", schema, fn)
    pol = ActivityPolicy(reg, {"recall": tier})

    ok = pol.dispatch("recall", {"hash": h})
    assert ok == {"ok": True, "content": "the elided span"}
    miss = pol.dispatch("recall", {"hash": "0" * 64})
    assert miss["ok"] is False


def test_recall_untiered_is_fail_closed(tmp_path):
    """A recall tool NOT registered in the tier map is not callable — the no-bypass guarantee."""
    store = OffloadStore(tmp_path)
    schema, fn, _ = make_recall_tool(store)
    reg = ToolRegistry()
    reg.register("recall", schema, fn)
    pol = ActivityPolicy(reg, {})                    # no tier registered
    out = pol.dispatch("recall", {"hash": "0" * 64})
    assert "error" in out and "no tier" in out["error"]
