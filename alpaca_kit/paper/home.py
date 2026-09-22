"""Where a paper book lives: outside the workspace, the way the wallet home is.

``ALPHA_PAPER_HOME`` > ``$DSH_HOME/face/paper`` > ``~/.dsh/face/paper``. The engine is the only
writer of a book; Kairos can read it (the sandbox denies writes outside the workspace, not reads)
and cannot edit it — which is what makes the book a measurement rather than a self-report
(charter D1). A book is one directory per strategy, named as the strategy directory is.
"""
from __future__ import annotations

import os
import unicodedata
from collections.abc import Mapping
from pathlib import Path

MAX_NAME_CODEPOINTS = 41


def paper_home(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    explicit = (env.get("ALPHA_PAPER_HOME") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    dsh = (env.get("DSH_HOME") or "").strip()
    base = Path(dsh).expanduser() if dsh else Path.home() / ".dsh"
    return base / "face" / "paper"


def is_strategy_name(name: str) -> bool:
    """One path segment in the face's channel grammar: opens on a letter or digit, then letters,
    digits, combining marks, ``_`` and ``-``; at most 41 code points; never ``_template`` and never
    a name the face would not list (a leading ``.`` or ``__``)."""
    if not isinstance(name, str) or not name:
        return False
    name = unicodedata.normalize("NFC", name)
    if len(name) > MAX_NAME_CODEPOINTS or name == "_template" or name.startswith("__"):
        return False
    if not name[0].isalnum():
        return False
    for ch in name[1:]:
        if ch in "_-" or ch.isalnum() or unicodedata.category(ch).startswith("M"):
            continue
        return False
    return True


def book_dir(home: Path, strategy: str) -> Path:
    if not is_strategy_name(strategy):
        raise ValueError(f"not a strategy name: {strategy!r}")
    return Path(home) / unicodedata.normalize("NFC", strategy)
