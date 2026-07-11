"""D3: scripts/render_prompt.py prints a day's sidecar — assembled prompt + offered/dropped table."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import render_prompt  # noqa: E402


def test_render_prompt_prints_sidecar(tmp_path, capsys):
    side = {"date": "2026-01-05", "assembled": "SYSTEM PROMPT TEXT",
            "records": [{"kind": "skill", "id": "s1", "status": "offered"},
                        {"kind": "lesson", "id": "m1", "status": "dropped", "reason": "budget-cut"}]}
    (tmp_path / "2026-01-05.prompt.json").write_text(json.dumps(side))
    render_prompt.main([str(tmp_path), "2026-01-05"])
    out = capsys.readouterr().out
    assert "SYSTEM PROMPT TEXT" in out and "budget-cut" in out and "s1" in out
