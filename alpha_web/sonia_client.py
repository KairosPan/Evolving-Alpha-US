from __future__ import annotations

import asyncio
import os

import httpx


class SoniaClient:
    """Thin httpx wrapper over the Sonia meta-agent service. Network errors propagate as
    httpx.HTTPError (the web layer catches them and shows a 'Sonia unavailable' banner).

    Uses httpx.AsyncClient internally so it is compatible with both real HTTP and
    in-process ASGI transport (httpx.ASGITransport) for testing.
    """

    def __init__(self, base_url: str | None = None, *, transport=None, timeout: float = 30.0) -> None:
        self.base_url = base_url or os.environ.get("ALPHA_SONIA_URL", "http://127.0.0.1:8810")
        self._transport = transport
        self._timeout = timeout

    def _run(self, coro):
        """Run an async coroutine synchronously."""
        return asyncio.run(coro)

    async def _aget(self, path: str) -> dict | list:
        async with httpx.AsyncClient(
            base_url=self.base_url, transport=self._transport, timeout=self._timeout
        ) as c:
            r = await c.get(path)
            r.raise_for_status()
            return r.json()

    async def _apost(self, path: str, json: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(
            base_url=self.base_url, transport=self._transport, timeout=self._timeout
        ) as c:
            r = await c.post(path, json=json or {})
            r.raise_for_status()
            return r.json()

    def _get(self, path: str) -> dict | list:
        return self._run(self._aget(path))

    def _post(self, path: str, json: dict | None = None) -> dict | list:
        return self._run(self._apost(path, json))

    def healthz(self) -> dict:
        return self._get("/healthz")

    def new_session(self) -> dict:
        return self._post("/sessions/new")

    def list_sessions(self) -> list:
        return self._get("/sessions")

    def get_session(self, sid: str) -> dict:
        return self._get(f"/sessions/{sid}")

    def chat(self, session_id: str | None, text: str, attachments: list) -> dict:
        return self._post("/chat", {"session_id": session_id, "text": text,
                                    "attachments": [a.model_dump() for a in attachments]})

    def edit(self, sid: str, eid: str, action: str) -> dict:
        return self._post(f"/sessions/{sid}/edit/{eid}", {"action": action})

    def apply(self, sid: str, mid: str) -> dict:
        return self._post(f"/sessions/{sid}/messages/{mid}/apply")

    def rollback(self, sid: str, mid: str) -> dict:
        return self._post(f"/sessions/{sid}/messages/{mid}/rollback")
