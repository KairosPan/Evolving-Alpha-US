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
2. **Create the harness home.** `npx @deepseek-ai/dsh web` once (`$DSH_HOME`, default
   `~/.dsh`; the web UI comes up on http://127.0.0.1:3080). This is what creates the profile
   directory layout the next step writes into.
3. **Copy the profile in.** Copy `dsh/profile/cordis.yml` into the harness home's profile
   location per the current dsh docs — as of the frozen survey that is
   `$DSH_HOME/profiles/<name>/` and its patch file is `cordis.patch.yml` (for the `face`
   profile, that patch file is the ONLY one to edit — `kairos-face` rewrites
   `<profile>/cordis.yml` on every boot; see `face/README.md`). Fill in every
   `<ABSOLUTE PATH TO THIS REPO>` placeholder in the copy; the repo copy keeps the
   placeholders. In the same pass, replace the bare `python` in the server `command:` with the
   ABSOLUTE path of the interpreter step 1 installed into (`python -c "import sys;
   print(sys.executable)"`) — dsh spawns the server as a subprocess whose `PATH` need not be
   your shell's, and a bare `python` can resolve to a system interpreter that has none of the
   deps. Confirm what actually booted with `dsh --profile <name> --dump-config`.
4. **Give it the keys.** `source .env.alpaca` and `source .env.deepseek` in the shell that
   launches dsh (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `DEEPSEEK_API_KEY`), or put the
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
6. **The ORDERS flag lives ONLY in the home copy — and it is the only gate this repo enforces.**
   `place_order`/`cancel_order` register only when `ALPACA_KIT_ENABLE_ORDERS=1` **and** the APCA
   keys are present — the flag alone registers nothing (`alpaca_kit/mcp/tools.py` gates on
   `orders_on and has_keys`). That is the spec's **Gate 1, registration**; the `has_keys` half is
   extra hardening on the same gate, not a second one. The flag stays commented out in the repo
   copy of `cordis.yml` and is uncommented, if ever, only by the operator in the installed copy —
   outside the agent's workspace, where the agent cannot edit it back on.

   **Gate 2 — per-order human approval — is INTENT in this branch, not an established layer.**
   The template's `permissions: always_ask: [place_order, cancel_order]` is written in the same
   indicative shape as the rest of the file and is **not** validated against a live dsh: in the
   frozen survey, approval policy is a per-SESSION `ask`/`never` knob, per-tool allow/deny/ask
   lives in the `tools/pre-execute` waterfall rather than in profile YAML, and MCP tools carry a
   `serverName` namespace, so bare tool names would not match even if a top-level block bound. An
   unrecognised YAML key merges silently, which fails open. So: **pin Gate 2 at install** against
   the current dsh docs, by whichever mechanism it then offers — a permission preset whose
   approval policy is `ask` (the shipped `workspace-write` preset already is), a
   `tools/pre-execute` ask rule, or a per-tool key if one now exists — and then **confirm that an
   order call actually prompts, before you trust the flag**. Until that confirmation, treat Gate 1
   as the only layer standing between the agent and a paper order; do not rely on Gate 2 to hold
   if the flag is ever mis-set. The face's approval surface and its drill live in
   `face/README.md` — once that drill passes on a live face, Gate 2 has a validated home there.
7. **Re-check the key names.** dsh is a developer preview and states that there will be
   compatibility-breaking changes. The shape in `profile/cordis.yml` is indicative, pinned
   against a survey frozen 2026-08-22
   (`docs/research/2026-08-22-deepseek-harness-dsh-survey.md`), not against a live install.
   Expect one adaptation pass; the content is the deliverable, the container is not.

## Notes

- **Skill roots are the group directories.** Discovery expects `<root>/<name>/SKILL.md`, so
  the profile lists `dsh/skills/mechanics` and `dsh/skills/style-kairos` separately rather
  than their shared parent.
- **MCP server noise.** `python -m alpaca_kit.mcp` runs FastMCP, which logs INFO to stderr at
  boot. If dsh surfaces that as noise, quiet it from the profile with
  `FASTMCP_LOG_LEVEL=WARNING` in the server's env block (FastMCP reads its settings from
  `FASTMCP_`-prefixed variables; verified against mcp 1.28.1). Do not edit
  `alpaca_kit/mcp/server.py` for this.
- **Editing.** The repo copy under `dsh/` is the source of truth to edit. Installed copies
  under the harness home are operator territory — `AGENTS.md` puts them on the never-edit list.
