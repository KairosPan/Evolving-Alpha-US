// face/plugins/bot.js
/**
 * `kairos-bot` — the one plugin every bot composition mounts.
 *
 * A bot is a dsh agent preset the FACE declares (src/bot-presets.ts): dsh
 * 0.2.0 scans no directory and reads no preset file (NEW
 * packages/preset/agent-preset-registry/README.md "neither scans directories
 * nor accepts preset paths"). The composition on disk,
 * `bots/<id>/agent.cordis.yml`, still names this file by a RELATIVE path
 * (`../../face/plugins/bot.js`); the face rebases it to an absolute `file:`
 * URL against `bots/<id>/` while building the declaration, because dsh
 * resolves a preset's rows against the DECLARING context's base, not the bot
 * directory (NEW agent-preset-registry/src/index.ts:108, src/mount.ts:258-264).
 * This file imports nothing ON PURPOSE, so a file URL is all it needs.
 *
 * The persona goes in through `ctx.systemPrompt.section`, the mask through
 * `ctx.tools.restrict`, both registered into the CALLING context's scope — the
 * preset revision's standing layer (NEW packages/core/scope/src/store.ts:226-264)
 * — so they cover every agent joined to that revision and nothing else.
 * dsh-subagent composes a child the same way. The persona section is named
 * `deployment:persona-prefix` at the central prefix order: a scoped section of
 * that name SHADOWS the deployment's global prefix, which is Kairos's persona
 * (NEW packages/core/system-prompt/src/index.ts:125-127, 179, 251-253), as
 * 0.1.1's `deployment:persona` did. Kairos's `personaSuffix` is not touched;
 * the face sets none (PLAN S1).
 *
 * ACTIVATION IS EAGER. dsh 0.2.0 mounts a preset when it is DECLARED, not at
 * its first session (NEW agent-preset-registry/src/index.ts:80-118), and a
 * failed mount is final for that revision (:120-131). A mask computed once
 * would exclude every allowed tool that registers later — an MCP server that
 * connects late or reconnects under the same names. So the mask is recomputed
 * after every burst of `tools/change` (NEW packages/core/tools/src/index.ts:
 * 199-208, 835), an UNFILTERED registry notification that this scoped listener
 * receives too (NEW vendor/cordis/src/events.ts:165-174). Only the FIRST
 * computation, at the mount, may throw (the preset is then broken, visibly); a
 * later one runs from a timer, where a throw would be an uncaught exception,
 * so it is contained and logged and the mask in force stays.
 *
 * WHAT THIS IS NOT. The mask is visibility, not authority (dsh-tools README:
 * "live visibility composition, not an authority boundary"). What a bot may
 * WRITE is its session's sandbox mode; what it may ORDER is Gate 2. Spec D12.
 *
 * `allow`, not `deny`: dsh admits later-registered globals through a deny
 * mask and excludes them through an allow mask. Two of the tools a voice must
 * never see are registered AFTER the mount — `agent_<bin>` on connect, the
 * room's `dispatch` — and the re-expansion above never admits them, because it
 * admits only what the allow list NAMES and no allow list names them.
 * `mcp__…__place_order` is excluded the same way, by OMISSION from the allow
 * list, exactly as a deny list would have to name it.
 */
export const name = "kairos-bot";
export const inject = ["systemPrompt", "tools"];

/** dsh-system-prompt's `PERSONA_PREFIX_SECTION` (NEW
 *  packages/core/system-prompt/src/index.ts:179), restated rather than imported
 *  because this file imports nothing (see the header). tests/bot-plugin.test.ts
 *  pins it to the installed constant, so a rename upstream fails a test instead
 *  of silently turning the bot's persona into a SECOND persona beside Kairos's. */
export const PERSONA_PREFIX_SECTION = "deployment:persona-prefix";

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
 *  because `tools.restrict` rejects a name it does not know.
 *
 *  The star matches dsh's minting EXACTLY - `mcp__<server>__<raw>`, three
 *  non-empty `__`-separated segments - not merely a name ENDING in `__<raw>`.
 *  An ends-with test would let `mcp__a__b__earnings` answer `mcp__*__earnings`,
 *  admitting a tool whose raw name the operator never named. */
export function expandAllow(allow, known) {
  const out = [];
  const missing = [];
  for (const entry of allow) {
    const star = /^mcp__\*__(.+)$/.exec(entry);
    if (star !== null) {
      const raw = star[1];
      const hits = [...known].filter((n) => {
        const parts = n.split("__");
        return parts.length === 3 && parts[0] === "mcp" && parts[1] !== "" && parts[2] === raw;
      }).sort();
      if (hits.length === 0) missing.push(entry);
      else out.push(...hits);
      continue;
    }
    if (known.has(entry)) out.push(entry);
    else missing.push(entry);
  }
  return { allow: out, missing };
}

/** The names an allow list is matched against: `schemas()` with no scope is
 *  the UNMASKED global view (NEW packages/core/tools/src/index.ts:1260, a
 *  `view(undefined)`), the same set `restrict` validates a preset scope's names
 *  against (`restrictableNames`, :1114, :1194-1197). Never the bot's own masked
 *  view, which would hide every tool the mask does not admit yet. */
const globalNames = (ctx) => new Set(ctx.tools.schemas().map((schema) => schema.name));

export function apply(ctx, config) {
  const problem = validateBotConfig(config);
  if (problem !== undefined) throw new Error(`kairos-bot: ${problem}`);
  /** The allow list in force, as a key; null until the first mask lands. */
  let applied = null;
  /** The disposer that lifts the mask in force. */
  let lift;
  /** False once this revision unloads: a fiber that is unloading refuses new
   *  effects (NEW vendor/cordis/src/fiber.ts:420), and `restrict` is one. */
  let active = true;
  /** The one re-expansion queued behind a burst of `tools/change`s. */
  let pending;
  const sync = () => {
    const { allow, missing } = expandAllow(config.allow, globalNames(ctx));
    /* Warned once, at the mount, where a missing name is a configuration fact
     * worth a line. Later a name goes missing because its tool went away - an
     * MCP reconnect, or every tool unregistering while the face shuts down -
     * and a line per bot there would be noise, not a diagnosis. */
    if (applied === null && missing.length > 0) {
      ctx.logger?.warn?.(`kairos-bot: allow names not (yet) in this tree: ${missing.join(", ")}`);
    }
    /* Never lift to "no mask": when every allowed tool is gone the mask in
     * force stays, naming tools that no longer exist - which admits nothing. */
    if (allow.length === 0) return;
    const key = allow.join("\n");
    if (key === applied) return;
    const previous = applied;
    /* Set BEFORE restrict: restrict mutates the layer and then emits
     * `tools/change` synchronously (NEW scope/src/store.ts:233-262), and the
     * sync that emission queues must find this key already applied. */
    applied = key;
    let next;
    try {
      next = ctx.tools.restrict({ allow });
    } catch (error) {
      applied = previous;
      throw error;
    }
    /* Restrictions intersect (NEW tools/src/index.ts:1199-1201), so the new
     * mask is in force before the old one lifts: no instant with no mask. */
    const old = lift;
    lift = next;
    old?.();
  };
  sync();
  if (applied === null) throw new Error("kairos-bot: none of the allowed tools exist in this tree; the bot would have no hands at all");
  ctx.effect(() => ctx.systemPrompt.section({
    name: PERSONA_PREFIX_SECTION,
    order: ctx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_PREFIX"),
    text: config.persona,
  }));
  /* Coalesced, not synchronous. Every bot re-derives the whole global view per
   * sync (`schemas()` clones each schema), and changes arrive in bursts: every
   * tool of a reconnecting MCP server, every tool of the tree while the face
   * shuts down. Measured on the NEW registry with 10 bots and 45 tools,
   * unregistering them one by one blocked the event loop for ~1 s (385
   * emits) when each emit re-expanded synchronously. One deferred sync per
   * burst sees the same final tool set; until it runs, a bot sees the mask it
   * had, which names nothing it may not use. */
  ctx.on("tools/change", () => {
    if (!active || pending !== undefined) return;
    pending = setTimeout(() => {
      pending = undefined;
      if (!active) return;
      try {
        sync();
      } catch (error) {
        ctx.logger?.warn?.(`kairos-bot: the tool mask could not follow a tool change; the previous mask stays in force: ${error instanceof Error ? error.message : String(error)}`);
      }
    }, 0);
    /* A queued re-expansion is never a reason for the process to stay up. */
    pending.unref?.();
  });
  ctx.effect(() => () => {
    active = false;
    if (pending !== undefined) clearTimeout(pending);
    pending = undefined;
    const current = lift;
    lift = undefined;
    current?.();
  });
}
