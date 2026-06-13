# tests/test_features_echelon.py
import pandas as pd
from youzi.schemas.market import EchelonRung
from youzi.features.echelon import build_echelon, max_board_height


def _zt():
    return pd.DataFrame({
        "code": ["1", "2", "3", "4"],
        "name": ["中马传动", "甲", "乙", "丙"],
        "boards": [7, 3, 3, 1],
    })


def test_build_echelon_groups_by_height_desc():
    rungs = build_echelon(_zt())
    assert rungs[0] == EchelonRung(height=7, count=1, representatives=["中马传动"])
    assert rungs[1].height == 3 and rungs[1].count == 2
    assert rungs[-1].height == 1


def test_max_board_height_empty_is_zero():
    assert max_board_height(pd.DataFrame(columns=["boards"])) == 0
    assert max_board_height(_zt()) == 7


def test_build_echelon_excludes_nonpositive_boards():
    df = pd.DataFrame({"code": ["1", "2"], "name": ["甲", "乙"], "boards": [0, 2]})
    rungs = build_echelon(df)
    assert [r.height for r in rungs] == [2]   # boards=0 行被剔除,不抛 ValidationError
