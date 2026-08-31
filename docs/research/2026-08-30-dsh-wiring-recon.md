# dsh wiring recon — for the chat-face implementation decision (2026-08-30)

Two-agent recon: the frozen 2026-08-22 survey re-read against the INSTALLED build
(`@deepseek-ai/dsh` 0.1.1-rc.2, running at 127.0.0.1:3080). Design input, frozen — records
what was true on this date; the build is a developer preview and will break.

## Ground truth from the installed build

**The web API is a published, typed contract, not internal wiring** (this corrects the
survey's implied read):

- Subpath export `@deepseek-ai/dsh-host-apiproxy/api` — per-domain `.d.ts` + zod schema pairs
  (sessions, events, approvals, questions, goals, jobs, rpc, rpc-map…). rpc.js calls the
  envelope "documented here as wire contract".
- Transport: unary `POST /api/<method>` with `{type:"client-request", rpcId, method, payload}`
  → `{type:"server-response", rpcId, result:{ok,…}}`, zod-validated both ways.
- ~50 methods incl. `session.list/search/create/history/rename/fork/prompt/cancel`,
  `subagent.list/history/prompt/interrupt`, `skill.list`, `settings.*`, `llm.*`.
- Event stream: `GET /api/events.mux` (all session-event frames, multiplexed) +
  `/api/events.host` — WebSocket upgrade paths (426 on plain GET, live-confirmed).
- **Approvals ride the same stream**: approval/question prompts arrive as server-request
  frames on events.mux; the client answers via `POST /api/respond`. Our face can BE the
  Gate-2 surface.
- Auth: none on localhost — only an anti-DNS-rebinding Host-header fence (403 on foreign
  Host, live-confirmed; source comments "this fence is not an auth layer"). Any local process
  can call the full API including `session.prompt`.
- Also exported: `createApiProxy` / `toFetchHandler` / `InProcessApiClient` — a Node host can
  mount the same API in-process without the web server (a middle path).

**The headless CLI cannot power a live face**: `dsh --profile headless "job"` is a one-shot
direct Agent driver — fresh session, run to quiescence, print final text, exit. No resume, no
attach, no stream. The "headless" bundle means *no Host/HTTP/browser plugins at all*, not a
headless server.

**Session storage**: `~/.dsh/sessions/<cwd-slug>/session-<uuid>/session.jsonl.zstd`,
append-only zstd-framed JSONL with a package-private decoder — the sanctioned read paths are
`session.history` and `events.mux`, not the file.

**Stability**: rc under 0.x, no changelog, pre-release anti-legacy policy (no shims, free
renames, backends reject old formats). The contract is typed and intentional but unpinned.

## From the survey (programmatic substrates)

- TS SDK (`packages/sdk`, JSON-RPC client/server) and Python SDK ("the programmatic
  alternative to the Web UI"; `run(task, session_id)` over stdio JSON-RPC; session_id reuse
  preserves conversation + shell state) — both "maintained projections of the loop".
- ACP server — automation-only agent sessions over JSON-RPC stdio.
- Custom UI is a *documented* extension point: "drive ctx.agents and render from
  session/event"; interactive apps mount their own approval/question adapters.
- Approval semantics: fail-closed closed set; ApprovalRequest omits tool args — the client
  correlates via callId against the already-streamed tool call, so an approval surface MUST
  consume the event stream.

## Wiring options as they now stand

| | Shape | For | Against |
|---|---|---|---|
| **B — client of the dsh web API** | our face talks HTTP+WS to 127.0.0.1:3080 | zero agent-loop code; the exact wire the bundled UI rides (breaks loudly and visibly with it); covers composer (`session.prompt`), stream (`events.mux`), Gate 2 (`respond`) | pre-1.0 breakage; needs `dsh web` running; browser CORS means our face fronts it through its own tiny server |
| **B′ — in-process embed** | own Node host mounts the same API via `InProcessApiClient` | one process; same typed contract | we own host composition; deepest coupling; TS/Node stack |
| **A — SDK-driven** | Python SDK behind our own server | Python matches the repo; SDK is a tracked surface | event-stream + interactive-approval story unproven for a custom face; more moving parts than B for the same result |

Nothing forces C (own agent loop); it stays rejected.
