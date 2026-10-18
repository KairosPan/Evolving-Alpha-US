// face/plugins/gravit.js
/**
 * `gravit` - the face-owned plugin Gravit's own preset mounts, and the first
 * row of `bots/gravit/agent.cordis.yml`. It holds what only Gravit is told; at
 * plan 1 of the 2026-10-15 redesign that is one section, the date. Plans 2 and
 * 3 add the `roles` and `cycle` config keys: the validator below already
 * checks them, nothing reads them yet, and the shipped row is `config: {}`.
 *
 * WHY A DATE. The 2026-10-10 prompt trace found no date anywhere in the
 * assembled prompt, so Gravit could not tell a fresh bar from a stale one or
 * resolve "yesterday" and "this week". `deployment:today` closes that.
 *
 * The text is a FUNCTION, not a string. dsh resolves a section's text at every
 * assembly - `typeof section.text === "function" ? section.text(context) :
 * section.text` (dsh-system-prompt README "Sections carry static or
 * context-resolved text"; `assemble` in the installed lib) - so a session that
 * runs past midnight is told the new day on its next request, and the date is
 * never frozen at the mount. The zone is the process's own, named in the
 * sentence so "today" is never ambiguous.
 *
 * This file imports nothing ON PURPOSE, like plugins/bot.js: the composition
 * names it by a relative path, the face rebases that to an absolute `file:` URL
 * against `bots/gravit/` while it builds the declaration (src/bot-presets.ts
 * `definitionFor`), and a file URL is all the loader needs.
 *
 * SCOPED, NOT GLOBAL. `ctx.systemPrompt.section` registers into the CALLING
 * context's scope, the preset revision's standing layer, so the section
 * reaches every session joined to the `gravit` preset (and to its `kairos`
 * alias, which declares the same rows) and nobody else: a bot is its own
 * preset and never sees it. tests/bots-smoke.test.ts pins both halves on a real
 * boot.
 *
 * It masks nothing. `inject` names `systemPrompt` and never `tools`, so
 * Gravit's roster stays exactly the host's flat roster (bots-smoke S3).
 *
 * `interpolate: false` because the text is a sentence, not a template: the dsh
 * system prompt is a strict `{{...}}` template with no escape. The order is the
 * persona slot's + 1, so the date follows identity - harness identity, the
 * persona prefix, then the date - and precedes every centrally ordered policy
 * and tool section.
 */
export const name = "gravit";
export const inject = ["systemPrompt"];

/** The one section this plugin registers. Its own name: it shadows nothing, and
 *  nothing shadows it. */
export const TODAY_SECTION = "deployment:today";

/** A role's tool name: the `role_` prefix keeps the roster's role tools apart
 *  from every host and MCP tool. */
const ROLE_TOOL = /^role_[a-z0-9_]+$/;

/** What would fail at mount or render, as a reason; `undefined` when the config
 *  is valid. `{}` is the shipped config. `cycle` and `roles` are the keys plans
 *  3 and 2 fill; they are checked here when present so a malformed value
 *  refuses the mount, loudly, instead of loading a silently dead config. */
export function validateGravitConfig(config) {
  if (config === null || typeof config !== "object" || Array.isArray(config)) return "config must be an object";
  const { cycle, roles } = config;
  if (cycle !== undefined && (typeof cycle !== "string" || cycle.trim() === "")) return "cycle must be a non-empty string";
  if (roles !== undefined) {
    if (!Array.isArray(roles)) return "roles must be an array of { tool, summary }";
    for (const [index, role] of roles.entries()) {
      if (role === null || typeof role !== "object" || Array.isArray(role)) return `roles[${index}] must be an object with tool and summary`;
      if (typeof role.tool !== "string" || !ROLE_TOOL.test(role.tool)) return `roles[${index}].tool must match ${ROLE_TOOL}`;
      if (typeof role.summary !== "string" || role.summary.trim() === "") return `roles[${index}].summary must be a non-empty string`;
    }
  }
  return undefined;
}

/** `Today is YYYY-MM-DD, Weekday (Zone).` - the LOCAL date in `timeZone`, not
 *  UTC's: at 03:00Z on the 18th it is still the 17th in New York. The two
 *  formatters pin their own locales, so the ISO date order and the English
 *  weekday hold whatever locale the process runs in. */
export function todayText(now, timeZone) {
  const date = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const weekday = new Intl.DateTimeFormat("en-US", { timeZone, weekday: "long" }).format(now);
  return `Today is ${date}, ${weekday} (${timeZone}).`;
}

export function apply(ctx, config) {
  const problem = validateGravitConfig(config);
  if (problem !== undefined) throw new Error(`gravit: ${problem}`);
  /* The disposer `section` returns is what unregisters it, so unloading the
   * preset revision takes the date out of every prompt with it. */
  ctx.effect(() => ctx.systemPrompt.section({
    name: TODAY_SECTION,
    order: ctx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1,
    interpolate: false,
    text: () => todayText(new Date(), Intl.DateTimeFormat().resolvedOptions().timeZone),
  }));
}
