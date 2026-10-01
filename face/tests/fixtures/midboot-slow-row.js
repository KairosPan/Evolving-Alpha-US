// face/tests/fixtures/midboot-slow-row.js
/**
 * A deliberately SLOW plugin row, for tests/order-gate-midboot-smoke.test.ts
 * only. It stands in for any row that keeps dsh's `boot()` pending while the
 * rest of the tree already serves - an MCP server still importing (AKShare's
 * FastMCP server is spawned twice per connect, src/akshare.ts), a bot, a
 * plugin doing I/O in `apply`. `boot()` resolves only once the Loader has
 * settled every row (NEW packages/boot/app-boot/src/index.ts:1004-1012), so
 * while this row's `apply` is pending, `bootFace` cannot return - which is the
 * window REVIEW-adversarial finding 1 proved an order could dispatch in.
 *
 * It holds that window open until the TEST releases it (the drill's
 * `released` promise) rather than for a fixed time, so the smoke's mid-boot
 * steps can never lose a race with a timer on a slow machine; `holdCapMs`
 * bounds it anyway, so a test that dies without releasing cannot hang the
 * process. The drill object is the test's, on `globalThis` under a registered
 * symbol, because the row is loaded by the Loader and the test cannot hand it
 * anything else. Imports nothing, so a `file:` URL row is all it needs (the
 * same shape as face/plugins/bot.js).
 */
export const name = "midboot-slow-row";

/** The drill's key; tests/order-gate-midboot-smoke.test.ts uses the same one. */
const DRILL = Symbol.for("kairos-face.order-gate-midboot-drill");

/**
 * Hold this row's activation until the test releases it (or the cap passes).
 * @throws when no drill is installed - this row belongs to one test only.
 */
export async function apply() {
  const drill = globalThis[DRILL];
  if (drill === undefined) {
    throw new Error(`${name}: no drill installed - this fixture runs only under tests/order-gate-midboot-smoke.test.ts`);
  }
  drill.slowStarted = Date.now();
  let timer;
  await Promise.race([
    drill.released,
    new Promise((resolve) => { timer = setTimeout(resolve, drill.holdCapMs); }),
  ]);
  clearTimeout(timer);
  drill.slowDone = Date.now();
}
