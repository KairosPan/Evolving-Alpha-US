import test from "node:test";
import assert from "node:assert/strict";
import {
  ROOM_CAPS, dispatchResultText, finalTextOf, formatDelta, isPass, memberPrompt, parseModelRoute,
  resolveMentions, roomLinesOf, roundEndText, validateDispatch, type EventLike, type MessageLike, type RosterBot,
} from "../src/room-rules.ts";

const roster: RosterBot[] = [
  { id: "buffett", name: "巴菲特型" },
  { id: "speculator", name: "投机型" },
  { id: "macro-view", name: "Macro View" }, // a multi-word display name: reached by id only
];

test("ROOM_CAPS is the spec's block, verbatim", () => {
  assert.deepEqual(ROOM_CAPS, {
    maxRounds: 3, maxContinuations: 2, maxBotMessages: 10, maxMembers: 6,
    turnTimeoutMs: 180_000, turnHardCapMs: 1_200_000,
  });
});

test("resolveMentions: by id always, by display name only when it is one token; anchored; unknown and e-mail pass through", () => {
  assert.deepEqual(resolveMentions("@buffett what about leverage?", roster), ["buffett"]);
  assert.deepEqual(resolveMentions("我想听 @投机型 的看法", roster), ["speculator"]);
  assert.deepEqual(resolveMentions("@投机型，你呢？", roster), ["speculator"], "trailing punctuation is not part of the token");
  assert.deepEqual(resolveMentions("@Macro View please", roster), [], "a multi-word name is not matched by its first word");
  assert.deepEqual(resolveMentions("@macro-view please", roster), ["macro-view"]);
  assert.deepEqual(resolveMentions("mail me at pan@buffett.example", roster), [], "an e-mail address is not a mention");
  assert.deepEqual(resolveMentions("@nobody and @buffett and @speculator and @buffett", roster), ["buffett", "speculator"], "unknown dropped, duplicates folded, order kept");
  assert.deepEqual(resolveMentions("no mentions here", roster), []);
  assert.deepEqual(resolveMentions("@buffett", []), [], "an empty roster resolves nothing");
});

test("isPass: the Hermes regex, whole-text only", () => {
  for (const text of ["(pass)", "pass", "(pass).", " ( pass ) ", "PASS"]) assert.equal(isPass(text), true, text);
  for (const text of ["I pass on this one", "pass, but note X", ""]) assert.equal(isPass(text), false, text);
});

const msg = (turn: number, text: string, seq: number): EventLike => ({
  type: "assistant/message", seq, data: { turn, step: 1, message: { id: `m${seq}`, role: "assistant", content: [{ type: "text", text }], source: { kind: "model", provider: "p", model: "m" } } },
});
const tool = (turn: number, seq: number): EventLike => ({ type: "tool/result", seq, data: { turn, step: 1, message: { id: `t${seq}`, role: "user", content: [{ type: "tool-result", toolCallId: "c1", content: [] }], source: { kind: "tool", callId: "c1" } } } });

test("finalTextOf: a text-only turn is its text; a tool-using turn is the text after the last tool result; a tool-only turn is empty", () => {
  assert.equal(finalTextOf([msg(1, "hello", 3)], 1), "hello");
  assert.equal(finalTextOf([msg(1, "let me check", 3), tool(1, 4), msg(1, "checked: yes", 5)], 1), "checked: yes");
  assert.equal(finalTextOf([msg(1, "a", 3), tool(1, 4), msg(1, "b", 5), msg(1, "c", 6)], 1), "b\n\nc");
  assert.equal(finalTextOf([msg(1, "running tool", 3), tool(1, 4)], 1), "");
  assert.equal(finalTextOf([msg(1, "other turn", 3), msg(2, "mine", 4)], 2), "mine", "only this turn's events count");
});

test("validateDispatch: empty to, duplicates, roster miss naming the roster, unknown mode, empty brief/reason", () => {
  const ok = validateDispatch({ to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  assert.deepEqual(ok, { ok: true, value: { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" } });
  const miss = validateDispatch({ to: ["ghost"], mode: "parallel", brief: "q", reason: "r" }, roster);
  assert.equal(miss.ok, false);
  assert.match((miss as { message: string }).message, /ghost/);
  assert.match((miss as { message: string }).message, /buffett, speculator, macro-view/, "the refusal names the roster - that is how the model learns it");
  assert.equal(validateDispatch({ to: [], mode: "parallel", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett", "buffett"], mode: "serial", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "round-robin", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "serial", brief: " ", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "serial", brief: "q" }, roster).ok, false);
  assert.equal(validateDispatch(null, roster).ok, false);
});

test("dispatchResultText names who was called, the mode, and who was NOT called (Rule 5), and tells the model to end its turn", () => {
  const args = { to: ["buffett", "speculator"], mode: "parallel" as const, brief: "q", reason: "two views first" };
  const text = dispatchResultText(args, roster, 1, 2, []);
  assert.match(text, /巴菲特型, 投机型 \(parallel\)/);
  assert.match(text, /Not called: Macro View\./);
  assert.match(text, /round 1/);
  assert.match(text, /2 rounds? left/i);
  assert.match(text, /end your turn/i);
  const all = dispatchResultText({ ...args, to: roster.map((b) => b.id) }, roster, 3, 0, ["投机型: model stub/x is not served; using the default route."]);
  assert.match(all, /Not called: none\./);
  assert.match(all, /stub\/x is not served/);
  assert.match(all, /0 rounds left/);
});

const user = (id: string, text: string, seq: number, source: Record<string, unknown> = { kind: "user" }): EventLike => ({
  type: "user/message", seq, data: { id, role: "user", content: [{ type: "text", text }], source },
});
const answer = (id: string, bot: string, name: string, text: string, seq: number): EventLike =>
  user(id, text, seq, { kind: "room", form: "answer", bot, name, sessionId: "s-b", turn: 1, round: 1 });

test("roomLinesOf: operator prompts, Kairos replies and member answers, in order; room events, plugin context and tool results are not lines", () => {
  const events: EventLike[] = [
    user("u1", "开个会", 1),
    user("ctx", "Instructions from AGENTS.md", 2, { kind: "plugin", plugin: "agent-instructions", form: "instructions" }),
    msg(1, "让大家先说", 3),
    tool(1, 4),
    answer("a1", "buffett", "巴菲特型", "买", 5),
    user("re", "Round 1 ended (settled)", 6, { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [] }),
    user("u2", "@speculator 你呢", 7, { kind: "user", mention: ["speculator"] }),
  ];
  const pending: MessageLike[] = [
    { id: "a2", role: "user", content: [{ type: "text", text: "卖" }], source: { kind: "room", form: "answer", bot: "speculator", name: "投机型", sessionId: "s-s", turn: 1, round: 1 } },
    { id: "a1", role: "user", content: [{ type: "text", text: "dup" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "s-b", turn: 1, round: 1 } },
  ];
  const lines = roomLinesOf(events, pending, roster);
  assert.deepEqual(lines.map((l) => l.id), ["u1", "m3", "a1", "u2", "a2"], "pending lines follow the log; an id already in the log is not repeated");
  assert.deepEqual(lines[0].speaker, { kind: "operator" });
  assert.deepEqual(lines[1].speaker, { kind: "kairos" });
  assert.deepEqual(lines[2].speaker, { kind: "bot", bot: "buffett", name: "巴菲特型" });
  assert.deepEqual(lines[4].speaker, { kind: "bot", bot: "speculator", name: "投机型" });
});

test("formatDelta attributes every line and marks the reader's own", () => {
  const lines = roomLinesOf([user("u1", "开个会", 1), msg(1, "先各说各的", 3), answer("a1", "buffett", "巴菲特型", "买\n理由：便宜", 5), answer("a2", "speculator", "投机型", "卖", 6)], [], roster);
  assert.equal(formatDelta(lines, "buffett"), "操作员: 开个会\nKairos: 先各说各的\n巴菲特型 (you): 买\n  理由：便宜\n投机型: 卖");
  assert.equal(formatDelta([], "buffett"), "(nothing new)");
});

test("memberPrompt carries the delta, the brief when given, the trigger, and the four standing rules", () => {
  const text = memberPrompt({ roomName: "storage-chain", roster, self: "buffett", delta: "操作员: 开个会", brief: "state your view on SanDisk", trigger: "dispatch" });
  assert.match(text, /storage-chain/);
  assert.match(text, /操作员: 开个会/);
  assert.match(text, /state your view on SanDisk/);
  assert.match(text, /exactly \(pass\)/);
  assert.match(text, /verbatim/);
  assert.match(text, /this room only/);
  assert.match(text, /@<bot>/);
  assert.match(text, /投机型/, "the other voices are named so a peer mention can be spelled");
  const mention = memberPrompt({ roomName: "x", roster, self: "buffett", delta: "(nothing new)", trigger: "mention" });
  assert.match(mention, /operator addressed you directly/i);
  assert.doesNotMatch(mention, /Kairos asks this batch/);
  const cont = memberPrompt({ roomName: "x", roster, self: "buffett", delta: "(nothing new)", trigger: "continuation" });
  assert.match(cont, /continuation/i);
});

test("roundEndText: outcome word, each state group, rounds left; superseded and capped say why", () => {
  const turns = [
    { bot: "buffett", name: "巴菲特型", sessionId: "s1", state: "answered" as const, turn: 2 },
    { bot: "speculator", name: "投机型", sessionId: "s2", state: "passed" as const, turn: 1 },
    { bot: "macro-view", name: "Macro View", sessionId: "s3", state: "failed" as const, reason: "preset missing" },
  ];
  const settled = roundEndText(1, "settled", turns, 2);
  assert.match(settled, /^Round 1 ended \(settled\)/);
  assert.match(settled, /Answered: 巴菲特型\./);
  assert.match(settled, /Passed: 投机型\./);
  assert.match(settled, /Failed: Macro View \(preset missing\)\./);
  assert.match(settled, /Timed out: none\./);
  assert.match(settled, /2 rounds left/);
  assert.match(settled, /name the disagreements/i);
  assert.match(roundEndText(3, "capped", turns, 0), /capped/);
  assert.match(roundEndText(3, "capped", turns, 0), /0 rounds left/);
  assert.match(roundEndText(1, "superseded", turns, 2), /superseded by a new operator message/i);
});

test("parseModelRoute splits provider/model once and refuses anything else", () => {
  assert.deepEqual(parseModelRoute("deepseek-official/deepseek-v4-flash"), { provider: "deepseek-official", model: "deepseek-v4-flash" });
  assert.deepEqual(parseModelRoute("stub/echo:v2"), { provider: "stub", model: "echo:v2" });
  assert.equal(parseModelRoute("deepseek-v4-flash"), undefined);
  assert.equal(parseModelRoute("a/b/c"), undefined);
  assert.equal(parseModelRoute(""), undefined);
});
