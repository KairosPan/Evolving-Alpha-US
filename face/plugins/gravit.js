// face/plugins/gravit.js
/**
 * `gravit` - the face-owned plugin Gravit's own preset mounts, and the first
 * row of the composition the face renders for that preset (src/roles.ts
 * `gravitRows`; `bots/gravit/agent.cordis.yml` is the render's generated
 * mirror). It holds what only Gravit is told: the date (`deployment:today`) and
 * the list of its roles (`gravit:roles`, from the `roles` config key, which
 * `gravitRows` fills from `roles/`). The `cycle` config key is the third
 * section's, plan 3 of the 2026-10-15 redesign: the validator below already
 * checks it, nothing reads it yet, and the shipped row carries none.
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
 * sentence so "today" is never ambiguous; a `TZ` Intl cannot format in (empty,
 * or not a zone name) is rendered in UTC and labelled `(UTC)` - see
 * {@link resolveZone}.
 *
 * This file imports nothing ON PURPOSE, like plugins/bot.js: the rendered
 * composition names it by an absolute `file:` URL (src/roles.ts
 * `GRAVIT_PLUGIN_URL`; the mirror spells the relative path
 * `../../face/plugins/gravit.js`, which `definitionFor` in src/bot-presets.ts
 * rebases to that same URL), and a file URL is all the loader needs.
 *
 * THE ROLE LIST. The `role_<id>` tools are registered by the sibling
 * `@deepseek-ai/dsh-tool-subagent` rows, one per role, and that package has no
 * description key: this section is where Gravit reads what each role is for -
 * a sentence on what a role is and why its report is a claim to check, then one
 * line per entry of the `roles` config, `- <tool> — <summary>`. It sits one
 * past dsh's own subagent section (`TOOL_SUBAGENT` + 1), so it reads straight
 * after the delegation tool it extends. A `roles: []` config mounts the section
 * and renders nothing: dsh drops an empty section from the prompt.
 *
 * GATED ON WHAT THE ASSEMBLING SCOPE CAN CALL. A child JOINS the preset it was
 * delegated from, so a scoped section reaches it too, and an allow list removes
 * tools but cannot remove a sentence. The roles text is therefore a function of
 * the assembly context: it lists only the roles whose tool the assembling scope
 * resolves ({@link canCall}, the lookup dsh-tool-web and dsh-tool-subagent gate
 * their own sections with). A role child, whose allow list restricts the
 * `role_<id>` tools away, gets `""` and is never told of roles it cannot call;
 * a `subagent_fork` child - seeded and unrestricted - resolves every role tool,
 * so it gets Gravit's text unchanged and the system prompt its inherited history
 * was cached under stays byte-identical (roles-smoke pins both); a role whose
 * tool never registered (no `spawn` provider, a row that did not mount) is not
 * advertised. The date is left on for every child.
 *
 * SCOPED, NOT GLOBAL. `ctx.systemPrompt.section` registers into the CALLING
 * context's scope, the preset revision's standing layer, so each section
 * reaches every session joined to the `gravit` preset (and to its `kairos`
 * alias, which declares the same rows) and nobody else: a bot is its own
 * preset and never sees it. tests/bots-smoke.test.ts pins both halves on a real
 * boot.
 *
 * It masks nothing. `inject` names `tools` only to READ the registry's view of
 * the assembling scope; this plugin never registers or restricts a tool: the
 * `role_<id>` tools come from the sibling rows (bots-smoke S3 pins the roster).
 *
 * `interpolate: false` on both sections because their text is prose, not a
 * template: the dsh system prompt is a strict `{{...}}` template with no
 * escape. The date's order is the persona slot's + 1, so the date follows
 * identity - harness identity, the persona prefix, then the date - and
 * precedes every centrally ordered policy and tool section.
 */
export const name = "gravit";
export const inject = ["systemPrompt", "tools"];

/** The date section. Its own name: it shadows nothing, and nothing shadows it. */
export const TODAY_SECTION = "deployment:today";

/** The role list. Registered only when the config carries `roles`; its own name,
 *  like the date's. */
export const ROLES_SECTION = "gravit:roles";

/** What a role is, said once above the list. The list's lines follow it. */
const ROLES_INTRO = "Roles. One-shot delegates on your team, each with its own persona and tools; call one by its tool name with a self-contained brief, and treat its report as a claim to check, never a result to copy. Every report carries four headings: status, what was measured, paths, limits.";

/** A role's tool name: the `role_` prefix keeps the roster's role tools apart
 *  from every host and MCP tool. */
const ROLE_TOOL = /^role_[a-z0-9_]+$/;

/** What would fail at mount or render, as a reason; `undefined` when the config
 *  is valid. `{}` is valid (no roles, no cycle); the shipped row carries
 *  `roles`. `roles` and `cycle` are the optional keys of plans 2 and 3; they are
 *  checked here when present so a malformed value refuses the mount, loudly,
 *  instead of loading a silently dead config. */
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

/** The zone the sentence names: the process's own when Intl will format in it,
 *  `"UTC"` when it will not. `Intl.DateTimeFormat().resolvedOptions().timeZone`
 *  is NOT always usable - measured on Node 22, `TZ=` (empty) resolves to
 *  `"Etc/Unknown"`, which `new Intl.DateTimeFormat(locale, { timeZone })` refuses
 *  with a RangeError, and `TZ=Foo/Bar` or `TZ=:/etc/localtime` resolve to
 *  `undefined`. `apply` never calls the text function, so the mount would
 *  succeed and every Gravit prompt would then fail at assembly; the fallback
 *  keeps the date sentence total. */
export function resolveZone() {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (typeof zone !== "string" || zone === "" || zone === "Etc/Unknown") return "UTC";
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
    return zone;
  } catch {
    return "UTC";
  }
}

/** Whether the scope whose prompt is being assembled can call `name`: the
 *  registry's view of that scope resolves it. The lookup is the one dsh-tool-web
 *  and dsh-tool-subagent gate their own sections with -
 *  `ctx.tools.get(name, context.scope) === void 0` - and `get` applies every
 *  restriction on the scope's chain, so a tool a child's allow list removed reads
 *  as absent. `assembleContextFor` sets `scope` to the agent; a context without
 *  one reads the global view, where no preset-scoped tool lives. */
export function canCall(ctx, context, name) {
  return ctx.tools.get(name, context?.scope) !== undefined;
}

/** The role list: `""` for no roles, else {@link ROLES_INTRO} and one line per
 *  role, `- <tool> — <summary>`. */
export function rolesText(roles) {
  if (roles.length === 0) return "";
  return [ROLES_INTRO, ...roles.map((role) => `- ${role.tool} — ${role.summary}`)].join("\n");
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
    text: () => todayText(new Date(), resolveZone()),
  }));
  if (config.roles !== undefined) {
    ctx.effect(() => ctx.systemPrompt.section({
      name: ROLES_SECTION,
      order: ctx.systemPrompt.getSectionOrder("TOOL_SUBAGENT") + 1,
      interpolate: false,
      text: (context) => rolesText(config.roles.filter((role) => canCall(ctx, context, role.tool))),
    }));
  }
}
