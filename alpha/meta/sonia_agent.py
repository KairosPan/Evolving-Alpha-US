from __future__ import annotations

from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.meta import prompts
from alpha.meta.agent import preview_op
from alpha.meta.models import Message, Session, new_message_id, now_iso
from alpha.refine.ops import parse_ops

_INSTRUCTIONS = (
    "\n\nYou are Sonia, a US speculative-momentum trading co-pilot. Discuss freely and ask "
    "clarifying questions. When (and only when) a concrete brain change is warranted, write prose "
    "for the operator and then append a SINGLE fenced JSON object with \"directions\" (each "
    "{\"title\":..., \"summary\":...}) and/or \"ops\". " + prompts._TOOLS_DOC
)


def _turn_text(m: Message) -> str:
    extra = "\n\n".join(a.text for a in m.attachments if a.text)
    return (m.text + ("\n\n" + extra if extra else "")).strip()


class SoniaAgent:
    """Stateless-per-request chat meta-agent. Reasons over the thread; proposes dry-run edit cards.
    The live brain is never mutated here — apply is the service's job."""

    def __init__(self, tools: MetaTools, copilot: ChatLLMClient, *, retire_min: int = 5, promote_min: int = 3) -> None:
        self.tools = tools
        self.h = tools.h
        self.copilot = copilot
        self._retire_min = retire_min
        self._promote_min = promote_min

    def _system(self) -> str:
        return prompts.render_brain_summary(self.h) + _INSTRUCTIONS

    def _history(self, session: Session, user_message: Message) -> list[ChatMessage]:
        msgs = [ChatMessage(role=m.role, text=_turn_text(m)) for m in session.messages]
        msgs.append(ChatMessage(role="user", text=_turn_text(user_message)))
        return msgs

    def respond(self, session: Session, user_message: Message) -> Message:
        reply = self.copilot.chat(self._system(), self._history(session, user_message))
        block = extract_json_object(reply)
        prose = reply.replace(block, "").strip() if block else reply.strip()
        directions = prompts.parse_directions(reply)
        edits = [preview_op(self.h, op, retire_min=self._retire_min, promote_min=self._promote_min)
                 for op in parse_ops(reply)]
        return Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                       text=prose, directions=directions, edits=edits)
