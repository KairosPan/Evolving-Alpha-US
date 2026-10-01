# dsh/ — the repo-side profile template and skill packs

STRATEGY runs on DeepSeek Harness (dsh). This directory is the repo's half of that setup:

| Path | What |
|---|---|
| `profile/cordis.yml` | profile TEMPLATE — mounts the alpaca-kit MCP server, the skill roots, and the INTENDED approval list (see step 6) |
| `skills/mechanics/` | neutral mechanics, always apply: `backtest-rules`, `alpaca-kit-guide` |
| `skills/style-kairos/` | the operator's own style: `doctrine`, `signals`, `lessons` — converted from the retired `seeds_v2/` JSON packs by `scripts/convert_seeds.py` |

Mechanics vs style is the load-bearing split. Mechanics are how the data and the honest-eval
bed work — findings never overrule them. Style is the operator's preference: follow it by
default, but when research contradicts an entry, REPORT the conflict instead of silently
deferring. Every style-kairos SKILL.md carries that scope header at the top.

## Install

1. **Install the Python side first.** `pip install -e ".[live]"` in this repo. The profile
   mounts the MCP server as `python -m alpaca_kit.mcp`, which imports `alpaca_kit` and its
   deps (`mcp`, `pandas`, `pyarrow`, `pydantic`); `[live]` adds `alpaca-py`, without which the
   live `daily_bars` path cannot fetch. Nothing below works until this import does:
   `python -c "import alpaca_kit.mcp.server"`.
2. **Create the harness home and the face profile.** `cd face && npm install && npm run setup`
   creates `$DSH_HOME/profiles/face/` (`$DSH_HOME` defaults to `~/.dsh`): a `package.json`
   bundling `dsh-base`, the operator's `cordis.patch.yml` and `pnpm-workspace.yaml`; it never
   overwrites an existing profile (see `face/README.md`). The dsh command line is not part of
   this install, and another dsh sharing the home changes it: the 0.2.0-rc.2 CLI's first
   run imports `$DSH_HOME/settings.yaml` into ITS OWN active profile and renames the file
   `settings.yaml.imported`, and a 0.1.1-rc.2 CLI or face must never run again on a home that
   0.2.0 has written — it re-heals its module link farm under `profiles/node_modules` and forks
   the session history (`DEVELOPMENT.md` §4.8, PLAN D12 and D13). A home a 0.1.1 face already
   uses moves to 0.2.0 by the go-live runbook
   (`docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`): backup, a dry run on a
   copy (`face/scripts/check-home.ts`), the decisions, then the first boot.
3. **Copy the profile in.** Copy `dsh/profile/cordis.yml` into the harness home's profile
   location per the current dsh docs — as of the frozen survey that is
   `$DSH_HOME/profiles/<name>/` and its patch file is `cordis.patch.yml` (for the `face`
   profile, put this file's rows INTO `$DSH_HOME/profiles/face/cordis.patch.yml` — that
   patch file is the only one to edit there, because `kairos-face` rewrites
   `<profile>/cordis.yml` on every boot; see `face/README.md`). Fill in every
   `<ABSOLUTE PATH TO THIS REPO>` placeholder in the copy; the repo copy keeps the
   placeholders. In the same pass, replace the bare `python` in the server `command:` with the
   ABSOLUTE path of the interpreter step 1 installed into (`python -c "import sys;
   print(sys.executable)"`) — dsh spawns the server as a subprocess whose `PATH` need not be
   your shell's, and a bare `python` can resolve to a system interpreter that has none of the
   deps. Add Kairos's default model to the same file — the face reads no `settings.yaml`, so
   without this row it runs dsh-base's `deepseek-official/deepseek-flash`, and nothing in the
   running face saves a model choice back:
   ```yaml
   - id: agent-default-model
     config: { provider: deepseek-official, model: deepseek-v4-pro, reasoningEffort: max }
   ```
   Confirm what actually booted in the face's plugin panel (`/data/plugins.json`: every loader
   row with its phase, and the tools each MCP server registered). `dsh --profile face
   --dump-config` shows the profile's own layers only — never the face's policy, AKShare and host
   rows — and only a 0.2.0 CLI may run it on this home (step 2).
4. **Give it the keys.** `source .env.alpaca` and `source .env.deepseek` in the shell that
   launches the face (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `DEEPSEEK_API_KEY`), or put the
   variables in the home profile's env block. Neither file is loaded automatically, and
   neither is in git. `ALPHA_PIT_ROOT` is already in the template's env block (`data/pit/2yr`,
   relative to the server's `cwd`) — keep it: without it the snapshot-backed tools
   (`market_snapshot`, `screen`, `breadth`) do not register at all. `data/` is gitignored, so a
   fresh clone has NO bed — restore `data/pit/2yr` from the operator backup
   (`alpha-us-backup-20260829`) or capture a new one with `scripts/capture_window.py`; the bed
   windows and their out-of-window failure modes are in `AGENTS.md`.
5. **Check what registered, before blaming dsh.** The toolset is a pure function of the
   environment, so it is checkable without the harness — but check it under the environment the
   PROFILE gives the server, not whatever your shell happens to carry. dsh spawns the server with
   the `cwd` and the `env:` block from `cordis.yml`, so reproduce both, with the same absolute
   interpreter path you filled in at step 3:
   ```bash
   cd <ABSOLUTE PATH TO THIS REPO>
   ALPHA_PIT_ROOT=data/pit/2yr /ABSOLUTE/PATH/TO/python \
     -c "from alpaca_kit.mcp.tools import build_tools; print(sorted(build_tools()))"
   ```
   Read the result by which names are MISSING, since two different half-configured states both
   print seven:
   - **ten** — `account`, `breadth`, `calendar`, `corp_actions`, `daily_bars`, `earnings`,
     `market_snapshot`, `orders`, `positions`, `screen`. Everything arrived; no order tools is
     the correct, fully-configured result.
   - **seven, no `market_snapshot`/`screen`/`breadth`** — `ALPHA_PIT_ROOT` did not reach the
     process at all; the keys did.
   - **seven, no `account`/`orders`/`positions`** — the bed arrived, the APCA keys did not.
   - **only `earnings`** — neither reached the process.

   Registration only asks whether `ALPHA_PIT_ROOT` is SET, never whether a bed is actually there,
   so a wrong path still lists all ten. That failure shows up per call instead:
   `screen` returns `ok=False, SnapshotMissingError`. Ten tools means the wiring is right; it does
   not by itself mean the bed is.
6. **The ORDERS flag lives ONLY in the home copy.** `place_order`/`cancel_order` register only
   when `ALPACA_KIT_ENABLE_ORDERS=1` **and** the APCA keys are present — the flag alone registers
   nothing (`alpaca_kit/mcp/tools.py` gates on `orders_on and has_keys`). That is the spec's
   **Gate 1, registration**; the `has_keys` half is extra hardening on the same gate, not a second
   one. The flag stays commented out in the repo copy of `cordis.yml` and is uncommented, if ever,
   only by the operator in the installed copy — outside the agent's workspace, where the agent
   cannot edit it back on.

   **Gate 2 — per-order human approval — is the face's, not the profile's.** `face/src/orders.ts`
   (built 2026-09-04) registers a `tools/pre-execute` listener that raises an approval card for
   every `place_order`/`cancel_order` call, matched on the raw tool name so a renamed MCP server
   cannot slip one past, and a guard that admits the call only on a logged one-shot approval for
   that exact call. It binds only while dsh runs inside the face; a dsh tree composed without the
   face has Gate 1 alone. The template's `permissions: always_ask: [place_order, cancel_order]`
   block is inert — an unrecognised YAML key merges silently, which fails open — and stays in the
   template as the record of what did not work. The gate's automated drill passes on a real tree,
   the approved order dispatching included; its human half has not been run. Run the
   order-approval drill in `face/README.md` in a SCRATCH home, and see a person read the card,
   before the flag ever flips in the real one.
7. **Re-check the key names.** dsh is a developer preview and states that there will be
   compatibility-breaking changes. The shape in `profile/cordis.yml` is indicative, pinned
   against a survey frozen 2026-08-22
   (`docs/research/2026-08-22-deepseek-harness-dsh-survey.md`), not against a live install.
   Expect one adaptation pass; the content is the deliverable, the container is not.

## Installed state — the `face` profile (2026-08-31; re-checked for dsh 0.2.0-rc.2 on 2026-09-30)

The template above is realized, live and drilled, in the face's profile. The shapes that
actually bound, for the next install or the next pin bump:

- **The MCP bridge is `@deepseek-ai/dsh-mcp-client`, and it is NOT in dsh-base.** It is
  declared in `face/package.json` at the exact `DSH_PIN` (the lockstep sweep in
  `face/tests/version.test.ts` covers it automatically), not installed into the profile —
  patch rows resolve plugin names from the face's dependency closure through the runtime
  module resolution the face computes from `face/package.json` at every boot. There is no
  module fallback to heal any more: 0.1.1's link farm under `$DSH_HOME/profiles/node_modules`
  is written by nothing, and a stale one is consulted only for a row naming a package outside
  the face's closure — delete it once no 0.1.1 tool runs on the home (`DEVELOPMENT.md` §4.8,
  PLAN D13).
- **The two operator rows live in `$DSH_HOME/profiles/face/cordis.patch.yml`:** one
  `dsh-mcp-client` insert (`serverName: alpaca-kit`, stdio, absolute interpreter path,
  `cwd` = this repo, env block as in the template) and one `skill-filesystem` config patch
  (`customSkillDirs` = the two group roots — a patch REPLACES the addressed row's whole
  config, which is fine here because dsh-base mounts the row configless). Both are unchanged
  and valid at 0.2.0-rc.2: the stdio config and the `customSkillDirs` / `includeDefaultRoots`
  keys are the same. Since 0.2.0 stdio negotiation starts a probe process before the serving
  one, so the server is spawned twice per connect.
- **The default-model row lives there too** (`agent-default-model`, step 3). 0.1.1 took the
  model from `$DSH_HOME/settings.yaml`; the face at 0.2.0 reads no settings file (it provides
  no `profileContext`), so the row is the only place Kairos's model is set.
- **`toolCallTimeoutMs: 300000` on the MCP row is load-bearing.** `screen(trend_template)`
  computes ~188 s for one day on the 2yr bed (measured 2026-08-31); the 60 s default kills
  it every time, as `MCP error -32001: Request timed out`. Since then screen/breadth results
  disk-cache per (bed, code version, day, kind) under `data/.screen_cache`
  (`alpaca_kit/mcp/cache.py`), so only the FIRST call for a (day, kind) pays the walk — the
  timeout raise still matters for exactly those cold calls.
- **The MCP child's env is scrubbed.** The APCA keys must be passed explicitly on the row
  (`!!js process.env...`); they do not flow in ambiently.
- **Accepted residual:** the face process holds the paper keys in its environment (for
  `/account` and the watchlist's quotes). A session's bash tool does NOT inherit them — dsh
  drops every `KEY|PASSWORD|SECRET|TOKEN` name from a child's environment — but a shell turn
  can read `.env.alpaca` at the repo root and import `alpaca_kit.account` directly, so Gate 1
  gates the ORDER TOOLS, not the capability. Accepted operator-trust posture (paper account,
  single operator, git as ledger), not an oversight.
- **The approval-channel drill (`face/README.md`'s "Gate-2 drill"): PASSED on the live face,
  2026-08-31, on dsh 0.1.1-rc.2.** A file write outside the workspace escalated to a card; both
  outcomes exercised — deny (command did not run, model saw a rejection result) and approve
  (`allowed-once`, one-shot) — with paired `approval/asked`/`approval/decided` records in the
  session log. At 0.2.0-rc.2 the channel is automated on a real tree (`face/tests/smoke.test.ts`,
  `order-gate-smoke.test.ts`); the live re-run is owed.

## Notes

- **Skill roots are the group directories.** Discovery expects `<root>/<name>/SKILL.md`, so
  the profile lists `dsh/skills/mechanics` and `dsh/skills/style-kairos` separately rather
  than their shared parent.
- **SKILL.md frontmatter is mandatory.** dsh's skill discovery drops any SKILL.md whose
  YAML frontmatter is missing `name` and `description` — SILENTLY, at warn level in a log
  nobody reads. Every skill in this repo carries the block, and `scripts/convert_seeds.py`
  emits it; a skill that goes missing from a session starts its diagnosis here.
- **MCP server noise.** `python -m alpaca_kit.mcp` runs FastMCP, which logs INFO to stderr at
  boot. If dsh surfaces that as noise, quiet it from the profile with
  `FASTMCP_LOG_LEVEL=WARNING` in the server's env block (FastMCP reads its settings from
  `FASTMCP_`-prefixed variables; verified against mcp 1.28.1). Do not edit
  `alpaca_kit/mcp/server.py` for this.
- **Editing.** The repo copy under `dsh/` is the source of truth to edit. Installed copies
  under the harness home are operator territory — `AGENTS.md` puts them on the never-edit list.
