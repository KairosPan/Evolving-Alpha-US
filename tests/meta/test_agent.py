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
