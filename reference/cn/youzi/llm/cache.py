# youzi/llm/cache.py
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from youzi.llm.client import LLMClient

CacheMode = Literal["read_write", "read_only", "off"]
_MODES: tuple[str, ...] = ("read_write", "read_only", "off")


class CacheMissError(KeyError):
    """read_only 模式下缓存未命中:决不静默回落 live(防假离线)。"""


def compute_key(model: str, temperature: float, system: str, user: str,
                fingerprint: str = "") -> str:
    """content-addressed key = sha256(canonical_json(成分))。

    成分 = {fingerprint, model, temperature, system, user},canonical = sort_keys
    + 紧凑分隔符 + ensure_ascii=False,跨进程/跨平台稳定。fingerprint 是提示版本
    指纹(如 build_system_prompt 模板版本):模板演化后旧响应自动失配,防误用
    (E1 spec"提示已变需重录")。提示本身是 H 状态+当日数据的纯函数,故 key
    天然区分 H 演化的每个状态,无需独立 H-hash。
    """
    payload = {"fingerprint": fingerprint, "model": model, "temperature": temperature,
               "system": system, "user": user}
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class CachedLLMClient:
    """LLM record/replay 缓存:包装任意 LLMClient,对调用方透明(同样实现 Protocol)。

    三模式(以 E1 spec 为准):
    - ``read_write``:hit→返回缓存(不调内层);miss→调内层并原子落盘(record+replay 合一)。
    - ``read_only``:hit→返回缓存;miss→raise CacheMissError,决不静默回落 live(防假离线)。
    - ``off``:纯透传,不读不写。

    落盘:每条响应一个 JSON 文件 store_dir/<key[:2]>/<key>.json,tmp+os.replace
    原子写(同 PITStore/RunStore 惯例)。条目存 key 成分原文(model/temperature/
    fingerprint/system/user)+ response + created——全文虽 ~24KB/条但磁盘便宜,
    审计价值大(可直接 diff 提示演化)。

    model/temperature 进 key 但 Protocol 不暴露:构造时显式传入优先,否则从内层
    client 的 ``_model``/``_temperature``(DeepSeekClient 私有)或 ``model``/
    ``temperature`` 公有属性取;都取不到则 raise——key 必须稳定,不臆造默认值。
    """

    def __init__(self, inner: LLMClient, store_dir: str | Path,
                 mode: CacheMode = "read_write",
                 model: str | None = None, temperature: float | None = None,
                 fingerprint: str = "") -> None:
        if mode not in _MODES:
            raise ValueError(f"未知缓存模式: {mode!r}(可选 {_MODES})")
        self._inner = inner
        self._root = Path(store_dir)
        self._mode: CacheMode = mode
        self._model = model if model is not None else self._from_inner(inner, "_model", "model")
        t = temperature if temperature is not None \
            else self._from_inner(inner, "_temperature", "temperature")
        self._temperature = float(t)
        self._fingerprint = fingerprint
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _from_inner(inner: LLMClient, *names: str):
        """从内层 client 取 key 成分(私有名优先);取不到即报错,决不臆造。"""
        for n in names:
            v = getattr(inner, n, None)
            if v is not None:
                return v
        raise ValueError(f"内层 client 无 {'/'.join(names)} 属性,请构造时显式传入"
                         f"(key 成分必须稳定,不臆造默认值)")

    # ---- LLMClient Protocol ----

    def complete(self, system: str, user: str) -> str:
        if self._mode == "off":
            return self._inner.complete(system, user)
        key = compute_key(self._model, self._temperature, system, user, self._fingerprint)
        cached = self._load(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        if self._mode == "read_only":
            raise CacheMissError(
                f"LLM 缓存未命中(read_only 决不回落 live): key={key} "
                f"model={self._model} temperature={self._temperature} "
                f"fingerprint={self._fingerprint!r}——提示/模型可能已变,需用 read_write 重录")
        response = self._inner.complete(system, user)
        self._save(key, system, user, response)
        return response

    # ---- 存储 ----

    def _path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.json"

    def _load(self, key: str) -> str | None:
        """命中返回 response,未命中/损坏/key 不符返回 None(损坏视同 miss,read_write 会重录覆盖)。"""
        p = self._path(key)
        if not p.exists():
            return None
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None
        if entry.get("key") != key or not isinstance(entry.get("response"), str):
            return None
        return entry["response"]

    def _save(self, key: str, system: str, user: str, response: str) -> None:
        entry = {"key": key, "model": self._model, "temperature": self._temperature,
                 "fingerprint": self._fingerprint, "system": system, "user": user,
                 "response": response,
                 "created": datetime.now(timezone.utc).isoformat()}
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=final.parent, suffix=".json.tmp")
        os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(entry, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            os.replace(tmp, final)              # 原子写:决不在最终路径留截断文件
        except BaseException:                   # 含 KeyboardInterrupt:清理临时、不发布半成品
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def keys(self) -> list[str]:
        """列出全部已缓存 key(供黄金 run 固化/审计)。跳过 ._AppleDouble/隐藏文件
        (macOS 非原生卷如 /Volumes 会生成二进制 ._*.json,项目已知坑)。"""
        if not self._root.is_dir():
            return []
        out: list[str] = []
        for p in self._root.glob("*/*.json"):
            if p.name.startswith(".") or p.parent.name.startswith("."):
                continue
            out.append(p.stem)
        return sorted(out)
