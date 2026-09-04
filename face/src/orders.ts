/** The per-order approval gate: what makes `place_order` raise a card.
 *
 * Gate 1 is registration — `ALPACA_KIT_ENABLE_ORDERS=1` plus both APCA keys, in
 * the operator's harness, decides whether the mutating tools exist at all
 * (`alpaca_kit/mcp/tools.py:298`). Gate 2 is this: given that they DO exist,
 * every call to one stops for a human first.
 *
 * Until 2026-09-04 Gate 2 did not exist for orders. The approval CHANNEL was
 * real and drilled, but its only producer was a sandbox escalation, and an MCP
 * call never takes that path — so arming the flag would have let `place_order`
 * run with no card and no `approval/asked` event. This module is the producer.
 *
 * WHAT IT IS NOT. `tools/execute` runs AFTER the guard below, is handed the
 * execution explicitly as mutable (`dsh-tools/lib/index.js:3200-3202`), and the
 * body then re-resolves the tool by its CURRENT name (`:3178`) — so a
 * `tools/execute` wrapper can rename a guard-approved call into `place_order`
 * after the fact. Nothing here changes that, and Kairos has an unrestricted
 * shell besides. Per charter Rule 2 — enforce below the layer that runs
 * arbitrary code, or admit the gate is prose — this gates the model's ordinary
 * tool calls. It is not containment. `face/README.md` says so where an operator
 * will read it.
 * @module
 */

/** The mutating tools, matched by their RAW names rather than by a full public
 * name. dsh mints `mcp__<serverName>__<rawName>` (`dsh-mcp-client/lib/index.js:120`)
 * and the serverName is the OPERATOR's — it lives in their cordis patch, not in
 * this repo — so a constant list of full names would quietly stop matching the
 * day they rename the row. Anchoring on the raw suffix survives that rename.
 *
 * The read-only `orders` listing (`alpaca_kit/mcp/tools.py:292`) deliberately
 * does NOT match: a substring test for "order" would gate a harmless query. */
const ORDER_RAW_NAMES = ["place_order", "cancel_order"] as const;

/** The marker alpaca-kit stamps on both mutating tools' descriptions
 * (`alpaca_kit/mcp/tools.py:303,307`). Cross-checked against the name test in
 * {@link auditOrderTools} so a rename on either side is caught by the other. */
export const OPERATOR_GATED_MARKER = "(operator-gated)";

/** Every approval policy this gate distinguishes. `never` is the one that
 * matters: it auto-rejects without reaching an answerer, so no card appears. */
export type ApprovalPolicyLike = "ask" | "never" | (string & {});

/** The pre-dispatch decision, structurally — the face does not depend on
 * `@deepseek-ai/dsh-tools` (it is not in `package.json`), and states the shapes
 * it needs rather than importing them, the same way `panels.ts` does. */
export type PreToolDecision =
  | { kind: "allow" }
  | { kind: "deny"; reason: string }
  | { kind: "ask"; reason?: string };

/** One registered tool as the registry advertises it. */
export interface ToolSchemaLike {
  name: string;
  description?: string;
}

/** Is this the name of a tool that MOVES money (or cancels something that
 * would)? Matches the raw name itself and any `mcp__<server>__<raw>` minting of
 * it, so an operator's server rename cannot slip a live order tool past. */
export function isOrderTool(name: string): boolean {
  return ORDER_RAW_NAMES.some((raw) => name === raw || name.endsWith(`__${raw}`));
}

/** Reconstruct the policy an ask would resolve under, from PUBLIC surface only.
 *
 * `ApprovalService.effectivePolicy` is private (`dsh-user-approval`'s
 * `index.d.ts:179`), but its body is exactly
 * `overrideOf(session) ?? config.policy ?? "ask"` (`lib/index.js:168-170`), and
 * both halves are public. Reproduced rather than reached into, so a future
 * change to the private method surfaces here as a behaviour difference under
 * test instead of a runtime crash.
 * @param approval - the approval service, structurally.
 * @param session - the calling agent's session.
 * @returns the policy in force for this session right now.
 */
export function effectiveApprovalPolicy(
  approval: {
    overrideOf(session: unknown): ApprovalPolicyLike | undefined;
    config?: { policy?: ApprovalPolicyLike };
  },
  session: unknown,
): ApprovalPolicyLike {
  return approval.overrideOf(session) ?? approval.config?.policy ?? "ask";
}

/**
 * The gate's decision for one pending call.
 *
 * Returns `null` for anything that is not an order tool — the caller delegates
 * to `next()`, leaving every other tool exactly as it was.
 *
 * Under policy `never` this DENIES rather than asking. Returning `ask` there
 * would be worse than useless: `ApprovalService.request` short-circuits on
 * `never` before any answerer runs (`dsh-user-approval/lib/index.js:188`), and
 * `serviceAsk` then renders that as `the user rejected tool "<name>"`
 * (`dsh-tools/lib/index.js:3331-3338`) — a sentence that is false, because
 * nobody was asked. The model would learn the operator refused an order they
 * never saw. Denying in our own words keeps the transcript honest, and makes
 * the gate un-disarmable by `DSH_PERMISSION_MODE=danger-full-access` or by a
 * runtime switch to the `danger-full-access` preset.
 * @param name - the registered tool name (`exec.name`).
 * @param policy - the session's effective approval policy.
 * @param args - `exec.arguments`, rendered onto the card so the human can decide.
 * @returns the decision, or `null` when this call is none of our business.
 */
export function orderApprovalDecision(
  name: string,
  policy: ApprovalPolicyLike,
  args?: unknown,
): PreToolDecision | null {
  if (!isOrderTool(name)) return null;
  if (policy === "never") {
    return {
      kind: "deny",
      reason:
        `${name} needs a per-order approval card, and this session's approval policy is "never" - ` +
        `no card can be raised, so the order does not run. Nobody has refused it; nobody was asked. ` +
        `Clear DSH_PERMISSION_MODE=danger-full-access, or switch off the danger-full-access preset, ` +
        `and try again.`,
    };
  }
  return { kind: "ask", reason: `PAPER order - ${describeOrder(name, args)}` };
}

/** One line an operator can actually decide on.
 *
 * The approval card renders `reason` and nothing else - `ApprovalRequest` carries
 * agent, toolName, callId, reason and signal, and the frame the face draws from
 * carries the same. So if the order's symbol, side and size are not IN this
 * string, the human is approving a tool NAME, which is a click-through, not a
 * decision.
 *
 * Deliberately total and defensive: this runs inside a gate, and a throw here
 * would propagate out of the listener. Anything unexpected degrades to the tool
 * name rather than losing the card.
 * @param name - the registered tool name, the fallback when arguments are odd.
 * @param args - `exec.arguments`, already frozen and JSON-safe by the registry.
 * @returns a compact human-readable summary, never empty.
 */
export function describeOrder(name: string, args: unknown): string {
  if (args === null || typeof args !== "object" || Array.isArray(args)) return name;
  const row = args as Record<string, unknown>;
  const scalar = (key: string): string | undefined => {
    const value = row[key];
    if (value === undefined || value === null) return undefined;
    if (typeof value === "object") return undefined;
    /* Model-controlled text on the operator's only line of information: bound it
     * so a crafted field cannot push a plausible sentence past the real one. */
    const text = String(value);
    return text.length > 40 ? `${text.slice(0, 40)}…` : text;
  };
  /* place_order(symbol, qty, side, order_type, limit_price) and
   * cancel_order(order_id) - alpaca_kit/mcp/tools.py:298-307. Unknown keys are
   * appended rather than dropped, so a tool that grows a field still shows it
   * (charter Rule 5: what is never surfaced is never governed). */
  const known = ["side", "qty", "symbol", "order_type", "limit_price", "order_id"];
  const parts = known.map((key) => {
    const value = scalar(key);
    return value === undefined ? undefined : `${key}=${value}`;
  }).filter((part): part is string => part !== undefined);
  const extra = Object.keys(row)
    .filter((key) => !known.includes(key))
    .map((key) => {
      const value = scalar(key);
      return value === undefined ? `${key}=?` : `${key}=${value}`;
    });
  const summary = [...parts, ...extra].join(" ");
  return summary === "" ? name : `${name}: ${summary}`;
}

/** One session event, structurally - only the fields the grant check reads. */
export interface ApprovalEventLike {
  type: string;
  data?: { id?: unknown; callId?: unknown; outcome?: unknown; toolName?: unknown };
}

/**
 * Did THIS call actually receive an operator grant?
 *
 * `ApprovalService.request` appends `approval/asked` (carrying `callId` and a
 * fresh `id`) and then `approval/decided` (carrying that `id` and the outcome)
 * - `dsh-user-approval/lib/index.js:147-158`. `allowed-once` is the ONLY outcome
 * the tools layer turns into an allow (`dsh-tools/lib/index.js:3327`), so it is
 * the only one that counts as a grant here.
 *
 * This is what the guard asks instead of "did my listener SEE this call". A
 * sighting is not an approval: a `tools/pre-execute` listener registered outside
 * this gate can take our `ask` and return `allow`, and a sighting-based guard
 * would wave that through. Only the log proves a human said yes.
 * @param events - `exec.agent.session.events`.
 * @param callId - `exec.callId`.
 * @param toolName - `exec.name`, so a grant for another tool cannot be replayed.
 * @returns true only when this call has a logged `allowed-once` for this tool.
 */
export function hasApprovalGrant(
  events: readonly ApprovalEventLike[],
  callId: unknown,
  toolName?: string,
): boolean {
  if (callId === undefined || callId === null) return false;
  const granted = new Set<unknown>();
  for (const event of events) {
    if (event.type !== "approval/asked") continue;
    if (event.data?.callId !== callId) continue;
    /* `callId` is the MODEL's tool-call id (`dsh-agent-loop` sets it from the
     * block id), so it is not by itself proof of WHICH tool was approved. The
     * asked event records the tool name; require it to match, so a grant won
     * for some other approval-requiring call cannot be replayed onto an order. */
    if (toolName !== undefined && event.data?.toolName !== toolName) continue;
    /* An id-less asked event cannot pair with anything: skipping it stops a
     * malformed pair from matching an equally id-less decided event. */
    if (event.data?.id === undefined) continue;
    granted.add(event.data.id);
  }
  if (granted.size === 0) return false;
  return events.some((event) =>
    event.type === "approval/decided" &&
    granted.has(event.data?.id) &&
    event.data?.outcome === "allowed-once"
  );
}

/** Is this call subject to the gate at all - by name, or by the marker on its
 * live description? The description half is what catches a tool that registered
 * AFTER boot (dsh-mcp-client activates even when its first connection failed,
 * so the boot audit can run against a registry that has not filled in yet) and
 * one whose public name took a hash suffix (dsh normalizes and hashes any name
 * over 64 chars or carrying a character outside [A-Za-z0-9_-], so the raw-name
 * suffix anchor does not always hold).
 *
 * The marker test is confined to `mcp__` names: it is a substring test on
 * operator-supplied text, and an unrelated tool that happened to carry the
 * phrase would otherwise be denied with a message blaming a rename.
 * @param name - `exec.name`.
 * @param description - the live registry's description for it, if any.
 * @returns true when the gate must have a grant before this call dispatches.
 */
export function isGatedTool(name: string, description: string | undefined): boolean {
  if (isOrderTool(name)) return true;
  return name.startsWith("mcp__") && (description ?? "").includes(OPERATOR_GATED_MARKER);
}

/** What {@link auditOrderTools} found in the live registry. */
export interface OrderToolAudit {
  /** Registered order tools this gate covers. */
  gated: string[];
  /** Registered tools alpaca-kit marked operator-gated that this gate would
   * NOT stop — a rename that opened a hole. Boot refuses on any of these. */
  ungated: string[];
}

/**
 * Cross-check the live registry against the gate, in both directions.
 *
 * The face cannot read `ALPACA_KIT_ENABLE_ORDERS`: it is passed to the
 * alpaca-kit row's own `env:` block in the operator's cordis patch, not to this
 * process. So the flag cannot be asserted on — the REGISTRY is the only honest
 * source of whether order tools are live, and this reads it.
 *
 * The direction that matters is `ungated`: alpaca-kit stamps both mutating
 * tools `(operator-gated)`, so a tool carrying that marker whose name this gate
 * does not match means someone renamed one side and the gate now misses a live
 * order tool. That is the failure this whole module exists to prevent, and it
 * would otherwise be invisible — the face would come up healthy with the gate
 * quietly covering nothing.
 * @param schemas - `ctx.tools.schemas()`, the live registry.
 * @returns the covered names and the dangerous ones.
 */
export function auditOrderTools(schemas: readonly ToolSchemaLike[]): OrderToolAudit {
  const gated: string[] = [];
  const ungated: string[] = [];
  for (const schema of schemas) {
    if (isOrderTool(schema.name)) gated.push(schema.name);
    else if (isGatedTool(schema.name, schema.description)) ungated.push(schema.name);
  }
  return { gated, ungated };
}

/**
 * The guard's whole decision, as a pure function.
 *
 * Extracted so it can be drilled: a guard is evaluated on every allow and is the
 * only monotonic layer here, which makes it the piece that most needs testing
 * and the piece hardest to reach through the pipeline. Charter Rule 4 - a guard
 * that has never been drilled is presumed broken.
 * @param name - `exec.name`.
 * @param description - the LIVE registry description, read per call rather than
 *   snapshotted at boot: the registry fills in asynchronously.
 * @param events - `exec.agent.session.events`, when there is a session.
 * @param callId - `exec.callId`.
 * @returns a denial reason, or `undefined` to let the call through.
 */
export function orderGuardReason(
  name: string,
  description: string | undefined,
  events: readonly ApprovalEventLike[] | undefined,
  callId: unknown,
): string | undefined {
  if (!isGatedTool(name, description)) return undefined;
  if (events !== undefined && hasApprovalGrant(events, callId, name)) return undefined;
  return isOrderTool(name)
    ? `${name} reached dispatch without a logged allowed-once approval for this call`
    : `${name} is marked ${OPERATOR_GATED_MARKER} but the order gate does not recognise its name,` +
      ` so it can never be approved - add its raw name to ORDER_RAW_NAMES in face/src/orders.ts`;
}
