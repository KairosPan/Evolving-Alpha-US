import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const GRAVIT_MD = fileURLToPath(new URL("../../GRAVIT.md", import.meta.url));
const RULES_MD = fileURLToPath(new URL("../../docs/backtest-rules.md", import.meta.url));
/** Spec §4.2: the budget of the one file every dsh agent in the tree reads on its first request. */
const BUDGET_BYTES = 4500;

test("GRAVIT.md fits its budget and contains no template group", () => {
  const text = readFileSync(GRAVIT_MD, "utf8");
  assert.ok(Buffer.byteLength(text, "utf8") <= BUDGET_BYTES, `GRAVIT.md is ${Buffer.byteLength(text, "utf8")} bytes; the budget is ${BUDGET_BYTES}`);
  assert.equal(text.includes("{{"), false, "the system prompt is a strict template with no escape");
});

test("GRAVIT.md's bed table is docs/backtest-rules.md's, row for row", () => {
  /* trimmed: docs/backtest-rules.md indents its table inside a list item */
  const rows = (file: string) => readFileSync(file, "utf8").split("\n").map((line) => line.trim()).filter((line) => /^\| `data\/pit\//.test(line));
  const expected = rows(RULES_MD);
  assert.equal(expected.length, 2, "backtest-rules.md has the two bed rows");
  assert.deepEqual(rows(GRAVIT_MD), expected, "a bed window changed in one file and not the other");
});

test("GRAVIT.md states facts, not identity: it never tells the reader who it is", () => {
  const text = readFileSync(GRAVIT_MD, "utf8");
  assert.equal(/^You are /m.test(text), false);
});
