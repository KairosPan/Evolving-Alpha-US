/** Pure speaker-label decision: whose name the transcript writes over a turn.
 *
 * No DOM, no network, no state — one session summary's `agentPreset` plus the
 * roster in, one display name out. Split out of chat.js for the same reason
 * grouping.js and channelName.js are: the decision has to be drillable without
 * a browser.
 *
 * THE BUG THIS CLOSES (R12). A bot's home session answered in the bot's
 * persona and the sidebar filed it under the bot's name, but the four surfaces
 * in `chat.js` that NAME the speaker each wrote a literal `Kairos`: the `who`
 * element over an assistant bubble, the ask card's `… asks` head, the composer
 * placeholder, and the status pulse. Four surfaces, one name, as many agents
 * as the operator had bots.
 *
 * WHAT IT IS NOT. It is not attribution. It reads the SESSION's own header,
 * the same `agentPreset` field `botOf` (chat.js) buckets the sidebar by, so
 * the label and the bucket can never disagree — but it says nothing about
 * which agent produced any individual frame. Per-MESSAGE attribution, several
 * voices in one room log, is plan 3 and does not exist yet.
 *
 * THE FALLBACK DIRECTION IS THE POINT. An unknown preset (a deleted bot, a
 * roster fetch that failed) degrades to the ID, never to `Kairos`. Labelling a
 * bot's words as the host's is the failure worth avoiding; an unlovely
 * `buffett-type` over a bubble is not. Fail-away-from-the-host.
 * @module
 */

/** The host agent's display name — the label for every session no bot owns. */
export const HOST_NAME = "Kairos";

/**
 * The voice a session speaks with: a bot's display name when `agentPreset`
 * names one (never the default `kairos`, and never a blank string — a header
 * field present but empty is no preset at all), the bot's id when the roster
 * has no name for it, else Kairos.
 * @param {{agentPreset?: unknown}|null|undefined} summary - the session
 *   summary from `session.list`/`session.create`, or `null` for no session.
 * @param {{id: string, name?: unknown}[]} bots - the `/data/bots.json` rows.
 * @returns {string} the display name to write over the session's turns.
 */
export function speakerFor(summary, bots) {
  const id = summary?.agentPreset;
  if (typeof id !== "string" || id.trim() === "" || id === "kairos") return HOST_NAME;
  const bot = (Array.isArray(bots) ? bots : []).find((b) => b?.id === id);
  const name = typeof bot?.name === "string" ? bot.name.trim() : "";
  return name === "" ? id : name;
}
