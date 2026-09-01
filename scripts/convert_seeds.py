"""One-shot: convert the retired seeds_v2 JSON packs into style-kairos SKILL.md files.

Kept in the tree as the provenance record for dsh/skills/style-kairos/: the JSON packs it
reads (seeds_v2/) were deleted in the same commit, so this file is the only remaining
statement of where that prose came from and how it was rendered. Re-running it needs the
packs restored from git history.

The seeds_v2 schema, as it actually was on disk (the accessors below are pinned to THESE
names, not to the plan's guesses):

    doctrine.json  39 entries: section, guidance, immutable, plus EITHER regime="all" OR a
                   phases list - the two are mutually exclusive and both are the entry's
                   scope, so neither can be dropped.
    skills.json     6 entries: skill_id, name, type, phases, trigger, entry, exit_stop,
                   taboo (a LIST, not a string), status, and depends_on on one entry.
    memory.json    21 entries: lesson_id, phases, outcome, failure_signature, named_analog,
                   and `lesson` - the actual prose, which is the point of the pack.

seeds_v2/connectors.json is deliberately NOT converted: it described the alpaca connector as
a harness component (env keys, capabilities, the announce_date:=process_date PIT key), and
those facts now live in dsh/skills/mechanics/alpaca-kit-guide/SKILL.md and the profile
template, not in an operator-style skill.

Paths are anchored on this file, never on the CWD, so it runs from anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

STYLE_HEADER = """> **Scope: operator style, not market law.** These are the operator's personal
> investment rules and preferences. Follow them by default — but when research findings
> conflict with an entry here, REPORT the conflict; do not silently defer.

"""
_REPO = Path(__file__).resolve().parents[1]
SEEDS = _REPO / "seeds_v2"
ROOT = _REPO / "dsh" / "skills" / "style-kairos"


def _write(name: str, description: str, lines: list[str]) -> Path:
    # dsh's skill discovery drops any SKILL.md without YAML frontmatter carrying
    # name and description (silently, at warn level) — the block is load-bearing.
    frontmatter = f"---\nname: {name}\ndescription: {description}\n---\n"
    out = ROOT / name / "SKILL.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(frontmatter + "\n".join(lines), encoding="utf-8")
    return out


def _scope(entry: dict) -> str:
    """The entry's scope line: regime='all' and a phases list are the two encodings of it."""
    phases = entry.get("phases")
    if phases:
        return f"*Phases: {', '.join(phases)}*\n"
    regime = entry.get("regime")
    return f"*Regime: {regime}*\n" if regime else ""


def main() -> None:
    doctrine = json.loads((SEEDS / "doctrine.json").read_text(encoding="utf-8"))
    skills = json.loads((SEEDS / "skills.json").read_text(encoding="utf-8"))
    memory = json.loads((SEEDS / "memory.json").read_text(encoding="utf-8"))

    d = ["# Doctrine — operator trading rules\n", STYLE_HEADER]
    for e in doctrine:
        tag = " (red-line)" if e.get("immutable") else ""
        d.append(f"## {e['section']}{tag}\n{_scope(e)}{e['guidance']}\n")
    _write("doctrine",
           "Operator trading rules — red-lines plus market/theme/stock cycle doctrine. "
           "Follow by default; when research conflicts with an entry, report the conflict, "
           "never silently defer.", d)

    s = ["# Signals — operator setups\n", STYLE_HEADER]
    for e in skills:
        # A detector-type signal carries an empty entry/exit_stop by design; an empty bullet
        # would read as a missing rule, so drop the field instead of printing a blank one.
        bullets = [f"- **{label}:** {e[key]}"
                   for label, key in (("Trigger", "trigger"), ("Entry", "entry"),
                                      ("Exit/stop", "exit_stop"))
                   if e.get(key)]
        # taboo is a list of strings: render one bullet each, never a Python list repr.
        if e.get("taboo"):
            bullets.append("- **Taboo:**" + "".join(f"\n  - {t}" for t in e["taboo"]))
        if e.get("depends_on"):
            bullets.append(f"- **Depends on:** {', '.join(e['depends_on'])}")
        s.append(f"## {e['skill_id']} — {e.get('name', '')}\n"
                 f"*{e.get('type', '')} · {e.get('status', '')} · "
                 f"phases: {', '.join(e.get('phases', []))}*\n"
                 + "\n".join(bullets) + "\n")
    _write("signals",
           "The operator's entry/exit setups (base breakout and kin) — operator style, "
           "follow by default and report conflicts with research findings.", s)

    m = ["# Lessons — operator failure signatures\n", STYLE_HEADER]
    for e in memory:
        # A principle-outcome lesson often carries no failure_signature and no phases; same
        # rule as signals - an empty bullet reads as missing content, so drop the field.
        bullets = [f"- **{label}:** {e[key]}"
                   for label, key in (("Failure", "failure_signature"),
                                      ("Analog", "named_analog"), ("Lesson", "lesson"))
                   if e.get(key)]
        if e.get("phases"):
            bullets.insert(-1, f"- **Phases:** {', '.join(e['phases'])}")
        outcome = e.get("outcome")
        m.append(f"## {e.get('lesson_id', 'lesson')}"
                 f"{f' ({outcome})' if outcome else ''}\n"
                 + "\n".join(bullets) + "\n")
    _write("lessons",
           "The operator's recorded failure signatures and the lessons drawn from them — "
           "operator style, follow by default and report conflicts with research findings.", m)

    print("wrote", *sorted(p.name for p in ROOT.iterdir()))


if __name__ == "__main__":
    main()
