from __future__ import annotations

from pathlib import Path

import pytest

from alpaca_kit.paper.home import book_dir, is_strategy_name, paper_home


def test_home_precedence():
    assert paper_home({"ALPHA_PAPER_HOME": "/x/books", "DSH_HOME": "/h"}) == Path("/x/books")
    assert paper_home({"ALPHA_PAPER_HOME": "  ", "DSH_HOME": "/h"}) == Path("/h/face/paper")
    assert paper_home({}) == Path.home() / ".dsh" / "face" / "paper"
    assert paper_home({"DSH_HOME": "~/dsh-home"}) == Path.home() / "dsh-home" / "face" / "paper"


@pytest.mark.parametrize("name", ["aqr-r1000", "storage_chain", "市场情绪", "Bloom-Energy营收预期分析", "a", "9lives"])
def test_channel_names_are_strategy_names(name):
    assert is_strategy_name(name)
    assert book_dir(Path("/home"), name) == Path("/home") / name


@pytest.mark.parametrize("name", ["", "_template", "__x", ".hidden", "-lead", "has space", "a/b", "a\\b", "..",
                                  "a" * 42, "dot.name"])
def test_non_names_are_refused(name):
    assert not is_strategy_name(name)
    with pytest.raises(ValueError, match="not a strategy name"):
        book_dir(Path("/home"), name)
