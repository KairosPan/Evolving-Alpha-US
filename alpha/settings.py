"""Frozen app-layer settings: THE single definition of env names + defaults (mining §2.7).

Consumption tiers: producer scripts construct Settings.from_env() ONCE in main() and
thread values down; services construct per call inside their store/client helpers —
that per-call timing is load-bearing (tests/web's module-scoped client and the autouse
brain_session_isolation fixture set env AFTER app creation); a boot-time freeze is
deferred until the fixture strategy changes.

Exemptions (deliberate): secrets (APCA_*/DEEPSEEK_*/ANTHROPIC_*) stay at client/source
construction with their lazy RuntimeError-naming-the-var behavior — the offline suite
needs no keys; alpha/llm/config.py's per-role reads stay put (already a central point);
ALPHA_UNSAFE_AUTONOMOUS stays duplicated in the two evolution scripts (the friction is
the point); __main__ host/port uvicorn args stay inline.

Co-flip couplings: the five brain-state dirs (live_brain_dir/sessions_dir/projects_db/
conflicts_dir/proposals_dir) move together — the cross-face reconcile sweep opens the
OTHER face's stores (see tests/conftest.py::brain_session_isolation); workspace_dir ×
live_brain_dir feed the workbench boot assert and must resolve the same way its stores do.
"""
from __future__ import annotations

import os
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

# the evolution scripts' default episodes DB (save_decisions deliberately has NO default)
EVOLUTION_EPISODES_DB_DEFAULT = "./state/brain.db"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    live_brain_dir: str = "./state/brain"
    sessions_dir: str = "./state/sessions"
    projects_db: str = "./state/projects/state.db"
    conflicts_dir: str = "./state/conflicts"
    proposals_dir: str = "./state/proposals"  # mirror only; alpha/meta/proposal_store.proposals_dir() is authoritative (TCB file, reads env itself)
    workspace_dir: str = "./state/workspaces"
    episodes_db: str | None = None
    sonia_url: str = "http://127.0.0.1:8810"
    workbench_url: str = "http://127.0.0.1:8820"
    data_source: str = "alpaca"
    pit_root: str | None = None
    data_feed: str = "iex"
    # alpha_web: absence is load-bearing (None -> frozen seeds / badged SAMPLE)
    web_live_brain_dir: str | None = None
    web_decision: str | None = None
    web_decisions_dir: str | None = None
    web_verdict: str | None = None
    web_verdicts_dir: str | None = None
    web_evolution: str | None = None

    _ENV: ClassVar[dict[str, str]] = {
        "live_brain_dir": "ALPHA_LIVE_BRAIN_DIR",
        "sessions_dir": "ALPHA_SESSIONS_DIR",
        "projects_db": "ALPHA_PROJECTS_DB",
        "conflicts_dir": "ALPHA_CONFLICTS_DIR",
        "proposals_dir": "ALPHA_PROPOSALS_DIR",
        "workspace_dir": "ALPHA_WORKSPACE_DIR",
        "episodes_db": "ALPHA_EPISODES_DB",
        "sonia_url": "ALPHA_SONIA_URL",
        "workbench_url": "ALPHA_WORKBENCH_URL",
        "data_source": "ALPHA_DATA_SOURCE",
        "pit_root": "ALPHA_PIT_ROOT",
        "data_feed": "ALPHA_DATA_FEED",
        "web_live_brain_dir": "ALPHA_LIVE_BRAIN_DIR",
        "web_decision": "ALPHA_WEB_DECISION",
        "web_decisions_dir": "ALPHA_WEB_DECISIONS_DIR",
        "web_verdict": "ALPHA_WEB_VERDICT",
        "web_verdicts_dir": "ALPHA_WEB_VERDICTS_DIR",
        "web_evolution": "ALPHA_WEB_EVOLUTION",
    }

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        return cls(**{f: env[v] for f, v in cls._ENV.items() if v in env})
