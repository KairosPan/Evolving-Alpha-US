"""alpha/integrity — the one hashing utility (kairos-mining §6 order-3)."""
import hashlib
from alpha.integrity import sha256_bytes, sha256_file, canonical_json, sha256_canonical_json


def test_sha256_bytes_matches_hashlib():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert sha256_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_canonical_json_is_order_insensitive():
    assert canonical_json({"b": 1, "a": [2, 3]}) == canonical_json({"a": [2, 3], "b": 1})
    assert canonical_json({"a": 1}) == '{"a":1}'


def test_sha256_canonical_json_stable():
    assert sha256_canonical_json({"x": 1}) == sha256_canonical_json({"x": 1})


def test_proposal_store_canonical_json_delegates():
    # the meta-layer canonicalizer and the integrity one must be THE SAME function
    from alpha.meta import proposal_store
    from alpha import integrity
    assert proposal_store.canonical_json is integrity.canonical_json
