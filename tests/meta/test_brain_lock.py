import os, threading, time
import pytest
from alpha.meta.store import LiveBrainStore


def test_lock_is_exclusive_and_times_out(tmp_path):
    s = LiveBrainStore(tmp_path)
    held = threading.Event(); release = threading.Event()
    def holder():
        with s.lock():
            held.set(); release.wait(2)
    t = threading.Thread(target=holder); t.start()
    assert held.wait(1)
    with pytest.raises(RuntimeError):           # second acquirer cannot get it within the timeout
        with LiveBrainStore(tmp_path).lock(timeout=0.3):
            pass
    release.set(); t.join()
    with LiveBrainStore(tmp_path).lock(timeout=1):   # acquirable once released
        pass


def test_lock_file_created_under_root(tmp_path):
    with LiveBrainStore(tmp_path).lock():
        assert (tmp_path / ".brain.lock").exists()
