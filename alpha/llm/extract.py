from __future__ import annotations


def extract_json_object(raw: str) -> str | None:
    """Return the first BALANCED JSON object substring from text that may contain prose / markdown
    fences / thinking prefixes. Scans to the first '{', balances by brace depth; braces inside string
    literals don't count (respecting \\ escapes). Returns None if no balanced object is found."""
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
