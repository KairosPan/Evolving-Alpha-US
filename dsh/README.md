# dsh/ — the repo-side profile template and skill packs

STRATEGY runs on DeepSeek Harness (dsh). This directory is the repo's half of that setup:

| Path | What |
|---|---|
| `profile/cordis.yml` | profile TEMPLATE — mounts the alpaca-kit MCP server, the skill roots, the approval list |
| `skills/mechanics/` | neutral mechanics, always apply: `backtest-rules`, `alpaca-kit-guide` |
| `skills/style-kairos/` | the operator's own style: `doctrine`, `signals`, `lessons` — converted from the retired `seeds_v2/` JSON packs by `scripts/convert_seeds.py` |

Mechanics vs style is the load-bearing split. Mechanics are how the data and the honest-eval
bed work — findings never overrule them. Style is the operator's preference: follow it by
default, but when research contradicts an entry, REPORT the conflict instead of silently
deferring. Every style-kairos SKILL.md carries that scope header at the top.

## Install

1. **Create the harness home.** `npx @deepseek-ai/dsh web` once (`$DSH_HOME`, default
   `~/.dsh`; the web UI comes up on http://127.0.0.1:3080). This is what creates the profile
   directory layout the next step writes into.
2. **Copy the profile in.** Copy `dsh/profile/cordis.yml` into the harness home's profile
   location per the current dsh docs — as of the frozen survey that is
   `$DSH_HOME/profiles/<name>/` and its patch file is `cordis.patch.yml`. Fill in every
   `<ABSOLUTE PATH TO THIS REPO>` placeholder in the copy; the repo copy keeps the
   placeholders. Confirm what actually booted with `dsh --profile <name> --dump-config`.
3. **Give it the keys.** `source .env.alpaca` and `source .env.deepseek` in the shell that
   launches dsh (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `DEEPSEEK_API_KEY`), or put the
   variables in the home profile's env block. Neither file is loaded automatically, and
   neither is in git. Without `ALPHA_PIT_ROOT` the snapshot-backed tools
   (`market_snapshot`, `screen`, `breadth`) do not register at all.
4. **The ORDERS flag lives ONLY in the home copy.** `ALPACA_KIT_ENABLE_ORDERS=1` is what
   registers `place_order`/`cancel_order`. It stays commented out in the repo copy of
   `cordis.yml` and is uncommented, if ever, only by the operator in the installed copy —
   outside the agent's workspace, where the agent cannot edit it back on.
5. **Re-check the key names.** dsh is a developer preview and states that there will be
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
