// face/plugins/bot.js
/**
 * `kairos-bot` — the one plugin every bot composition mounts.
 *
 * A bot is a dsh agent preset (`bots/<id>/agent.cordis.yml`, spec §2). Its
 * composition names this file by a RELATIVE path (`../../face/plugins/bot.js`),
 * which the preset mount resolves from the preset's own directory
 * (dsh-agent-presets README, "A relative path still resolves from the preset's
 * own directory"). From `bots/` no `node_modules` is reachable, so this file
 * imports nothing: the persona goes in through `ctx.systemPrompt.section`, the
 * mask through `ctx.tools.restrict`, both registered into the CALLING context's
 * scope — the preset's standing layer — so they cover every agent joined to the
 * preset and nothing else. dsh-subagent composes a child the same way.
 *
 * WHAT THIS IS NOT. The mask is visibility, not authority (dsh-tools README:
 * "live visibility composition, not an authority boundary"). What a bot may
 * WRITE is its session's sandbox mode; what it may ORDER is Gate 2. Spec D12.
 *
 * `allow`, not `deny`: dsh admits later-registered globals through a deny
 * mask and excludes them through an allow mask. The tools a voice must never
 * see — `agent_<bin>` on connect, `mcp__…__place_order` when the MCP server
 * comes up, `dispatch` in plan 2 — are all registered AFTER the mount.
 */
export const name = "kairos-bot";
export const inject = ["systemPrompt", "tools"];

/** The dsh system prompt is a strict `{{…}}` template with no escape; a bot's
 *  persona interpolates nothing, so any `{{` would fail every render. */
export function validateBotConfig(config) {
  if (config === null || typeof config !== "object") return "config must be an object";
  const { persona, allow } = config;
  if (typeof persona !== "string" || persona.trim() === "") return "persona must be a non-empty string";
  if (persona.includes("{{")) return "persona must not contain '{{' (the system prompt is a strict template with no escape)";
  if (!Array.isArray(allow) || allow.length === 0 || allow.some((n) => typeof n !== "string" || n === "")) {
    return "allow must be a non-empty array of tool names";
  }
  return undefined;
}

/** Resolve the allow list against the tools the tree actually has: exact names
 *  pass when present; `mcp__*__<raw>` expands to every MCP tool with that raw
 *  name whatever the operator named the server; everything else is reported,
 *  because `tools.restrict` rejects a name it does not know. */
export function expandAllow(allow, known) {
  const out = [];
  const missing = [];
  for (const entry of allow) {
    const star = /^mcp__\*__(.+)$/.exec(entry);
    if (star !== null) {
      const raw = star[1];
      const hits = [...known].filter((n) => /^mcp__[^_].*__/.test(n) && n.endsWith(`__${raw}`)).sort();
      if (hits.length === 0) missing.push(entry);
      else out.push(...hits);
      continue;
    }
    if (known.has(entry)) out.push(entry);
    else missing.push(entry);
  }
  return { allow: out, missing };
}

export function apply(ctx, config) {
  const problem = validateBotConfig(config);
  if (problem !== undefined) throw new Error(`kairos-bot: ${problem}`);
  const known = new Set(ctx.tools.schemas().map((schema) => schema.name));
  const { allow, missing } = expandAllow(config.allow, known);
  if (missing.length > 0) ctx.logger?.warn?.(`kairos-bot: allow names not in this tree, ignored: ${missing.join(", ")}`);
  if (allow.length === 0) throw new Error("kairos-bot: none of the allowed tools exist in this tree; the bot would have no hands at all");
  ctx.effect(() => ctx.systemPrompt.section({ name: "deployment:persona", order: 0, text: config.persona }));
  ctx.effect(() => ctx.tools.restrict({ allow }));
}
