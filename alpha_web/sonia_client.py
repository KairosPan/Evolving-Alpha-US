from __future__ import annotations

import os

import httpx


class SoniaClient:
    """Thin synchronous httpx wrapper over the Sonia meta-agent service.

    Network errors propagate as httpx.HTTPError (the web layer catches them and shows a
    'Sonia unavailable' banner). Fully sync so it is safe to call from a sync or async
    web route (no asyncio.run, no AsyncClient). In tests a Starlette TestClient (itself a
    sync httpx.Client subclass over an ASGI app) is injected to drive Sonia in-process.
    """

    def __init__(self, base_url: str | None = None, *, client=None, timeout: float = 30.0) -> None:
        self.base_url = base_url or os.environ.get("ALPHA_SONIA_URL", "http://127.0.0.1:8810")
        self._client = client
        self._timeout = timeout

    def _request(self, method: str, path: str, json: dict | None = None) -> dict | list:
        if self._client is not None:
            r = self._client.request(method, path, json=json)
            r.raise_for_status()
            return r.json()
        with httpx.Client(base_url=self.base_url, timeout=self._timeout) as c:
            r = c.request(method, path, json=json)
            r.raise_for_status()
            return r.json()

    def healthz(self) -> dict:
        return self._request("GET", "/healthz")

    def new_session(self) -> dict:
        return self._request("POST", "/sessions/new")

    def list_sessions(self) -> list:
        return self._request("GET", "/sessions")

    def get_session(self, sid: str) -> dict:
        return self._request("GET", f"/sessions/{sid}")

    def delete_session(self, sid: str) -> dict:
        return self._request("POST", f"/sessions/{sid}/delete")

    def chat(self, session_id: str | None, text: str, attachments: list) -> dict:
        return self._request("POST", "/chat", json={
            "session_id": session_id,
            "text": text,
            "attachments": [a.model_dump() for a in attachments],
        })

    def edit(self, sid: str, eid: str, action: str) -> dict:
        return self._request("POST", f"/sessions/{sid}/edit/{eid}", json={"action": action})

    def apply(self, sid: str, mid: str) -> dict:
        return self._request("POST", f"/sessions/{sid}/messages/{mid}/apply")

    def rollback(self, sid: str, mid: str) -> dict:
        return self._request("POST", f"/sessions/{sid}/messages/{mid}/rollback")
