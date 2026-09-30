import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PERSONA_PREFIX_SECTION, renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import { PERSONA_PATH, PERSONA_VARIABLES, readPersona, validatePersonaTemplate } from "../src/persona.ts";

/** The installed renderer, on the one section the persona fills at dsh 0.2.0
 *  (`personaPrefix` → `deployment:persona-prefix`, NEW
 *  packages/core/system-prompt/src/index.ts:179, 432-437). `provider`, `model`
 *  and `cwd` are what dsh-agent-loop registers (NEW
 *  packages/core/agent-loop/src/index.ts:370-372). */
const renderPersona = (text: string): string => renderPrompt({
  sections: [{ name: PERSONA_PREFIX_SECTION, text }],
  contexts: [],
  tools: [],
  variables: { provider: "deepseek-official", model: "deepseek-flash", cwd: "/work/tree" },
});

test("validatePersonaTemplate accepts model and cwd, refuses everything else the strict renderer would throw on", () => {
  assert.equal(validatePersonaTemplate("You are Kairos. Your working directory is {{cwd}} on {{model}}."), undefined);
  assert.match(validatePersonaTemplate("") ?? "", /empty/);
  assert.match(validatePersonaTemplate("   \n") ?? "", /empty/);
  assert.match(validatePersonaTemplate("Hello {{date}}") ?? "", /unknown persona variable \{\{date\}\}/);
  assert.match(validatePersonaTemplate("Hello {{ model }") ?? "", /unbalanced/);
  assert.match(validatePersonaTemplate("Hello {{{model}}}") ?? "", /unbalanced|unknown/);
  assert.match(validatePersonaTemplate("Hello {{ model }}") ?? "", /unknown persona variable/);
});

test("readPersona returns the trimmed file and throws with the path on a bad template", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-persona-"));
  const good = join(dir, "good.md");
  await writeFile(good, "\nYou are Probe in {{cwd}}.\n\n");
  assert.equal(readPersona(good), "You are Probe in {{cwd}}.");
  const bad = join(dir, "bad.md");
  await writeFile(bad, "You are {{nobody}}.");
  assert.throws(() => readPersona(bad), (err: Error) => err.message.includes(bad) && /nobody/.test(err.message));
});

test("the shipped persona.md is valid and names Kairos", () => {
  const text = readPersona(PERSONA_PATH);
  assert.match(text, /You are Kairos/);
  assert.equal(validatePersonaTemplate(text), undefined);
});

/* The validator is only worth its refusal if it is never LOOSER than the
 * renderer it guards: a persona it passes that dsh then throws on fails every
 * step of every session. Pinned against the installed strict renderer so an
 * upstream change to the variable grammar fails here, at the pin bump. */
test("whatever validatePersonaTemplate accepts, dsh's strict renderer renders - and what dsh throws on, it refuses", () => {
  assert.equal(renderPersona(readPersona(PERSONA_PATH)).includes("/work/tree"), true, "the shipped persona renders, cwd substituted");
  for (const variable of PERSONA_VARIABLES) {
    assert.doesNotThrow(() => renderPersona(`You run {{${variable}}}.`), variable);
  }
  assert.equal(renderPersona("You are Kairos in {{cwd}} on {{model}}."), "You are Kairos in /work/tree on deepseek-flash.");
  for (const text of ["Hello {{date}}", "Hello {{ model }}", "Hello {{Model}}"]) {
    assert.notEqual(validatePersonaTemplate(text), undefined, `the face refuses ${text}`);
    assert.throws(() => renderPersona(text), `and dsh would have thrown on ${text}`);
  }
});
