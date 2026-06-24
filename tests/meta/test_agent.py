from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.llm.client import MockLLMClient
from alpha.meta.agent import MetaAgent
from alpha.meta.models import ProposedEdit
from alpha.meta import prompts


def test_render_brain_summary_lists_redlines_and_skills():
    h = load_seeds("seeds")
    s = prompts.render_brain_summary(h)
    assert "RED-LINE" in s and any(sk.skill_id in s for sk in h.skills.all()[:1])


def test_parse_directions_tolerant_and_assigns_ids():
    raw = '{"directions": [{"title": "lean into squeezes", "summary": "s", "target_kinds": ["skills"]}, {"bad": 1}]}'
    out = prompts.parse_directions(raw)
    assert len(out) == 1 and out[0].title == "lean into squeezes" and out[0].direction_id
    assert prompts.parse_directions("not json") == []


def test_apply_mutates_live_brain_and_marks_rows():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    tools = MetaTools(h0, EditLog())
    agent = MetaAgent(tools, MockLLMClient("{}"))
    e = ProposedEdit(edit_id="e1", tool="patch_skill", target_id=sid,
                     args={"skill_id": sid, "notes": "applied now"}, rationale="r", status="accepted")
    applied, rows = agent.apply([e])
    assert len(applied) == 1 and h0.skills.get(sid).notes == "applied now"
    assert rows[0].status == "applied" and rows[0].applied_seq == 0 and len(tools.log) == 1
