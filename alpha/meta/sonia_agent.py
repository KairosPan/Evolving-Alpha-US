from __future__ import annotations

from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.meta import prompts
from alpha.meta.models import Message, Session, new_message_id, now_iso

_INSTRUCTIONS = (
    "\n\nYou are Sonia, a US speculative-momentum trading co-pilot. Discuss freely, ask clarifying "
    "questions, and think out loud with the operator. You may optionally append a SINGLE fenced JSON "
    "object with \"directions\" (each {\"title\":..., \"summary\":...}) to surface candidate changes — "
    "but do NOT emit brain edits here; the operator crystallizes edits explicitly on demand."
)


def turn_text(m: Message) -> str:
    extra = "\n\n".join(a.text for a in m.attachments if a.text)
    return (m.text + ("\n\n" + extra if extra else "")).strip()


class SoniaAgent:
    """Stateless-per-request chat meta-agent. Reasons over the thread; returns prose + directions.
    Chat never crystallizes ops — edits are proposed only via an explicit /propose pass.
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
        msgs = [ChatMessage(role=m.role, text=turn_text(m)) for m in session.messages]
        msgs.append(ChatMessage(role="user", text=turn_text(user_message)))
        return msgs

    def respond(self, session: Session, user_message: Message) -> Message:
        reply = self.copilot.chat(self._system(), self._history(session, user_message))
        block = extract_json_object(reply)
        prose = reply.replace(block, "").strip() if block else reply.strip()
        directions = prompts.parse_directions(reply)
        return Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                       text=prose, directions=directions, edits=[], origin="model")
