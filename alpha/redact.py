"""Value-based secret redaction for the persistence waists (kairos-mining §1.5/§4.3).

Key/credential-scoped ONLY: collect the VALUES of env vars whose NAME matches
KEY|SECRET|TOKEN|PASSWORD (>= 8 chars), replace occurrences inside persisted strings
with [REDACTED:<VAR>]. Never pattern-guesses content, never touches market/PIT data;
callers must not route rollback-replay payloads (StagedEdit.op/preview, ProposedEdit)
through it. Ordering invariant for the future integrity chain (A4): redact BEFORE hash.
Stdlib-only, imports nothing from alpha.
"""
from __future__ import annotations

import os
import re

_NAME_RE = re.compile(r"KEY|SECRET|TOKEN|PASSWORD", re.IGNORECASE)
_MIN_LEN = 8


def collect_secrets(env=None) -> dict[str, str]:
    env = os.environ if env is None else env
    return {n: v for n, v in env.items() if _NAME_RE.search(n) and len(v) >= _MIN_LEN}


def redact(obj, secrets: dict[str, str]):
    if isinstance(obj, str):
        for name, value in secrets.items():
            if value in obj:
                obj = obj.replace(value, f"[REDACTED:{name}]")
        return obj
    if isinstance(obj, dict):
        return {k: redact(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, secrets) for v in obj]
    return obj
