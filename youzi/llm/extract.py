# youzi/llm/extract.py
from __future__ import annotations


def extract_json_object(raw: str) -> str | None:
    """从含 prose/markdown 围栏/thinking 前缀的文本里取第一个**配平**的 JSON 对象子串。

    扫描:跳到第一个 '{',按括号深度配平;字符串字面量内的 '{'/'}' 不计深度(尊重 \\ 转义)。
    深度归零处截断返回。找不到配平对象 → None。
    已知限制:若 prose 中先出现一个配平的 {...}(非目标 JSON),会返回它——agent/Refiner 均用
    json_object 模式,响应基本是纯 JSON,故风险低。
    """
    s = raw or ""
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None
