from pathlib import Path
from alpha.converse.workspace import Workspace


def test_workspace_root_is_resolved_dir(tmp_path):
    ws = Workspace(tmp_path / "proj")
    assert ws.root == (tmp_path / "proj").resolve()
    assert isinstance(ws.root, Path)
