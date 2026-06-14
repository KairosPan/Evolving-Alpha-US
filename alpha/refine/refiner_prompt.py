from __future__ import annotations

from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.refine.credit import CreditReport
from alpha.refine.ops import PassKind
from alpha.refine.signatures import FailureSignature
from alpha.eval.trajectory import Trajectory

_PASS_DESC: dict[PassKind, str] = {
    "p": "DOCTRINE pass: rewrite the guidance text of a MUTABLE doctrine entry. You cannot add, remove, "
         "or edit immutable red-line entries.",
    "K": "SKILLS pass: write (new -> incubating), patch, retire (-> dormant), revive, or promote skills.",
    "M": "MEMORY pass: process (add) a lesson, update a lesson's text, or demote a lesson's weight.",
}

_PASS_TOOLS_DOC: dict[PassKind, str] = {
    "p": '- rewrite_doctrine{section, new_guidance, rationale}',
    "K": ('- write_skill{skill_id,name,type,family?,phases?,trigger?,entry?,exit_stop?,taboo?,gate?, rationale}  '
          '(always minted INCUBATING)\n'
          '- patch_skill{skill_id, <fields...>, rationale}  (WHOLE-FIELD REPLACE: include ALL existing list '
          'items you want to keep)\n'
          '- retire_skill{skill_id, permanent?, rationale}\n'
          '- revive_skill{skill_id, rationale}  (dormant -> incubating)\n'
          '- promote_skill{skill_id, rationale}  (incubating -> active)'),
    "M": ('- process_memory{lesson_id,outcome,lesson,phases?,family?,pattern?, rationale}\n'
          '- update_memory{lesson_id, <fields...>, rationale}\n'
          '- demote_memory{lesson_id, factor (0..1], rationale}'),
}

_OUTPUT_CONTRACT = ('Output STRICT JSON only: {"ops": [{"tool": "<one tool above>", "args": {...}, '
                    '"rationale": "<why, non-empty>"}]}. Be sparing — emit an empty ops list if the '
                    'evidence does not justify a change. Every op MUST carry a non-empty rationale.')


def _skill_line(s: Skill) -> str:
    st = s.stats
    rec = (f" [n={st.n} nukes={st.nukes}"
           + (f" exp={st.expectancy:+.2f}" if st.expectancy is not None else "")
           + (f" exp_raw={st.expectancy_raw:+.2f}" if st.expectancy_raw is not None else "") + "]") if st.n > 0 else ""
    return f"- {s.skill_id} ({s.name}) [{s.type}, {s.status}, {s.family or 'any'}]{rec}"


def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind, *, min_retire_samples: int = 5,
                                min_promote_samples: int = 3,
                                involved_skill_ids: set[str] | None = None) -> str:
    """Per-pass system prompt: role + this pass's tools + discipline + a slice of the current H + contract."""
    involved = involved_skill_ids or set()
    parts: list[str] = [
        "You are the Refiner (复盘官) of a US speculative-momentum trading harness. You revise the playbook "
        "H from realized evidence. You edit ONLY via the tools listed; you never trade.",
        "\n" + _PASS_DESC[pass_kind],
        "\nTOOLS (this pass only):\n" + _PASS_TOOLS_DOC[pass_kind],
        "\nRULES: immutable red-line doctrine is READ-ONLY (never editable). Every op needs a non-empty "
        "rationale. patch_skill / update_memory are WHOLE-FIELD REPLACE — re-list every existing item you keep.",
    ]
    if pass_kind == "p":
        parts.append("\nMUTABLE doctrine (editable):")
        parts += [f"- {e.section}: {e.guidance}" for e in h.doctrine.mutable_entries()]
        parts.append("\nIMMUTABLE red-lines (READ-ONLY, cannot be edited):")
        parts += [f"- [RED-LINE] {e.section}: {e.guidance}" for e in h.doctrine.immutable_core()]
    elif pass_kind == "K":
        parts.append(f"\nRETIRE DISCIPLINE: retire_skill is REJECTED unless the skill has n>={min_retire_samples} "
                     "scored samples. 'faded' is a no-follow-through MISS (score 0), NOT a loss — do not retire on "
                     "a few fadeds. 'nuked' is the real loss; contract on nukes first. Prefer patch over retire.")
        parts.append(f"PROMOTE DISCIPLINE: promote_skill is REJECTED unless n>={min_promote_samples} AND "
                     "expectancy (advantage vs the same-day pool) > 0. No zero-evidence activation.")
        parts.append("\nCURRENT SKILLS (involved skills carry their track record):")
        parts += [_skill_line(s) for s in h.skills.all()
                  if s.skill_id in involved or s.status in ("active", "incubating", "dormant")]
    elif pass_kind == "M":
        parts.append("\nCURRENT LESSONS:")
        parts += [f"- {l.lesson_id} [{l.outcome}] {l.lesson}" for l in h.memory.all()]
    parts.append("\n" + _OUTPUT_CONTRACT)
    return "\n".join(parts)


def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport, signatures: list[FailureSignature], *,
                              window: int = 10, recent_reports: list | None = None) -> str:
    """Shared evidence across passes: recent scored steps, per-skill credit, failure signatures, and the
    last <=2 RefineReports (applied: don't re-propose; rejected: don't resend verbatim)."""
    parts: list[str] = ["EVIDENCE (realized, <= t-horizon):"]
    parts.append("\nRecent scored days:")
    for step in traj.scored_steps()[-window:]:
        picks = ", ".join(f"{sym}:{sc.outcome}({sc.advantage:+.2f})" for sym, sc in step.outcomes.items()) or "no-trade"
        parts.append(f"- {step.date}: {picks}")
    parts.append("\nPer-skill credit (this window):")
    for sid, c in credit.per_skill.items():
        parts.append(f"- {sid}: n={c.n} hit={c.hit_rate:.2f} nuke={c.nuke_rate:.2f} "
                     f"exp(adv)={c.expectancy:+.2f} exp_raw={c.expectancy_raw:+.2f}")
    if credit.unattributed:
        parts.append(f"- (unattributed picks: n={credit.unattributed.n})")
    if signatures:
        parts.append("\nFailure signatures (where it lost):")
        parts += [f"- {s.date} {s.symbol} [{s.kind}] {s.evidence} (skill={s.skill_id or '?'})" for s in signatures]
    for rep in (recent_reports or []):
        if rep.applied:
            parts.append("\nAlready APPLIED recently (do NOT re-propose): "
                         + "; ".join(f"{e.tool}:{e.target_id}" for e in rep.applied))
        if rep.rejected:
            parts.append("Recently REJECTED (do NOT resend verbatim): "
                         + "; ".join(f"{e.tool}:{e.target_id} ({e.reason})" for e in rep.rejected))
    return "\n".join(parts)
