#!/usr/bin/env python3
"""Lint the growth-doctrine manuscript against its §0 编辑契约 (DEVELOPMENT-PLAN §1 P0.2).

The manuscript (`docs/doctrine/*.md`) is the source handed to Sonia for iteration; §0.1/§0.4
state a format contract with no enforcer. This is that enforcer — enforcement = tests, so the
gate test in tests/scripts/test_lint_doctrine.py lints the real file and any future edit that
breaks the contract fails pytest.

Four checks (pure core `lint_text`; each Violation carries its check letter a/b/c/d):
  (a) id_resolution   — entry-ID uniqueness; every （道：`x`）backref resolves to a 道条 ID;
                        every 轮回锚 → A-xx reference resolves to an Appendix A row.
  (b) dao_shu_pairing — a `.rule` entry lives only in §4 and carries ≥1 resolving （道：）backref;
                        a 道条 (non-.rule) entry lives only in §1–§3; id-suffix ⇔ 道/术 tag agree.
  (c) enum_legality   — in any blockquote that maps a declared clock-state to an action (a
                        `token：` whose token is one of the §1 枚举), every such mapped token is
                        itself in the union of the three §1 declared enums.
  (d) appendix_b_cov  — every `.rule` entry is mentioned in an Appendix B row, else is explicitly
                        marked deferred / 暂不蒸馏 / 不蒸馏 / distill=none in its own entry body.

Design note on (b): the manuscript pairs 术→道 by the （道：`base`）backref, NOT by stem match
(`trend_template.rule` backrefs `rs_as_jury`); the §0.1 "id = 道条 id + .rule" wording is looser
than the tree, so pairing is enforced as "the backref resolves to a real 道条". (c) anchors on the
declared enums (a lone `token：` label such as `failure_signature：` in §L is never adjacent to a
declared state, so it is not treated as a state-mapping) — the caught threat is an undeclared token
smuggled into an existing state enumeration.

Usage: python scripts/lint_doctrine.py [path.md ...]   # default: docs/doctrine/*.md
Exit non-zero on any violation.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ENTRY_HEADER = re.compile(r"^>\s\*\*`([a-z][a-z0-9_.]*)`\*\*（([道术])")
SECTION = re.compile(r"^##\s+(.+?)\s*$")
BACKREF_SPAN = re.compile(r"（道：([^）\n]*)）")
BACKTICK_TOKEN = re.compile(r"`([a-z][a-z0-9_.]*)`")
ANCHOR_LINE = re.compile(r"轮回锚\s*→\s*([^）\n]*)")
ANCHOR_ID = re.compile(r"A-\d{2}")
APPENDIX_A_ROW = re.compile(r"^\|\s*(A-\d{2})\s*\|")
ENUM_DECL = re.compile(r"^枚举：")
INLINE_CODE = re.compile(r"`([^`]+)`")           # a whole `...` span (enum groups pack several)
ENUM_INNER = re.compile(r"[a-z][a-z0-9_]*")      # tokens inside a span, split from / and → separators
RULE_BACKTICK = re.compile(r"`([a-z][a-z0-9_]*\.rule)`")
# whole-word ascii token immediately before a fullwidth colon, not a suffix of a hyphenated word
COLON_TOKEN = re.compile(r"(?<![A-Za-z0-9_\-])([a-z][a-z0-9_]*)：")
DEFERRED_MARK = re.compile(r"deferred|暂定不设|暂不蒸馏|不蒸馏|distill\s*=\s*none")


@dataclass(frozen=True)
class Violation:
    check: str      # 'a' | 'b' | 'c' | 'd'
    code: str       # short machine code, e.g. 'backref_unresolved'
    entity: str     # offending id / anchor / token
    line: int       # 1-based source line (0 = not line-specific)
    message: str

    def __str__(self) -> str:
        where = f":{self.line}" if self.line else ""
        return f"[{self.check}] {self.code}{where}: {self.entity} — {self.message}"


@dataclass(frozen=True)
class Entry:
    id: str
    tag: str        # 道 | 术
    section: str    # normalized section key, e.g. '§4', '附录B'
    line: int
    text: str       # the full blockquote body


def _norm_section(heading: str) -> str:
    parts = heading.split()
    head = parts[0]
    if head == "附录" and len(parts) > 1:
        return "附录" + parts[1]
    return head


def _blockquotes(lines: list[str]) -> list[tuple[int, str]]:
    """Contiguous runs of '>'-prefixed lines → (1-based start line, joined text)."""
    blocks, i, n = [], 0, len(lines)
    while i < n:
        if lines[i].startswith(">"):
            start, buf = i, [lines[i]]
            j = i + 1
            while j < n and lines[j].startswith(">") and not ENTRY_HEADER.match(lines[j]):
                buf.append(lines[j])
                j += 1
            blocks.append((start + 1, "\n".join(buf)))
            i = j
        else:
            i += 1
    return blocks


def _parse(lines: list[str]) -> tuple[list[Entry], str]:
    """Return (entries, current-section threading is internal). Entries carry their section."""
    entries, section = [], ""
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        msec = SECTION.match(line)
        if msec:
            section = _norm_section(msec.group(1))
            i += 1
            continue
        mhdr = ENTRY_HEADER.match(line)
        if mhdr:
            start, buf = i, [line]
            j = i + 1
            while j < n and lines[j].startswith(">") and not ENTRY_HEADER.match(lines[j]):
                buf.append(lines[j])
                j += 1
            entries.append(Entry(mhdr.group(1), mhdr.group(2), section, start + 1, "\n".join(buf)))
            i = j
            continue
        i += 1
    return entries, section


def lint_text(text: str) -> list[Violation]:
    """Pure core: lint a manuscript string, return every violation found across all four checks."""
    lines = text.splitlines()
    entries, _ = _parse(lines)
    out: list[Violation] = []

    # --- shared indexes -------------------------------------------------------
    doctrine_ids = {e.id for e in entries if e.tag == "道"}
    appendix_a_rows: set[str] = set()
    dup_a: list[str] = []
    for ln in lines:
        m = APPENDIX_A_ROW.match(ln)
        if m:
            if m.group(1) in appendix_a_rows:
                dup_a.append(m.group(1))
            appendix_a_rows.add(m.group(1))
    enum_tokens: set[str] = set()
    for ln in lines:
        if ENUM_DECL.match(ln):
            for span in INLINE_CODE.findall(ln):
                enum_tokens.update(ENUM_INNER.findall(span))
    appendix_b_rules: set[str] = set()
    sec = ""
    for ln in lines:
        m = SECTION.match(ln)
        if m:
            sec = _norm_section(m.group(1))
        elif sec == "附录B":
            appendix_b_rules.update(RULE_BACKTICK.findall(ln))

    # --- (a) entry-ID uniqueness + reference resolution ----------------------
    seen: set[str] = set()
    for e in entries:
        if e.id in seen:
            out.append(Violation("a", "duplicate_id", e.id, e.line, "entry ID defined more than once"))
        seen.add(e.id)
    for a in dup_a:
        out.append(Violation("a", "duplicate_anchor_row", a, 0, "Appendix A row defined more than once"))
    for e in entries:
        for span in BACKREF_SPAN.findall(e.text):
            for tok in BACKTICK_TOKEN.findall(span):
                if tok not in doctrine_ids:
                    out.append(Violation("a", "backref_unresolved", tok, e.line,
                                         f"（道：`{tok}`）in {e.id} resolves to no 道条"))
    for idx, ln in enumerate(lines, start=1):
        for span in ANCHOR_LINE.findall(ln):
            for anchor in ANCHOR_ID.findall(span):
                if anchor not in appendix_a_rows:
                    out.append(Violation("a", "anchor_unresolved", anchor, idx,
                                         "轮回锚 points to no Appendix A row"))

    # --- (b) 道/术 pairing + placement ---------------------------------------
    for e in entries:
        is_rule = e.id.endswith(".rule")
        if is_rule and e.tag != "术":
            out.append(Violation("b", "rule_tag_mismatch", e.id, e.line, "`.rule` id tagged 道, expected 术"))
        if not is_rule and e.tag == "术":
            out.append(Violation("b", "shu_missing_rule_suffix", e.id, e.line, "术条 id lacks `.rule` suffix"))
        if is_rule:
            if e.section != "§4":
                out.append(Violation("b", "rule_outside_sec4", e.id, e.line,
                                     f"`.rule` entry lives in {e.section or '(no section)'}, must be §4"))
            if not BACKREF_SPAN.search(e.text):
                out.append(Violation("b", "rule_missing_backref", e.id, e.line, "`.rule` carries no （道：）backref"))
        elif e.tag == "道" and e.section not in {"§1", "§2", "§3"}:
            out.append(Violation("b", "doctrine_outside_123", e.id, e.line,
                                 f"道条 lives in {e.section or '(no section)'}, must be §1–§3"))

    # --- (c) controlled-enum legality ----------------------------------------
    for start_line, body in _blockquotes(lines):
        toks = COLON_TOKEN.findall(body)
        if any(t in enum_tokens for t in toks):        # this blockquote maps clock-states → actions
            for t in toks:
                if t not in enum_tokens:
                    out.append(Violation("c", "undeclared_state", t, start_line,
                                         "clock-state token used in a state mapping but not declared in §1 枚举"))

    # --- (d) Appendix-B distillation coverage --------------------------------
    for e in entries:
        if e.id.endswith(".rule"):
            covered = e.id in appendix_b_rules or bool(DEFERRED_MARK.search(e.text))
            if not covered:
                out.append(Violation("d", "appendix_b_uncovered", e.id, e.line,
                                     "`.rule` absent from Appendix B and not marked deferred/不蒸馏/distill=none"))
    return out


def lint_file(path: Path) -> list[Violation]:
    return lint_text(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(__file__).resolve().parents[1]
    paths = [Path(a) for a in argv] or sorted((repo / "docs" / "doctrine").glob("*.md"))
    total = 0
    for p in paths:
        vs = lint_file(p)
        total += len(vs)
        for v in vs:
            print(f"{p}:{v}")
    if total:
        print(f"\n{total} violation(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
