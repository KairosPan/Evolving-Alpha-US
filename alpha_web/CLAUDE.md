# alpha_web/ — the read-only console + Sonia chat cockpit (:8100)

FastAPI + Jinja2 + HTMX — no JS CDN, no build step (htmx vendored at `static/htmx.min.js`;
webfonts still load from Google Fonts and degrade gracefully offline). **Read-only over the
brain**; talks to the sonia (:8810) and workbench (:8820) services over HTTP
(`sonia_client.py` / `workbench_client.py`) — never imports their packages.

```bash
pip install -e ".[web]"
python -m alpha_web                    # :8100  (ALPHA_WEB_HOST / ALPHA_WEB_PORT)
python -m pytest tests/web -q          # scoped tests (offline; autouse store isolation)
```

Artifact wiring (else pages render a badged SAMPLE built from the real models via `sample.py`):
`ALPHA_WEB_DECISIONS_DIR` / `ALPHA_WEB_VERDICTS_DIR` / `ALPHA_WEB_EVOLUTION`, single-file
overrides `ALPHA_WEB_DECISION` / `ALPHA_WEB_VERDICT`; `ALPHA_SONIA_URL` points the chat cockpit
at Sonia (defaults to `http://127.0.0.1:8810`).

## HTMX gotchas — a real shipped-bug class, don't reintroduce

- **Never redirect an HTMX XHR with 302** — htmx follows it and swaps the FULL page into the
  target, nesting the app inside itself. Post-action navigation = **204 + `HX-Redirect` header**.
- Deletions that remove an element return **empty 200**, not 204 — htmx *skips the swap* on 204,
  so the row would survive its own deletion.
- Session links in the rail are **plain `href`**, not `hx-get` (full navigation, no nesting).
- The left-rail brain drawer is **vanilla JS** — no HTMX in the rail; server pre-expands via
  `active ∈ BRAIN_KEYS`.

*Owner: KairosPan · reviewed 2026-07-10.*
