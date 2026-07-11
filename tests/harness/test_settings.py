"""D2: alpha/settings — THE single definition of app-layer env names + defaults."""
import pytest
from alpha.settings import Settings, EVOLUTION_EPISODES_DB_DEFAULT


def test_defaults_match_todays_literals():
    s = Settings()
    assert s.live_brain_dir == "./state/brain"
    assert s.sessions_dir == "./state/sessions"
    assert s.projects_db == "./state/projects/state.db"
    assert s.conflicts_dir == "./state/conflicts"
    assert s.proposals_dir == "./state/proposals"
    assert s.workspace_dir == "./state/workspaces"
    assert s.data_source == "alpaca" and s.data_feed == "iex"
    assert s.sonia_url == "http://127.0.0.1:8810"
    assert s.workbench_url == "http://127.0.0.1:8820"
    # asymmetric no-defaults are load-bearing (unset -> seeds / SAMPLE / no episode store)
    assert s.web_live_brain_dir is None and s.episodes_db is None
    assert s.web_decision is None and s.web_decisions_dir is None
    assert s.web_verdict is None and s.web_verdicts_dir is None and s.web_evolution is None
    assert s.pit_root is None
    assert EVOLUTION_EPISODES_DB_DEFAULT == "./state/brain.db"


def test_from_env_overrides_and_ignores_unrelated(monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", "/tmp/b")
    monkeypatch.setenv("TOTALLY_UNRELATED", "x")
    s = Settings.from_env()
    assert s.live_brain_dir == "/tmp/b"


def test_frozen_and_forbid():
    s = Settings()
    with pytest.raises(Exception):
        s.live_brain_dir = "/x"          # frozen
    with pytest.raises(Exception):
        Settings(unknown_field="x")      # extra="forbid"
