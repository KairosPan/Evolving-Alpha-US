"""Route smoke + data-binding contract: every page returns 200 and renders the real brain content.
HTMX filter requests return just the list partial (no chrome)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.parametrize("path", ["/", "/deck", "/doctrine", "/memory", "/skills", "/workflow", "/connector", "/subagent", "/decisions", "/verdict", "/evolution"])
def test_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!doctype html>" in r.text.lower()


def test_dashboard_shows_brain_counts_and_the_phase_cycle(client):
    body = client.get("/deck").text            # deck moved from / to /deck
    assert "16" in body and "12" in body          # skills / doctrine counts
    for phase in ("Washout", "Recovery", "Ignition", "Trend", "Distribution", "Flush"):
        assert phase in body                       # the six-phase cycle is on the deck


def test_doctrine_page_shows_a_real_redline(client):
    body = client.get("/doctrine").text
    assert "stop_discipline" in body or "The stop is the plan" in body
    assert "immutable" in body.lower()


def test_skills_filter_returns_partial_for_htmx(client):
    full = client.get("/skills")
    assert "<html" in full.text.lower()
    partial = client.get("/skills?family=meme", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text.lower()      # fragment only
    assert "Short Squeeze" in partial.text          # a meme skill
    assert "Gap and Go" not in partial.text         # a runner skill is filtered out


def test_memory_filter_by_outcome_partial(client):
    partial = client.get("/memory?outcome=loss", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text.lower()


def test_decisions_page_renders_sample_ticket(client):
    body = client.get("/decisions").text
    assert "sample" in body.lower()                  # honest badge
    # a size tier and the portfolio risk surface
    assert any(t in body.lower() for t in ("probe", "core", "heavy"))


def test_decisions_page_shows_narrative_and_netted_exposure(client):
    body = client.get("/decisions").text
    assert "ai-compute" in body          # the shared narrative (chip + correlated group)
    assert "Netted exposure" in body     # L3 netting surfaced


def test_verdict_page_renders(client):
    body = client.get("/verdict").text
    assert "HCH" in body and "Hexpert" in body


# ── real-artifact path (ALPHA_WEB_DECISION / ALPHA_WEB_VERDICT) ────────────────
def test_decisions_handles_no_trade_package(client, tmp_path, monkeypatch):
    """A baseline / parse-failure package has regime=None, portfolio=None, no candidates — it must
    render, not 500 (the bug the review caught)."""
    from datetime import date
    from alpha.eval.decision import DecisionPackage
    pkg = DecisionPackage(date=date(2026, 1, 5), no_trade_reason="no gainers — washout tape")
    f = tmp_path / "decision.json"
    f.write_text(pkg.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200
    assert "no gainers — washout tape" in r.text
    assert "no-trade" in r.text.lower()
    assert "Sample package" not in r.text


def test_decisions_renders_growth_market_clock_regime(client, tmp_path, monkeypatch):
    """P2: a growth-pack DecisionPackage carries a non-canonical market-clock phase
    ("market:confirmed_uptrend"), which is NOT in the six-phase PHASE_BY_KEY. The console must render
    it (the growth token as the pill label), not 500 on the unmapped phase_by_key lookup."""
    from datetime import date
    from alpha.eval.decision import Candidate, DecisionPackage
    from alpha.regime.classifier import RegimeRead
    pkg = DecisionPackage(date=date(2026, 1, 5), candidates=[Candidate(symbol="NVDA")],
                          regime=RegimeRead(phase="market:confirmed_uptrend", confidence=0.6,
                                            frontside=True, risk_gate=0.6))
    f = tmp_path / "decision.json"
    f.write_text(pkg.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200
    assert "market:confirmed_uptrend" in r.text and "frontside" in r.text


def test_deck_dashboard_renders_growth_market_clock_phase(client, monkeypatch):
    """P2 fix #5: the /deck ring + tagline lookups must degrade for a non-canonical market-clock phase
    (defensive — the ring is momo-shaped; a growth instrument is deferred). Inject a growth regime and
    assert 200 (the ring/tagline guards render the raw token rather than 500 on phase_by_key)."""
    from alpha.regime.classifier import RegimeRead
    from alpha_web import sample
    monkeypatch.setattr(sample, "sample_regime",
                        lambda: RegimeRead(phase="market:confirmed_uptrend", confidence=0.6,
                                           frontside=True, risk_gate=0.6))
    r = client.get("/deck")
    assert r.status_code == 200
    assert "market:confirmed_uptrend" in r.text


def test_real_decision_artifact_renders_without_sample_badge(client, tmp_path, monkeypatch):
    from alpha_web import sample
    f = tmp_path / "decision.json"
    f.write_text(sample.sample_decision().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200 and "GPUX" in r.text and "Sample package" not in r.text


def test_malformed_decision_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "bad.json"
    f.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200 and "wired artifact" in r.text


def test_malformed_verdict_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "bad.json"
    f.write_text("definitely not json", encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "wired artifact" in r.text


def test_wrong_shape_verdict_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "v.json"
    f.write_text('{"arms": {}}', encoding="utf-8")     # valid JSON, missing required keys
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "wired artifact" in r.text


# ── decisions store browsing (ALPHA_WEB_DECISIONS_DIR) ─────────────────────────
def _store_with(tmp_path, rows):
    from alpha.eval.decision import Candidate, DecisionPackage
    from alpha.eval.decision_store import DecisionStore
    store = DecisionStore(tmp_path)
    for d, sym in rows:
        store.put(DecisionPackage(date=d, candidates=[Candidate(symbol=sym, pattern="gap_and_go",
                                                                size_tier="probe")]))
    return store


def test_decisions_store_defaults_to_latest_and_lists_dates(client, tmp_path, monkeypatch):
    from datetime import date
    _store_with(tmp_path, [(date(2026, 2, 2), "AAA"), (date(2026, 2, 3), "BBB"), (date(2026, 2, 4), "CCC")])
    monkeypatch.setenv("ALPHA_WEB_DECISIONS_DIR", str(tmp_path))
    r = client.get("/decisions")
    assert r.status_code == 200 and "Sample package" not in r.text
    assert "CCC" in r.text and "2026-02-04" in r.text     # latest is shown
    assert "2026-02-02" in r.text and "2026-02-03" in r.text   # all dates offered in the picker


def test_decisions_store_selects_requested_date(client, tmp_path, monkeypatch):
    from datetime import date
    _store_with(tmp_path, [(date(2026, 2, 2), "AAA"), (date(2026, 2, 4), "CCC")])
    monkeypatch.setenv("ALPHA_WEB_DECISIONS_DIR", str(tmp_path))
    r = client.get("/decisions?date=2026-02-02")
    assert r.status_code == 200 and "AAA" in r.text and "CCC" not in r.text


def test_single_decision_file_overrides_the_store(client, tmp_path, monkeypatch):
    from datetime import date
    from alpha.eval.decision import Candidate, DecisionPackage
    _store_with(tmp_path / "store", [(date(2026, 2, 2), "DIRX")])
    f = tmp_path / "one.json"
    f.write_text(DecisionPackage(date=date(2026, 9, 9),
                                 candidates=[Candidate(symbol="FILEX", pattern="x")]).model_dump_json(),
                 encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISIONS_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200 and "FILEX" in r.text and "DIRX" not in r.text


def test_decisions_renders_corp_blind_note(client, tmp_path, monkeypatch):
    # P3: a persisted package's corp-actions blind note (a plain key_risks string) round-trips through
    # DecisionStore and renders in the console key_risks list without breaking the page.
    from datetime import date
    from alpha.eval.decision import Candidate, DecisionPackage
    from alpha.eval.decision_store import DecisionStore
    from alpha.guard.screen import CORP_BLIND_NOTE
    DecisionStore(tmp_path).put(DecisionPackage(
        date=date(2026, 3, 3), candidates=[Candidate(symbol="GAIN", pattern="gap_and_go")],
        key_risks=[CORP_BLIND_NOTE]))
    monkeypatch.setenv("ALPHA_WEB_DECISIONS_DIR", str(tmp_path))
    r = client.get("/decisions")
    assert r.status_code == 200 and "guard ran blind" in r.text


# ── verdict store browsing (ALPHA_WEB_VERDICTS_DIR) ────────────────────────────
def test_verdict_store_browse_by_run(client, tmp_path, monkeypatch):
    import json
    from alpha_web import sample
    from alpha.eval.verdict_store import VerdictStore
    store = VerdictStore(tmp_path)
    a = sample.sample_verdict(); a["headline"]["hch_minus_hexpert"] = 0.0111
    b = sample.sample_verdict(); b["headline"]["hch_minus_hexpert"] = -0.0222
    store.put("2026Q1", a)
    store.put("2026Q2", b)
    monkeypatch.setenv("ALPHA_WEB_VERDICTS_DIR", str(tmp_path))
    r = client.get("/verdict")
    assert r.status_code == 200 and "Sample verdict" not in r.text
    assert "2026Q1" in r.text and "2026Q2" in r.text          # picker lists both runs
    assert "-0.0222" in r.text                                 # latest (2026Q2) shown by default
    r1 = client.get("/verdict?run=2026Q1")
    assert r1.status_code == 200 and "+0.0111" in r1.text


def test_verdict_null_stat_fields_render(client, tmp_path, monkeypatch):
    # a real "insufficient" verdict has null ci/p/mde — must render n/a, not 500
    import json
    from alpha_web import sample
    v = sample.sample_verdict()
    v["stat_verdict"] = {"verdict": "insufficient", "n_days": 0, "mean_diff": 0.0,
                         "ci_low": None, "ci_high": None, "p_value": None, "mde": None}
    f = tmp_path / "v.json"
    f.write_text(json.dumps(v), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "insufficient" in r.text and "n/a" in r.text


def test_single_verdict_file_overrides_dir(client, tmp_path, monkeypatch):
    import json
    from alpha_web import sample
    from alpha.eval.verdict_store import VerdictStore
    VerdictStore(tmp_path / "store").put("dirrun", sample.sample_verdict())
    one = sample.sample_verdict(); one["headline"]["hch_minus_hexpert"] = 0.0777
    f = tmp_path / "one.json"
    f.write_text(json.dumps(one), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_VERDICTS_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "+0.0777" in r.text and "dirrun" not in r.text


def test_run_verdict_json_output_renders_in_console(client, tmp_path, monkeypatch):
    # end-to-end: run_verdict (offline) -> comparison_to_view -> file -> console renders it cleanly
    import sys, json
    import pandas as pd
    from datetime import date
    from pathlib import Path
    from alpha.data.source import FakeSource
    from alpha.llm.client import MockLLMClient
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import run_verdict as rv

    n = 6
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    src = FakeSource(calendar=cal, bars=bars, snapshots=snaps)
    cr = rv.run_verdict(src, cal[0], cal[-1],
                        agent_llm_factory=lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'))
    view = rv.comparison_to_view(cr, start=cal[0], end=cal[-1], horizon=2, screen=True)
    f = tmp_path / "v.json"
    f.write_text(json.dumps(view), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "wired artifact" not in r.text and "HCH" in r.text


# ── evolution / edit-log view (ALPHA_WEB_EVOLUTION) ────────────────────────────
def test_evolution_shows_sample_edits(client):
    body = client.get("/evolution").text
    assert "sample" in body.lower()                         # honest badge
    assert "promote" in body and "short_squeeze" in body    # a sample edit + its target
    assert "Refine passes" in body                          # run summary


def test_evolution_wired_file_renders(client, tmp_path, monkeypatch):
    import json
    evo = {"window": {"start": "2026-01-02", "end": "2026-01-31"},
           "summary": {"refines": 1, "breaker_trips": 0, "frozen_from": None, "n_edits": 1},
           "edits": [{"seq": 0, "tool": "promote_skill", "target_kind": "skill", "target_id": "base_breakout",
                      "op": "promote", "summary": "incubating → active", "payload": None,
                      "rationale": "earned promotion"}]}
    f = tmp_path / "evo.json"
    f.write_text(json.dumps(evo), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_EVOLUTION", str(f))
    r = client.get("/evolution")
    assert r.status_code == 200 and "base_breakout" in r.text and "Sample evolution" not in r.text


def test_evolution_empty_edits_renders_held_steady(client, tmp_path, monkeypatch):
    import json
    evo = {"window": {"start": "2026-01-02", "end": "2026-01-05"},
           "summary": {"refines": 0, "breaker_trips": 0, "frozen_from": None, "n_edits": 0}, "edits": []}
    f = tmp_path / "evo.json"
    f.write_text(json.dumps(evo), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_EVOLUTION", str(f))
    r = client.get("/evolution")
    assert r.status_code == 200 and "held steady" in r.text.lower()


def test_evolution_malformed_falls_back(client, tmp_path, monkeypatch):
    f = tmp_path / "bad.json"
    f.write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_EVOLUTION", str(f))
    r = client.get("/evolution")
    assert r.status_code == 200 and "wired artifact" in r.text


# ── brain accordion group ──────────────────────────────────────────────────────
def test_brain_group_lists_six_children_in_order(client):
    body = client.get("/").text
    # The six brain components appear, in the spec order, as sub-item links.
    order = ["/doctrine", "/memory", "/workflow", "/skills", "/connector", "/subagent"]
    positions = [body.index(f'href="{p}"') for p in order]
    assert positions == sorted(positions)                 # strictly increasing == in order
    assert 'class="nav-group' in body                     # the drawer group is rendered
    assert "Brain" in body


def test_brain_drawer_auto_expands_only_on_brain_pages(client):
    open_body = client.get("/doctrine").text              # doctrine is a brain component
    assert "nav-group is-open" in open_body
    assert 'aria-expanded="true"' in open_body
    collapsed = client.get("/deck").text                  # deck is NOT a brain component
    assert "nav-group is-open" not in collapsed
    assert 'aria-expanded="false"' in collapsed


def test_active_brain_child_is_marked(client):
    body = client.get("/memory").text
    assert 'class="nav-subitem is-active"' in body        # the open drawer highlights Memory


@pytest.mark.parametrize("path,title,needle", [
    ("/workflow", "Workflow", "playbooks"),
    ("/connector", "Connector", "connections"),
    ("/subagent", "Subagent", "sub-agents"),
])
def test_brain_stub_pages_render_readonly(client, path, title, needle):
    r = client.get(path)
    assert r.status_code == 200
    assert "<!doctype html>" in r.text.lower()             # full page, not a fragment
    assert title in r.text                                 # component name
    assert needle in r.text                                # the one-line blurb
    assert "not yet built" in r.text.lower()               # honest read-only empty state
    assert "nav-group is-open" in r.text                   # opens under the Brain drawer
