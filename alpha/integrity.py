"""One hashing utility (kairos-mining §6 order-3): file-bytes + canonical-JSON sha256.

Stdlib-only and imports nothing from alpha — any layer (harness, data, meta, scripts)
may use it without cycle risk. canonical_json is THE one canonicalizer for content
hashing (moved here from alpha/meta/proposal_store.py, which re-exports it).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_canonical_json(obj) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))
