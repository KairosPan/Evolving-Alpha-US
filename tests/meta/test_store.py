from alpha.meta.store import LiveBrainStore
from alpha.harness.edit_log import EditLog


def test_load_empty_falls_back_to_seeds_without_writing(tmp_path):
    store = LiveBrainStore(tmp_path)
    assert store.is_live() is False
    h, log = store.load()
    assert len(h.skills.all()) > 0 and len(log) == 0   # seeds loaded
    assert not (tmp_path / "brain.json").exists()       # read never writes
    assert store.edit_count() == 0


def test_save_then_load_roundtrips_and_marks_live(tmp_path):
    store = LiveBrainStore(tmp_path)
    h, log = store.load()
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)
    assert store.is_live() is True and store.edit_count() == 1
    h2, log2 = store.load()
    assert len(log2) == 1 and log2.records()[0].target_id == "base_breakout"
    assert len(h2.skills.all()) == len(h.skills.all())


def test_snapshot_and_restore(tmp_path):
    store = LiveBrainStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                  # v0: no edits
    snap = store.snapshot("sess1")
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)
    assert store.edit_count() == 1
    store.restore(snap)
    assert store.edit_count() == 0                      # rolled back to pre-edit
