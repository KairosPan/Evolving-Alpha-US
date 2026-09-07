/**
 * Propose a bot id from a display name - the browser twin of `proposeBotId`
 * in face/src/bots.ts (kept byte-identical in logic; botId.test.ts pins that
 * a non-empty proposal is always an id the server accepts).
 *
 * WHAT IT IS NOT. It is not a fence. `createBot` (src/bots.ts) keeps the only
 * gate: dsh's preset grammar `[a-z0-9][a-z0-9-]*`, minus `kairos` and
 * `_template`. This runs before the POST so the operator sees the id a name
 * becomes and can type another; a name with no ASCII letters proposes
 * nothing, and the form then requires the id field. Fail-closed.
 */
export function proposeBotId(displayName) {
  return displayName
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}
