// face/tests/room-client.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { avatarGlyph, foldMembers, gateSpeaker, isMemberSession, isMentionText, normalizeRoomDiscussion, normalizeRoomView, roomAnswerDisplay, roundEndLine, stripChips } from "../client/room.js";
import { bucketFor } from "../client/grouping.js";

test("avatarGlyph is deterministic per id and differs between the two template bots", () => {
  assert.equal(avatarGlyph("buffett"), avatarGlyph("buffett"));
  assert.equal(typeof avatarGlyph("x"), "string");
  assert.equal(avatarGlyph("buffett").length > 0, true);
  const set = new Set(["buffett", "speculator", "macro-view", "alpha", "beta", "gamma"].map(avatarGlyph));
  assert.ok(set.size >= 4, "six ids spread over at least four glyphs");
});

test("isMentionText is the composer anchor: start or whitespace, then @ and a token; an e-mail is not one", () => {
  assert.equal(isMentionText("@buffett hi"), true);
  assert.equal(isMentionText("hi @投机型"), true);
  assert.equal(isMentionText("mail pan@example.com"), false);
  assert.equal(isMentionText("no mention"), false);
  assert.equal(isMentionText("@ alone"), false);
});

const rows = [
  { sessionId: "room", agentPreset: "kairos", cwd: "/c" },
  { sessionId: "m1", parentSessionId: "room", agentPreset: "buffett", cwd: "/c" },
  { sessionId: "m2", parentSessionId: "room", agentPreset: "speculator", cwd: "/c" },
  { sessionId: "fork", parentSessionId: "room", agentPreset: "kairos", cwd: "/c" },
  { sessionId: "child", parentSessionId: "room", agentPreset: "buffett", origin: "subagent", cwd: "/c" },
  { sessionId: "orphan", parentSessionId: "gone", agentPreset: "buffett", cwd: "/c" },
  { sessionId: "home", agentPreset: "buffett", cwd: "/bots/buffett/journal" },
  { sessionId: "nested", parentSessionId: "m1", agentPreset: "buffett", cwd: "/c" },
];

test("foldMembers: a bot session parented by a host session is a member; forks, subagent children, orphans, homes and members-of-members are not", () => {
  const { rooms, members } = foldMembers(rows);
  assert.deepEqual([...rooms.keys()], ["room"]);
  assert.deepEqual(rooms.get("room")!.map((r) => r.sessionId), ["m1", "m2"]);
  assert.deepEqual([...members].sort(), ["m1", "m2"]);
});

test("isMemberSession: a member's own transcript is not a room - the delta's projection says so, and the header fold says so before it lands", () => {
  const { members } = foldMembers(rows);
  // the member's own projection, the shape room-projection.ts writes on a delta
  assert.equal(isMemberSession({ kind: "member", room: "room", bot: "buffett" }, new Set(), "m1"), true);
  // no projection yet (a cold open, before the delta is replayed): the fold answers
  assert.equal(isMemberSession(undefined, members, "m1"), true);
  // the room itself, and a session in no room, keep their strip
  assert.equal(isMemberSession({ kind: "room", organizing: true, members: {} }, members, "room"), false);
  assert.equal(isMemberSession(undefined, members, "solo"), false);
  assert.equal(isMemberSession(undefined, members, null), false);
});

test("bucketFor: a member never files under its bot's home bucket, whatever precedence says otherwise", () => {
  const bot = { id: "buffett", label: "巴菲特型" };
  assert.equal(bucketFor({ workspaceId: "ws", title: "c" }, false, bot, false).key, "bot:buffett");
  assert.equal(bucketFor({ workspaceId: "ws", title: "c" }, false, bot, true).key, "ws");
  assert.equal(bucketFor(null, false, bot, true).key, "__ungrouped");
  assert.equal(bucketFor(null, true, bot, true).key, "__archived");
});

const roster = [{ id: "buffett", name: "巴菲特型" }, { id: "speculator", name: "投机型" }, { id: "cracked", name: "cracked", broken: "not a list" }];

test("stripChips: Kairos first; roster members read the projection's coarse state, the pulses' fine state while called, a pending gate over both; a rostered-but-unmounted bot is shown broken; a member no longer rostered is left", () => {
  const projection = { kind: "room", organizing: true, members: { buffett: { sessionId: "m1", state: "called" }, speculator: { sessionId: "m2", state: "passed" }, ghost: { sessionId: "m3", state: "answered", name: "Ghost" } } };
  const chips = stripChips({ roster, projection, members: { ghost: { sessionId: "m3", name: "Ghost" } }, gates: new Set(["m2"]), fine: new Map([["m1", "writing"]]), running: false, kairosName: "Kairos" });
  assert.deepEqual(chips.map((c) => `${c.id}:${c.state}`), ["kairos:organizing", "buffett:writing", "speculator:waiting for you", "cracked:idle", "ghost:left"]);
  assert.equal(chips[0].kairos, true);
  assert.equal(chips[3].broken, "not a list");
  assert.equal(chips[1].sessionId, "m1");
});

test("stripChips: before any dispatch the strip is the roster at idle, and Kairos follows the running flag", () => {
  const chips = stripChips({ roster, projection: { kind: "none" }, members: {}, gates: new Set(), fine: new Map(), running: true, kairosName: "Kairos" });
  assert.deepEqual(chips.map((c) => c.state), ["organizing", "idle", "idle", "idle"]);
  assert.deepEqual(stripChips({ roster: [], projection: undefined, members: {}, gates: new Set(), fine: new Map(), running: false, kairosName: "Kairos" }).map((c) => c.id), ["kairos"]);
});

test("roundEndLine reads the outcome and each state group; capped and superseded say so", () => {
  const turns = [{ bot: "b", name: "巴菲特型", state: "answered" }, { bot: "s", name: "投机型", state: "passed" }, { bot: "m", name: "Macro", state: "timed-out" }];
  assert.equal(roundEndLine({ round: 1, outcome: "settled", turns }), "round 1 · settled · answered: 巴菲特型 · passed: 投机型 · timed out: Macro");
  assert.match(roundEndLine({ round: 2, outcome: "capped", turns: [] }), /^round 2 · capped/);
  assert.match(roundEndLine({ round: 1, outcome: "superseded", turns: [] }), /superseded/);
});

test("gateSpeaker names the member's bot for a member's gate, else the fallback", () => {
  const memberRows = [{ sessionId: "m1", agentPreset: "buffett" }];
  const bots = [{ id: "buffett", name: "巴菲特型" }];
  assert.equal(gateSpeaker("m1", memberRows, bots, "Kairos"), "巴菲特型");
  assert.equal(gateSpeaker("m9", memberRows, bots, "Kairos"), "Kairos");
  assert.equal(gateSpeaker("m1", memberRows, [], "Kairos"), "buffett", "no roster name: the id, never the host");
});

const account = {
  position: "需要更多证据。",
  evidence: ["公司报告中的收入数字尚未交叉核对。"],
  uncertainties: ["统计口径是否一致？"],
  changeConditions: ["独立来源确认同一口径。"],
  disagreements: [{ with: "macro", point: "增长率不能直接证明需求持续。" }],
};

test("room view validation accepts empty claims but rejects malformed or partially missing accounts", () => {
  assert.deepEqual(normalizeRoomView(account), account);
  const empty = { position: "暂不判断", evidence: [], uncertainties: [], changeConditions: [], disagreements: [] };
  assert.deepEqual(normalizeRoomView(empty), empty);
  for (const invalid of [null, [], "position", { ...account, position: " " }, { ...account, evidence: "fact" },
    { ...account, uncertainties: undefined }, { ...account, changeConditions: [3] },
    { ...account, disagreements: [{ with: "macro" }] }, { ...account, disagreements: [null] }]) {
    assert.equal(normalizeRoomView(invalid), null);
  }
});

test("answer display uses authoritative metadata and preserves raw prose on missing or malformed accounts", () => {
  const raw = "原始回答\n```room-view\n{...}\n```";
  assert.deepEqual(roomAnswerDisplay({ text: raw, roomView: account, displayText: "原始回答" }), { text: "原始回答", view: account, issue: null });
  assert.equal(roomAnswerDisplay({ text: raw, roomView: account, displayText: "  " }).text, account.position);
  assert.equal(roomAnswerDisplay({ text: raw, displayText: "不可信的替代正文" }).text, raw);
  const malformed = roomAnswerDisplay({ text: raw, roomView: { position: "不完整" }, displayText: "替代正文", viewIssue: "Internal parser detail" });
  assert.equal(malformed.text, raw);
  assert.equal(malformed.view, null);
  assert.equal(malformed.issue, "观点字段未完整记录，已保留原文。");
  assert.deepEqual(roomAnswerDisplay({ text: "旧回答，无结构化字段" }), { text: "旧回答，无结构化字段", view: null, issue: null });
});

test("discussion validates contributions independently and retains unstructured speakers for reviewing original text", () => {
  const brief = { question: "收入能持续吗？", context: "只讨论已披露材料", evidence: ["季度报告"], falsification: "口径不一致", output: "给出下一项核查" };
  const discussion = normalizeRoomDiscussion({
    brief,
    views: [
      { bot: "value", name: "Value", sessionId: "v1", turn: 2, view: account },
      { bot: "broken", name: "Broken", sessionId: "b1", view: { position: "缺失依据" } },
      { bot: "missing-session", view: account },
      null,
    ],
    unstructuredBots: ["legacy", "legacy", 42],
  });
  assert.ok(discussion);
  assert.deepEqual(discussion.brief, brief);
  assert.equal(discussion.views.length, 1);
  assert.equal(discussion.views[0].turn, 2);
  assert.deepEqual(discussion.unstructuredBots, ["legacy", "broken", "missing-session"]);
  assert.deepEqual(discussion.disagreements, [{ bot: "value", name: "Value", with: "macro", point: account.disagreements[0].point }]);
});

test("no declared disagreement never becomes inferred consensus, even with matching positions", () => {
  const view = { ...account, disagreements: [] };
  const discussion = normalizeRoomDiscussion({
    brief: "同样的判断是否依据相同？",
    views: [{ bot: "a", name: "A", sessionId: "a1", view }, { bot: "b", name: "B", sessionId: "b1", view }],
    unstructuredBots: [],
  });
  assert.ok(discussion);
  assert.deepEqual(discussion.disagreements, []);
  assert.equal(discussion.disagreementNotice, "未记录明确分歧；这不代表已经达成共识。");
});

test("old or malformed round metadata degrades to the original state line without inventing a brief", () => {
  for (const payload of [undefined, null, [], "agreement", { views: [] }, { views: {}, unstructuredBots: [] }]) assert.equal(normalizeRoomDiscussion(payload), null);
  const malformedBrief = normalizeRoomDiscussion({ brief: { question: 5, context: "x" }, views: [], unstructuredBots: [] });
  assert.equal(malformedBrief?.brief, undefined);
});

test("structured account strings remain literal data, never parsed as markup or inferred into claims", () => {
  const literal = { ...account, position: '<img src=x onerror="alert(1)">', evidence: ["**verified** [source](javascript:alert(1))"] };
  const normalized = normalizeRoomView(literal);
  assert.deepEqual(normalized, literal);
  normalized!.evidence.push("local display change");
  assert.equal(literal.evidence.length, 1, "normalization does not mutate the original event");
});
