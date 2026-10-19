/** Gravit's research-cycle contract - `dsh/profile/cycle.md`, the one file that tells Gravit how
 * to run a cycle: one batched question, then a goal-driven loop of role calls to a verdict (spec
 * §6). {@link readCycle} reads it where `composeFace` renders Gravit's default preset
 * (src/boot.ts) and hands the text to `gravitRows` (src/roles.ts) as the `gravit` row's `cycle`
 * key, which `plugins/gravit.js` turns into the `gravit:cycle` section of every prompt a scope
 * that can call `create_goal` assembles: Gravit's, and a `subagent_fork` child's. A role child is
 * told nothing.
 *
 * Unlike the persona (src/persona.ts), the text is NOT a template. The section registers with
 * `interpolate: false`, so a `{{...}}` group in it is literal prose, not an unknown variable that
 * would fail every step of every session; the reader therefore checks the size and nothing else.
 *
 * The text rides in every request Gravit makes, so it is capped at {@link CYCLE_MAX_BYTES} bytes,
 * the prompt budget of spec §7. An empty file and an oversized one are refused where the file is
 * read, with its path first, so a boot names the file at fault instead of shipping a Gravit with
 * no contract or a heavier prompt than was budgeted.
 * @module
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Resolved from this module, never from the working directory (persona.ts does the same). */
export const CYCLE_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "dsh", "profile", "cycle.md");

/** The largest `cycle.md`, in bytes as `wc -c` counts them. */
export const CYCLE_MAX_BYTES = 3000;

/** The cycle text, trimmed. Throws an `Error` that opens with the path when the file is empty or
 * over {@link CYCLE_MAX_BYTES}; a file that cannot be read throws the read's own error, which names
 * the path too. Braces are allowed: the section does not interpolate. */
export function readCycle(path: string): string {
  const bytes = readFileSync(path);
  const text = bytes.toString("utf8").trim();
  if (text === "") throw new Error(`${path}: the cycle is empty`);
  if (bytes.length > CYCLE_MAX_BYTES) throw new Error(`${path}: is ${bytes.length} bytes; the limit is ${CYCLE_MAX_BYTES}`);
  return text;
}
