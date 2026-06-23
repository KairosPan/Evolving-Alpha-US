from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.llm.client import MockLLMClient
from alpha.meta.agent import MetaAgent
from alpha.meta.models import LessonSource, ProposedDirection, ProposedEdit
from alpha.meta import prompts


def _src():
    return LessonSource(kind="text", title="squeeze writeup", text="High short interest + low float...")


def _agent(scripted):
    h = load_seeds("seeds")
    return MetaAgent(MetaTools(h, EditLog()), MockLLMClient(scripted)), h


def test_render_brain_summary_lists_redlines_and_skills():
    h = load_seeds("seeds")
    s = prompts.render_brain_summary(h)
    assert "RED-LINE" in s and any(sk.skill_id in s for sk in h.skills.all()[:1])


def test_build_directions_prompt_mentions_source_and_asks_json():
    h = load_seeds("seeds")
    system, user = prompts.build_directions_prompt(h, _src(), comment=None)
    assert "directions" in system.lower() and "squeeze writeup" in user


def test_parse_directions_tolerant_and_assigns_ids():
    raw = '{"directions": [{"title": "lean into squeezes", "summary": "s", "target_kinds": ["skills"]}, {"bad": 1}]}'
    out = prompts.parse_directions(raw)
    assert len(out) == 1 and out[0].title == "lean into squeezes" and out[0].direction_id
    assert prompts.parse_directions("not json") == []


def test_propose_directions_parses_cards():
    agent, _ = _agent('{"directions": [{"title": "lean into squeezes"}, {"title": "tighten stops"}]}')
    dirs = agent.propose_directions(_src())
    assert [d.title for d in dirs] == ["lean into squeezes", "tighten stops"]
    assert all(d.direction_id for d in dirs)


def test_expand_to_edits_previews_without_mutating_live_brain():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    scripted = ('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "from article"}, '
                '"rationale": "the article shows this"}]}') % sid
    agent = MetaAgent(MetaTools(h0, EditLog()), MockLLMClient(scripted))
    direction = ProposedDirection(direction_id="d1", title="tighten")
    edits = agent.expand_to_edits(_src(), direction)
    assert len(edits) == 1
    e = edits[0]
    assert e.status == "proposed" and e.op == "update" and e.target_id == sid
    assert e.payload["after"] == {"notes": "from article"}
    assert h0.skills.get(sid).notes != "from article"          # live brain NOT mutated by preview


def test_expand_to_edits_bad_op_becomes_failed_row_not_a_crash():
    agent, _ = _agent('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "nope", "notes": "x"}, "rationale": "r"}]}')
    edits = agent.expand_to_edits(_src(), ProposedDirection(direction_id="d1", title="t"))
    assert len(edits) == 1 and edits[0].status == "failed" and edits[0].apply_reason


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


def test_repropose_edit_replaces_one_row_keeping_id():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    scripted = ('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "revised"}, '
                '"rationale": "operator asked"}]}') % sid
    agent = MetaAgent(MetaTools(h0, EditLog()), MockLLMClient(scripted))
    prior = ProposedEdit(edit_id="keep-me", tool="patch_skill", target_id=sid,
                         args={"skill_id": sid, "notes": "old"}, rationale="r")
    out = agent.repropose_edit(_src(), ProposedDirection(direction_id="d1", title="t"), prior, "make it tighter")
    assert out.edit_id == "keep-me" and out.user_comment == "make it tighter"
    assert out.payload["after"] == {"notes": "revised"} and out.status == "proposed"


def test_repropose_edit_no_op_returns_failed_keeping_id():
    agent, _ = _agent('{"ops": []}')
    prior = ProposedEdit(edit_id="keep-me", tool="patch_skill", args={"skill_id": "x"}, rationale="r")
    out = agent.repropose_edit(_src(), ProposedDirection(direction_id="d1", title="t"), prior, "no")
    assert out.edit_id == "keep-me" and out.status == "failed"
