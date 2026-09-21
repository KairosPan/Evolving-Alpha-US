import test from "node:test";
import assert from "node:assert/strict";
import {
  BUDGET_RAW_NAME, MAX_BUDGET_HOSTS, PURPOSE_CHARS, budgetApprovalDecision, budgetGuardReason,
  budgetRequestRefusal, classifyRequester, describeBudgetRequest, isBudgetTool, requesterOf,
} from "../src/budgets.ts";
import { DEFAULT_PRESET } from "../src/overlay.ts";

/* --- which tool the gate claims ------------------------------------------- */

test("isBudgetTool: the budget request matches by its exact registered name", () => {
  assert.equal(BUDGET_RAW_NAME, "wallet_budget_request");
  assert.equal(isBudgetTool("wallet_budget_request"), true);
});

test("isBudgetTool: the other wallet tools are NOT gated - only the one that creates a mandate", () => {
  // The listing, the delegate and the disable are ungated by design (spec §3):
  // delegation is bounded by an already-approved parent, and a substring test
  // on "budget" would gate the harmless listing.
  for (const name of ["wallet_budgets", "wallet_budget_delegate", "wallet_budget_disable", "wallet_pay", "bash"]) {
    assert.equal(isBudgetTool(name), false, name);
  }
});

test("isBudgetTool: the face registers this tool itself, so no server prefix is honoured", () => {
  // There is no `mcp__<server>__` minting to survive: the name is the face's own.
  assert.equal(isBudgetTool("mcp__x__wallet_budget_request"), false);
});

/* --- reading the requester off the session -------------------------------- */

test("requesterOf: reads the header's preset, origin and parent", () => {
  const session = { header: { agentPreset: "drill-bull", origin: "subagent", parentSession: "p1" }, events: [] };
  assert.deepEqual(requesterOf(session), { agentPreset: "drill-bull", origin: "subagent", parentSession: "p1" });
});

test("requesterOf: the LAST agent-preset/selected event outranks the header", () => {
  // A blank session switched onto a bot preset runs as that bot now; the
  // header still says what it was created with (dsh's resolveSessionPreset).
  const session = {
    header: { agentPreset: DEFAULT_PRESET },
    events: [
      { type: "agent-preset/selected", data: { agentPreset: "drill-bear" } },
      { type: "message/user", data: {} },
      { type: "agent-preset/selected", data: { agentPreset: "drill-bull" } },
    ],
  };
  assert.equal(requesterOf(session).agentPreset, "drill-bull");
});

test("requesterOf: is total - a missing header is {}, and no undefined-valued keys appear", () => {
  assert.deepEqual(requesterOf(undefined), {});
  assert.deepEqual(requesterOf(null), {});
  assert.deepEqual(requesterOf("text"), {});
  assert.deepEqual(requesterOf({}), {});
  assert.deepEqual(requesterOf({ header: {}, events: [] }), {});
  assert.deepEqual(requesterOf({ header: { agentPreset: 42 }, events: "nope" }), {});
});

test("classifyRequester: origin subagent is a child, whatever the preset says", () => {
  // A child runs as Kairos, so its preset says principal; only the origin the
  // session store stamped on it tells it apart. A bot's child is a child too.
  assert.equal(classifyRequester({ origin: "subagent" }), "child");
  assert.equal(classifyRequester({ origin: "subagent", agentPreset: DEFAULT_PRESET }), "child");
  assert.equal(classifyRequester({ origin: "subagent", agentPreset: "drill-bull" }), "child");
});

test("classifyRequester: no preset or the default preset is the principal - the dispatch rule", () => {
  assert.equal(classifyRequester({}), "principal");
  assert.equal(classifyRequester({ agentPreset: DEFAULT_PRESET }), "principal");
  // A fork: parentSession set, no origin.
  assert.equal(classifyRequester({ parentSession: "p1" }), "principal");
});

test("classifyRequester: any other preset is a bot", () => {
  assert.equal(classifyRequester({ agentPreset: "drill-bull" }), "bot");
  assert.equal(classifyRequester({ agentPreset: "drill-bear", parentSession: "room" }), "bot");
});

/* --- the card line -------------------------------------------------------- */

const request = {
  purpose: "market data for AAPL thesis",
  limit_usd: "5.00",
  per_call_usd: "0.01",
  valid_for_hours: 168,
  hosts: ["api.example.com", "data.example.com"],
};

test("describeBudgetRequest: the line carries purpose, limit, per-call cap, validity and every host", () => {
  const line = describeBudgetRequest(request);
  assert.equal(
    line,
    'BUDGET - "market data for AAPL thesis" · limit $5.00 · per call $0.01 · valid 168h · hosts api.example.com, data.example.com',
  );
});

test("describeBudgetRequest: no per-call cap reads `none`, never a blank", () => {
  const { per_call_usd: _cap, ...uncapped } = request;
  assert.match(describeBudgetRequest(uncapped), /per call none/);
});

test("describeBudgetRequest: hosts are NEVER elided, even five long ones", () => {
  const hosts = Array.from({ length: MAX_BUDGET_HOSTS }, (_, i) =>
    `${"subdomain".repeat(4)}-${i}.${"segment".repeat(3)}.example-organisation.com:8443`);
  const line = describeBudgetRequest({ ...request, hosts });
  for (const host of hosts) assert.ok(line.includes(host), `host must appear in full: ${host}`);
  assert.doesNotMatch(line.slice(line.indexOf("hosts ")), /…/);
});

test("describeBudgetRequest: the purpose is bounded, and the bound is visible", () => {
  const line = describeBudgetRequest({ ...request, purpose: "p".repeat(300) });
  const quoted = /"([^"]*)"/.exec(line)?.[1] ?? "";
  assert.equal(quoted.length, PURPOSE_CHARS + 1, "80 chars plus the ellipsis");
  assert.match(quoted, /…$/);
  // ...and the hosts after it are still all there.
  assert.match(line, /hosts api\.example\.com, data\.example\.com$/);
});

test("describeBudgetRequest: odd arguments degrade to `?` fields, never throw", () => {
  for (const args of [undefined, null, "text", 42, []]) {
    assert.equal(describeBudgetRequest(args), 'BUDGET - "?" · limit $? · per call none · valid ?h · hosts (none)');
  }
  assert.match(describeBudgetRequest({ hosts: ["a.com", 7] }), /hosts a\.com, \?/);
});

/* --- what is refused before any card -------------------------------------- */

test("budgetRequestRefusal: a well-formed request is not refused", () => {
  assert.equal(budgetRequestRefusal(request), undefined);
  assert.equal(budgetRequestRefusal({ ...request, hosts: ["*.example.com"] }), undefined, "an org-level wildcard is decidable");
  assert.equal(budgetRequestRefusal({ ...request, hosts: ["127.0.0.1:4021"] }), undefined, "host:port is a host");
});

test("budgetRequestRefusal: six hosts are refused - the card shows every host in full or none", () => {
  const six = Array.from({ length: 6 }, (_, i) => `h${i}.example.com`);
  assert.match(budgetRequestRefusal({ ...request, hosts: six }) ?? "", /6 hosts/);
  assert.match(budgetRequestRefusal({ ...request, hosts: six }) ?? "", /at most 5/);
  const five = six.slice(0, 5);
  assert.equal(budgetRequestRefusal({ ...request, hosts: five }), undefined);
});

test("budgetRequestRefusal: `*` is refused - a budget for anywhere is not a budget", () => {
  assert.match(budgetRequestRefusal({ ...request, hosts: ["api.example.com", "*"] }) ?? "", /any host/);
  // agentpay trims and lowercases before matching, so padding is not a way round.
  assert.notEqual(budgetRequestRefusal({ ...request, hosts: [" * "] }), undefined);
});

test("budgetRequestRefusal: a bare top-level wildcard is refused, with or without a port", () => {
  for (const host of ["*.com", "*.io", "*.COM", "*.com:8080"]) {
    assert.match(budgetRequestRefusal({ ...request, hosts: [host] }) ?? "", /top-level wildcard/, host);
  }
});

test("budgetRequestRefusal: hosts must be a non-empty list of non-empty strings", () => {
  assert.notEqual(budgetRequestRefusal({ ...request, hosts: undefined }), undefined);
  assert.notEqual(budgetRequestRefusal({ ...request, hosts: "api.example.com" }), undefined);
  assert.notEqual(budgetRequestRefusal({ ...request, hosts: [] }), undefined);
  assert.match(budgetRequestRefusal({ ...request, hosts: ["a.com", 7] }) ?? "", /non-empty string/);
  assert.match(budgetRequestRefusal({ ...request, hosts: ["a.com", ""] }) ?? "", /non-empty string/);
  assert.notEqual(budgetRequestRefusal(undefined), undefined);
});

/* --- the decision --------------------------------------------------------- */

const principal = { agentPreset: DEFAULT_PRESET };

test("budgetApprovalDecision: anything that is not the budget tool is none of our business", () => {
  // null, not allow: the caller must delegate to next().
  assert.equal(budgetApprovalDecision("wallet_pay", "ask", request, principal), null);
  assert.equal(budgetApprovalDecision("bash", "ask", request, principal), null);
});

test("budgetApprovalDecision: the principal under policy `ask` raises a card", () => {
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "ask", request, principal);
  assert.equal(decision?.kind, "ask");
  assert.equal(budgetApprovalDecision(BUDGET_RAW_NAME, "ask", request, {})?.kind, "ask", "no preset is the principal");
});

test("budgetApprovalDecision: the ask reason is decidable - terms, every host, channel and requester", () => {
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "ask", request, { ...principal, channelName: "strategies/aapl-momentum" });
  const reason = decision?.kind === "ask" ? decision.reason ?? "" : "";
  for (const fragment of ["market data for AAPL thesis", "limit $5.00", "per call $0.01", "valid 168h",
    "api.example.com", "data.example.com", "from strategies/aapl-momentum", "by principal"]) {
    assert.ok(reason.includes(fragment), `${fragment} in ${JSON.stringify(reason)}`);
  }
});

test("budgetApprovalDecision: without a channel the card says so rather than inventing one", () => {
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "ask", request, principal);
  assert.match(decision?.kind === "ask" ? decision.reason ?? "" : "", /from no channel by principal$/);
});

test("budgetApprovalDecision: a bot is denied in the face's words, before any card, whatever the policy", () => {
  for (const policy of ["ask", "never"]) {
    const decision = budgetApprovalDecision(BUDGET_RAW_NAME, policy, request, { agentPreset: "drill-bull" });
    assert.equal(decision?.kind, "deny", policy);
    const reason = decision?.kind === "deny" ? decision.reason : "";
    assert.match(reason, /drill-bull/);
    assert.match(reason, /no wallet/i);
    assert.match(reason, /no card was raised/i);
    assert.doesNotMatch(reason, /the user rejected/i);
    assert.doesNotMatch(reason, /danger-full-access/, "the remedy for a bot is not a permission mode");
  }
});

test("budgetApprovalDecision: a child task is denied before the `never` branch, and told to ask for delegation", () => {
  // Children run under policy `never`; reaching that branch would tell them
  // to clear DSH_PERMISSION_MODE, which is the wrong remedy.
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "never", request, { origin: "subagent", agentPreset: DEFAULT_PRESET });
  assert.equal(decision?.kind, "deny");
  const reason = decision?.kind === "deny" ? decision.reason : "";
  assert.match(reason, /child task/);
  assert.match(reason, /wallet_budget_delegate/);
  assert.doesNotMatch(reason, /danger-full-access/);
});

test("budgetApprovalDecision: a bot or child is refused BEFORE the request is even looked at", () => {
  // Order of the branches: who, then what. A bot with a bad request hears
  // about its wallet, not its hosts.
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "ask", { ...request, hosts: ["*"] }, { agentPreset: "drill-bull" });
  assert.match(decision?.kind === "deny" ? decision.reason : "", /no wallet/i);
});

test("budgetApprovalDecision: a refused request is denied with the refusal, and no card", () => {
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "ask", { ...request, hosts: ["*.com"] }, principal);
  assert.equal(decision?.kind, "deny");
  const reason = decision?.kind === "deny" ? decision.reason : "";
  assert.match(reason, /top-level wildcard/);
  assert.match(reason, /no card was raised/i);
});

test("budgetApprovalDecision: under policy `never` it denies ITSELF, and says nobody was asked", () => {
  // Mirrors orderApprovalDecision: ApprovalService short-circuits on `never`
  // before any answerer runs, and dsh-tools would render that as a refusal
  // nobody made.
  const decision = budgetApprovalDecision(BUDGET_RAW_NAME, "never", request, principal);
  assert.equal(decision?.kind, "deny");
  const reason = decision?.kind === "deny" ? decision.reason : "";
  assert.match(reason, /nobody was asked/i);
  assert.match(reason, /no mandate is created/i);
  assert.doesNotMatch(reason, /the user rejected/i);
  assert.match(reason, /danger-full-access/);
});

/* --- the guard: the monotonic half --------------------------------------- */

const asked = (id: string, callId: string, toolName = BUDGET_RAW_NAME) =>
  ({ type: "approval/asked", data: { id, callId, toolName } });
const decided = (id: string, outcome: string) => ({ type: "approval/decided", data: { id, outcome } });
const granted = [asked("g", "c1"), decided("g", "allowed-once")];

test("budgetGuardReason: an approved request passes", () => {
  assert.equal(budgetGuardReason(BUDGET_RAW_NAME, granted, "c1"), undefined);
});

test("budgetGuardReason: a request with NO grant is denied - a sighting is not an approval", () => {
  assert.match(budgetGuardReason(BUDGET_RAW_NAME, [], "c1") ?? "", /without a logged allowed-once/);
  assert.notEqual(budgetGuardReason(BUDGET_RAW_NAME, undefined, "c1"), undefined, "no session, no grant");
});

test("budgetGuardReason: a rejection, another call's grant, or another tool's grant does not pass", () => {
  assert.notEqual(budgetGuardReason(BUDGET_RAW_NAME, [asked("g", "c1"), decided("g", "rejected")], "c1"), undefined);
  assert.notEqual(budgetGuardReason(BUDGET_RAW_NAME, granted, "c2"), undefined);
  // An order approved in the same turn (same model call id, different tool)
  // must not license a mandate: the pairing reuses orders' toolName check.
  const order = [asked("g", "c1", "mcp__x__place_order"), decided("g", "allowed-once")];
  assert.notEqual(budgetGuardReason(BUDGET_RAW_NAME, order, "c1"), undefined);
});

test("budgetGuardReason: everything else passes untouched", () => {
  for (const name of ["bash", "wallet_pay", "wallet_budgets", "mcp__x__place_order"]) {
    assert.equal(budgetGuardReason(name, [], "c1"), undefined, name);
  }
});
