from youzi.harness.cycle import StateMachine, EmotionPhase


def _states():
    return [
        {"phase": "退潮", "you_see": ["龙头与补涨龙共振下跌"],
         "transitions": [{"to": "混沌冰点", "signal": "板高降至4B-"}],
         "source_lines": [372]},
        {"phase": "主升", "you_see": ["龙头不断突破"],
         "transitions": [{"to": "震荡补涨", "signal": "第一根强分歧阴K且次日非强修复"}]},
    ]


def test_state_machine_get_and_signals():
    sm = StateMachine.from_seed_list(_states())
    assert sm.get("退潮").you_see == ["龙头与补涨龙共振下跌"]
    assert sm.next_signals("主升") == [("震荡补涨", "第一根强分歧阴K且次日非强修复")]
    assert sm.get("不存在") is None
    assert sm.phase_names() == ["退潮", "主升"]


def test_state_machine_rejects_duplicate_phases():
    import pytest
    with pytest.raises(ValueError):
        StateMachine.from_seed_list([
            {"phase": "主升", "you_see": [], "transitions": []},
            {"phase": "主升", "you_see": [], "transitions": []}])
