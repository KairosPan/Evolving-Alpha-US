/** Bot home model defaults and an operator view of the mounted configuration.
 * Saved files are not runtime evidence. Own-journal context is captured afresh
 * as a runtime-context snapshot on each assembly (dsh 0.2.0 logs assembled
 * contexts as `{kind:'runtime-context', form:'snapshot', sections}`, NEW
 * `packages/core/agent-loop/src/runtime-context.ts:14-19, 161`).
 * Inspections never resume a cold agent
 * or assemble concurrently with a turn; last-request facts come from its log.
 */
import { resolve } from "node:path";
import type { Context } from "@deepseek-ai/cordis";
import { assembleContextFor, type Agent } from "@deepseek-ai/dsh-agent";
import { PERSONA_PREFIX_SECTION, type PromptAssembly } from "@deepseek-ai/dsh-system-prompt";
import type { LlmCallConfig } from "@deepseek-ai/dsh-llm";
import { isBotId, type BotRow } from "./bots.ts";
import { formatBotJournal, type BotJournalSnapshot } from "./bot-journal.ts";
import { isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError } from "./http.ts";
import type { RouteRegistrar } from "./static.ts";

type Seed = { id: string; revision: string; route?: { provider: string; model: string } };
type Snapshot = { soul: string | null; model: string | null; tools: string[] };
type JournalInfo = Omit<BotJournalSnapshot, "text">;
const routeName = (config: { provider?: string; model?: string } | undefined): string | null =>
  config?.provider && config.model ? `${config.provider}/${config.model}` : null;
const toolNames = (tools: readonly { name: string }[]): string[] => tools.map((t) => t.name).sort();

/** The slice of `ctx.sessionProjections` this module reads (NEW
 * `packages/session/session-projection/src/index.ts:319`, `stateOf`). */
interface ProjectionsLike {
  stateOf(session: Agent["session"], key: "agentPreset"): string | null | undefined;
}

/** The preset a session RUNS, not the one it was created with. dsh 0.2.0
 * dropped `resolveSessionPreset` (the `dsh-agent-presets` package is gone,
 * PLAN S5); its replacement is the registry's `agentPreset` session
 * projection - initialised from the frozen header and advanced by every
 * logged `agent-preset/selected` (NEW
 * `packages/preset/agent-preset-registry/src/session.ts:33-43`) - read exactly
 * as the session controller does (`presetForSession`, NEW
 * `packages/api/session-controller/src/agent.ts:360-362`). `null` (no preset)
 * and `undefined` (unit unregistered) both mean "none", as upstream maps them.
 * A MISSING projection service is not "none": the preset registry injects it
 * (`agent-preset-registry/src/index.ts:52`) and boot asserts the registry, so
 * its absence is a broken tree - throw rather than silently demoting every
 * bot conversation to "not a bot" (no seeded model, no journal, no capture).
 * @param ctx - the root context the runtime was installed on.
 * @returns the reader, bound late so a reloaded projection service is followed. */
export function sessionPresetReader(ctx: { get(name: string): unknown }): (session: Agent["session"]) => string | undefined {
  return (session) => {
    const projections = ctx.get("sessionProjections") as ProjectionsLike | undefined;
    if (projections === undefined) {
      throw new Error("kairos-face: sessionProjections service is absent - cannot tell which agent preset a session runs");
    }
    return projections.stateOf(session, "agentPreset") ?? undefined;
  };
}

export function installBotRuntime(ctx: Context, listBots: () => Promise<BotRow[]>, options: {
  readJournal?: (botId: string) => Promise<BotJournalSnapshot>;
} = {}) {
  const seeds = new WeakMap<Agent, Promise<Seed | undefined>>();
  const snapshots = new WeakMap<Agent, Snapshot>();
  const assembledRoutes = new WeakMap<Agent, LlmCallConfig>();
  const journals = new WeakMap<Agent, JournalInfo>();
  const presetOf = sessionPresetReader(ctx as unknown as { get(name: string): unknown });
  const seedFor = (agent: Agent): Promise<Seed | undefined> => {
    const id = presetOf(agent.session);
    if (!isBotId(id)) return Promise.resolve(undefined);
    let pending = seeds.get(agent);
    if (pending === undefined) {
      pending = listBots().then((bots) => {
        const bot = bots.find((b) => b.id === id);
        if (!bot) return undefined;
        const home = !agent.session.header.parentSession &&
          resolve(agent.session.header.cwd ?? "") === resolve(bot.homeCwd);
        const split = bot.model?.indexOf("/") ?? -1;
        return { id, revision: bot.revision, ...(home && split > 0 ? {
          route: { provider: bot.model!.slice(0, split), model: bot.model!.slice(split + 1) },
        } : {}) };
      });
      seeds.set(agent, pending);
    }
    return pending;
  };
  const capture = (agent: Agent, assembly: PromptAssembly): Snapshot => {
    const value = {
      // The bot's SOUL is the scoped persona-PREFIX section plugins/bot.js
      // registers; dsh 0.2.0 renamed `deployment:persona` to this constant
      // (NEW packages/core/system-prompt/src/index.ts:179). Matching the old
      // name would read `soul: null` for every bot, silently.
      soul: assembly.sections.find((s) => s.name === PERSONA_PREFIX_SECTION)?.text ?? null,
      model: routeName(assembly.variables), tools: toolNames(assembly.tools),
    };
    snapshots.set(agent, value);
    return value;
  };
  const disposers = [
    // dsh 0.2.0: `agent/created` is a SERIAL, awaited dispatch with payload
    // `{agent, source, signal?}` (NEW packages/core/agent/src/runtime-types.ts:261,
    // dispatched at src/index.ts:550); a throw or rejection here fails the
    // agent's creation. So stay synchronous and swallow the seed warm-up: it
    // is a cache prime, re-derived on first assembly anyway (where a broken
    // tree still fails loudly, see sessionPresetReader).
    ctx.on("agent/created", ({ agent }) => {
      try { void seedFor(agent).catch(() => undefined); } catch { /* re-derived at assembly */ }
      return undefined;
    }),
    // Prepend makes this the outer waterfall, after the gateway has supplied
    // its default. Only the first real request is seeded: the gateway then
    // inherits the logged model and still owns explicit later model switches.
    ctx.on("system-prompt/assemble", async (_assembly, context, next) => {
      const agent = (context as { agent?: Agent }).agent;
      if (!agent) return next();
      if (!isBotId(presetOf(agent.session))) {
        assembledRoutes.delete(agent);
        snapshots.delete(agent);
        journals.delete(agent);
        return next();
      }
      const seed = await seedFor(agent);
      let selected: LlmCallConfig | undefined;
      if (seed && seed.id === presetOf(agent.session) && seed.route && !agent.session.requestHeader()) {
        try { selected = await ctx.llm.resolveCallConfig(seed.route, context.signal); }
        catch { throw new HttpError(409, `Bot model ${routeName(seed.route)} is unavailable. Update the saved route and start a new conversation.`); }
      }
      const assembly = await next();
      if (options.readJournal) {
        const id = presetOf(agent.session)!;
        let journal: BotJournalSnapshot;
        try { journal = await options.readJournal(id); }
        catch { journal = { status: "unavailable", text: "", revision: null, truncated: false, note: "The journal could not be read for this request." }; }
        const { text: _text, ...info } = journal;
        journals.set(agent, info);
        // dsh records this as a runtime-context snapshot message with named
        // sections (NEW packages/core/agent-loop/src/runtime-context.ts:14-19, 161).
        // It is data alongside the room delta, never SOUL.
        assembly.contexts = [...assembly.contexts.filter((entry) => entry.name !== "bot-journal"),
          { name: "bot-journal", text: formatBotJournal(journal) }];
      }
      if (selected) {
        assembledRoutes.set(agent, selected);
        assembly.variables = { ...assembly.variables, provider: selected.provider, model: selected.model };
      } else assembledRoutes.delete(agent);
      capture(agent, assembly);
      return assembly;
    }, { prepend: true }),
    ctx.on("agent/request", async ({ agent }, next) => {
      const config = await next();
      const selected = assembledRoutes.get(agent);
      if (!selected || agent.session.requestHeader()) return config;
      const id = presetOf(agent.session);
      if (!isBotId(id) || (await seedFor(agent))?.id !== id) return config;
      const { reasoningEffort: _effort, ...base } = config;
      return { ...base, provider: selected.provider, model: selected.model,
        ...(selected.reasoningEffort === undefined ? {} : { reasoningEffort: selected.reasoningEffort }) };
    }, { prepend: true }),
  ];

  async function inspect(id: string, sessionId: string) {
    if (!isBotId(id) || !/^session-[A-Za-z0-9-]+$/.test(sessionId)) throw new HttpError(400, "invalid bot or session id");
    const bot = (await listBots()).find((b) => b.id === id);
    if (!bot) throw new HttpError(404, "no such bot");
    const agent = ctx.agents.get(sessionId as Agent["id"]);
    const empty = { sessionId, attached: false, source: "unavailable", revisionAtStart: null,
      soul: null, soulMatchesSaved: null, model: null, tools: [], skills: [], lastRequest: null };
    if (!agent) return { ...empty, note: "This conversation is not attached. Open it and send a message before inspecting its mounted settings." };
    if (presetOf(agent.session) !== id) throw new HttpError(409, "this conversation belongs to a different agent");
    const seed = await seedFor(agent);
    let snapshot = snapshots.get(agent);
    let source = "last-request";
    if (agent.status === "idle") {
      try {
        snapshot = await agent.runMaintenance(async (signal) => capture(agent,
          await ctx.systemPrompt.assemble(assembleContextFor(agent, signal))));
        source = "mounted";
      } catch (error) {
        if (error instanceof HttpError) throw error;
        throw new HttpError(409, "The conversation is busy or its settings could not be assembled. Retry after its turn finishes.");
      }
    }
    const header = agent.session.requestHeader();
    const lastRequest = header ? { model: routeName(header.config), tools: toolNames(header.tools ?? []) } : null;
    const skills = ctx.get("skills") as { list(options: { scope: Agent; cwd?: string }): Promise<{ name: string; description: string }[]> };
    const skillRows = await skills.list({ scope: agent, cwd: agent.session.header.cwd });
    return {
      sessionId, attached: true, status: agent.status, source: snapshot || header ? source : "unavailable",
      revisionAtStart: seed?.id === id ? seed.revision : null,
      soul: snapshot?.soul ?? null,
      soulMatchesSaved: snapshot?.soul == null ? null : snapshot.soul.trim() === bot.soul.trim(),
      model: source === "mounted" ? snapshot?.model ?? null : lastRequest?.model ?? null,
      tools: source === "mounted" ? snapshot?.tools ?? [] : lastRequest?.tools ?? [],
      skills: skillRows.map(({ name, description }) => ({ name, description })), lastRequest,
      ...(journals.has(agent) ? { journal: journals.get(agent)! } : {}),
      ...(source === "mounted" ? { note: "Mounted preview; last request records what was actually sent. Test saved persona/model changes in new conversations; journal notes refresh on each request." }
        : { note: "A turn is running. Showing the last captured persona and logged request; no preview was assembled." }),
    };
  }
  return { inspect, dispose: () => disposers.forEach((off) => off()) };
}

export function registerBotRuntimeRoutes(web: RouteRegistrar, runtime: ReturnType<typeof installBotRuntime>): void {
  web.register({ kind: "exact", path: "/data/bots/runtime", handler: async (req, res) => {
    const send = (status: number, value: unknown) => {
      res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
      res.end(typeof value === "string" ? value : JSON.stringify(value));
    };
    if (!isTrustedDataRequest(req)) return send(403, FORBIDDEN);
    if (req.method !== "GET") return send(405, { ok: false, error: "GET only" });
    try {
      const query = new URL(req.url ?? "", "http://localhost").searchParams;
      return send(200, { ok: true, runtime: await runtime.inspect(query.get("id") ?? "", query.get("sessionId") ?? "") });
    } catch (error) {
      if (error instanceof HttpError) return send(error.status, { ok: false, error: error.message });
      console.error("kairos-face: bot runtime inspection failed:", error);
      return send(500, { ok: false, error: "runtime inspection failed" });
    }
  } });
}
