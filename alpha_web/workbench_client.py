from __future__ import annotations

import os

import httpx


class WorkbenchClient:
    """Thin synchronous httpx wrapper over the Workbench conversational service.

    Network errors propagate as httpx.HTTPError (the web layer catches them and shows a
    'Workbench unavailable' banner). Fully sync so it is safe to call from a sync or async
    web route (no asyncio.run, no AsyncClient). In tests a Starlette TestClient (itself a
    sync httpx.Client subclass over an ASGI app) is injected to drive Workbench in-process.
    """

    def __init__(self, base_url: str | None = None, *, client=None, timeout: float = 30.0) -> None:
        self.base_url = base_url or os.environ.get("ALPHA_WORKBENCH_URL", "http://127.0.0.1:8820")
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

    def converse(self, text: str) -> dict:
        return self._request("POST", "/converse", json={"text": text})

    def get_project(self) -> dict:
        return self._request("GET", "/project")

    def approve_edit(self, eid: str) -> dict:
        return self._request("POST", f"/edits/{eid}/approve")

    def reject_edit(self, eid: str) -> dict:
        return self._request("POST", f"/edits/{eid}/reject")

    def rollback(self) -> dict:
        return self._request("POST", "/rollback")
