"""On-disk result cache for the slow snapshot-walk MCP tools (screen, breadth).

Modeled on scripts/face_data.py's market cache: one JSON file per (bed, producer code
version, day, result name), living OUTSIDE any bed — a bed's identity is its CHECKSUMS
manifest, built from an rglob of the bed root, so a cache dropped inside would make the
bed report dirty. `data/` is gitignored wholesale. Module-relative, never cwd-relative,
which assumes the editable-install layout this repo pins (the package sits in the repo
root with `data/` beside it — the same posture scripts/face_data.py takes).

The producer of a screen result is not one module but a package chain (mcp/tools ->
universe -> features -> pit/source/firewall), so `code_hash` digests EVERY alpaca_kit
.py file: an edit anywhere invalidates every entry. That over-invalidates — an
account.py edit rebuilds screens too — but a rebuild costs one recompute (~3 min/day on
the 2yr bed) while a stale hit under changed code is a wrong answer. Like the face
cache, the key trusts a captured bed to be static: recapturing a bed IN PLACE without
touching alpaca_kit would serve the old entries, so delete data/.screen_cache after a
recapture.

PIT: entries are keyed by the screened day, and the caller must run its lookahead check
BEFORE consulting the cache (tools.py hoists guard.check(day) above the read) — a hit
can then never show an earlier as_of cursor a day it could not have computed itself.
Failures are never cached: fail-soft must not become fail-sticky.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import tempfile
from datetime import date as Date
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]           # alpaca_kit/
CACHE_DIR = _PACKAGE_ROOT.parent / "data" / ".screen_cache"   # repo data/, outside any bed


def _short_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


@functools.lru_cache(maxsize=1)
def _package_hash() -> str:
    """Digest of the whole package's source, computed once per process: the hash must
    describe the code this process LOADED, not whatever lands on disk mid-run (the MCP
    server is long-lived and editable-installed)."""
    h = hashlib.sha256()
    for p in sorted(_PACKAGE_ROOT.rglob("*.py")):
        h.update(str(p.relative_to(_PACKAGE_ROOT)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:8]


def code_hash() -> str:
    return _package_hash()


def cache_path(pit_root, name: str, day: Date) -> Path:
    """One file per (bed, code version, day, result name). The bed keys by a hash of its
    RESOLVED path, so two beds never collide and a relative/absolute spelling of the same
    bed hits the same entry. `name` separates results computed for the same day
    (screen-gainer / screen-trend_template / breadth)."""
    root_hash = _short_sha(str(Path(pit_root).resolve()).encode())
    return CACHE_DIR / f"{name}-{root_hash}-{code_hash()}-{day.isoformat()}.json"


def read(path: Path):
    """The cached payload, or None when it is absent, unreadable, corrupt or not a
    payload-shaped object (in which case the caller recomputes and overwrites it)."""
    try:
        cached = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return cached if isinstance(cached, dict) else None


def write(path: Path, payload: dict) -> None:
    """Atomic write: a reader must never see a truncated cache file. A cache that cannot
    be written is logged to stderr and otherwise ignored — the payload in hand is good,
    and failing the tool call over the cache would be the worse trade."""
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, default=str, allow_nan=False)
        os.replace(tmp, path)
        tmp = None
    except (OSError, TypeError, ValueError) as exc:
        print(f"alpaca_kit.mcp: screen cache not written ({exc})", file=sys.stderr)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
