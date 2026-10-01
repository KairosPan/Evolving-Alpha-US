/** Kairos's deployment persona — the order-0 `deployment:persona-prefix`
 * section of every prompt the face assembles, set as `personaPrefix` on
 * dsh-base's `system-prompt` row by the patch `composeFace` pushes (boot.ts).
 * dsh 0.2.0 renamed the key and the section (`persona` / `deployment:persona`
 * at 0.1.1; NEW packages/core/system-prompt/src/index.ts:125-127, 179,
 * 409-436; commit 40792330c0) without moving the slot: order 0, after the
 * harness identity line. Before this file existed the row's persona was `''`
 * and the model was never told it was Kairos (charter D11).
 *
 * The renderer is STRICT (NEW packages/core/system-prompt/src/index.ts:
 * 268-279, 325-347: complete `{{…}}` groups are interpreted against the
 * registered variables with no escape syntax): an unknown variable fails EVERY
 * step of EVERY session. So the text is validated where it is read, and a bad
 * file refuses the boot with the path in the message rather than shipping a
 * prompt that throws later.
 * @module
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** The variables the shipped loop registers ("The loop supplies `model` and
 * `cwd`": NEW packages/core/system-prompt/README.md:70; unchanged at 0.2.0-rc.2). */
export const PERSONA_VARIABLES: readonly string[] = ["model", "cwd"];

/** Resolved from this module, never from the working directory (data.ts does the same). */
export const PERSONA_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "dsh", "profile", "persona.md");

/** `undefined` when the text will render; otherwise one reason. Stricter than
 * dsh: every `{{` here must open a known variable, so a lone brace is refused too. */
export function validatePersonaTemplate(text: string): string | undefined {
  if (text.trim() === "") return "persona is empty";
  const GROUP = /\{\{([^{}]*)\}\}/g;
  /* The name is the RAW text between the braces, never trimmed - dsh takes
   * `group[0].slice(2, -2)` and tests it against `/^[a-z][a-z0-9_]*$/` (NEW
   * packages/core/system-prompt/src/index.ts:185, 188, 334-347).
   * So `{{ model }}` is malformed there, and trimming here would pass it. */
  for (const match of text.matchAll(GROUP)) {
    const variable = match[1];
    if (!PERSONA_VARIABLES.includes(variable)) {
      return `unknown persona variable {{${variable}}} (known: ${PERSONA_VARIABLES.join(", ")})`;
    }
  }
  /* Stricter than dsh on purpose: once every complete `{{model}}`/`{{cwd}}`
   * group is removed, no brace may remain. dsh tolerates a lone `{`, but
   * `{{{model}}}` and `{{ model }}` both throw there (a `{{` with no later
   * `}}` it copies through as literal text instead), and persona prose has no
   * use for a stray brace - refusing them all is the cheaper rule to explain. */
  if (/[{}]/.test(text.replace(GROUP, ""))) return "unbalanced {{ }} in persona (a brace outside a {{model}}/{{cwd}} group)";
  return undefined;
}

/** Read and validate; throws with the path so a boot failure names the file. */
export function readPersona(path: string): string {
  const text = readFileSync(path, "utf8");
  const problem = validatePersonaTemplate(text);
  if (problem !== undefined) throw new Error(`kairos-face: ${path}: ${problem}`);
  return text.trim();
}
