"""Named LLM stacks + the shared entity-switch state file.

One tiny JSON file (`state/llm_stack.json`, env `ALPHA_LLM_STACK_FILE`) is the single source of
truth for the console's Claude↔DeepSeek switch: `{"sonia": "claude", "kairos": "deepseek"}`.
Every process reads it per `make_client` call (both web faces AND the CLI batch scripts), so a
switch takes effect on the next LLM call — mid-chat-session included — and survives restarts.
Reads are fail-safe (missing/corrupt file or unknown name → fall through to defaults, one warning,
never an exception); writes are atomic (tmp + os.replace). Precedence lives in llm/config.py:
explicit ALPHA_<ROLE>_* env > this file's entity stack > _DEFAULTS.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile

_log = logging.getLogger("alpha.llm.stack")

# Stack name → (provider, model). Defined HERE only. After the Fable-5-on-subscription promo ends
# (2026-07-19), re-point "claude" to claude-opus-4-8 in this one line.
STACKS: dict[str, tuple[str, str]] = {
    "claude": ("claude_sdk", "claude-fable-5"),
    "deepseek": ("openai_compat", "deepseek-chat"),
}

# Role → charter entity. Sonia the teacher owns teaching chat + evolution; Kairos the worker owns
# the decide path + the workbench face.
ROLE_ENTITY: dict[str, str] = {
    "sonia": "sonia",
    "refiner": "sonia",
    "agent": "kairos",
    "converse": "kairos",
}

_DEFAULT_PATH = "./state/llm_stack.json"


def stack_file_path() -> str:
    return os.environ.get("ALPHA_LLM_STACK_FILE", _DEFAULT_PATH)


def read_stacks(path: "str | None" = None) -> dict[str, str]:
    """Entity → stack name from the state file. Fail-safe: any read/parse/shape problem returns {}
    (one warning) so a corrupt file can never take the LLM seam down."""
    p = path or stack_file_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 — corrupt/unreadable file: fall back, loudly once
        _log.warning("llm stack file %s unreadable (%s: %s) — using defaults", p, type(e).__name__, e)
        return {}
    if not isinstance(data, dict):
        _log.warning("llm stack file %s is not a JSON object — using defaults", p)
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def resolve_stack(role: str) -> "tuple[str, str] | None":
    """(provider, model) for the role's entity per the state file, or None to fall through to
    _DEFAULTS. Unknown stack names fall through too (fail-safe forward-compat)."""
    entity = ROLE_ENTITY.get(role)
    if entity is None:
        return None
    name = read_stacks().get(entity)
    if name is None:
        return None
    pair = STACKS.get(name)
    if pair is None:
        _log.warning("unknown llm stack %r for entity %r — using defaults", name, entity)
        return None
    return pair


def write_stacks(stacks: dict[str, str], path: "str | None" = None) -> None:
    """Atomically replace the state file (tmp + os.replace in the same dir — readers only ever see
    a complete old or new file). Caller validates stack names against STACKS."""
    p = path or stack_file_path()
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".llm_stack.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(stacks, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
