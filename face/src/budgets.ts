/** The budget approval gate (Gate 3): what makes `wallet_budget_request` raise a card.
 *
 * The agent wallet (spec `docs/superpowers/specs/2026-09-20-agent-wallet-design.md`)
 * moves money inside mandates, and a mandate exists only because an operator
 * approved it on a card. This module is the card's producer, built to the same
 * shape as Gate 2 (`orders.ts`): a pure decision for a prepended
 * `tools/pre-execute` listener, and a pure guard reason evaluated on every
 * allow, both wired in `boot.ts`. One budget request = one card = one mandate
 * (spec decision 2); the logged `approval/asked` + `approval/decided{allowed-once}`
 * pair for the callId is the audit, and the guard requires it before the body
 * runs.
 *
 * What is different from Gate 2, and why it is a separate module rather than a
 * third raw name in `ORDER_RAW_NAMES`:
 * - the tool is the FACE's own, registered in-process (spec decision 1), so
 *   there is no `mcp__<server>__` minting to survive and no `(operator-gated)`
 *   marker audit to run: the name is exact;
 * - WHO asks matters before WHAT is asked. Only the principal (Kairos) may
 *   request a budget; a child task runs under approval policy `never` and gets
 *   its money by delegation, and a bot has no wallet at all (spec decisions 5
 *   and §3's caller rule). Both are refused in the face's own words BEFORE the
 *   `never` and `ask` branches, so the transcript never says an operator
 *   refused a card they never saw;
 * - the card line has hosts on it, every one in full: a mandate's hosts are
 *   what it may pay, and a request that cannot be shown in full (more than five
 *   hosts) or that means "anywhere" (`*`, `*.<tld>`) is refused before any card,
 *   because a card the operator cannot read is a click-through.
 *
 * Like Gate 2 this is not containment (the `tools/execute` seam can rename a
 * guard-approved call, R-W6; the payer key is readable from any shell turn,
 * D16). It gates the model's ordinary tool calls, and the spec says so.
 * @module
 */
import {
  hasApprovalGrant,
  type ApprovalEventLike,
  type ApprovalPolicyLike,
  type PreToolDecision,
} from "./orders.ts";
import { DEFAULT_PRESET } from "./overlay.ts";

/** The one tool this gate covers, by its exact registered name. The face
 * registers it itself (`wallet.ts`, through `ctx.tools.register`), so unlike
 * the order tools there is no operator-owned server name in front of it and
 * nothing to anchor a suffix on. dsh only rewrites names over 64 chars or
 * outside `[A-Za-z0-9_-]`; this one is 21 chars of `[a-z_]`, so the registered
 * name IS this string. */
export const BUDGET_RAW_NAME = "wallet_budget_request";

/** How many hosts one budget may name. Every host is printed in full on the
 * card (never elided), so the bound is on the request, not on the line. Five
 * long hosts still fit one readable card; a sixth is refused, not truncated. */
export const MAX_BUDGET_HOSTS = 5;

/** Bound on the model-written purpose, the one free-text field on the card. As
 * in `describeOrder`: model-controlled text on the operator's only line must
 * not push a plausible sentence past the real one. Twice the order bound
 * because a purpose is a sentence and forty characters cut one mid-word. */
export const PURPOSE_CHARS = 80;

/** Is this the budget request tool? Exact match: see {@link BUDGET_RAW_NAME}.
 * A tool that merely mentions budgets (`wallet_budgets`, the listing) is not
 * gated, for the reason the read-only `orders` listing is not. */
export function isBudgetTool(name: string): boolean {
  return name === BUDGET_RAW_NAME;
}

/** Who is asking, as the face can READ it off the session rather than be told
 * it in arguments (spec decision 4: attribution is a fact the face reads, not
 * a claim the model makes). All fields optional because {@link requesterOf} is
 * total over anything `exec.agent?.session` might be. */
export interface RequesterLike {
  /** The live preset: the last `agent-preset/selected` event, else the header's. */
  agentPreset?: string;
  /** `'subagent'` for a child task; absent for a top-level session or a fork. */
  origin?: string;
  /** The session this one was forked from, or the child's parent. */
  parentSession?: string;
  /** The channel the session works in, when the caller resolved one. Never
   * derived here: the boot wiring has no channel resolver and passes it
   * `undefined`; `wallet.ts` names channels on the tool RESULT instead. */
  channelName?: string;
}

/** The requester's class, by the ordered rule in spec §3. */
export type RequesterClass = "principal" | "child" | "bot";

/**
 * Read the requester off a session, totally.
 *
 * The live preset is the LAST `agent-preset/selected` event when the session
 * has one, else `header.agentPreset` — exactly `resolveSessionPreset`
 * (`dsh-agent-presets/lib/index.js:762-768`), which dsh keeps private. The
 * event's payload field is `agentPreset` (`dsh-host-apiproxy/lib/index.js:3260`
 * is the only append site). A switched session must be classified under the
 * preset it is running now, not the one it was created with; a bot preset
 * selected onto a blank session is a bot.
 *
 * Total on purpose: this runs inside a gate, where a throw would propagate out
 * of the listener. Not an object → `{}`; a header missing any field leaves it
 * unset, so a result never carries an `undefined`-valued key.
 * @param session - `exec.agent?.session`, whatever shape it has.
 * @returns the requester fields the session actually carries.
 */
export function requesterOf(session: unknown): RequesterLike {
  const out: RequesterLike = {};
  if (session === null || typeof session !== "object") return out;
  const row = session as { header?: unknown; events?: unknown };
  const header = row.header !== null && typeof row.header === "object"
    ? row.header as Record<string, unknown>
    : undefined;
  const str = (value: unknown): string | undefined => typeof value === "string" ? value : undefined;
  let preset = str(header?.agentPreset);
  if (Array.isArray(row.events)) {
    for (let index = row.events.length - 1; index >= 0; index -= 1) {
      const event = row.events[index] as { type?: unknown; data?: { agentPreset?: unknown } } | undefined;
      if (event?.type !== "agent-preset/selected") continue;
      const selected = str(event.data?.agentPreset);
      if (selected !== undefined) preset = selected;
      break;
    }
  }
  if (preset !== undefined) out.agentPreset = preset;
  const origin = str(header?.origin);
  if (origin !== undefined) out.origin = origin;
  const parent = str(header?.parentSession);
  if (parent !== undefined) out.parentSession = parent;
  return out;
}

/**
 * Classify a requester by the ONE ordered rule the wallet uses (spec §3).
 *
 * 1. `origin === 'subagent'` → child, whatever the preset: a child task runs
 *    as Kairos (charter §7.2), so its preset says principal, and only the
 *    origin the session store stamped on it (`dsh-session` header `origin`,
 *    set by `dsh-subagent/lib/index.js:537`) tells it apart.
 * 2. No preset, or the default one, → principal. This is the rule `dispatch`
 *    uses (`room.ts`: `preset !== undefined && preset !== DEFAULT_PRESET` is a
 *    voice). A fork (`parentSession` set, no origin) is a principal.
 * 3. Any other preset → bot.
 * @param requester - what {@link requesterOf} read.
 * @returns the class every wallet tool keys its refusals on.
 */
export function classifyRequester(requester: RequesterLike): RequesterClass {
  if (requester.origin === "subagent") return "child";
  if (requester.agentPreset === undefined || requester.agentPreset === DEFAULT_PRESET) return "principal";
  return "bot";
}

/** `wallet_budget_request`'s arguments as the card reads them. Everything is
 * `unknown` because the registry has validated nothing this module relies on;
 * the body re-derives the mandate's terms from `exec.arguments` on its own. */
type BudgetArgsLike = Record<string, unknown>;

/** The argument object, or `undefined` when the arguments are not one. */
function argsOf(args: unknown): BudgetArgsLike | undefined {
  if (args === null || typeof args !== "object" || Array.isArray(args)) return undefined;
  return args as BudgetArgsLike;
}

/** A scalar argument as card text, bounded, or `undefined` when absent or not
 * a scalar. Amounts cross the tool boundary as strings (spec §3), but a model
 * that sends a number is still shown what it sent. */
function scalarOf(row: BudgetArgsLike | undefined, key: string, chars: number): string | undefined {
  const value = row?.[key];
  if (value === undefined || value === null || typeof value === "object") return undefined;
  const text = String(value);
  return text.length > chars ? `${text.slice(0, chars)}…` : text;
}

/**
 * One line an operator can actually decide a BUDGET on.
 *
 * As with `describeOrder`, the card renders `reason` and nothing else, so what
 * is not in this string is not being approved. A budget is decided on five
 * things — purpose, limit, per-call cap, validity, hosts — and the requester
 * ({@link budgetApprovalDecision} appends that). Hosts are printed in full and
 * NEVER elided: an elided host list is a mandate the operator did not read,
 * and {@link budgetRequestRefusal} bounds the count instead so this can hold.
 *
 * Total and defensive, like `describeOrder`: odd arguments degrade to `?`
 * fields rather than losing the card. The line is neither the tool's schema
 * check nor the body's: the model sees the refusal when the body validates.
 * @param args - `exec.arguments`.
 * @returns `BUDGET - "<purpose>" · limit $<limit> · per call $<cap|none> · valid <h>h · hosts <all>`.
 */
export function describeBudgetRequest(args: unknown): string {
  const row = argsOf(args);
  const purpose = scalarOf(row, "purpose", PURPOSE_CHARS) ?? "?";
  const limit = scalarOf(row, "limit_usd", 24) ?? "?";
  const perCall = scalarOf(row, "per_call_usd", 24);
  const hours = scalarOf(row, "valid_for_hours", 24) ?? "?";
  const hosts = Array.isArray(row?.hosts)
    ? row.hosts.map((host) => typeof host === "string" ? host : "?").join(", ")
    : "";
  return `BUDGET - "${purpose}" · limit $${limit} · per call ${perCall === undefined ? "none" : `$${perCall}`}` +
    ` · valid ${hours}h · hosts ${hosts === "" ? "(none)" : hosts}`;
}

/**
 * Why this request cannot be put on a card at all, or `undefined` when it can.
 *
 * Refused BEFORE any card, in the face's own words (spec §2):
 * - more than {@link MAX_BUDGET_HOSTS} hosts: the card prints every host in
 *   full, and a list too long to read is a list the operator will not read;
 * - `*`: agentpay's "any host" pattern (`pay:packages/wallet/src/hosts.ts:18`).
 *   A budget for anywhere is not a budget the card can describe;
 * - `*.<tld>` (`*.com`, `*.io:8080`): a wildcard whose apex is a bare TLD is
 *   "anywhere" with one extra step. agentpay matches `*.x` as any host ending
 *   in `.x` (`hosts.ts:19-22`), so `*.com` is every `.com`. Compared after the
 *   same trim + lowercase agentpay applies (`hosts.ts:15`) so `*.COM ` is not a
 *   way round;
 * - hosts that are not a non-empty list of non-empty strings: agentpay would
 *   drop or refuse them (`pay:packages/wallet/src/mandate-store.ts:117-124`),
 *   which means the card would show a list the mandate does not get.
 *
 * Deeper wildcards (`*.example.com`) pass: that is a real organisation's
 * hosts, which the operator can decide on.
 * @param args - `exec.arguments`.
 * @returns a reason for the deny, or `undefined` when the request may be asked.
 */
export function budgetRequestRefusal(args: unknown): string | undefined {
  const hosts = argsOf(args)?.hosts;
  if (!Array.isArray(hosts) || hosts.length === 0) {
    return `${BUDGET_RAW_NAME} needs hosts: a non-empty list of the hosts this budget may pay`;
  }
  if (hosts.length > MAX_BUDGET_HOSTS) {
    return `${BUDGET_RAW_NAME} names ${hosts.length} hosts; a budget card shows every host in full,` +
      ` so at most ${MAX_BUDGET_HOSTS} may be requested at once - split the request`;
  }
  for (const host of hosts) {
    if (typeof host !== "string" || host.trim() === "") {
      return `${BUDGET_RAW_NAME}: every host must be a non-empty string (got ${JSON.stringify(host)})`;
    }
    const pattern = host.trim().toLowerCase();
    if (pattern === "*") {
      return `${BUDGET_RAW_NAME}: host "*" would allow paying any host; name the hosts this budget is for`;
    }
    if (/^\*\.[^.]+$/.test(pattern)) {
      return `${BUDGET_RAW_NAME}: host ${JSON.stringify(host)} is a bare top-level wildcard, which would allow` +
        ` paying any host under it; name the hosts this budget is for`;
    }
  }
  return undefined;
}

/**
 * The gate's decision for one pending call.
 *
 * Returns `null` for anything that is not the budget tool — the caller
 * delegates to `next()`, leaving every other tool exactly as it was.
 *
 * Order of the branches is the contract (spec §4.2):
 * 1. a bot or a child is denied in the face's own words BEFORE anything else.
 *    A child runs under policy `never`; letting it reach the `never` branch
 *    would tell it to clear `DSH_PERMISSION_MODE`, which is the wrong remedy —
 *    its remedy is a delegated sub-budget (`wallet_budget_delegate`). A bot has
 *    no wallet (charter §7.1): it says what a resource costs in its answer and
 *    Kairos decides;
 * 2. a request that cannot go on a card ({@link budgetRequestRefusal}) is
 *    denied with that reason;
 * 3. policy `never` DENIES rather than asks, for the reason `orderApprovalDecision`
 *    gives: `ApprovalService.request` short-circuits on `never` before any
 *    answerer runs (`dsh-user-approval/lib/index.js:188`) and `serviceAsk`
 *    renders that as `the user rejected tool "<name>"`
 *    (`dsh-tools/lib/index.js:3331-3338`) — false, since nobody was asked;
 * 4. else `ask`, with a line that carries the five terms and the requester.
 * @param name - `exec.name`.
 * @param policy - the session's effective approval policy.
 * @param args - `exec.arguments`, rendered onto the card.
 * @param requester - what {@link requesterOf} read, plus `channelName` when the
 *   caller resolved one.
 * @returns the decision, or `null` when this call is none of our business.
 */
export function budgetApprovalDecision(
  name: string,
  policy: ApprovalPolicyLike,
  args: unknown,
  requester: RequesterLike,
): PreToolDecision | null {
  if (!isBudgetTool(name)) return null;
  const who = classifyRequester(requester);
  if (who === "bot") {
    return {
      kind: "deny",
      reason:
        `${name} is Kairos's tool: a bot voice (preset "${requester.agentPreset}") has no wallet and cannot ` +
        `request a budget. No card was raised. Say what the resource costs in your answer; Kairos decides ` +
        `whether to pay.`,
    };
  }
  if (who === "child") {
    return {
      kind: "deny",
      reason:
        `${name} is the principal's tool: a child task (origin "subagent") cannot raise a budget card. ` +
        `No card was raised. Ask the parent session to delegate a sub-budget with wallet_budget_delegate ` +
        `and pay from that.`,
    };
  }
  const refusal = budgetRequestRefusal(args);
  if (refusal !== undefined) return { kind: "deny", reason: `${refusal}. No card was raised.` };
  if (policy === "never") {
    return {
      kind: "deny",
      reason:
        `${name} needs a budget approval card, and this session's approval policy is "never" - ` +
        `no card can be raised, so no mandate is created. Nobody has refused it; nobody was asked. ` +
        `Clear DSH_PERMISSION_MODE=danger-full-access, or switch off the danger-full-access preset, ` +
        `and try again.`,
    };
  }
  return {
    kind: "ask",
    reason: `${describeBudgetRequest(args)} · from ${requester.channelName ?? "no channel"} by ${who}`,
  };
}

/**
 * The guard's whole decision, as a pure function — the monotonic half.
 *
 * Evaluated on every allow (`dsh-tools/lib/index.js:3116`), including the
 * allow an `allowed-once` becomes, and it asks the session LOG rather than
 * remembering what the listener saw: `hasApprovalGrant` is satisfied only by a
 * logged `allowed-once` for this exact callId and tool name. The same override
 * case as Gate 2 — a listener registered outside the gate taking our `ask`
 * and returning `allow` — is what this stops.
 * @param name - `exec.name`.
 * @param events - `exec.agent.session.events`, when there is a session.
 * @param callId - `exec.callId`.
 * @returns a denial reason, or `undefined` to let the call through.
 */
export function budgetGuardReason(
  name: string,
  events: readonly ApprovalEventLike[] | undefined,
  callId: unknown,
): string | undefined {
  if (!isBudgetTool(name)) return undefined;
  if (events !== undefined && hasApprovalGrant(events, callId, name)) return undefined;
  return `${name} reached dispatch without a logged allowed-once approval for this call`;
}
