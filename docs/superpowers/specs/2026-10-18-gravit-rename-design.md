# Gravit Rename — Design

**Status:** agreed in conversation on 2026-10-08, in two segments the operator approved one by one;
this written spec awaits the operator's review. Not built.
**Pins:** `main` @ `69225d8`; dsh `0.2.0-rc.2` (the face's pin); branch `chore/gravit-rename` in
`.claude/worktrees/gravit-rename`.
**Language of citations:** `pkg/…` cites the vendored dsh package under `face/node_modules/@deepseek-ai/`;
bare paths are this repository; symbols, not line numbers.

---

## 1. Intent

The operator, 2026-10-08: "把agent的名字从Kairos换成gravit覆盖整个项目" — rename the principal agent
from Kairos to Gravit across the whole project, the dated history included. In the same exchange the
retired product's other name leaves the tracked tree: the 42 documents that carry it are untracked and
ignored, not deleted (§6.1), and the remaining mentions are rewritten (§6.2).

Done means:

- every tracked file names the agent Gravit, except the lines §4 keeps on purpose;
- `python -m pytest`, `npm test`, `npm run typecheck` and `FACE_SMOKE=1 npm test` pass;
- every archived session still opens, as Gravit (§5.1), and the watchlist a browser saved survives (§5.2);
- a case-insensitive search of the tracked tree for the retired product's other name finds nothing (§8).

Gravit already names the public landing page (`face/landing`); after this the agent matches it.

## 2. Spelling

`Gravit` in prose, `gravit` in identifiers and paths, `GRAVIT` where the old name was upper case —
the landing page's own spelling ("Gravit" in its copy, `gravit.` as the wordmark).

## 3. What changes

### 3.1 Paths (`git mv`)

| Old | New |
|---|---|
| `Kairos-Design.md` | `Gravit-Design.md` |
| `bots/kairos/` | `bots/gravit/` |
| `dsh/skills/style-kairos/` | `dsh/skills/style-gravit/` |

### 3.2 Identifiers

| What | Old | New | Where |
|---|---|---|---|
| default preset id | `kairos` | `gravit` | `face/src/overlay.ts` `DEFAULT_PRESET` |
| its Loader row id | `preset-kairos` | `preset-gravit` | `presetRowId` |
| package name, log prefix | `kairos-face` | `gravit-face` | `face/package.json`, `face/package-lock.json`, every `BIN` |
| bot plugin name | `kairos-bot` | `gravit-bot` | `face/plugins/bot.js` `name` and its error prefixes |
| skill pack | `style-kairos` | `style-gravit` | `face/src/panels.ts` (pack rank), `dsh/profile/cordis.yml` (template), `scripts/convert_seeds.py` |
| persona | "You are Kairos" | "You are Gravit" | `dsh/profile/persona.md` |
| host display name | `Kairos` | `Gravit` | `face/client/speaker.js` `HOST_NAME`, `face/src/panels.ts` (main agent), `bots/gravit/preset.yml` |
| page titles and brand | `KAIROS` | `GRAVIT` | `face/client/{index,market,account}.html` |
| view role, room speaker kind | `kairos` | `gravit` | `face/client/{mapper,chat,member-traces}.js`, `face/src/room-rules.ts` — in memory only, never persisted |
| watchlist key | `kairos.market.watchlist.v1` | `gravit.market.watchlist.v1` | `face/client/market-model.js` (§5.2) |
| HTTP user agent | `Kairos-Symbol-Search` | `Gravit-Symbol-Search` | `face/src/symbol-search.ts` |
| drill symbol | `kairos-face.order-gate-midboot-drill` | `gravit-face.order-gate-midboot-drill` | face tests and fixtures |
| test and fixture names | `kairos…` | `gravit…` | `face/tests/**` |

`face/scripts/capture-demo-assets.mjs` maps `KAIROS`/`Kairos` to `GRAVIT`/`Gravit` for the landing
page's screenshots; the mapping becomes a no-op and is removed.

### 3.3 Text

Every other mention in a tracked file reads Gravit: code comments and prompt text, the live docs
(`CLAUDE.md`, the charter, `DEVELOPMENT.md`, `AGENTS.md`, the face, dsh and bots READMEs) and the dated
history under `docs/` (specs, plans, runbooks, research, design prototypes). Measured at `69225d8`,
after §6.1 removes its 42 files: 171 files, 1,364 lines, §4's lines included.

## 4. What stays

### 4.1 Not the agent's name

| Kept | Why | Lines |
|---|---|---|
| `KairosPan` | the operator's GitHub account (owner fields, `KairosPan/Evolving-Alpha-US`) | 7 |
| `kairoszhe@gmail.com` | the operator's address on the landing page | 4 |
| `kairospans-projects` | the Vercel team slug (`face/README.md`) | 3 |
| `kairos-intro` | a page on Linqi's `feat/payment` branch, named in the 2026-10-05 handoff | 1 |
| `"agentPreset": "kairos"` in `strategies/aqr-r1000/launch-verification.json` | recorded values; the archived sessions carry exactly this id | 3 |

### 4.2 Kept by necessity

- The legacy preset alias and the legacy watchlist key (§5.1, §5.2) name the old id; every such site
  carries a comment saying why.
- This spec is the rename's record and names the old name.

### 4.3 Dead citations: dropped in code, relabelled in the history

`kairos-mining` labels a findings document that exists neither in this repository nor in the sibling one.
Three Python comments cite it (`alpaca_kit/integrity.py`, `alpaca_kit/feeds/offerings.py`,
`tests/test_integrity.py`); there the citation is removed, not renamed into a document that never existed.
Nine citations in five dated specs of 2026-07-13 (p1, p2, p3, p5b short-interest/offerings, p6) carry
section numbers that are part of their record; there the label becomes `design-mining` (for example
`design-mining §2.5`), which names neither an agent nor a file. A dry run of the history pass found these
nine on 2026-10-18.

### 4.4 Never touched

- `demo/` — Linqi's repository at its pinned commit; its own docs keep their wording. The `CLAUDE.md` row
  that describes it is renamed like any other line.
- The `~/.dsh` session logs — read, never rewritten; §5.1 opens them as they are.
- Other branches: `feat/agent-redesign`, `feat/gravit-ui`, `feat/modal-vercel-hosting`, the parked ones.
- Untracked files in the primary checkout, which belong to other arcs (for example
  `docs/design/2026-10-13-backend-architecture.md`, `docs/research/2026-10-06-agent-phone-and-email.*`,
  `docs/superpowers/plans/2026-10-09-gravit-ui-frontend.md`).
- `.claude/settings.local.json` — the operator's local permissions.

## 5. Runtime compatibility

### 5.1 The legacy preset `kairos`

Nine archived sessions persist `agentPreset: "kairos"` — eight of this project's and one of
`~/Desktop/trend-dragon`; one of them, `session-556f232a`, is in the v4 format dsh 0.2.0 reads. dsh
resolves a session's stored preset through `AgentPresetRegistry.retain`
(`pkg/dsh-agent-preset-registry/lib/index.js`), which throws `agent-preset/not-found` for an id no row
declares. Without an alias, every one of them would refuse to open. So:

- `faceOverlay` declares a second static row, `preset-kairos`, beside `preset-gravit`: id `kairos`, the
  same `[]` composition read from `bots/gravit/` by `definitionFor`, the name "Gravit", and a description
  saying it is the agent's id before 2026-10-08. A constant `LEGACY_PRESET = "kairos"` sits beside
  `DEFAULT_PRESET` in `face/src/overlay.ts`.
- The registry's default is `gravit`, so every new session writes `gravit`. `bootFace` asserts that both
  rows are listed and neither is broken; a broken alias refuses the boot rather than every old session.
- The alias has no `bots/` directory, so `/data/bots.json` never lists it. `RESERVED_IDS` holds `gravit`
  and `kairos`, and `face/client/botId.js`'s description of the server gate follows.
- Every test of a session's preset against the host accepts both ids through one predicate per side,
  `isHostPreset` — exported by `face/src/overlay.ts` for the server and by `face/client/speaker.js` for the
  page:
  - server: `room.ts`, the `dispatch` preset lock — a session whose records name only host presets may
    dispatch, no wider than today, since the alias is the host composition itself. It is the server's one
    such test; `bots.ts` and `bot-presets.ts` compare directory names, and the default's directory is
    `gravit`;
  - page: `room.js` `isHost`, `speaker.js` `speakerFor`, and in `chat.js` the subagent hint, the room roster
    filter and the bot lookup the sidebar groups by; `channels.js`'s roster filter.
- Retiring the alias is a later decision, taken once no session the operator keeps names it.

### 5.2 The watchlist key

`face/client/market-model.js` gets `STORAGE_KEY = "gravit.market.watchlist.v1"` and
`LEGACY_STORAGE_KEY = "kairos.market.watchlist.v1"`. `readWatchlist` reads the new key and, only when it is
absent, the legacy key; every save writes the new key. The legacy entry is never written or deleted, so a
rollback to the old code still finds it. `market.js`'s cross-tab `storage` listener follows the new key.
`face/scripts/capture-demo-assets.mjs` seeds the new key.

### 5.3 The operator's profile patch

`~/.dsh/profiles/face/cordis.patch.yml` names the style skill root by absolute path
(`…/dsh/skills/style-kairos`). Right after the merge — the primary checkout's directory is renamed only
then — the file is copied to `cordis.patch.yml.bak-<merge date>` and four lines change: that path, and the
old names in three comments. Nothing else under `~/.dsh` changes. A face that is running during the merge
is restarted by the operator, and every open tab is hard-reloaded (`face/client/*` is served with no cache
headers).

## 6. The retired product's documents

### 6.1 Untracked and ignored, not deleted

The selection: every file under `docs/superpowers/` dated 2026-06 or 2026-07, plus
`runbooks/p-b-p-c-activation.md`, that mentions the retired product's second agent by name — 42 files
(25 specs, 16 plans, 1 runbook; 15,663 lines). They describe the product the 2026-08-29 reset retired; no
live file and no later document cites them.

- `git rm --cached` takes them out of the tree. The files stay on disk unchanged; the rename pass does not
  run over them.
- `.gitignore` lists each one under a comment that names no product. Four of the file names carry the
  retired name; their lines put `*` in its place (for example
  `docs/superpowers/specs/2026-07-13-a7-*-proposer-design.md`), and each line matches exactly one file.
- The other 63 documents dated 2026-06/07 stay tracked and are renamed like the rest.
- A merge deletes the tracked files it untracks, so right after it the primary checkout's copies are
  restored with `git restore --source=<main before the merge> --worktree -- <the 42 paths>`; ignored, they
  stay out of `git status`.

### 6.2 Rewritten

37 lines in 9 tracked files still name the retired product or its second agent: `CLAUDE.md`,
`docs/design/prototypes/BRIEF.md`, five files under `docs/research/`, and the 2026-08-29 reset plan and
spec. Each is rewritten without the name:

- the product becomes "the previous product";
- its second agent becomes "the retired meta-agent";
- links into the sibling repository and to the retired charter file are removed, and the sentence is
  reworded to stand without them;
- the reset plan's recorded commands drop the retired package's directory from their argument lists, and a
  note beside them says the retired meta-agent's package went with the same step.

## 7. Process

- Branch `chore/gravit-rename` from `main` @ `69225d8` in `.claude/worktrees/gravit-rename`. The primary
  checkout, shared by the operator's other sessions, is not touched before the merge.
- After this spec, four commits: (1) code, tests, the alias and the key — green on its own; (2) the live
  docs, with the alias and its reason in `DEVELOPMENT.md` and `face/README.md`; (3) the dated history;
  (4) §6 — the 42 untracked and ignored, the 37 lines rewritten.
- The text pass is a one-off script with §4's keep-list built in and case-preserving replacement
  (`Kairos`→`Gravit`, `kairos`→`gravit`, `KAIROS`→`GRAVIT`); its diff is read per category. The §5 sites
  are written by hand, test first.
- Merge on the operator's word only: a fast-forward of `main` in the primary checkout, then §6.1's restore,
  then §5.3, then the operator restarts any running face. No push.

## 8. Verification

- `python -m pytest` at the root; `npm test`, `npm run typecheck` and `FACE_SMOKE=1 npm test` in `face/`
  (real boots on local stubs, no model calls).
- New tests:
  - unit — the composed tree carries `preset-gravit` and `preset-kairos` with the same plugins;
    `isHostPreset` on each side accepts exactly the two ids and refuses near misses (`gravit-2`, `kairos-2`);
    `RESERVED_IDS` refuses both; the watchlist reads the legacy key only when the new one is absent;
  - smoke — a session created with preset `kairos` joins the host composition, keeps the host's whole
    roster, and may `dispatch`.
- Audits at the branch head: `git grep -i -n kairos -- . ':!demo'` lists only §4's lines;
  `git grep -i -n 'son[i]a' -- . ':!demo'` lists nothing.

## 9. Sequencing and scope

- The agent redesign (`feat/agent-redesign`, spec `2026-10-15-gravit-agent-redesign-design.md`) is written
  against the post-rename ids and starts only after this lands; that branch then merges `main`. Its own
  files carry their own wording, and the doc debts it defers until after the rename are its own pass.
- Out of scope: renaming the GitHub repository or any account; `demo/`'s wording, which would be a change to
  Linqi's repository; retiring the legacy alias.
