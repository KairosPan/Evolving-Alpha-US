"""Gate + non-vacuity tests for scripts/lint_doctrine.py (DEVELOPMENT-PLAN §1 P0.2).

Each of the four checks is proven non-vacuous by a matched pair: a CLEAN minimal manuscript that
the check passes, and a seeded mutant that the check FAILS on — so a check that never fires (a
vacuous pass) cannot survive. The final gate test lints the REAL manuscript so any future edit that
breaks the §0 编辑契约 fails pytest.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import lint_doctrine as ld  # noqa: E402

MANUSCRIPT = REPO / "docs" / "doctrine" / "2026-07-12-us-growth-doctrine-draft.md"

# Allowlist for knowingly-unrouted `.rule` entries (a NEW unrouted rule still trips the gate).
# Emptied 2026-07-12: the v0.1 skeleton's 5 gaps received Appendix B ledger rows.
KNOWN_APPENDIX_B_GAPS: set[str] = set()

# A minimal, fully-contract-compliant manuscript. Every per-check test mutates ONE thing.
CLEAN_DOC = """# test doctrine

## §1 周期总纲

枚举：`confirmed_uptrend / under_pressure / correction`，外加 `panic_state`。
枚举：`emerging → institutional → public_laggard → exhaustion`。
枚举：`base → advance → top → decline`。

> **`cycle_eye`**（道）：先问相位再谈买卖。（轮回锚 → A-01）

## §3 龙头

> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。

## §4 纪律

> **`trend_template.rule`**（术）：宇宙过滤八条。confirmed_uptrend：可进攻；under_pressure：防守。（道：`leader_definition`）

## §L 教训

> L-001：failure_signature：论点未设可证伪节点。

## 附录 A

| ID | 概念 | 判定 |
|---|---|---|
| A-01 | 情绪周期 | 变形 |

## 附录 B

| 条目 ID | 去向 | 状态 |
|---|---|---|
| `trend_template.rule` | screen | 待前置工程 |
"""


def codes(vs):
    return {v.code for v in vs}


def checks(vs):
    return {v.check for v in vs}


# --- the clean baseline must be silent (else every non-vacuity claim below is hollow) --------
def test_clean_doc_has_zero_violations():
    assert ld.lint_text(CLEAN_DOC) == []


# --- (a) id uniqueness + reference resolution ------------------------------------------------
def test_a_duplicate_entry_id():
    dirty = CLEAN_DOC.replace(
        "> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。",
        "> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。\n\n> **`leader_definition`**（道）：重复定义。",
    )
    assert "duplicate_id" in codes(ld.lint_text(dirty))


def test_a_backref_to_nonexistent_dao():
    dirty = CLEAN_DOC.replace("（道：`leader_definition`）", "（道：`ghost_dao`）")
    vs = ld.lint_text(dirty)
    assert "backref_unresolved" in codes(vs)
    assert any(v.entity == "ghost_dao" for v in vs)


def test_a_rulun_anchor_to_missing_appendix_a_row():
    dirty = CLEAN_DOC.replace("轮回锚 → A-01", "轮回锚 → A-99")
    vs = ld.lint_text(dirty)
    assert "anchor_unresolved" in codes(vs)
    assert any(v.entity == "A-99" for v in vs)


# --- (b) 道/术 pairing + placement -----------------------------------------------------------
def test_b_rule_defined_outside_section_4():
    # a `.rule` header planted under §3 (a 道条 zone)
    dirty = CLEAN_DOC.replace(
        "> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。",
        "> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。\n\n"
        "> **`stray.rule`**（术）：混进 §3 的规则。（道：`leader_definition`）",
    )
    assert "rule_outside_sec4" in codes(ld.lint_text(dirty))


def test_b_rule_without_backref_is_orphan():
    dirty = CLEAN_DOC.replace("防守。（道：`leader_definition`）", "防守。")
    assert "rule_missing_backref" in codes(ld.lint_text(dirty))


def test_b_doctrine_defined_inside_section_4():
    dirty = CLEAN_DOC.replace(
        "> **`trend_template.rule`**（术）：宇宙过滤八条。",
        "> **`stray_dao`**（道）：不该住 §4 的道条。\n\n> **`trend_template.rule`**（术）：宇宙过滤八条。",
    )
    assert "doctrine_outside_123" in codes(ld.lint_text(dirty))


def test_b_rule_suffix_and_tag_must_agree():
    dirty = CLEAN_DOC.replace("> **`trend_template.rule`**（术）：", "> **`trend_template.rule`**（道）：")
    assert "rule_tag_mismatch" in codes(ld.lint_text(dirty))


# --- (c) controlled-enum legality ------------------------------------------------------------
def test_c_undeclared_state_in_mapping_fails():
    dirty = CLEAN_DOC.replace("under_pressure：防守。", "under_pressure：防守；distribution_phase：清仓。")
    vs = ld.lint_text(dirty)
    assert "undeclared_state" in codes(vs)
    assert any(v.entity == "distribution_phase" for v in vs)


def test_c_lone_colon_label_is_not_a_state_mapping():
    # `failure_signature：` sits alone in §L with no declared state beside it → must NOT be flagged
    assert "c" not in checks(ld.lint_text(CLEAN_DOC))


def test_c_hyphenated_word_suffix_is_not_a_state_token():
    # `read-through：` must not be misread as a state token `through`
    dirty = CLEAN_DOC.replace(
        "> **`leader_definition`**（道）：龙头 = 利润承载 × 市场确认。",
        "> **`leader_definition`**（道）：用财报做 read-through：客户 capex 指引即供应商前瞻。",
    )
    assert "c" not in checks(ld.lint_text(dirty))


# --- (d) Appendix-B distillation coverage ----------------------------------------------------
def test_d_rule_absent_from_appendix_b_fails():
    dirty = CLEAN_DOC.replace(
        "> **`trend_template.rule`**（术）：宇宙过滤八条。confirmed_uptrend：可进攻；under_pressure：防守。（道：`leader_definition`）",
        "> **`trend_template.rule`**（术）：宇宙过滤八条。confirmed_uptrend：可进攻；under_pressure：防守。（道：`leader_definition`）\n\n"
        "> **`orphan.rule`**（术）：未登记路由的规则。（道：`leader_definition`）",
    )
    vs = ld.lint_text(dirty)
    assert "appendix_b_uncovered" in codes(vs)
    assert any(v.entity == "orphan.rule" for v in vs)


def test_d_deferred_marker_satisfies_coverage():
    # same orphan rule, but explicitly marked deferred → the OR-clause exempts it
    dirty = CLEAN_DOC.replace(
        "> **`trend_template.rule`**（术）：宇宙过滤八条。confirmed_uptrend：可进攻；under_pressure：防守。（道：`leader_definition`）",
        "> **`trend_template.rule`**（术）：宇宙过滤八条。confirmed_uptrend：可进攻；under_pressure：防守。（道：`leader_definition`）\n\n"
        "> **`held.rule`**（术·暂定不设，deferred 2026-07-12）：留空待拍板。（道：`leader_definition`）",
    )
    assert not any(v.entity == "held.rule" for v in ld.lint_text(dirty))


# --- the gate: lint the REAL manuscript ------------------------------------------------------
def test_real_manuscript_clean_on_checks_a_b_c():
    vs = ld.lint_file(MANUSCRIPT)
    offenders = [str(v) for v in vs if v.check in {"a", "b", "c"}]
    assert offenders == [], "manuscript broke an id/pairing/enum contract:\n" + "\n".join(offenders)


def test_real_manuscript_appendix_b_gap_within_known_skeleton():
    vs = ld.lint_file(MANUSCRIPT)
    uncovered = {v.entity for v in vs if v.code == "appendix_b_uncovered"}
    new = uncovered - KNOWN_APPENDIX_B_GAPS
    assert new == set(), f"new `.rule`(s) with no Appendix B routing — add a ledger row: {new}"


def test_real_manuscript_gate_is_non_vacuous():
    # the gate must actually parse entries AND exercise check (c) — guard against a manuscript whose
    # enum declarations vanished (which would silently make (c) a no-op even while staying "green")
    lines = MANUSCRIPT.read_text(encoding="utf-8").splitlines()
    entries, _ = ld._parse(lines)
    rules = [e for e in entries if e.id.endswith(".rule")]
    assert len(rules) >= 12 and any(e.id == "trend_template.rule" for e in rules)
    enum = set()
    for ln in lines:
        if ld.ENUM_DECL.match(ln):
            for span in ld.INLINE_CODE.findall(ln):
                enum.update(ld.ENUM_INNER.findall(span))
    assert {"confirmed_uptrend", "public_laggard", "base"} <= enum   # all three clocks declared
    mapped = [b for _, b in ld._blockquotes(lines) if any(t in enum for t in ld.COLON_TOKEN.findall(b))]
    assert len(mapped) >= 2                                          # (c) has real mappings to police


# --- CLI wrapper ------------------------------------------------------------------------------
def test_main_returns_nonzero_on_violation(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text(CLEAN_DOC.replace("（道：`leader_definition`）", "（道：`ghost_dao`）"), encoding="utf-8")
    assert ld.main([str(bad)]) == 1
    assert "backref_unresolved" in capsys.readouterr().out


def test_main_returns_zero_on_clean(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(CLEAN_DOC, encoding="utf-8")
    assert ld.main([str(good)]) == 0
