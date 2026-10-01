// Validate tests/fixtures/events.jsonl - the frames mapper.test.ts and
// api.test.ts feed the browser client - against the INSTALLED dsh's own
// acceptance code, so the fixture cannot drift from the wire it stands for.
// Re-run on every dsh pin bump: `npm run check:fixture` (from face/).
//
// Upstream code used, never a copy of it:
// - assertSessionWireEvent (NEW packages/api/session-controller/src/client/
//   session-wire-event.ts): the check upstream's client journal applies to
//   every follow/page record. The package exports it from no public entry
//   (`./client` bundles it privately), so it is loaded from the module the
//   package ships beside its types, lib/types/client/session-wire-event.js -
//   the same layout the gateway exposes publicly as `./stream-protocol`. If a
//   pin moves it, this script fails loudly at load, never passes silently.
// - parseRemoteStreamServerMessage, isRemoteEventId, isRemoteEventAgentId
//   (@deepseek-ai/dsh-api-gateway/stream-protocol): the mux frame parser and
//   the `$events` id predicates.
// Plus the one rule the upstream follow transport adds to a snapshot: an
// opted-in follow's snapshot must carry its assistantStream baseline
// (session-controller src/client/transport.ts, `SessionEventStream.follow`).
//
// Frames with no upstream acceptance function (assistant-stream, projection)
// are counted and named, not silently passed.
// Usage: node scripts/validate-fixture.mjs [path/to/events.jsonl]
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const FACE = join(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURE = process.argv[2] ?? join(FACE, "tests", "fixtures", "events.jsonl");
const req = createRequire(join(FACE, "package.json"));
const load = async (spec) => import(pathToFileURL(req.resolve(spec)).href);

const controllerDir = dirname(req.resolve("@deepseek-ai/dsh-api-session-controller/package.json"));
const { version: controllerVersion } = JSON.parse(readFileSync(join(controllerDir, "package.json"), "utf8"));
const { assertSessionWireEvent } = await import(
  pathToFileURL(join(controllerDir, "lib", "types", "client", "session-wire-event.js")).href
);
if (typeof assertSessionWireEvent !== "function") {
  throw new Error(`@deepseek-ai/dsh-api-session-controller ${controllerVersion} no longer ships assertSessionWireEvent where this script looks`);
}
const { parseRemoteStreamServerMessage, isRemoteEventId, isRemoteEventAgentId } =
  await load("@deepseek-ai/dsh-api-gateway/stream-protocol");

/** One fixture line, checked by the upstream function that owns its frame type. */
function check(frame) {
  switch (frame.type) {
    case "session/event":
      assertSessionWireEvent(frame.event);
      return "validated";
    case "snapshot":
      for (const record of frame.records) assertSessionWireEvent(record.event);
      if (frame.assistantStream === undefined) throw new Error("snapshot without its opted-in assistantStream baseline");
      return "validated";
    case "error":
      parseRemoteStreamServerMessage(JSON.stringify(frame));
      return "validated";
    case "waterfall":
      if (!isRemoteEventId(frame.eventId) || !isRemoteEventAgentId(frame.agentId)
        || typeof frame.event !== "string" || typeof frame.request !== "object" || frame.request === null) {
        throw new Error("waterfall frame with an invalid eventId, agentId, event or request");
      }
      return "validated";
    case "cancel":
      if (!isRemoteEventId(frame.eventId)) throw new Error("cancel frame with an invalid eventId");
      return "validated";
    default:
      return "unchecked";
  }
}

const lines = readFileSync(FIXTURE, "utf8").split("\n").filter((line) => line.trim() !== "");
let validated = 0;
const unchecked = new Map();
const rejected = [];
lines.forEach((line, i) => {
  let frame;
  try {
    frame = JSON.parse(line);
    const verdict = check(frame);
    if (verdict === "validated") validated += 1;
    else unchecked.set(frame.type, (unchecked.get(frame.type) ?? 0) + 1);
  } catch (err) {
    rejected.push(`line ${i + 1} (${frame?.type ?? "not JSON"}): ${err instanceof Error ? err.message : String(err)}`);
  }
});
for (const line of rejected) console.log(`REJECTED ${line}`);
const skipped = [...unchecked].map(([type, n]) => `${n} ${type}`).join(", ");
console.log(
  `${FIXTURE}: ${lines.length} lines; ${validated} validated with dsh ${controllerVersion}'s acceptance code, ` +
    `${rejected.length} rejected${skipped === "" ? "" : `; no upstream validator for: ${skipped}`}`,
);
process.exitCode = rejected.length === 0 && validated > 0 ? 0 : 1;
