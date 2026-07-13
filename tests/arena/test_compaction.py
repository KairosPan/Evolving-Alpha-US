"""A3 PART 1 — 4-phase compaction with protected bookends + provenance-preserving pruning."""
from __future__ import annotations

import json

from alpha.arena.context import (FakeSummarizer, OffloadStore, compact_messages, elided_hashes)
from alpha.llm.chat import ChatMessage


def _msgs(n: int) -> list[ChatMessage]:
    out = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        origin = "user" if role == "user" else "model"    # principal-origin stamp, not the role
        out.append(ChatMessage(role=role, text=f"message number {i}", origin=origin))
    return out


def test_under_threshold_is_byte_identical(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(5)
    out = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                           protect_head=1, protect_tail=3, threshold=10)
    assert out is msgs                               # untouched (same object): byte-identical


def test_threshold_none_is_byte_identical(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(50)
    out = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                           protect_head=1, protect_tail=3, threshold=None)
    assert out is msgs                               # threshold None → dormant


def test_no_middle_to_compact_is_identity(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(4)
    out = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                           protect_head=2, protect_tail=2, threshold=3)
    assert out is msgs                               # head+tail cover everything → nothing to elide


def test_compaction_protects_bookends_and_elides_middle(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(12)
    out = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                           protect_head=1, protect_tail=4, threshold=6)
    # head bookend (turn-0 task) preserved byte-identical
    assert out[0] == msgs[0]
    # tail bookend (last-4) preserved byte-identical
    assert out[-4:] == msgs[-4:]
    # exactly one kernel-origin summary+marker replaces the middle
    assert len(out) == 1 + 1 + 4
    note = out[1]
    assert note.origin == "kernel"
    assert "[context-compacted]" in note.text


def test_pruning_leaves_a_recoverable_handle_not_a_silent_drop(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(12)
    out = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                           protect_head=1, protect_tail=4, threshold=6)
    note = out[1]
    hashes = elided_hashes(note.text)
    assert len(hashes) == 1                          # the marker carries a recall hash
    # the offloaded span round-trips to the ORIGINAL middle messages, verbatim
    recovered = json.loads(store.get(hashes[0]))
    middle = msgs[1:-4]
    assert recovered == [m.model_dump() for m in middle]


def test_compaction_is_deterministic_offline(tmp_path):
    store = OffloadStore(tmp_path)
    msgs = _msgs(12)
    a = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                         protect_head=1, protect_tail=4, threshold=6)
    b = compact_messages(msgs, summarizer=FakeSummarizer(), offload_store=store,
                         protect_head=1, protect_tail=4, threshold=6)
    assert [m.model_dump() for m in a] == [m.model_dump() for m in b]
