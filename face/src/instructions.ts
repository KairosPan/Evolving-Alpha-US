/** Which workspace instruction files the face's dsh agents read from a
 * project: `GRAVIT.md` and its machine-local twin `GRAVIT.local.md`, in each
 * directory from the project root down to the session's cwd - no other file
 * name is a candidate. The repo's `AGENTS.md` and `CLAUDE.md` are the coding
 * agents' files, not Gravit's (spec §4.1 L3, §4.3).
 *
 * The seam is dsh-base's own row. The installed `@deepseek-ai/dsh-base`
 * `cordis.patch.yml` mounts `agent-instructions`
 * (`@deepseek-ai/dsh-agent-instructions`) with `config: { maxBytes: 65536 }`
 * and no candidate lists, which is the package's defaults: `['AGENTS.md',
 * 'CLAUDE.md']` for the base files and `['AGENTS.local.md', 'CLAUDE.local.md']`
 * for the local overlay (`Config` in the package's `lib/index.js`). The row is
 * host-plane (spec §4.1 L3), so one patch serves every agent in the tree, not
 * Gravit alone; tests/room-smoke.test.ts pins the chain on each bot session of
 * a room.
 *
 * {@link instructionsPatch} is pushed by `composeFace` (boot.ts) after the
 * operator's layers, like the persona patch, and guarded the same way. A
 * non-insert patch REPLACES the row's whole config (the persona patch's comment
 * in boot.ts documents the rule), so the face restates `maxBytes` beside the
 * two candidate lists - and unlike the persona patch it merges nothing in: the
 * row's config is the face's, whole, and an operator key on this row is dropped
 * (setup.ts PATCH_HEADER says so to the operator).
 *
 * Out of reach, deliberately: the user-global `$DSH_HOME/AGENTS.md` is a name
 * hard-coded in the package (`USER_GLOBAL_FILE`), not a candidate, so the
 * lists below neither rename nor suppress it.
 * @module
 */
import type { Config as AgentInstructionsConfig } from "@deepseek-ai/dsh-agent-instructions";

/** dsh-base's row id (installed `dsh-base/cordis.patch.yml`, row `agent-instructions`). */
export const AGENT_INSTRUCTIONS_ROW_ID = "agent-instructions";

/** The one base instruction file, read in every directory of the chain. */
export const INSTRUCTION_FILE = "GRAVIT.md";

/** Its local overlay, loaded after the base file in the same directory; gitignored. */
export const LOCAL_INSTRUCTION_FILE = "GRAVIT.local.md";

/** The row's whole config. `satisfies` is the contract check: a renamed or
 * misspelled key is a type error against the package's own `Config`. `maxBytes`
 * is dsh-base's own value, restated because the patch replaces the config. */
export const INSTRUCTIONS_CONFIG = {
  maxBytes: 65536,
  instructionFileCandidates: [INSTRUCTION_FILE],
  localInstructionFileCandidates: [LOCAL_INSTRUCTION_FILE],
} satisfies AgentInstructionsConfig;

/** The id patch for the row. A fresh object every call, config included: the
 * include's patch algorithm assigns into rows by reference, so a shared object
 * could be rewritten under every later composition. */
export function instructionsPatch(): { id: string; name: "@deepseek-ai/dsh-agent-instructions"; config: typeof INSTRUCTIONS_CONFIG } {
  return {
    id: AGENT_INSTRUCTIONS_ROW_ID,
    name: "@deepseek-ai/dsh-agent-instructions",
    config: structuredClone(INSTRUCTIONS_CONFIG),
  };
}
