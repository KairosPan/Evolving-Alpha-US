# tests/test_llm_cache.py
"""E1 LLM record/replay 缓存:全离线,MockLLMClient 作内层,决不触网。"""
from __future__ import annotations

import json

import pytest

from youzi.llm.cache import CachedLLMClient, CacheMissError, compute_key
from youzi.llm.client import LLMClient, MockLLMClient


def _client(store, inner, mode="read_write", **kw):
    kw.setdefault("model", "deepseek-chat")
    kw.setdefault("temperature", 0.0)
    return CachedLLMClient(inner, store, mode=mode, **kw)


# ---- record → replay 往返 ----

def test_read_write_records_then_replays_within_instance(tmp_path):
    inner = MockLLMClient('{"a":1}')
    c = _client(tmp_path, inner)
    assert c.complete("sys", "usr") == '{"a":1}'
    assert len(inner.calls) == 1                       # miss → 调内层
    assert c.complete("sys", "usr") == '{"a":1}'
    assert len(inner.calls) == 1                       # hit → 内层不被调
    assert (c.misses, c.hits) == (1, 1)


def test_replay_across_instances_returns_recorded_not_inner(tmp_path):
    _client(tmp_path, MockLLMClient('{"a":1}')).complete("sys", "usr")   # record
    inner2 = MockLLMClient('{"b":2}')                  # 内层换了响应也不该被触达
    c2 = _client(tmp_path, inner2)
    assert c2.complete("sys", "usr") == '{"a":1}'      # 回放录制值
    assert inner2.calls == []


def test_satisfies_llmclient_protocol(tmp_path):
    c = _client(tmp_path, MockLLMClient("ok"))
    assert isinstance(c, LLMClient)                    # runtime-checkable Protocol,对调用方透明


# ---- read_only:miss 即 raise,决不静默回落 live ----

def test_read_only_miss_raises_and_never_calls_inner(tmp_path):
    inner = MockLLMClient("live-应永不出现")
    c = _client(tmp_path, inner, mode="read_only")
    with pytest.raises(CacheMissError):
        c.complete("sys", "usr")
    assert inner.calls == []                           # 决不回落 live


def test_read_only_hit_returns_cached_without_inner(tmp_path):
    _client(tmp_path, MockLLMClient("recorded")).complete("sys", "usr")
    inner = MockLLMClient("live-应永不出现")
    c = _client(tmp_path, inner, mode="read_only")
    assert c.complete("sys", "usr") == "recorded"
    assert inner.calls == []


def test_read_only_fingerprint_mismatch_misses(tmp_path):
    """提示版本指纹进 key:模板演化后旧响应失配,防误用(spec'提示已变需重录')。"""
    _client(tmp_path, MockLLMClient("v1响应"), fingerprint="prompt-v1").complete("s", "u")
    c = _client(tmp_path, MockLLMClient("x"), mode="read_only", fingerprint="prompt-v2")
    with pytest.raises(CacheMissError):
        c.complete("s", "u")


# ---- off:纯透传,不读不写 ----

def test_off_mode_passes_through_and_writes_nothing(tmp_path):
    inner = MockLLMClient("live")
    c = _client(tmp_path, inner, mode="off")
    assert c.complete("s", "u") == "live"
    assert c.complete("s", "u") == "live"
    assert len(inner.calls) == 2                       # 每次都打内层
    assert list(tmp_path.rglob("*.json")) == []        # 不落盘


# ---- key 区分:成分任一变,key 必变 ----

def test_key_discriminates_every_component():
    base = compute_key("m", 0.0, "sys", "usr", "fp")
    variants = [
        compute_key("m2", 0.0, "sys", "usr", "fp"),    # model
        compute_key("m", 0.3, "sys", "usr", "fp"),     # temperature
        compute_key("m", 0.0, "sys2", "usr", "fp"),    # system
        compute_key("m", 0.0, "sys", "usr2", "fp"),    # user
        compute_key("m", 0.0, "sys", "usr", "fp2"),    # fingerprint
    ]
    assert len({base, *variants}) == 6


def test_key_is_stable_across_calls():
    assert compute_key("m", 0.0, "系统", "用户") == compute_key("m", 0.0, "系统", "用户")


def test_distinct_prompts_create_distinct_entries(tmp_path):
    inner = MockLLMClient(["r1", "r2"])
    c = _client(tmp_path, inner)
    assert c.complete("sys", "u1") == "r1"
    assert c.complete("sys", "u2") == "r2"
    assert len(c.keys()) == 2
    assert c.complete("sys", "u1") == "r1"             # 各自独立回放
    assert c.complete("sys", "u2") == "r2"
    assert len(inner.calls) == 2


# ---- 原子写产物:可重载、不留 .tmp ----

def test_entry_on_disk_is_reloadable_and_complete(tmp_path):
    c = _client(tmp_path, MockLLMClient('{"r":1}'), fingerprint="fp1")
    c.complete("系统提示", "用户提示")
    key = compute_key("deepseek-chat", 0.0, "系统提示", "用户提示", "fp1")
    p = tmp_path / key[:2] / f"{key}.json"
    assert p.exists()                                  # 路径 = store/<key[:2]>/<key>.json
    entry = json.loads(p.read_text(encoding="utf-8"))
    assert entry["key"] == key
    assert entry["model"] == "deepseek-chat"
    assert entry["temperature"] == 0.0
    assert entry["fingerprint"] == "fp1"
    assert entry["system"] == "系统提示"               # 全文落盘,可审计
    assert entry["user"] == "用户提示"
    assert entry["response"] == '{"r":1}'
    assert entry["created"]
    assert list(tmp_path.rglob("*.tmp")) == []         # 原子写不留临时文件


def test_corrupt_entry_treated_as_miss_and_rerecorded(tmp_path):
    c = _client(tmp_path, MockLLMClient("good"))
    c.complete("s", "u")
    key = compute_key("deepseek-chat", 0.0, "s", "u")
    p = tmp_path / key[:2] / f"{key}.json"
    p.write_bytes(b"\x00\x05\x16\x07 not json")        # 损坏(如截断/二进制)
    assert c.complete("s", "u") == "good"              # 视同 miss → 重录覆盖
    assert json.loads(p.read_text(encoding="utf-8"))["response"] == "good"


# ---- ._AppleDouble 垃圾被跳过(/Volumes 已知坑) ----

def test_appledouble_files_are_skipped(tmp_path):
    c = _client(tmp_path, MockLLMClient("real"))
    c.complete("s", "u")
    key = compute_key("deepseek-chat", 0.0, "s", "u")
    (tmp_path / key[:2] / f"._{key}.json").write_bytes(b"\x00\x05\x16\x07AppleDouble")
    (tmp_path / "._garbage.json").write_bytes(b"\x00\x05")
    assert c.keys() == [key]                           # 只见真条目
    assert c.complete("s", "u") == "real"              # 回放不受垃圾影响


def test_keys_empty_when_store_missing(tmp_path):
    c = _client(tmp_path / "不存在", MockLLMClient("x"))
    assert c.keys() == []


# ---- 构造参数:model/temperature 显式传入或从内层取,决不臆造 ----

def test_model_temperature_taken_from_inner_private_attrs(tmp_path):
    class FakeDeepSeek:                                # 模拟 DeepSeekClient 的私有属性形态
        _model = "deepseek-chat"
        _temperature = 0.0

        def complete(self, system: str, user: str) -> str:
            return "from-inner"

    c1 = CachedLLMClient(FakeDeepSeek(), tmp_path)     # 不显式传:从 _model/_temperature 取
    assert c1.complete("s", "u") == "from-inner"
    c2 = _client(tmp_path, MockLLMClient("x"), mode="read_only")   # 显式同值 → 同 key 命中
    assert c2.complete("s", "u") == "from-inner"


def test_missing_model_raises(tmp_path):
    with pytest.raises(ValueError):
        CachedLLMClient(MockLLMClient("x"), tmp_path)  # Mock 无 model/temperature 且未显式传


def test_unknown_mode_raises(tmp_path):
    with pytest.raises(ValueError):
        _client(tmp_path, MockLLMClient("x"), mode="replay")   # 仅 read_write/read_only/off
