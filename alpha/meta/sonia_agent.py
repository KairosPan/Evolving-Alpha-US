from __future__ import annotations

from alpha.converse.loop import run_conversation
from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.meta import prompts
from alpha.meta.models import Message, Session, new_message_id, now_iso
from alpha.meta.sonia_tools import render_tool_specs

_INSTRUCTIONS = (
    "\n\nYou are Sonia, a US speculative-momentum trading co-pilot. Discuss freely, ask clarifying "
    "questions, and think out loud with the operator. You have read-only view_* browse tools to pull "
    "the full detail of any brain element on demand (the brain summary above is only an index). You "
    "may optionally append a SINGLE fenced JSON object with \"directions\" (each {\"title\":..., "
    "\"summary\":...}) to surface candidate changes — but do NOT emit brain edits here; the operator "
    "crystallizes edits explicitly on demand."
)


def turn_text(m: Message) -> str:
    extra = "\n\n".join(a.text for a in m.attachments if a.text)
    return (m.text + ("\n\n" + extra if extra else "")).strip()


class SoniaAgent:
    """Stateless-per-request chat meta-agent. Reasons over the thread; returns prose + directions.
    Chat never crystallizes ops — edits are proposed only via an explicit /propose pass.
    The live brain is never mutated here — apply is the service's job."""

    def __init__(self, tools: MetaTools, copilot: ChatLLMClient, *, retire_min: int = 5,
                 promote_min: int = 3, registry_factory=None) -> None:
        self.tools = tools
        self.h = tools.h
        self.copilot = copilot
        self._retire_min = retire_min
        self._promote_min = promote_min
        # registry_factory(h) -> (ToolRegistry, ActivityPolicy). When set, respond() runs a bounded
        # observe-tier tool loop (view_* brain browse) instead of a single chat() call.
        self._registry_factory = registry_factory

    def _system(self, registry=None) -> str:
        base = prompts.render_brain_summary(self.h) + _INSTRUCTIONS
        # Advertise the observe tools (name + arg names) so the model can actually call them — the
        # loop is a TEXT protocol and a real LLM only calls a tool whose arg names it can see.
        return base if registry is None else base + "\n\n" + render_tool_specs(registry)

    def _history(self, session: Session, user_message: Message) -> list[ChatMessage]:
        msgs = [ChatMessage(role=m.role, text=turn_text(m)) for m in session.messages]
        msgs.append(ChatMessage(role="user", text=turn_text(user_message)))
        return msgs

    def respond(self, session: Session, user_message: Message) -> Message:
        history = self._history(session, user_message)
        if self._registry_factory is not None:
            reg, pol = self._registry_factory(self.h)
            # A directions-only reply has no "tool" key, so the loop treats it as final_text — the
            # extract_json_object/parse_directions post-processing below then still fires (critical).
            res = run_conversation(reg, self.copilot, self._system(reg), history,
                                   max_iters=6, dispatch=pol.dispatch)
            reply = res.final_text
        else:
            reply = self.copilot.chat(self._system(), history)
        block = extract_json_object(reply)
        prose = reply.replace(block, "").strip() if block else reply.strip()
        directions = prompts.parse_directions(reply)
        return Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                       text=prose, directions=directions, edits=[], origin="model")
