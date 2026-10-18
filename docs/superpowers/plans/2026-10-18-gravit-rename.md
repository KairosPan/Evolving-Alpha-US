# Gravit Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the principal agent Kairos → Gravit across the tracked tree, keep every archived session and every saved watchlist working, and take the retired product's 42 documents out of the tree without deleting them.

**Architecture:** A one-off, case-preserving rename tool with the spec's keep-list built in runs three passes — code and runtime content, live docs, dated history — each read as its own diff. The compatibility seams are written by hand, test first: a hidden alias preset `kairos` declared beside `gravit`, one `isHostPreset` predicate per side, and a read-only fallback to the old watchlist key. Two departures from spec §7's commit list, both about order only: the retired documents leave the tree first (Task 1), so every later pass runs over `git ls-files` with no exclusion list, and spec §7's commit (1) lands as three commits (Tasks 3–5), each green.

**Tech Stack:** Node 22, tsx, `node:test`, `tsc --noEmit` (face); Python 3 + pytest (repo root); git 2.52; dsh `0.2.0-rc.2` vendored under `face/node_modules/@deepseek-ai/`.

**Spec:** `docs/superpowers/specs/2026-10-18-gravit-rename-design.md`

## Global Constraints

- Work only in the worktree `.claude/worktrees/gravit-rename` on `chore/gravit-rename`. Never `git switch`, `checkout`, `reset` or `stash` in the primary checkout; it is touched only in Task 9, on the operator's word.
- Spelling: `Gravit` in prose, `gravit` in identifiers and paths, `GRAVIT` where the old name was upper case.
- Kept verbatim (spec §4.1): `KairosPan`, `kairoszhe@gmail.com`, `kairospans-projects`, `kairos-intro`, and the whole of `strategies/aqr-r1000/launch-verification.json`.
- The old id appears only in §4.1's lines, in the compat sites Tasks 4–6 name, in the spec and in this plan. Outside `face/src/overlay.ts`, `face/src/setup.ts`, `face/client/speaker.js`, `face/client/market-model.js`, the tests and the two docs of Task 6, code and comments name it through `LEGACY_PRESET` or as "the pre-rename id".
- No tracked file and no commit message contains the retired product's other name. The check is `git grep -i -n 'son[i]a' -- . ':!demo'`; this plan calls it "the retired name" and never writes it.
- Never touched: `demo/`, the `~/.dsh` session logs, other branches, untracked files in the primary checkout, `.claude/settings.local.json`.
- Two scratch paths outside the repository carry across tasks: `RETIRED_LIST` (Task 1) and `RENAME_TOOL` (Task 2). Neither is ever committed.
- Commit messages go through a file, `git commit -F <file>`: backticks, `$()` and parentheses inside `-m` run as shell.
- Long runs get `caffeinate -i` in front: on battery the Mac idle-sleeps and stalls real-timer tests.
- No push.

## Review Focus

1. **A session on record under both host ids** — header `kairos` with a running preset `gravit` after a re-select, or the reverse — is the host and may dispatch. Pinned in Task 4 (the `mixed` room of the room-engine test).
2. **A browser holding both watchlist keys** — the new key wins whenever it exists, even holding an empty list the operator saved on purpose. Pinned in Task 5.
3. **A malformed pre-rename watchlist entry** — reported with the existing corrupt-data error, left byte-identical, never written. Pinned in Task 5.
4. **A stray `bots/kairos/` directory** — after the merge an untracked file (`.DS_Store`, a journal) can keep the directory alive in the primary checkout; it must not surface as a broken bot in `/data/bots.json`, nor be declared. Pinned in Task 4 (the `listBots` test).
5. **Near-miss ids** — `kairos-2`, `kaiross`, `gravit-2`, `gravits`, `Gravit`, `" gravit"` are never the host, on either side. Pinned in Tasks 4 and 5.

---

## File map

| File | Responsibility in this change | Task |
|---|---|---|
| `.gitignore` | lists the 42 retired documents | 1 |
| the 9 files that still carry the retired name | 37 lines reworded without it | 1 |
| `RENAME_TOOL` (outside the repository) | the case-preserving pass with the keep-list | 2 |
| `Gravit-Design.md`, `bots/gravit/`, `dsh/skills/style-gravit/` | the three `git mv`s | 3 |
| every tracked file outside `docs/` and the live docs | the code pass | 3 |
| `face/src/overlay.ts` | `LEGACY_PRESET`, `LEGACY_PRESET_DESCRIPTION`, `isHostPreset`, the alias row | 4 |
| `face/src/boot.ts` | refuses a boot whose alias is absent or broken | 4 |
| `face/src/bots.ts` | reserved ids, the default directory's checks, `listBots` skips the legacy directory | 4 |
| `face/src/room.ts` | the `dispatch` lock through `isHostPreset` | 4 |
| `face/src/setup.ts` | the template comment lists the alias row | 4 |
| `face/client/speaker.js` | `HOST_PRESETS`, `isHostPreset` | 5 |
| `face/client/room.js`, `chat.js`, `channels.js` | host tests through `isHostPreset` | 5 |
| `face/client/market-model.js` | `LEGACY_STORAGE_KEY` and the read fallback | 5 |
| the live docs | the docs pass; the alias and the key documented | 6 |
| `docs/**` | the history pass | 7 |

---

### Task 1: The retired product's documents leave the tree (spec §6)

**Files:**
- Modify: `.gitignore` (append one block)
- Untrack, keep on disk: the 42 files Step 1 selects
- Modify: `CLAUDE.md`, `docs/design/prototypes/BRIEF.md`, `docs/research/2026-07-11-us-growth-unknown-unknowns.html`, `docs/research/2026-07-16-codex-connection-architecture.md`, `docs/research/2026-08-22-deepseek-harness-dsh-survey.md`, `docs/research/2026-08-22-harness-design-report.md`, `docs/research/2026-08-23-fused-harness-architecture.md`, `docs/superpowers/plans/2026-08-29-msa-skeleton-reset.md`, `docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md`

**Interfaces:**
- Produces: `RETIRED_LIST`, a file of the 42 repository-relative paths; a tree in which `git grep -i 'son[i]a'` finds nothing and `git ls-files` no longer lists the 42, which stay on disk, untracked and ignored.

- [ ] **Step 1: Select the 42**

```bash
RETIRED_LIST=<a path outside the repository>/retired42.txt
git ls-files docs/superpowers | grep -E '/2026-0[67]-|/p-b-p-c-activation\.md$' \
  | xargs grep -l -i 'son[i]a' > "$RETIRED_LIST"
wc -l < "$RETIRED_LIST"
```
Expected: `42` (25 specs, 16 plans, 1 runbook).

- [ ] **Step 2: Untrack them**

```bash
git rm --cached --quiet --pathspec-from-file="$RETIRED_LIST"
git status --short | grep -c '^D '
xargs ls < "$RETIRED_LIST" | wc -l
```
Expected: `42` staged deletions, and all 42 files still listed on disk.

- [ ] **Step 3: Append this block to `.gitignore`, verbatim**

```gitignore

# The previous product's design history (2026-06/07): kept on local disk and out of
# the repository since the Gravit rename (docs/superpowers/specs/
# 2026-10-18-gravit-rename-design.md §6.1). Four names below carry `*` where the
# retired name stood; each line matches exactly one file.
/docs/superpowers/plans/2026-06-23-*-standalone-meta-agent-service.md
/docs/superpowers/plans/2026-06-24-brain-drawer.md
/docs/superpowers/plans/2026-06-26-conflicts-adjudication-ui.md
/docs/superpowers/plans/2026-06-26-converse-face-live-entry.md
/docs/superpowers/plans/2026-06-26-phase1a-conversational-loop.md
/docs/superpowers/plans/2026-06-26-refine-live-conflict-feed.md
/docs/superpowers/plans/2026-06-26-self-evolution-provenance-conflict.md
/docs/superpowers/plans/2026-06-26-three-subphases-roadmap.md
/docs/superpowers/plans/2026-06-27-forge-auto-promote-demote.md
/docs/superpowers/plans/2026-06-28-pb-pc-experience-fitness.md
/docs/superpowers/plans/2026-06-30-agent-modification-drawer.md
/docs/superpowers/plans/2026-07-09-teach-crystallize.md
/docs/superpowers/plans/2026-07-10-a1-hygiene-floor.md
/docs/superpowers/plans/2026-07-10-landing-doc-adoption.md
/docs/superpowers/plans/2026-07-14-llm-stack-switch.md
/docs/superpowers/plans/2026-07-16-body-six-components.md
/docs/superpowers/runbooks/p-b-p-c-activation.md
/docs/superpowers/specs/2026-06-23-*-standalone-meta-agent-service-design.md
/docs/superpowers/specs/2026-06-24-brain-drawer-design.md
/docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md
/docs/superpowers/specs/2026-06-26-converse-face-live-entry-design.md
/docs/superpowers/specs/2026-06-26-refine-live-conflict-feed-design.md
/docs/superpowers/specs/2026-06-27-activity-space-arena-design.md
/docs/superpowers/specs/2026-06-27-forge-auto-promote-demote-design.md
/docs/superpowers/specs/2026-06-27-modification-ladder-and-body-axis-design.md
/docs/superpowers/specs/2026-06-27-phase1-hermes-vendoring-completion-design.md
/docs/superpowers/specs/2026-06-28-pb-pc-experience-fitness-design.md
/docs/superpowers/specs/2026-06-30-agent-modification-drawer-design.md
/docs/superpowers/specs/2026-07-01-teach-crystallize-design.md
/docs/superpowers/specs/2026-07-06-*-general-core-design.md
/docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md
/docs/superpowers/specs/2026-07-10-a1-hygiene-floor-design.md
/docs/superpowers/specs/2026-07-10-landing-doc-adoption-design.md
/docs/superpowers/specs/2026-07-13-a11-mem0-decision-memo.md
/docs/superpowers/specs/2026-07-13-a3-self-learning-design.md
/docs/superpowers/specs/2026-07-13-a4-session-organ-design.md
/docs/superpowers/specs/2026-07-13-a5-body-store-git-design.md
/docs/superpowers/specs/2026-07-13-a7-*-proposer-design.md
/docs/superpowers/specs/2026-07-13-a8-teach-counsel-design.md
/docs/superpowers/specs/2026-07-13-p05-prompt-isomorphism-design.md
/docs/superpowers/specs/2026-07-14-llm-stack-switch-design.md
/docs/superpowers/specs/2026-07-16-body-six-components-design.md
```

- [ ] **Step 4: Verify the block ignores exactly the 42**

```bash
git check-ignore --stdin < "$RETIRED_LIST" | wc -l
git status --short --untracked-files=all | grep -c '^??'
```
Expected: `42`, then `0`.

- [ ] **Step 5: Reword the 37 lines**

`git grep -n -i 'son[i]a' -- . ':!demo'` lists them: 37 lines, 38 occurrences, in the 9 files above. Rules (spec §6.2): the product becomes "the previous product"; its second agent becomes "the retired meta-agent"; links into the sibling repository and to the retired charter file go, and the sentence is reworded to stand without them. Each row gives the new text of the phrase that carries the name; the rest of the line stays.

| Line | New text |
|---|---|
| `CLAUDE.md:9` | "…reset 2026-08-29 from the previous product. MARKET + ACCOUNT" |
| `docs/design/prototypes/BRIEF.md:15` | "From the 2026-07-07 face round of the previous product (recovered from the design repo's git history):" |
| `…unknown-unknowns.html:141` | the eyebrow reads `上一代产品 · 投资稿重写 · 前置研究 · 2026-07-11` |
| `…:161` | "…写进投资稿前值得再查证。" |
| `…:361` | "（本轮未逐条对抗验证，写稿前复核）" |
| `…:431` | "给 LLM 下达重写任务时，…" |
| `…:432` | "任务：重写上一代产品的投资稿（doctrine 种子），…" |
| `…:498` | "…写入投资稿前建议逐条复核。" |
| `…codex-connection-architecture.md:3` | "…此后不随设计决策回改(与上一代产品 research 目录同一惯例)。…" |
| `…:7` | "冻结基线对照件:上一代产品仓库中 2026-07-07 的凭证隔离研究(Codex @ `9365b08`,不在本仓库)。" |
| `…:9` | "(`alpha/mcp/` + 已退役元 agent 的 gate + 写腰 lint,commit `178d03d`)" |
| `…:14` | "**Baseline:** the previous product's frozen 2026-07-07 credential-isolation study (Codex @ `9365b08`; not in this repository)." and "…`connectors.py`, the retired meta-agent's tool module under `alpha/meta/` (both read first-hand)." |
| `…:77` | "## ④ BORROW/DIVERGE vs the previous product's connector model" |
| `…:79` | "…else silently absent (the retired meta-agent's tool module, lines 131-135); …" |
| `…:81` | the header cell reads "previous-product equivalent" |
| `…:90` | "(the retired meta-agent proposes → user approves → Applier lands; user-direct hand)" |
| `…:92` | "…if we ever expose Kairos or the retired meta-agent as a service, …" |
| `…dsh-survey.md:4` | with line 3: "…as input to a" / "discussion of the previous product's charter. FROZEN INPUT: notes record what the" |
| `…harness-design-report.md:1` | "# Harness Design Report: DeepSeek Harness × Prime Agent × the Previous Product's Charter" |
| `…:6` | "**Charter under discussion:** the previous product's charter, retired with it." |
| `…:56` | the header cell reads "previous product's charter" |
| `…:58` | the quoted motto reads "Kairos acts, the meta-agent evolves" |
| `…:61` | "the retired meta-agent proposes → user approves → Applier lands" |
| `…:246` | "└─► the previous charter ───────────" — one `─` fewer, so the right end stays put |
| `…:342` | "### 6.3 The previous product mapped onto the fused stack" |
| `…:350` | "— the retired meta-agent proposes → user approves → Applier lands" |
| `…:455` | "(future meta-agent/workbench permission presets)" |
| `…:485` | "The retired meta-agent's triage" |
| `…fused-harness-architecture.md:3` | "…This document sets the previous product's" (line 4 goes on "charter aside …") |
| `…:279` | "…what the previous product's charter already reaches for by other names:" |
| `…:282` | "(the retired meta-agent proposes, user approves, worker never proposes)" |
| `…msa-skeleton-reset.md:85` | `git rm -r -q alpha_web workbench seeds reference spikes third_party`, under a new comment line `# this step also removed the retired meta-agent's package` |
| `…:105` | `  tests/sizing tests/state tests/web tests/workbench 2>/dev/null`, under a new comment line, above the command's first line, `# this step also removed the retired meta-agent's tests` |
| `…:116` | `git rm -q tcb.lock Backend-Design.md ROADMAP.md CLAUDE.md`, under a new comment line `# this step also removed the previous product's charter file` |
| `…:138` | "…or the previous product's sibling repository (those trees are gone)." |
| `…skeleton-design.md:4` | "**Supersedes:** the previous product's self-evolving-H concept (charter, H=(p,K,M,C,W,A)," |
| `…:11` | "The operator is resetting this project from the previous product's concept to a three-layer product:" |

- [ ] **Step 6: Verify**

```bash
git grep -i -n 'son[i]a' -- . ':!demo'; echo "exit $?"
git diff --stat
```
Expected: no hits and `exit 1`; the diff touches `.gitignore` and the nine files only.

- [ ] **Step 7: Commit**

Message file:
```
docs: the previous product's 42 documents leave the tree, kept on disk

The 42 design documents of 2026-06/07 that name the retired product's second agent
are untracked and listed in .gitignore; the files stay on disk unchanged. The 37
remaining lines that named it are reworded without the name (spec 2026-10-18 §6).
```
```bash
git add .gitignore CLAUDE.md docs/design/prototypes/BRIEF.md docs/research docs/superpowers/plans/2026-08-29-msa-skeleton-reset.md docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md
git commit -F <message file>
```

---

### Task 2: The rename tool

**Files:**
- Create: `RENAME_TOOL` — a path outside the repository, e.g. the executing session's scratchpad; never committed.

**Interfaces:**
- Produces: `python3 "$RENAME_TOOL" --self-test` prints `self-test ok`; `python3 "$RENAME_TOOL" -- <pathspec>…`, run from the worktree root, rewrites every tracked UTF-8 text file the pathspecs select and prints `<n> files rewritten`. Bytes outside the renamed words are untouched (no newline translation).

- [ ] **Step 1: Write the tool**

The keep-list and the case rule are the algorithm, so the source is given whole:

```python
#!/usr/bin/env python3
"""One-off for the Gravit rename (docs/superpowers/specs/2026-10-18-gravit-rename-design.md §3.3, §4).

Rewrites the old agent name, case-preserving, in tracked UTF-8 text files, leaving the
spec's keep-list alone. Run from the repository root:  rename_gravit.py -- <pathspec>...
"""
import re
import subprocess
import sys
from pathlib import Path

# Spec §4.1, matched case-insensitively: a match inside one of these stays. `kairos-mining`
# is a guard - Task 3 drops the code's three citations and Task 7 relabels the history's
# nine before their passes (spec §4.3), so a leftover shows up in the audit instead of
# becoming a document that never existed.
KEEP = ("kairospan", "kairoszhe", "kairos-intro", "kairos-mining")
SKIP = {
    "strategies/aqr-r1000/launch-verification.json",
    "docs/superpowers/specs/2026-10-18-gravit-rename-design.md",
    "docs/superpowers/plans/2026-10-18-gravit-rename.md",
}
WORD = re.compile("kairos", re.IGNORECASE)


def cased(old: str) -> str:
    if old.isupper():
        return "GRAVIT"
    return "Gravit" if old[0].isupper() else "gravit"


def rename(text: str) -> str:
    lower = text.lower()
    kept = []
    for token in KEEP:
        start = lower.find(token)
        while start != -1:
            kept.append((start, start + len(token)))
            start = lower.find(token, start + 1)

    def sub(match):
        if any(a <= match.start() < b for a, b in kept):
            return match.group(0)
        return cased(match.group(0))

    return WORD.sub(sub, text)


CASES = {
    "Kairos": "Gravit", "kairos": "gravit", "KAIROS": "GRAVIT",
    "Kairos's tool": "Gravit's tool", "kairos-face/bot-mask": "gravit-face/bot-mask",
    "Kairos-Design.md": "Gravit-Design.md", "dsh/skills/style-kairos": "dsh/skills/style-gravit",
    "window.KAIROS_FACES": "window.GRAVIT_FACES", "kairosName": "gravitName", "kaiross": "gravits",
    "KairosPan/Evolving-Alpha-US": "KairosPan/Evolving-Alpha-US",
    "mailto:kairoszhe@gmail.com": "mailto:kairoszhe@gmail.com",
    "--scope kairospans-projects": "--scope kairospans-projects",
    "kairos-intro 页": "kairos-intro 页", "kairos-mining §3": "kairos-mining §3",
    "Owner: KairosPan. Kairos acts.": "Owner: KairosPan. Gravit acts.",
}


def main(argv):
    if argv[:1] == ["--self-test"]:
        for old, new in CASES.items():
            assert rename(old) == new, (old, rename(old), new)
        print("self-test ok")
        return
    specs = argv[1:] if argv[:1] == ["--"] else argv
    listed = subprocess.run(["git", "ls-files", "-z", "--", *(specs or ["."])],
                            check=True, capture_output=True).stdout.decode()
    changed = 0
    for name in filter(None, listed.split("\0")):
        path = Path(name)
        if name in SKIP or path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = rename(text)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed += 1
    print(f"{changed} files rewritten")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 2: Run the self-test**

Run: `python3 "$RENAME_TOOL" --self-test`
Expected: `self-test ok`.

---

### Task 3: The agent is Gravit in code, tests and runtime content

**Files:**
- Rename: `Kairos-Design.md` → `Gravit-Design.md`, `bots/kairos/` → `bots/gravit/`, `dsh/skills/style-kairos/` → `dsh/skills/style-gravit/`
- Modify: `alpaca_kit/integrity.py:1`, `alpaca_kit/feeds/offerings.py:4`, `tests/test_integrity.py:1`, `face/scripts/capture-demo-assets.mjs` (the `labels` map)
- Modify (the pass): every tracked file outside `docs/`, `CLAUDE.md`, `Gravit-Design.md`, `DEVELOPMENT.md`, `AGENTS.md` and every `README.md`

**Interfaces:**
- Consumes: `RENAME_TOOL` (Task 2).
- Produces: `DEFAULT_PRESET === "gravit"` and `presetRowId("gravit") === "preset-gravit"` (`face/src/overlay.ts`); every `BIN` is `"gravit-face"`; the bot plugin's `name` is `"gravit-bot"`; `HOST_NAME === "Gravit"` (`face/client/speaker.js`); `STORAGE_KEY === "gravit.market.watchlist.v1"` (`face/client/market-model.js`); `face/tests/bots-fixture.ts` populates an inert `gravit/` (`name: Gravit`); `face/tests/overlay.test.ts`'s fixture constant is `GRAVIT` (`id: "gravit"`, `name: "Gravit"`); `face/tests/room-fake.ts` `newRoom` writes `agentPreset: "gravit"`.

- [ ] **Step 1: Install and record the baseline**

```bash
(cd face && npm ci)
python -m pytest
(cd face && npm test && npm run typecheck)
```
Expected: every suite passes; note pytest's `N passed` and node's `# pass N`. If `npm ci` cannot reach the registry, clone the primary checkout's install instead: `cp -cR /Users/pan/Desktop/self-evolve/evolving-alpha-us/face/node_modules face/`. If any test fails here, stop and report — the baseline must be green before the rename.

- [ ] **Step 2: Rename the three paths**

```bash
git mv Kairos-Design.md Gravit-Design.md
git mv bots/kairos bots/gravit
git mv dsh/skills/style-kairos dsh/skills/style-gravit
```

- [ ] **Step 3: Drop the dead citations and the no-op mapping**

- `alpaca_kit/integrity.py` line 1 becomes `"""One hashing utility: file-bytes + canonical-JSON sha256.`
- `alpaca_kit/feeds/offerings.py` line 4 becomes `# docs/superpowers/specs/2026-07-13-p5b-shortinterest-offerings-design.md`
- `tests/test_integrity.py` line 1 becomes `"""alpaca_kit.integrity — the one hashing utility."""`
- `face/scripts/capture-demo-assets.mjs`: delete the `labels` line that maps `'KAIROS'` and `'Kairos'`; the page says Gravit by itself now.

- [ ] **Step 4: Run the code pass**

```bash
python3 "$RENAME_TOOL" -- . ':!docs' ':!CLAUDE.md' ':!Gravit-Design.md' ':!DEVELOPMENT.md' ':!AGENTS.md' ':!*README.md'
```
Expected: `<n> files rewritten`, about eighty-five (a dry run on 2026-10-18 rewrote 83).

- [ ] **Step 5: Run every suite**

```bash
python -m pytest
(cd face && npm test && npm run typecheck)
```
Expected: the baseline's counts, all passing.

- [ ] **Step 6: Audit the pass**

```bash
git grep -i -n kairos -- . ':!docs' ':!CLAUDE.md' ':!Gravit-Design.md' ':!DEVELOPMENT.md' ':!AGENTS.md' ':!*README.md'
```
Expected: exactly 7 lines — 4 in `face/landing/index.html` (the operator's address) and 3 in `strategies/aqr-r1000/launch-verification.json`.

- [ ] **Step 7: Commit**

Message: `refactor: the agent is Gravit in code, tests and runtime content` with a body naming the three path renames and the three dropped citations. `git add -A -- . ':!docs'` then `git commit -F <message file>`; `git status --short` is empty afterwards.

---

### Task 4: `kairos` stays a hidden alias of the `gravit` preset (server)

**Files:**
- Modify: `face/src/overlay.ts`, `face/src/boot.ts`, `face/src/bots.ts`, `face/src/room.ts`, `face/src/setup.ts`
- Test: `face/tests/overlay.test.ts`, `face/tests/boot.test.ts`, `face/tests/bots.test.ts`, `face/tests/room-engine.test.ts`, `face/tests/room-fake.ts`, `face/tests/bots-smoke.test.ts`, `face/tests/room-smoke.test.ts`

**Interfaces:**
- Consumes: Task 3's `DEFAULT_PRESET`, `presetRowId`, `faceOverlay(port, defaultPreset)`, `definitionFor(botsRoot, id)`.
- Produces, in `face/src/overlay.ts`:
  - `export const LEGACY_PRESET = "kairos";`
  - `export const LEGACY_PRESET_DESCRIPTION = "Gravit under its id before 2026-10-08, kept so sessions created before the rename still open";`
  - `export const isHostPreset = (id: unknown): boolean` — `true` exactly for `DEFAULT_PRESET` and `LEGACY_PRESET`;
  - `faceOverlay` inserts, right after the `preset-gravit` row: `{ id: presetRowId(LEGACY_PRESET), name: "@deepseek-ai/dsh-agent-preset", config: { ...defaultPreset, id: LEGACY_PRESET, description: LEGACY_PRESET_DESCRIPTION } }`.
- Produces, in `face/tests/room-fake.ts`: `newRoom(id: string, cwd: string, agentPreset = "gravit"): FakeAgent`.

- [ ] **Step 1: Write the failing unit tests**

`face/tests/overlay.test.ts` — import `LEGACY_PRESET`, `LEGACY_PRESET_DESCRIPTION`, `isHostPreset`; `ROWS` gains `["preset-kairos", "@deepseek-ai/dsh-agent-preset"]` right after `["preset-gravit", "@deepseek-ai/dsh-agent-preset"]`, and the first test's title says "thirteen host rows". Add:

```ts
test("preset-kairos re-declares the default's definition under the pre-rename id", () => {
  assert.equal(LEGACY_PRESET, "kairos");
  assert.equal(LEGACY_PRESET_DESCRIPTION, "Gravit under its id before 2026-10-08, kept so sessions created before the rename still open");
  const row = rowsById().get(presetRowId(LEGACY_PRESET))!;
  assert.equal(row.name, "@deepseek-ai/dsh-agent-preset");
  assert.deepEqual(row.config, { ...GRAVIT, id: "kairos", description: LEGACY_PRESET_DESCRIPTION });
});

test("isHostPreset accepts exactly the default and the pre-rename id", () => {
  for (const id of ["gravit", "kairos"]) assert.equal(isHostPreset(id), true, id);
  for (const id of ["gravit-2", "gravits", "kairos-2", "kaiross", "Gravit", "KAIROS", " gravit", "", "drill-bull", undefined, null, 42]) {
    assert.equal(isHostPreset(id), false, JSON.stringify(id));
  }
});
```

`face/tests/boot.test.ts` — at the end of "composeFace takes the static preset-gravit row from bots/gravit" (import `LEGACY_PRESET_DESCRIPTION` from `../src/overlay.ts`):

```ts
  const legacy = composeEntries([patches]).find((entry) => entry.id === "preset-kairos");
  assert.deepEqual(legacy?.config, { id: "kairos", name: "Gravit Fixture", description: LEGACY_PRESET_DESCRIPTION, plugins: [] });
```

`face/tests/bots.test.ts` — the `isBotId` test refuses both `"gravit"` and `"kairos"` (Task 3 left only `"gravit"`). Add:

```ts
test("createBot refuses both host ids and names them in its error", async () => {
  const root = await makeBotsRoot();
  for (const id of ["gravit", "kairos"]) {
    await assert.rejects(createBot(root, { id, name: "X" }),
      (err: HttpError) => err.status === 400 && /not gravit, kairos or _template/.test(err.message), id);
  }
});

test("listBots never lists a directory named after the pre-rename id", async () => {
  const root = await makeBotsRoot();
  await mkdir(join(root, "kairos"));
  await writeFile(join(root, "kairos", "preset.yml"), "name: Stray\n");
  const rows = await listBots(root, noPresets);
  assert.equal(rows.some((row) => row.id === "kairos"), false);
  assert.equal(rows.find((row) => row.id === "gravit")?.isDefault, true);
});
```

`face/tests/room-fake.ts` — `newRoom` takes the optional third parameter `agentPreset = "gravit"` and writes it into the header.

`face/tests/room-engine.test.ts` — a new test whose setup copies the dispatch-tool test's lines from `const tree = makeFakeTree();` through `const tool = …` (the scripted `buffett` included), then:

```ts
  const exec = (agent: unknown) => ({ agent, signal: new AbortController().signal }) as never;
  const legacy = tree.newRoom("session-legacy", CHANNEL.dir, "kairos");
  assert.equal((await tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "legacy" }, exec(legacy)) as { round: number }).round, 1);
  const mixed = tree.newRoom("session-mixed", CHANNEL.dir, "kairos");
  tree.emit(mixed.session, { type: "agent-preset/selected", seq: mixed.session.seq, data: { agentPreset: "gravit" } });
  assert.equal((await tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "mixed" }, exec(mixed)) as { round: number }).round, 1);
  const voice = tree.newRoom("session-voice", CHANNEL.dir, "kairos");
  tree.emit(voice.session, { type: "agent-preset/selected", seq: voice.session.seq, data: { agentPreset: "buffett" } });
  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(voice)), /Gravit's tool/);
```
Title: "the dispatch lock admits the pre-rename host id, alone or beside the new one, and still refuses a voice"; teardown as the dispatch-tool test does.

- [ ] **Step 2: Run them to see them fail**

Run: `cd face && npx tsx --test tests/overlay.test.ts tests/boot.test.ts tests/bots.test.ts tests/room-engine.test.ts`
Expected: FAIL — `LEGACY_PRESET` is not exported, `preset-kairos` is not inserted, `kairos` is admitted as a bot id, and the lock refuses `session-legacy`.

- [ ] **Step 3: Implement**

- `face/src/overlay.ts`: the three exports and the row from the Interfaces block; a comment on `LEGACY_PRESET` says why — sessions created before the rename persist `kairos`, and `AgentPresetRegistry.retain` (`pkg/dsh-agent-preset-registry/lib/index.js`) throws `agent-preset/not-found` for an id no row declares (spec §5.1). `faceOverlay`'s doc names the second row.
- `face/src/boot.ts`, in `bootFace`, right after the default-preset check: refuse when the roster lacks `LEGACY_PRESET` or lists it broken, with `` `${BIN}: legacy agent preset "${LEGACY_PRESET}" is ` + (absent ? "not in the roster" : `broken: ${reason}`) + " - sessions created before 2026-10-08 would not open" ``.
- `face/src/bots.ts`: import `DEFAULT_PRESET` and `LEGACY_PRESET` from `./overlay.ts`; `RESERVED_IDS = new Set([DEFAULT_PRESET, LEGACY_PRESET])`; the default directory's two literal checks in the bot reader compare with `DEFAULT_PRESET`; `createBot`'s message ends `not gravit, kairos or _template)`; `listBots`' directory filter adds `&& e.name !== LEGACY_PRESET`.
- `face/src/room.ts`: the `dispatch` lock becomes `.some((preset) => !isHostPreset(preset))`; the import takes `isHostPreset` in place of an unused `DEFAULT_PRESET`.
- `face/src/setup.ts`: the template comment's face-owned rows read `agent-preset-registry, preset-gravit, preset-kairos`.

- [ ] **Step 4: Run them to see them pass, then everything**

Run: `cd face && npx tsx --test tests/overlay.test.ts tests/boot.test.ts tests/bots.test.ts tests/room-engine.test.ts && npm test && npm run typecheck`
Expected: PASS. Then `grep -n -E '[!=]== ?"(gravit|kairos)"' face/src/*.ts` prints nothing.

- [ ] **Step 5: The two real-boot proofs**

`face/tests/bots-smoke.test.ts` — the roster expectation becomes `["cracked", "gravit", "kairos", "probe", "shipped", "trader"]`; in the same callback, after its last assertion:

```ts
      /* The pre-rename id: an archived session names `kairos` and must join the host composition. */
      assert.equal(roster.find((p) => p.id === "kairos")?.broken, undefined, "the legacy alias is listed and whole");
      const l = await create({ cwd: home, agentPreset: "kairos" });
      assert.equal(l.agentPreset, "kairos");
      const legacy = agentOf(l.sessionId);
      assert.equal(legacy.session.header.agentPreset, "kairos");
      assert.deepEqual(names(tools.schemas(legacy)), names(tools.schemas()), "the alias adds and removes nothing");
      assert.ok((await promptOf(legacy)).includes(readPersona(PERSONA_PATH).split("{{")[0]), "the alias is told it is Gravit");
```

`face/tests/room-smoke.test.ts` — in the same callback, after its last assertion:

```ts
      const legacyRoom = await rpc<{ sessionId: string; agentPreset?: string }>("session/create", { request: { workspaceId: ws.id, agentPreset: "kairos" } });
      assert.equal(legacyRoom.agentPreset, "kairos");
      assert.ok(tools.schemas(agents.get(String(legacyRoom.sessionId)) as object).some((s) => s.name === "dispatch"), "a pre-rename room keeps dispatch");
```

Run: `cd face && caffeinate -i env FACE_SMOKE=1 npx tsx --test tests/bots-smoke.test.ts tests/room-smoke.test.ts`
Expected: PASS; the boot log line reads `agent presets: … gravit, kairos, …` with `(default gravit; …)`.

- [ ] **Step 6: Commit**

Message: `feat(face): kairos stays a hidden alias of the gravit preset, so archived sessions open`, body citing spec §5.1. `git add face/src face/tests && git commit -F <message file>`.

---

### Task 5: The page treats both host ids alike and reads the pre-rename watchlist key

**Files:**
- Modify: `face/client/speaker.js`, `face/client/room.js`, `face/client/chat.js`, `face/client/channels.js`, `face/client/market-model.js`, `face/client/botId.js` (its doc only)
- Test: `face/tests/speaker.test.ts`, `face/tests/room-client.test.ts`, `face/tests/market-model.test.ts`

**Interfaces:**
- Produces, in `face/client/speaker.js`: `export const HOST_PRESETS = Object.freeze(["gravit", "kairos"]);` and `export function isHostPreset(id)` → `true` exactly for those two strings.
- Produces, in `face/client/market-model.js`: `export const LEGACY_STORAGE_KEY = "kairos.market.watchlist.v1";` beside Task 3's `STORAGE_KEY`.

- [ ] **Step 1: Write the failing tests**

`face/tests/speaker.test.ts` — import `HOST_PRESETS` and `isHostPreset`; the fallback test's preset list gains `"kairos-2"` and `"kaiross"` beside Task 3's `"gravit-2"` and `"gravits"`. Add:

```ts
test("isHostPreset: exactly gravit and its pre-rename id kairos", () => {
  assert.deepEqual([...HOST_PRESETS], ["gravit", "kairos"]);
  assert.equal(HOST_NAME, "Gravit");
  for (const id of HOST_PRESETS) assert.equal(isHostPreset(id), true, id);
  for (const id of ["gravit-2", "gravits", "kairos-2", "kaiross", "Gravit", " gravit", "", null, undefined, 42, {}]) {
    assert.equal(isHostPreset(id), false, JSON.stringify(id));
  }
});

test("a session recorded under the pre-rename id speaks as the host", () => {
  assert.equal(speakerFor({ agentPreset: "kairos" }, bots), HOST_NAME);
  assert.equal(speakerFor({ agentPreset: "kairos" }, [{ id: "kairos", name: "Impostor" }]), HOST_NAME);
});
```

`face/tests/room-client.test.ts`:

```ts
test("foldMembers: a room recorded under the pre-rename id still folds its members, and its forks stay out", () => {
  const { rooms, members } = foldMembers([
    { sessionId: "legacy-room", agentPreset: "kairos", cwd: "/c" },
    { sessionId: "m-legacy", parentSessionId: "legacy-room", agentPreset: "buffett", cwd: "/c" },
    { sessionId: "legacy-fork", parentSessionId: "legacy-room", agentPreset: "kairos", cwd: "/c" },
  ]);
  assert.deepEqual(rooms.get("legacy-room")?.map((r) => r.sessionId), ["m-legacy"]);
  assert.deepEqual([...members], ["m-legacy"]);
});
```

`face/tests/market-model.test.ts` — import `LEGACY_STORAGE_KEY`. `memory(initial: string | null = null, legacy: string | null = null)` becomes a two-key store: `getItem` accepts either key and returns that key's value or `null`; `setItem` still asserts `key === STORAGE_KEY`; getters `value` (the new key), `legacy` (the old key), `writes`. The existing tests keep passing unchanged. Add:

```ts
test("a list saved under the pre-rename key is read until the first save, which writes only the new key", () => {
  assert.equal(STORAGE_KEY, "gravit.market.watchlist.v1");
  assert.equal(LEGACY_STORAGE_KEY, "kairos.market.watchlist.v1");
  const old = JSON.stringify({ version: 1, items: [us, cn] });
  const storage = memory(null, old);
  assert.deepEqual(readWatchlist(storage), { items: [us, cn], error: null });
  assert.equal(storage.writes, 0);
  assert.equal(saveWatchlist(storage, [crypto]), null);
  assert.deepEqual(readWatchlist(storage), { items: [crypto], error: null });
  assert.equal(storage.legacy, old, "the pre-rename entry is never rewritten");
});

test("the new key wins whenever it exists, even holding an empty list", () => {
  const storage = memory(JSON.stringify({ version: 1, items: [] }), JSON.stringify({ version: 1, items: [us] }));
  assert.deepEqual(readWatchlist(storage), { items: [], error: null });
});

test("a malformed pre-rename entry is reported and left untouched", () => {
  const storage = memory(null, "invalid JSON");
  const loaded = readWatchlist(storage);
  assert.deepEqual(loaded.items, []);
  assert.ok(loaded.error);
  assert.equal(storage.legacy, "invalid JSON");
  assert.equal(storage.writes, 0);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd face && npx tsx --test tests/speaker.test.ts tests/room-client.test.ts tests/market-model.test.ts`
Expected: FAIL — `HOST_PRESETS`, `isHostPreset` and `LEGACY_STORAGE_KEY` are not exported, and `foldMembers` treats `kairos` as a bot.

- [ ] **Step 3: Implement**

- `face/client/speaker.js`: the two exports, with a JSDoc saying why `kairos` is there (spec §5.1); `speakerFor`'s host test is `typeof id !== "string" || id.trim() === "" || isHostPreset(id)`.
- `face/client/room.js`: import `isHostPreset` from `./speaker.js`; `isHost` is `typeof row.agentPreset !== "string" || row.agentPreset === "" || isHostPreset(row.agentPreset)`.
- `face/client/chat.js`: import `isHostPreset` beside `HOST_NAME` and `speakerFor`. Three sites: the subagent hint's condition `(!summary?.agentPreset || isHostPreset(summary.agentPreset))`; the room strip's roster filter `.filter((b) => !isHostPreset(b.id))`; `botOf`'s early return `typeof id !== "string" || isHostPreset(id)`.
- `face/client/channels.js`: import `isHostPreset` from `./speaker.js`; the `allBots` filter is `(b) => !isHostPreset(b.id)`.
- `face/client/market-model.js`: `LEGACY_STORAGE_KEY`; inside `readWatchlist`'s existing `try`, after reading `STORAGE_KEY`, `if (raw === null) raw = storage.getItem(LEGACY_STORAGE_KEY);`. `saveWatchlist` is unchanged.
- `face/client/botId.js`: the module doc describes the server gate as "dsh's preset grammar `[a-z0-9][a-z0-9-]*`, minus the two host ids and `_template`" (spec §5.1).

- [ ] **Step 4: Run them to see them pass, then everything**

Run: `cd face && npx tsx --test tests/speaker.test.ts tests/room-client.test.ts tests/market-model.test.ts && npm test && npm run typecheck`
Expected: PASS. Then `grep -n -E '[!=]== ?"(gravit|kairos)"' face/client/*.js` prints nothing.

- [ ] **Step 5: Commit**

Message: `feat(face): the page treats both host ids alike and reads the pre-rename watchlist key`. `git add face/client face/tests && git commit -F <message file>`.

---

### Task 6: The live docs name the agent Gravit and record the alias

**Files:**
- Modify (the pass): `CLAUDE.md`, `Gravit-Design.md`, `DEVELOPMENT.md`, `AGENTS.md`, `dsh/README.md`, `face/README.md`, `bots/*/README.md`, `bots/*/skills/README.md`
- Modify (by hand): `DEVELOPMENT.md`, `face/README.md`

**Interfaces:**
- Consumes: Task 4's `LEGACY_PRESET`, `LEGACY_PRESET_DESCRIPTION`, `isHostPreset` and the boot refusal; Task 5's `LEGACY_STORAGE_KEY`.

- [ ] **Step 1: Run the docs pass**

```bash
python3 "$RENAME_TOOL" -- CLAUDE.md Gravit-Design.md DEVELOPMENT.md AGENTS.md '*README.md' ':!docs'
```
Expected: `<n> files rewritten`, about twenty (a dry run on 2026-10-18 rewrote 19).

- [ ] **Step 2: Write the alias and the key into `DEVELOPMENT.md`**

- §1's box: the row list `ask-user · agent-preset-registry · preset-gravit` gains ` · preset-kairos`, the right border kept aligned.
- §3.7, after the sentence that makes `bots/gravit` the static `preset-gravit` row: "A second static row, `preset-kairos`, declares the same definition under `kairos`, the agent's id before the 2026-10-08 rename. Sessions created before it persist that id, and dsh refuses to resume a session whose preset no row declares (`agent-preset/not-found`, `AgentPresetRegistry.retain`). The alias has no directory, so `/data/bots.json` never lists it, and `RESERVED_IDS` keeps both ids from naming a bot."
- §4.3's table, a row after `preset-gravit`: "| `preset-kairos` | `dsh-agent-preset` | the legacy alias: the default's definition under `kairos`, Gravit's id before 2026-10-08, so archived sessions resolve; `bootFace` refuses a boot where it is absent or broken; every host test goes through `isHostPreset` (`src/overlay.ts`, `client/speaker.js`) |"
- §5.4, the market page's key: "the market page keeps its own, `gravit.market.watchlist.v1`; a browser that saved before the rename is read from `kairos.market.watchlist.v1` until its first save, which writes only the new key."
- §7.3, where it lists boot.test.ts's `preset-gravit` assertion: "and the `preset-kairos` alias equal to it under the legacy id".

- [ ] **Step 3: Write the alias and the key into `face/README.md`**

- "What boot refuses": a bullet "the legacy preset `kairos` (Gravit's id before 2026-10-08) is absent or broken — sessions created before the rename would not open".
- "The profile": the face-owned row list `agent-preset-registry`, `preset-gravit` gains `preset-kairos`.
- "Bots", after the paragraph on the static `preset-gravit` row: "The face also declares `preset-kairos`, the same definition under `kairos`, Gravit's id before 2026-10-08: archived sessions persist it and dsh refuses a preset no row declares. It has no directory and never appears among the bots; `kairos` and `gravit` are both reserved ids."
- "Market watchlist", after the sentence naming `gravit.market.watchlist.v1`: "A browser that saved its list before the 2026-10-08 rename keeps it: the page reads `kairos.market.watchlist.v1` while the new key is absent and never writes or deletes the old one."

- [ ] **Step 4: Verify**

```bash
git diff --stat -- CLAUDE.md
git grep -n 'Kairos-Design' -- CLAUDE.md Gravit-Design.md DEVELOPMENT.md AGENTS.md '*README.md' ':!docs'
git grep -i -n kairos -- CLAUDE.md Gravit-Design.md DEVELOPMENT.md AGENTS.md '*README.md' ':!docs'
```
Expected: `CLAUDE.md` changes lines and adds none; the second prints nothing; every hit of the third is one of `face/README.md`'s three `kairospans-projects` lines or a line Steps 2–3 wrote about the alias or the legacy key.

- [ ] **Step 5: Commit**

Message: `docs: the live docs name the agent Gravit and record the kairos alias`. `git add -A -- . ':!docs' && git commit -F <message file>`.

---

### Task 7: The dated history names the agent Gravit

**Files:**
- Modify (by hand first): `docs/superpowers/specs/2026-07-13-p1-trap-day-battery-design.md`, `…-p2-growth-market-clock-design.md`, `…-p3-corp-actions-tristate-design.md`, `…-p5b-shortinterest-offerings-design.md`, `…-p6-eval-methodology-design.md`
- Modify (the pass): every tracked file under `docs/` except the spec and this plan

**Interfaces:**
- Consumes: `RENAME_TOOL` (Task 2; it skips the spec and this plan).

- [ ] **Step 1: Relabel the dead citations (spec §4.3)**

```bash
git grep -l 'kairos-mining' -- docs ':!docs/superpowers/specs/2026-10-18-gravit-rename-design.md' ':!docs/superpowers/plans/2026-10-18-gravit-rename.md' \
  | xargs sed -i '' 's/kairos-mining/design-mining/g'
git grep -c 'design-mining' -- docs ':!docs/superpowers/specs/2026-10-18-gravit-rename-design.md' ':!docs/superpowers/plans/2026-10-18-gravit-rename.md'
```
Expected: the five 2026-07-13 specs, 9 lines in all (p1 2, p2 1, p3 2, p5b short-interest/offerings 2, p6 2).

- [ ] **Step 2: Run the history pass**

Run: `python3 "$RENAME_TOOL" -- docs`
Expected: `<n> files rewritten`, about fifty-five (a dry run on 2026-10-18 rewrote 54).

- [ ] **Step 3: The prototypes still wire up**

```bash
comm -13 \
  <(git grep -h -o -E 'window\.GRAVIT_[A-Z_]+ *=' -- docs/design/prototypes | sed -E 's/ *=$//' | sort -u) \
  <(git grep -h -o -E 'window\.GRAVIT_[A-Z_]+' -- docs/design/prototypes | sort -u)
```
Expected: no output — every global a prototype page reads is one its data files define.

- [ ] **Step 4: Audit the pass**

Run: `git grep -i -n kairos -- docs`
Expected: hits only in the spec, in this plan, in seven `KairosPan` lines (`docs/superpowers/plans/2026-10-05-venue-plugins-unification-handoff.md` and six specs) and in the handoff's one `kairos-intro` line.

- [ ] **Step 5: Read the diff by category**

`git diff --stat -- docs/superpowers docs/research docs/design`, then three hunks from each of the three; tables and ASCII diagrams keep their alignment.

- [ ] **Step 6: Commit**

Message: `docs: the dated history names the agent Gravit`. `git add docs && git commit -F <message file>`.

---

### Task 8: Branch verification

**Files:** none changed.

- [ ] **Step 1: Every suite, real boots included**

```bash
python -m pytest
cd face && npm test && npm run typecheck && caffeinate -i env FACE_SMOKE=1 npm test
```
Expected: all pass; under `FACE_SMOKE=1` none of the real boots `face/README.md` lists is skipped.

- [ ] **Step 2: The audits at the branch head**

```bash
git grep -i -l kairos -- . ':!demo'
git grep -i -n 'son[i]a' -- . ':!demo'; echo "exit $?"
git check-ignore --stdin < "$RETIRED_LIST" | wc -l
git status --short
```
Expected, in order: exactly these 26 files —

```
DEVELOPMENT.md
docs/superpowers/plans/2026-10-05-venue-plugins-unification-handoff.md
docs/superpowers/plans/2026-10-18-gravit-rename.md
docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md
docs/superpowers/specs/2026-07-13-p2-growth-market-clock-design.md
docs/superpowers/specs/2026-07-13-p5b-float-feed-design.md
docs/superpowers/specs/2026-07-13-p5b-theme-breadth-design.md
docs/superpowers/specs/2026-07-13-stock-clock-design.md
docs/superpowers/specs/2026-07-13-theme-clock-consumer-design.md
docs/superpowers/specs/2026-10-18-gravit-rename-design.md
face/README.md
face/client/market-model.js
face/client/speaker.js
face/landing/index.html
face/src/overlay.ts
face/src/setup.ts
face/tests/boot.test.ts
face/tests/bots-smoke.test.ts
face/tests/bots.test.ts
face/tests/market-model.test.ts
face/tests/overlay.test.ts
face/tests/room-client.test.ts
face/tests/room-engine.test.ts
face/tests/room-smoke.test.ts
face/tests/speaker.test.ts
strategies/aqr-r1000/launch-verification.json
```
— then no retired-name hit and `exit 1`, then `42`, then a clean status.

- [ ] **Step 3: Hand off**

Report the branch head, the test counts and `git diff --stat main...HEAD | tail -1` to the operator, and stop: the merge is the operator's call (Task 9).

---

### Task 9: Merge and the steps after it (main session only, on the operator's word)

**Files:**
- Modify, outside the repository: `~/.dsh/profiles/face/cordis.patch.yml` (backed up first)

- [ ] **Step 1: Ask, and wait for an explicit yes.**

- [ ] **Step 2: Pre-flight in the primary checkout**

```bash
P=/Users/pan/Desktop/self-evolve/evolving-alpha-us
git -C "$P" branch --show-current
git -C "$P" status --short --untracked-files=no
PRE=$(git -C "$P" rev-parse main)
lsof -nP -iTCP:3090 -sTCP:LISTEN
```
Expected: `main`; no tracked edits; `PRE` recorded; whether a face is running. Run `ListAgents` too: a peer busy in the primary checkout is named to the operator before the merge.

- [ ] **Step 3: Fast-forward**

Run: `git -C "$P" merge --ff-only chore/gravit-rename`
Expected: a fast-forward to the branch head.

- [ ] **Step 4: Put the 42 back on disk**

```bash
git -C "$P" grep -l -i 'son[i]a' "$PRE" -- 'docs/superpowers/*/2026-06-*' 'docs/superpowers/*/2026-07-*' docs/superpowers/runbooks/p-b-p-c-activation.md \
  | sed "s|^$PRE:||" > "$RETIRED_LIST"
wc -l < "$RETIRED_LIST"
git -C "$P" restore --source="$PRE" --worktree --pathspec-from-file="$RETIRED_LIST"
git -C "$P" check-ignore --stdin < "$RETIRED_LIST" | wc -l
git -C "$P" status --short --untracked-files=all | grep -c '^??'
```
Expected: `42`, `42`, and no `??` line from them. (Tried on a scratch clone on 2026-10-18: the file comes back byte-identical and untracked.)

- [ ] **Step 5: The operator's profile patch**

```bash
F="$HOME/.dsh/profiles/face/cordis.patch.yml"
cp -p "$F" "$F.bak-$(date +%Y%m%d)"
```
Then change exactly four lines:
- line 2: `# api gateway, connection) are inserted programmatically by gravit-face at`
- line 10: `# accepted, overridden, and never reported. Change those in gravit-face's`
- line 46: `      - /Users/pan/Desktop/self-evolve/evolving-alpha-us/dsh/skills/style-gravit`
- line 48: `# dsh 0.2.0-rc.2 (2026-10-01): the face reads no settings.yaml any more, so Gravit's default`

Verify: `diff "$F.bak-$(date +%Y%m%d)" "$F"` shows those four lines and no other; `grep -n -i kairos "$F"` prints nothing; `ls "$P/dsh/skills/style-gravit"` lists `doctrine lessons signals`.

- [ ] **Step 6: Tell the operator**

A running face is restarted (`cd face && npm start`, then the printed `…/?token=…` URL) and every open tab hard-reloaded; `feat/agent-redesign` can now merge `main`. No push.

- [ ] **Step 7: Memory**

Update `gravit-rename-2026-10-08.md` (merged at the new head; the alias, the key and the profile patch done) and its `MEMORY.md` line; re-grep `MEMORY.md` for the slug afterwards, since peer sessions rewrite the index.
