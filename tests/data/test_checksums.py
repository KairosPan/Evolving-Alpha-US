# tests/data/test_checksums.py
"""D6: capture writes CHECKSUMS; verify is typed; fail-closed vs warn; missing manifest warns."""
from __future__ import annotations

from datetime import date

import pytest

from alpha.data.capture import capture_window
from alpha.data.pit_store import PITStore
from alpha.data.integrity_check import verify_checksums


def _captured_root(tmp_path, fake_source):
    root = tmp_path / "win"
    capture_window(fake_source, PITStore(root), date(2026, 6, 10), date(2026, 6, 12), ["RUN", "FLOP"])
    return root


def test_capture_writes_manifest_covering_every_file(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    manifest = root / "CHECKSUMS"
    assert manifest.exists()
    listed = {line.split(maxsplit=1)[1] for line in manifest.read_text().splitlines() if line}
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"CHECKSUMS"}
    assert listed == on_disk and len(listed) > 0        # non-vacuous


def test_clean_window_verifies_in_both_postures(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    assert verify_checksums(root, fail_closed=True) == []
    assert verify_checksums(root, fail_closed=False) == []


def test_tampered_file_fails_closed_with_typed_message(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    victim = next(p for p in root.rglob("*.parquet"))
    victim.write_bytes(victim.read_bytes() + b"x")
    with pytest.raises(RuntimeError, match="mismatch"):
        verify_checksums(root, fail_closed=True)
    problems = verify_checksums(root, fail_closed=False)     # warn posture: returned, not raised
    assert any("mismatch" in p and victim.name in p for p in problems)


def test_missing_and_extra_files_are_typed(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    (root / "stray.txt").write_text("x")
    next(iter(root.rglob("*.parquet"))).unlink()
    problems = verify_checksums(root, fail_closed=False)
    assert any(p.startswith("missing:") for p in problems)
    assert any(p.startswith("extra:") for p in problems)


def test_manifestless_window_warns_never_raises(tmp_path, fake_source, capsys):
    root = _captured_root(tmp_path, fake_source)
    (root / "CHECKSUMS").unlink()
    assert verify_checksums(root, fail_closed=True) == []
    assert "no CHECKSUMS" in capsys.readouterr().out
