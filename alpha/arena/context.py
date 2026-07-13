"""The context-management trio (A3 / charter *Session Is Not the Context Window*).

Long sessions grow the message list without bound. This module separates the two things the
charter keeps apart: **recoverable context storage** (the offload store — the session's job) from
**arbitrary context engineering** (compaction — the loop's job). Bytes are never lost: an elided
span is content-addressed, offloaded inside the Workspace under the path-guard, and recoverable
through a T0 recall tool.

Lives in `alpha/arena` (not converse) so the offload store rides the arena workspace path-guard;
`converse_project` receives the compactor as an INJECTED callable (mirrors `experience_writer`) so
converse never imports arena (AST-pinned layer spine). FakeSummarizer keeps the suite offline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from alpha.arena.contract import CapabilityTier
from alpha.integrity import sha256_bytes
from alpha.llm.chat import ChatMessage

# Provenance-preserving pruning marker (charter/mining, verbatim — note the en-dash). An elided span
# leaves this RECOVERABLE handle, never a silent drop; `recall(hash=…)` fetches the original back.
ELIDED_MARKER = "[...elided – recall hash={hash}]"
_MARKER_RE = re.compile(r"\[\.\.\.elided – recall hash=([0-9a-f]{64})\]")
_HASH_RE = re.compile(r"[0-9a-f]{64}")


def elided_hashes(text: str) -> list[str]:
    """Every recall hash carried by elided markers in *text* (for recovery / idempotency checks)."""
    return _MARKER_RE.findall(text or "")


class OffloadStore:
    """Content-addressed blob store rooted INSIDE a workspace, under the arena path-guard.

    Blobs live at ``<workspace>/.offload/<sha256>.txt``. `get` validates the hash is 64 lowercase
    hex chars AND the resolved path stays inside the store BEFORE any filesystem touch — the recall
    tool feeds a MODEL-supplied hash, so ``get("../../etc/passwd")`` returns None, never an escape.
    ``.offload/`` is internal recoverable storage, never a git-committed workspace artifact.
    """

    def __init__(self, workspace: Path | str) -> None:
        self._root = (Path(workspace).resolve() / ".offload")

    @property
    def root(self) -> Path:
        return self._root

    def _blob_path(self, h: str) -> Path | None:
        if not h or not _HASH_RE.fullmatch(h):
            return None                                   # non-hex / traversal string → refuse
        p = (self._root / f"{h}.txt").resolve()
        try:
            p.relative_to(self._root.resolve())
        except ValueError:
            return None
        return p

    def put(self, text: str) -> str:
        """Store *text*, return its content hash. Same content → same hash (deterministic)."""
        h = sha256_bytes(text.encode("utf-8"))
        self._root.mkdir(parents=True, exist_ok=True)
        p = self._blob_path(h)
        assert p is not None                              # a real sha256 always passes the guard
        p.write_text(text, encoding="utf-8")
        return h

    def get(self, h: str) -> str | None:
        """The offloaded span for *h*, or None (unknown/invalid/escaping hash — fail-closed)."""
        p = self._blob_path(h)
        if p is None or not p.exists():
            return None
        return p.read_text(encoding="utf-8")


@runtime_checkable
class Summarizer(Protocol):
    def summarize(self, messages: list[ChatMessage]) -> str: ...


class FakeSummarizer:
    """Deterministic extractive summary — keeps the offline suite keyless (no LLM). A live LLM
    summarizer is the activation-time swap behind the same `Summarizer` seam."""

    def summarize(self, messages: list[ChatMessage]) -> str:
        parts = []
        for m in messages:
            snippet = (m.text or "").strip().replace("\n", " ")[:40]
            parts.append(f"{m.role}:{snippet}")
        return f"[summary of {len(messages)} elided message(s)] " + " | ".join(parts)


def _serialize(messages: list[ChatMessage]) -> str:
    """Canonical text form of a message span, stored verbatim so recall returns it losslessly."""
    return json.dumps([m.model_dump() for m in messages], ensure_ascii=False)


def compact_messages(messages: list[ChatMessage], *, summarizer: Summarizer,
                     offload_store: OffloadStore, protect_head: int = 1, protect_tail: int = 6,
                     threshold: int | None) -> list[ChatMessage]:
    """4-phase compaction with protected bookends (charter fixed point 5 — assembly is kernel code).

    Entry guard (dormancy): threshold None, or ``len <= threshold``, or no middle to compact →
    return *messages* UNCHANGED (byte-identical when off / under threshold). Otherwise:
      1. Partition — head (turn-0 task) | middle | tail (last-N); the bookends are never touched.
      2. Offload   — content-address + store the middle verbatim (lose bytes not handles).
      3. Summarize — FakeSummarizer/LLM over the middle.
      4. Splice    — head + [one kernel-origin summary+marker message] + tail.
    """
    n = len(messages)
    if threshold is None or n <= threshold or protect_head + protect_tail >= n:
        return messages                                   # Phase 0: off / nothing to compact
    head = messages[:protect_head]                        # Phase 1: partition (protected bookends)
    tail = messages[n - protect_tail:]
    middle = messages[protect_head:n - protect_tail]
    if not middle:
        return messages
    h = offload_store.put(_serialize(middle))             # Phase 2: offload (recoverable by hash)
    summary_text = summarizer.summarize(middle)           # Phase 3: summarize
    note = ChatMessage(                                   # Phase 4: splice (kernel-authored note)
        role="user", origin="kernel",
        text=(f"[context-compacted] {summary_text}\n" + ELIDED_MARKER.format(hash=h)
              + f" — call recall(hash=…) to retrieve the {len(middle)} elided "
                "message(s) verbatim."))
    return head + [note] + tail


def make_recall_tool(offload_store: OffloadStore):
    """T0 recall tool: fetch an offloaded span by hash. Registered in build_arena, dispatched
    through the single ActivityPolicy choke point at T0 (read-only, autonomous)."""
    def recall(hash: str) -> dict:
        content = offload_store.get(hash)
        if content is None:
            return {"ok": False, "error": f"no offloaded span for hash: {hash}"}
        return {"ok": True, "content": content}
    schema = {"name": "recall",
              "description": "Retrieve an elided (offloaded) context span by its recall hash.",
              "parameters": {"type": "object",
                             "properties": {"hash": {"type": "string"}},
                             "required": ["hash"]}}
    return schema, recall, CapabilityTier.T0_OBSERVE
