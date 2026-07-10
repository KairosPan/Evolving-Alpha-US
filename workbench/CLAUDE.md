# workbench/ — Kairos's conversational staging face (:8820)

Runs `converse_project` with the **arena** injected via `registry_factory` (this apps-layer
package may import `alpha.arena` — layering details: `alpha/arena/CLAUDE.md`). Worker proposals
become pending `StagedEdit`s; only the user's `/edits/{eid}/approve` lands them — the gate runs
at approve time, stamping provenance `kairos` + `human_approver="user"`.

```bash
pip install -e ".[sonia,live]"   # sonia = fastapi/uvicorn; live = alpaca-py (the decide tool
                                 #   lazily imports it — without [live] every decide ImportErrors)
# live face: the decide tool builds a real PIT-guarded universe → needs Alpaca creds,
# and the chat model needs a valid API id (see the model-id gotcha in sonia/CLAUDE.md):
set -a; source .env.alpaca; set +a
ALPHA_CONVERSE_MODEL=deepseek-chat DEEPSEEK_API_KEY=... python -m workbench   # :8820
python -m pytest tests/workbench -q      # scoped tests (autouse full store isolation)
```

- Stores (env → default): `ALPHA_PROJECTS_DB`→`./state/projects/state.db`,
  `ALPHA_WORKSPACE_DIR`→`./state/workspaces`, `ALPHA_LIVE_BRAIN_DIR`, and `ALPHA_SESSIONS_DIR`
  (the SONIA store — swept by `/rollback`'s cross-face reconcile; both faces share one brain).
- **Boot assert (structural invariant):** `create_app()` fails fast if the brain dir lives
  inside the workspace (re-checked per `/converse`) — `LocalEnv` is not a kernel boundary, so a
  live shell could otherwise reach the brain files. Operator-trust posture (user-accepted): the
  logical write-waist holds for tool calls; physical brain integrity rests on the operator until
  a kernel `SandboxedEnv` exists.
- `/rollback` reverts the **highest `applied_seq`** (the true last apply, not the last-staged
  edit) and reconciles derived state across BOTH faces inside the brain flock.

*Owner: KairosPan · reviewed 2026-07-10.*
