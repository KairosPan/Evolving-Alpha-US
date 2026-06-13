# tests/test_refiner.py
import pytest
from youzi.refine.refiner import Refiner, RefinerConfig, RefineReport, AppliedEdit, RejectedEdit
from youzi.refine.ops import RefineOp
from youzi.harness.metatools import MetaTools
from youzi.llm.client import MockLLMClient
from tests.test_metatools import _harness


def _refiner(h=None, cfg=None):
    h = h or _harness()
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, cfg or RefinerConfig())
    return r, h, meta


def test_apply_op_accept_promote():
    # _harness 的技能 a 是 active;先 retire→revive 使其 incubating,再 promote
    r, h, meta = _refiner()
    meta.retire_skill("a"); meta.revive_skill("a")     # a -> incubating
    h.skills.get("a").stats.n = 3                      # A1 晋升证据门:n>=3 且超额>0
    h.skills.get("a").stats.expectancy = 0.2
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"},
                                   rationale="胜率回升"), "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert res.tool == "promote_skill" and res.target_id == "a"
    assert h.skills.get("a").status == "active"


def test_apply_op_reject_immutable():
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine",
                                   args={"section": "纪律:退潮不接力", "new_guidance": "篡改"},
                                   rationale="想放松"), "p", PASS_P())
    assert not ok and isinstance(res, RejectedEdit)
    assert "Immutable" in res.reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"   # 未变
    assert len(meta.log) == 0                                           # 未记日志


def test_apply_op_reject_invalid_transition():
    r, h, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="revive_skill", args={"skill_id": "a"},
                                   rationale="复活"), "K", PASS_K())   # a 是 active,非 dormant
    assert not ok and "InvalidTransition" in res.reason


def test_apply_op_reject_wrong_pass_tool():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"},
                                   rationale="r"), "K", PASS_K())      # rewrite 不在 K-pass
    assert not ok and "本 K-pass" in res.reason


def test_apply_op_reject_missing_rationale():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="  "),
                          "K", PASS_K())
    assert not ok and "rationale" in res.reason


def test_apply_op_reject_hallucinated_target():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "不存在", "notes": "x"},
                                   rationale="r"), "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_apply_op_reject_duplicate_write():
    r, _, _ = _refiner()
    skill = {"skill_id": "a", "name_cn": "重复", "type": "pattern",
             "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
             "exit_stop": "x", "status": "incubating"}
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=skill, rationale="r"), "K", PASS_K())
    assert not ok and "重复" in res.reason


def test_apply_op_reject_malformed_skill_args():
    r, _, _ = _refiner()
    bad = {"skill_id": "z", "name_cn": "缺字段"}        # 缺 type/trigger/... → ValidationError
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=bad, rationale="r"), "K", PASS_K())
    assert not ok and ("ValidationError" in res.reason or "validation" in res.reason.lower())


# ── 终审 blocking 回归:观测字段写保护 + 非字符串 regime 不崩 + write_skill 状态钳制 ──

def _legal_skill(skill_id="newk", **over):
    d = {"skill_id": skill_id, "name_cn": "新技能", "type": "pattern",
         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
         "exit_stop": "x", "status": "incubating"}
    d.update(over)
    return d


def test_apply_op_reject_patch_stats():
    # FIX 1(a)/(c)edit:Refiner 不可 patch 观测字段 stats(由 apply_credit 维护)
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="patch_skill",
                                   args={"skill_id": "a", "stats": {"n": 999, "wins": 999}},
                                   rationale="想伪造战绩"), "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert "stats" in res.reason
    assert h.skills.get("a").stats.n == 0          # 未被篡改
    assert len(meta.log) == 0                       # 未记日志


def test_apply_op_reject_update_importance():
    # FIX 1(b)/(c)edit:Refiner 不可 update 观测字段 importance(由 demote/时间衰减管理)
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="update_memory",
                                   args={"lesson_id": "l1", "importance": {"base": 99.0}},
                                   rationale="想拉高重要度"), "M", PASS_M())
    assert not ok and isinstance(res, RejectedEdit)
    assert h.memory.get("l1").importance.base == 1.0   # 未被篡改
    assert len(meta.log) == 0


def test_apply_op_write_skill_status_clamped():
    # FIX 1(c):LLM 即便指定 status=active,新建技能也只能 incubating(孵化→晋升闸)
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="write_skill",
                                   args=_legal_skill("newk", status="active"),
                                   rationale="新模式"), "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert h.skills.get("newk").status == "incubating"
    assert h.skills.get("newk") not in h.skills.by_status("active")


def test_apply_op_write_skill_drops_injected_stats():
    # FIX 1(c):LLM 注入的伪造 stats 必须被丢弃,新技能 stats 归零
    r, h, meta = _refiner()
    args = _legal_skill("newk")
    args["stats"] = {"n": 999, "wins": 999}
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=args, rationale="新模式"),
                          "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert h.skills.get("newk").stats.n == 0


def test_apply_op_process_memory_drops_injected_importance():
    # FIX 1(c):LLM 注入的伪造 importance 必须被丢弃,新教训 importance 归默认
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="process_memory",
                                   args={"lesson_id": "lnew", "regime": "主升",
                                         "outcome": "loss", "lesson": "新教训",
                                         "importance": {"base": 99.0}},
                                   rationale="记牢"), "M", PASS_M())
    assert ok and isinstance(res, AppliedEdit)
    assert h.memory.get("lnew").importance.base == 1.0


def test_apply_op_reject_nonstring_regime_process_memory():
    # FIX 2(a):非字符串 regime 必须被干净拒绝(不抛)
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="process_memory",
                                   args={"lesson_id": "lnew", "regime": ["主升"],
                                         "outcome": "loss", "lesson": "新教训"},
                                   rationale="记牢"), "M", PASS_M())
    assert not ok and isinstance(res, RejectedEdit)
    assert len(meta.log) == 0


def test_apply_op_reject_nonstring_regime_write_skill():
    # FIX 2(a):applicable_regime 含非字符串元素必须被干净拒绝(不抛)
    r, h, meta = _refiner()
    args = _legal_skill("newk", applicable_regime=["主升", 2024])
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=args, rationale="新模式"),
                          "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert len(meta.log) == 0


def test_refine_malformed_op_does_not_abort_pass():
    # 一条坏 op 不丢整轮:malformed write_skill 进 rejected,合法 promote 进 applied
    h = _harness()
    from youzi.harness.skill import Skill
    h.skills.write(Skill.from_seed(_legal_skill("inc1")))   # 一个 incubating 技能供 promote
    h.skills.get("inc1").stats.n = 3                        # A1 晋升证据门:n>=3 且超额>0
    h.skills.get("inc1").stats.expectancy = 0.2
    k_ops = ('{"ops": ['
             '{"tool": "write_skill", "args": {"skill_id": "bad1", "name_cn": "坏",'
             ' "type": "pattern", "applicable_regime": ["主升", 2024], "trigger": "t",'
             ' "entry": "e", "exit_stop": "x"}, "rationale": "坏regime"},'
             '{"tool": "promote_skill", "args": {"skill_id": "inc1"}, "rationale": "晋升"}]}')
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h)
    assert {e.tool for e in rep.applied} == {"promote_skill"}
    assert h2.skills.get("inc1").status == "active"
    assert any(rj.tool == "write_skill" for rj in rep.rejected)


# 小工具:从 ops 取白名单,避免在测试里硬写 frozenset
def PASS_K():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["K"]


def PASS_P():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["p"]


def PASS_M():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["M"]


from youzi.refine.refiner_prompt import build_refiner_system_prompt  # noqa
from youzi.refine.credit import CreditReport
from youzi.eval.trajectory import Trajectory


def _empty_evidence():
    return Trajectory(steps=[], horizon=1), CreditReport(n_scored=0), []


def _run_refine(scripts, h=None, cfg=None):
    """scripts:按 p/K/M 三次 live 调用顺序给出的 LLM 响应列表。"""
    h = h or _harness()
    meta = MetaTools(h)
    llm = MockLLMClient(scripts)
    r = Refiner(h, llm, meta, cfg or RefinerConfig())
    traj, credit, sigs = _empty_evidence()
    return r.refine(traj, credit, sigs), h, meta, llm


def test_refine_g_pass_is_noop_three_live_calls():
    # 三个 pass 都给空 ops;ΔG 不发调用 → MockLLM 恰好被调 3 次
    rep, h, meta, llm = _run_refine(['{"ops": []}', '{"ops": []}', '{"ops": []}'])
    assert len(llm.calls) == 3
    assert any("G-pass reserved" in n for n in rep.notes)
    assert rep.applied == [] and rep.rejected == []


def test_refine_happy_path_applies_and_logs():
    # p: 改 mutable doctrine;K: 新建 failure_detector 技能;M: 写一条 loss 教训
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "主升作战", "new_guidance": "只打最高板"}, "rationale": "杂毛连亏"}]}'
    k_ops = ('{"ops": [{"tool": "write_skill", "args": {"skill_id": "fd1", "name_cn": "追高板防闷",'
             ' "type": "failure_detector", "applicable_regime": ["主升"], "trigger": "最高板尾盘弱",'
             ' "entry": "不追", "exit_stop": "次日低开走", "status": "incubating"}, "rationale": "chased_into_nuke 反复"}]}')
    m_ops = '{"ops": [{"tool": "process_memory", "args": {"lesson_id": "ls1", "regime": "主升", "outcome": "loss", "lesson": "追最高板被闷"}, "rationale": "记牢"}]}'
    rep, h, meta, llm = _run_refine([p_ops, k_ops, m_ops])
    assert {e.tool for e in rep.applied} == {"rewrite_doctrine", "write_skill", "process_memory"}
    assert rep.rejected == []
    assert h.doctrine.get("主升作战").guidance == "只打最高板"
    assert h.skills.get("fd1") is not None and h.skills.get("fd1").type == "failure_detector"
    assert h.memory.get("ls1") is not None
    # 全进 EditLog,且带 rationale
    assert len(meta.log) == 3
    assert all(rec.rationale for rec in meta.log.records())


def test_refine_rejects_immutable_in_p_pass():
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "纪律:退潮不接力", "new_guidance": "放松"}, "rationale": "想改"}]}'
    rep, h, meta, llm = _run_refine([p_ops, '{"ops": []}', '{"ops": []}'])
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "Immutable" in rep.rejected[0].reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"
    assert len(meta.log) == 0


def test_refine_per_pass_cap_enforced():
    # K-pass 给 3 个 promote,但 cap=1 → 1 applied(被 a 占用?需先 incubating)+ 余者超限拒绝
    h = _harness()
    # 准备 3 个 incubating 技能 b/c/d
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
        h.skills.get(sid).stats.n = 3                   # A1 晋升证据门:n>=3 且超额>0
        h.skills.get(sid).stats.expectancy = 0.2
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "d"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=1, max_edits_per_refine=12)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 2 and all("per-pass" in r.reason for r in rep.rejected)


def test_refine_per_refine_cap_enforced():
    h = _harness()
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
        h.skills.get(sid).stats.n = 3                   # A1 晋升证据门:n>=3 且超额>0
        h.skills.get(sid).stats.expectancy = 0.2
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=5, max_edits_per_refine=1)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 1 and "per-refine" in rep.rejected[0].reason


# ── Phase-1b-3d:退役证据门(治小样本过度退役)──

def test_retire_gate_rejects_thin_samples():
    # _harness 技能 "a" stats.n=0(默认)< K=5 → 退役被拒、技能未退役、未记日志
    h = _harness()
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="想退役"),
                          "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert "证据不足" in res.reason and "min_retire_samples" in res.reason
    assert h.skills.get("a").status == "active"     # 未退役
    assert len(meta.log) == 0


def test_retire_gate_allows_when_enough_samples():
    h = _harness()
    h.skills.get("a").stats.n = 5                   # 样本足够
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="n=5真亏"),
                          "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert h.skills.get("a").status == "dormant"


def test_retire_gate_applies_to_permanent_too():
    h = _harness()                                  # a.stats.n=0 < 5
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill",
                                   args={"skill_id": "a", "permanent": True}, rationale="永久"),
                          "K", PASS_K())
    assert not ok and "证据不足" in res.reason
    assert h.skills.get("a").status == "active"


def test_retire_gate_does_not_swallow_hallucinated_target():
    # 不存在的技能仍走 dispatch 的 KeyError(门只挡"存在但样本不足"),不误吞
    h = _harness()
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "不存在"}, rationale="r"),
                          "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_refine_level_rejects_thin_retire():
    # refine() 整轮:K-pass 脚本退役 n<K 技能 → 进 rejected、H 未变
    k_ops = '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "a"}, "rationale": "想退"}]}'
    rep, h, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'],
                                    cfg=RefinerConfig(min_retire_samples=5))
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "证据不足" in rep.rejected[0].reason
    assert h.skills.get("a").status == "active"


def test_refiner_config_rejects_degenerate_min_retire():
    import pytest
    with pytest.raises(Exception):
        RefinerConfig(min_retire_samples=0)


# ── A1:晋升证据门(镜像退役门:n≥min_promote_samples 且 超额>0 才许 incubating→active)──

def _with_incubating(h, sid, n=0, expectancy=None):
    from youzi.harness.skill import Skill
    h.skills.write(Skill.from_seed(_legal_skill(sid)))
    s = h.skills.get(sid)
    s.stats.n = n
    s.stats.expectancy = expectancy
    return s


def test_promote_gate_rejects_thin_samples():
    h = _harness()
    _with_incubating(h, "inc1", n=2, expectancy=0.5)    # 超额够但 n=2<3
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_promote_samples=3))
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "inc1"},
                                   rationale="想晋升"), "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert "证据不足" in res.reason and "min_promote_samples" in res.reason
    assert h.skills.get("inc1").status == "incubating"   # 未半应用
    assert len(meta.log) == 0                            # 未记日志


def test_promote_gate_rejects_nonpositive_expectancy():
    h = _harness()
    _with_incubating(h, "inc1", n=5, expectancy=-0.1)   # n 够但超额<=0
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig())
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "inc1"},
                                   rationale="想晋升"), "K", PASS_K())
    assert not ok and "超额" in res.reason
    assert h.skills.get("inc1").status == "incubating"
    assert len(meta.log) == 0


def test_promote_gate_rejects_missing_expectancy():
    h = _harness()
    _with_incubating(h, "inc1", n=5, expectancy=None)   # n 够但无超额观测(防 n 被旁路填充)
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig())
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "inc1"},
                                   rationale="想晋升"), "K", PASS_K())
    assert not ok and "证据不足" in res.reason
    assert h.skills.get("inc1").status == "incubating"


def test_promote_gate_allows_when_evidence():
    h = _harness()
    _with_incubating(h, "inc1", n=3, expectancy=0.01)   # 达标:n>=3 且超额>0
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig())
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "inc1"},
                                   rationale="试验位3战皆超额"), "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert h.skills.get("inc1").status == "active"


def test_promote_gate_does_not_swallow_hallucinated_target():
    # 不存在的技能仍走 dispatch 的 KeyError(门只挡"存在但证据不足"),不误吞
    h = _harness()
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig())
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "不存在"},
                                   rationale="r"), "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_refine_level_rejects_zero_evidence_promote():
    # refine() 整轮:K-pass 脚本晋升 n=0 孵化技能 → 进 rejected、状态未变
    h = _harness()
    _with_incubating(h, "inc1")                          # n=0, expectancy=None
    k_ops = '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "inc1"}, "rationale": "想晋升"}]}'
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h)
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "证据不足" in rep.rejected[0].reason
    assert h2.skills.get("inc1").status == "incubating"


def test_k_pass_prompt_states_promote_gate_threshold():
    # K-pass 系统提示注明真实晋升门槛(config 值透传)
    p = build_refiner_system_prompt(_harness(), "K", min_promote_samples=4)
    assert "n≥4" in p and "超额>0" in p and "试验位" in p


def test_refiner_config_rejects_degenerate_min_promote():
    with pytest.raises(Exception):
        RefinerConfig(min_promote_samples=0)


def test_target_id_normalizes_numeric_id_no_crash():
    # LLM 把 id 发成数字({"skill_id": 7})时,拒绝路径不得崩——target_id 归一为 str
    h = _harness()
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": 7}, rationale="r"),
                          "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert res.target_id == "7"          # 归一为字符串,不崩
    assert "KeyError" in res.reason      # 无技能 "7" → dispatch KeyError → 干净拒绝


# ── A3:编辑史(_recent_reports)累积/maxlen=2 滚动/渲染进下次 user prompt ──

def test_refine_history_accumulates_rolls_and_renders():
    h = _harness()
    from youzi.harness.skill import Skill
    for sid in ("b", "c"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
        h.skills.get(sid).stats.n = 3                   # A1 晋升证据门:n>=3 且超额>0
        h.skills.get(sid).stats.expectancy = 0.2
    empty = '{"ops": []}'
    promote_b = '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "晋升b"}]}'
    # retire a:n=0<5 → 被退役证据门拒(产出 rejected 供历史渲染)
    retire_a = '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "a"}, "rationale": "想退"}]}'
    promote_c = '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "晋升c"}]}'
    # 3 次 refine × 各 3 次 live 调用(p/K/M):
    #   refine1: K 晋升 b(applied);refine2: K 退役 a(rejected);refine3: K 晋升 c
    llm = MockLLMClient([empty, promote_b, empty,
                         empty, retire_a, empty,
                         empty, promote_c, empty])
    r = Refiner(h, llm, MetaTools(h), RefinerConfig(min_retire_samples=5))
    traj, credit, sigs = _empty_evidence()

    rep1 = r.refine(traj, credit, sigs)
    assert list(r._recent_reports) == [rep1]
    # refine1 时无历史 → 编辑史段 "(无)"
    assert "(无)" in llm.calls[0][1].split("近期编辑史")[1]

    rep2 = r.refine(traj, credit, sigs)
    # refine2 的 user prompt 渲染了 refine1 的 applied(tool/target/rationale)
    u2 = llm.calls[3][1]
    assert "[第1次/applied] K/promote_skill → b: 晋升b" in u2
    assert list(r._recent_reports) == [rep1, rep2]

    rep3 = r.refine(traj, credit, sigs)
    # refine3 的 user prompt 同时渲染 refine1 的 applied 与 refine2 的 rejected(带拒因)
    u3 = llm.calls[6][1]
    assert "[第1次/applied] K/promote_skill → b: 晋升b" in u3
    assert "[第2次/rejected] K/retire_skill → a: 拒因=" in u3
    assert "证据不足" in u3                       # 拒因原文透给 LLM(此前完全不可见)
    # maxlen=2 滚动:rep1 被挤出,只剩最近 2 次
    assert list(r._recent_reports) == [rep2, rep3]
