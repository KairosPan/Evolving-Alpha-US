// face/tests/room-client.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { avatarGlyph, foldMembers, gateSpeaker, isMemberSession, isMentionText, roundEndLine, stripChips } from "../client/room.js";
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
