# youzi/refine/refiner_prompt.py
from __future__ import annotations

from typing import TYPE_CHECKING

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.skill import Skill
from youzi.refine.credit import CreditReport
from youzi.refine.ops import PassKind
from youzi.refine.signatures import FailureSignature

if TYPE_CHECKING:   # 仅类型标注:运行期不导入,避免与 refiner.py 循环依赖
    from youzi.refine.refiner import RefineReport

_PASS_DESC: dict[str, str] = {
    "p": "改写 mutable 作战 doctrine(纪律红线 immutable 改不动,试图改写会被拒绝)",
    "K": "增删改技能库 K(write/patch/retire/revive/promote)",
    "M": "增删改复盘记忆 M(process/update/demote)",
}

_PASS_TOOLS_DOC: dict[str, str] = {
    "p": '- rewrite_doctrine: {"section": "<已存在的 mutable 段名>", "new_guidance": "<新指导>"}',
    "K": ('- write_skill: {"skill_id","name_cn","type":"pattern|feature|failure_detector",'
          '"applicable_regime":[...],"trigger","entry","exit_stop","taboo":[...],"status":"incubating"}\n'
          '- patch_skill: {"skill_id","<字段>":<值>,...}(不可改 status/phases/ecologies)\n'
          '- retire_skill: {"skill_id","permanent":false}\n'
          '- revive_skill: {"skill_id"}(仅 dormant→incubating)\n'
          '- promote_skill: {"skill_id"}(仅 incubating→active,且须过证据门,见晋升纪律)'),
    "M": ('- process_memory: {"lesson_id","regime","outcome":"win|loss|principle","lesson",'
          '"pattern","failure_signature","named_analog"}\n'
          '- update_memory: {"lesson_id","<字段>":<值>,...}\n'
          '- demote_memory: {"lesson_id","factor":<0~1 之间>}'),
}


def _render_skill_full(s: Skill) -> list[str]:
    """A3:涉案技能全文行(trigger/entry/exit_stop/taboo/applicable_regime/stats 双口径)。

    让 K-pass patch 时看得见现值,不再盲改(如反复加同一条 taboo、覆盖丢失既有项)。
    """
    st = s.stats
    out = [f"  trigger: {s.trigger}",
           f"  entry: {s.entry}",
           f"  exit_stop: {s.exit_stop}",
           f"  taboo: {'; '.join(s.taboo) if s.taboo else '(无)'}",
           f"  applicable_regime: {', '.join(s.applicable_regime) or '(未标)'}"
           f"(归一相位: {', '.join(s.phases) or '—'})"]
    if st.n > 0:
        # stats 双口径(C2):超额=advantage(score−当日池基线,去市场β);原始分=旧口径
        exp = f"{st.expectancy:+.2f}" if st.expectancy is not None else "—"
        raw = f"{st.expectancy_raw:+.2f}" if st.expectancy_raw is not None else "—"
        out.append(f"  stats: n={st.n} wins={st.wins} losses={st.losses} nukes={st.nukes} "
                   f"超额={exp}(原始分={raw})")
    else:
        out.append("  stats: (无战绩)")
    return out


def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind,
                                min_retire_samples: int = 5,
                                involved_skill_ids: set[str] | None = None,
                                min_promote_samples: int = 3) -> str:
    """某 pass 的复盘官系统提示:本 pass 改哪个容器 + 可用 meta-tool schema + 规则 + 当前 H 切片。

    involved_skill_ids(A3,仅 K-pass 消费):本窗证据涉案技能集合
    (credit.per_skill keys ∪ signatures 的 skill_id,不含 unattributed 桶)——
    涉案的渲染全文,其余保持单行(定向切片不爆 token)。
    """
    out = [
        "你是 A股游资/超短交易系统的**复盘官(Refiner)**。读最近复盘窗口的决策与已实现结果、"
        "技能信用、失败签名,据此对当前打法 H 做**结构性编辑**,让系统下次更强。",
        f"\n## 本轮只允许:{_PASS_DESC[pass_kind]}",
        "## 可用编辑(严格按参数 schema):",
        _PASS_TOOLS_DOC[pass_kind],
        "\n## 规则:",
        "- 纪律红线(immutable)绝对改不动,试图改写会被拒绝。",
        "- 每条编辑必须带非空 rationale(理由),否则被拒绝。",
        "- 谨慎、少而精;只在证据充分时编辑,无可改则给空列表。",
    ]
    if pass_kind == "p":
        out.append("\n## 当前 mutable doctrine(可改写):")
        for e in h.doctrine.mutable_entries():
            out.append(f"- {e.section}: {e.guidance}")
        out.append("## 纪律红线(immutable,改不动,仅供参考):")
        for e in h.doctrine.immutable_core():
            out.append(f"- {e.section}: {e.guidance}")
    elif pass_kind == "K":
        involved = involved_skill_ids or set()
        out.append("\n## 当前技能(含战绩;本窗证据涉案技能渲染全文,其余单行):")
        for s in h.skills.all():
            st = s.stats
            perf = f" [n={st.n} nukes={st.nukes}]" if st.n > 0 else ""
            head = f"- {s.skill_id}({s.name_cn})[{s.type}/{s.status}]{perf}"
            if s.skill_id in involved:
                out.append(head + " ⟨本窗涉案,全文⟩")
                out.extend(_render_skill_full(s))
            else:
                out.append(head)
        out.append(
            f"\n## 收缩纪律(重要):结构性收缩(retire / 加 taboo)要克制——"
            f"**retire 需 n≥{min_retire_samples}**(样本不足会被拒);"
            f"**faded 是空耗(没续上,score 0)不是亏损**,别只因 1-2 次 faded 就退役/加禁忌;"
            f"**nuked(跌停/炸板)才是真亏**,优先据 nuke 收缩;能 patch 微调就别 retire。")
        out.append(
            "## patch 纪律(重要):patch_skill 是**整字段替换**:改 taboo 必须带上"
            "全部既有项+新增项,否则既有项会静默丢失(其他列表字段同理)。")
        out.append(
            f"## 晋升纪律(重要,A1):**promote 需 n≥{min_promote_samples} 且超额>0**"
            f"(样本不足或无正优势会被拒,零证据不上岗);incubating 技能会以试验位注入"
            f"决策提示(最多 3 条,创建新→旧)积累战绩——promote 前先让试验位证据说话。")
    elif pass_kind == "M":
        out.append("\n## 当前记忆:")
        for l in h.memory.all():
            out.append(f"- {l.lesson_id}[{l.outcome}]: {l.lesson}")
    out.append('\n## 输出严格 JSON(无 markdown 围栏):'
               '{"ops": [{"tool": "...", "args": {...}, "rationale": "..."}]}')
    return "\n".join(out)


def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport,
                              signatures: list[FailureSignature], window: int = 10,
                              recent_reports: list[RefineReport] | None = None) -> str:
    """渲染证据:最近 window 步决策→结果 + 技能信用 + 失败签名 + 近期编辑史(A3)。

    recent_reports:Refiner 最近 ≤2 次 RefineReport(自旧到新)——让 LLM 看见
    已 applied(别重复提)与已 rejected 及拒因(别原样重发),治编辑不收敛。
    """
    out = ["## 最近复盘窗口(决策 → 已实现结果):"]
    for st in traj.scored_steps()[-window:]:
        picks = ", ".join(f"{c.code}({c.pattern})" for c in st.decision.candidates) or "空仓"
        outs = ", ".join(f"{code}:{sc.outcome}" for code, sc in st.outcomes.items()) or "—"
        out.append(f"- {st.date} 选[{picks}] → {outs}")

    # 信用行双口径(C2):超额=advantage(score−当日池基线,>0 才是真技能);原始分=旧口径(含市场β)
    out.append("\n## 技能信用(本轮谁在亏;超额>0 才胜过闭眼买整个涨停池):")
    if credit.per_skill:
        for sid, c in credit.per_skill.items():
            out.append(f"- {sid}: n={c.n} 胜率={c.hit_rate:.2f} nuke率={c.nuke_rate:.2f} "
                       f"超额={c.expectancy:+.2f}(原始分={c.expectancy_raw:+.2f})")
    else:
        out.append("(无)")
    if credit.unattributed:
        u = credit.unattributed
        out.append(f"- [未归因] n={u.n} 胜率={u.hit_rate:.2f} "
                   f"超额={u.expectancy:+.2f}(原始分={u.expectancy_raw:+.2f})")

    out.append("\n## 失败签名(入场坑):")
    if signatures:
        for s in signatures:
            out.append(f"- {s.date} {s.code} [{s.kind}] pattern={s.pattern} "
                       f"skill={s.skill_id or '?'}: {s.evidence}")
    else:
        out.append("(无)")

    # A3 编辑史段:已 applied 的编辑别重复提;已 rejected 的连拒因一起亮出来(此前完全不可见)
    out.append("\n## 近期编辑史(最近 2 次 refine;"
               "已 applied 的不要重复提;已 rejected 的不要原样重发,要么修正要么放弃):")
    if recent_reports:
        for i, rep in enumerate(recent_reports, 1):
            if not rep.applied and not rep.rejected:
                out.append(f"- [第{i}次] (空 refine:无编辑)")
                continue
            for a in rep.applied:
                out.append(f"- [第{i}次/applied] {a.pass_kind}/{a.tool} → {a.target_id}: {a.rationale}")
            for rj in rep.rejected:
                out.append(f"- [第{i}次/rejected] {rj.pass_kind}/{rj.tool} → "
                           f"{rj.target_id or '?'}: 拒因={rj.reason}")
    else:
        out.append("(无)")
    return "\n".join(out)
