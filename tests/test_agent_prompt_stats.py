# tests/test_agent_prompt_stats.py
from youzi.agent.prompt import build_system_prompt
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState


def _h(skills, lessons):
    return HarnessState(
        doctrine=Doctrine(entries=[]),
        skills=SkillRegistry.from_skills(skills),
        memory=MemoryStore.from_lessons(lessons),
        cycle=StateMachine.from_seed_list([]))


def _skill(sid="s1", status="active"):
    return Skill.from_seed({"skill_id": sid, "name_cn": "龙头接力", "type": "pattern",
                            "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                            "exit_stop": "x", "status": status})


def test_no_stats_no_winmem_is_unchanged_skill_line():
    s = _skill()
    h = _h([s], [])
    prompt = build_system_prompt(h)
    # n==0:技能行不含战绩串
    assert "战绩" not in prompt
    assert "[成功]" not in prompt
    # 行体与原格式一致
    assert "- 龙头接力(s1)[pattern] 适用[主升] 触发:t 买点:e 卖/止:x 禁忌:" in prompt


def test_stats_rendered_when_n_positive():
    s = _skill()
    s.stats.n = 5
    s.stats.wins = 1
    s.stats.nukes = 3
    s.stats.ewma_winrate = 0.2
    s.stats.expectancy = -0.4
    h = _h([s], [])
    prompt = build_system_prompt(h)
    assert "[战绩 n=5 胜率=0.20 nukes=3 exp=-0.40]" in prompt


def test_win_memory_rendered():
    s = _skill()
    win = Lesson.from_seed({"lesson_id": "w1", "regime": "主升", "outcome": "win",
                            "named_analog": "妖股X", "lesson": "低吸成功"})
    h = _h([s], [win])
    prompt = build_system_prompt(h)
    assert "- [成功] 妖股X:低吸成功" in prompt
