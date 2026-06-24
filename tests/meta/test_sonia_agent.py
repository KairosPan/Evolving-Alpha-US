# tests/meta/test_sonia_agent.py
from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.llm.client import MockLLMClient
from alpha.meta.models import Message, Session
from alpha.meta.sonia_agent import SoniaAgent


def _agent(scripted, h=None):
    h = h if h is not None else load_seeds("seeds")
    return SoniaAgent(MetaTools(h, EditLog()), MockLLMClient(scripted)), h


def _user(text="teach me"):
    return Message(message_id="u1", role="user", text=text)


def test_prose_only_makes_no_cards():
    agent, _ = _agent("Let's discuss your squeeze thesis first — no edits yet.")
    out = agent.respond(Session(session_id="s1"), _user())
    assert out.role == "assistant" and "squeeze thesis" in out.text
    assert out.edits == [] and out.directions == []


def test_directions_become_direction_cards():
    agent, _ = _agent('Here is a direction. {"directions": [{"title": "lean into squeezes"}]}')
    out = agent.respond(Session(session_id="s1"), _user())
    assert [d.title for d in out.directions] == ["lean into squeezes"]
    assert "lean into squeezes" not in out.text or out.text.startswith("Here is a direction")


def test_ops_become_dryrun_edit_cards_without_mutating_brain():
    h = load_seeds("seeds")
    sid = h.skills.all()[0].skill_id
    scripted = ('proposing a patch. {"ops": [{"tool": "patch_skill", '
                '"args": {"skill_id": "%s", "notes": "from sonia"}, "rationale": "the writeup shows it"}]}') % sid
    agent, h = _agent(scripted, h)
    out = agent.respond(Session(session_id="s1"), _user())
    assert len(out.edits) == 1 and out.edits[0].status == "proposed"
    assert out.edits[0].payload["after"] == {"notes": "from sonia"}
    assert h.skills.get(sid).notes != "from sonia"               # live brain untouched


def test_redline_op_becomes_failed_card():
    scripted = '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "missing"}, "rationale": "r"}]}'
    agent, _ = _agent(scripted)
    out = agent.respond(Session(session_id="s1"), _user())
    assert len(out.edits) == 1 and out.edits[0].status == "failed" and out.edits[0].apply_reason


def test_history_is_threaded_into_the_chat_call():
    agent, _ = _agent("ok")
    prior = [Message(message_id="m0", role="user", text="earlier"),
             Message(message_id="m1", role="assistant", text="noted")]
    agent.respond(Session(session_id="s1", messages=prior), _user("now this"))
    system, sent = agent.copilot.chat_calls[0]
    assert "RED-LINE" in system                                  # brain summary in the system prompt
    assert [m.text for m in sent] == ["earlier", "noted", "now this"]
