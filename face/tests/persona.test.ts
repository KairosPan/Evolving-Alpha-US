import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PERSONA_PATH, readPersona, validatePersonaTemplate } from "../src/persona.ts";

test("validatePersonaTemplate accepts model and cwd, refuses everything else the strict renderer would throw on", () => {
  assert.equal(validatePersonaTemplate("You are Kairos. Your working directory is {{cwd}} on {{model}}."), undefined);
  assert.match(validatePersonaTemplate("") ?? "", /empty/);
  assert.match(validatePersonaTemplate("   \n") ?? "", /empty/);
  assert.match(validatePersonaTemplate("Hello {{date}}") ?? "", /unknown persona variable \{\{date\}\}/);
  assert.match(validatePersonaTemplate("Hello {{ model }") ?? "", /unbalanced/);
  assert.match(validatePersonaTemplate("Hello {{{model}}}") ?? "", /unbalanced|unknown/);
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
