# AGENTS.md — for coding agents

This file is read by coding agents working on this repository (Claude Code and Codex read it).
The research agent, Gravit, does not: dsh hands it `GRAVIT.md` and nothing else.

- Read `CLAUDE.md` first — the map, the commands, the gotchas. Depth: `DEVELOPMENT.md`
  (mechanism), `Gravit-Design.md` (intent), `face/README.md` (the face's contracts and drills).
- `GRAVIT.md` is a product file: every dsh agent in the tree reads it on its first request.
  Change it as you would change a prompt — deliberately, inside its byte budget, with
  `face/tests/gravit-md.test.ts` green.
- `strategies/` is Gravit's arena. `bots/`, `roles/`, `data/pit/` and `docs/research/` are the
  operator's: do not edit them unless asked.
- Keep both suites green: `python -m pytest` at the root; `npm test && npm run typecheck` in
  `face/`, plus `FACE_SMOKE=1 npm test` after any change under `face/src`, `face/plugins` or to
  the dsh pins.
- Commit messages go in a file and through `git commit -F`; never backticks or `$()` in `-m`.
