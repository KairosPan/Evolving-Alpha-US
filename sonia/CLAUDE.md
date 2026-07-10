# sonia/ — the Sonia meta-agent service (:8810)

Owns the **live brain** and every gated landing (the Sonia half of root §1). Landing/revert
surfaces and their exact routes:
`POST /sessions/{sid}/messages/{mid}/propose` (crystallization: `extract_ops`, enforced-JSON,
ops-or-`{no_edit,reason}` — never silent) → user accept → `…/{mid}/apply` · `POST /edit` (the
USER's direct hand, `user_direct` provenance) · `/proposals` + `/proposals/{pid}/resolve`
(fork-evolution packets: adopt validates base hash AND result — prefix/records/red-line checks)
· `/conflicts` · `/snapshots` + `/snapshots/{name}/restore` (the generic revert lever; runs the
full derived-state sweep) · `…/{mid}/rollback`.

```bash
pip install -e ".[sonia]"
DEEPSEEK_API_KEY=... python -m sonia               # :8810
ALPHA_SONIA_PROVIDER=mock python -m sonia          # offline (ALPHA_MOCK_RESPONSE scripts replies)
python -m pytest tests/sonia -q                    # scoped tests (autouse mock + store isolation)
```

- **Model-id gotcha:** the default `deepseek-v4-pro` is the intended model *name*; if the live
  API rejects it as an unknown id, override with `ALPHA_SONIA_MODEL=deepseek-chat` (any
  OpenAI-compatible id).
- Stores (env → default): `ALPHA_LIVE_BRAIN_DIR`→`./state/brain`, `ALPHA_SESSIONS_DIR`,
  `ALPHA_CONFLICTS_DIR`, `ALPHA_PROPOSALS_DIR`, and `ALPHA_PROJECTS_DB` (the WORKBENCH store —
  read for the cross-face reconcile sweep; both faces share one brain).

## Concurrency discipline (load-bearing)

- Every brain mutation: `_MUTATION_LOCK` (route) + `bstore.lock()` (cross-process flock).
  **The flock opens a fresh fd per call — same-process nesting self-blocks and fails with
  `RuntimeError` after the 10s bounded retry.** `adopt_proposal` takes the brain lock itself;
  never wrap it in another `bstore.lock()`.
- Derived records (`applied_seqs`, session puts) persist **inside** the flock; the post-restore
  reconcile sweep also runs inside it — derived state must never lag the brain across processes.
- A locked/corrupt workbench DB during a sweep is surfaced in the response
  (`workbench_sweep: "failed: …"`), never a silent ok.

*Owner: KairosPan · reviewed 2026-07-10.*
