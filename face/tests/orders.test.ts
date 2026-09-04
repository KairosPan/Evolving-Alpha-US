import test from "node:test";
import assert from "node:assert/strict";
import {
  auditOrderTools, effectiveApprovalPolicy, isOrderTool, orderApprovalDecision,
} from "../src/orders.ts";

/* --- which tools the gate claims ------------------------------------------ */

test("isOrderTool: the two mutating tools match, raw and as dsh mints them", () => {
  for (const raw of ["place_order", "cancel_order"]) {
    assert.equal(isOrderTool(raw), true, raw);
    assert.equal(isOrderTool(`mcp__alpaca-kit__${raw}`), true, `mcp__alpaca-kit__${raw}`);
  }
});

test("isOrderTool: a server rename cannot slip a live order tool past", () => {
  // The serverName is the operator's, in their cordis patch, not this repo's.
  assert.equal(isOrderTool("mcp__alpaca__place_order"), true);
  assert.equal(isOrderTool("mcp__broker_prod__cancel_order"), true);
});

test("isOrderTool: the read-only `orders` listing is NOT gated", () => {
  // The trap a substring test for "order" would fall into: `orders` only reads.
  assert.equal(isOrderTool("orders"), false);
  assert.equal(isOrderTool("mcp__alpaca-kit__orders"), false);
  // ...and neither are the other read-only tools that mention orders nowhere.
  assert.equal(isOrderTool("mcp__alpaca-kit__account"), false);
  assert.equal(isOrderTool("mcp__alpaca-kit__positions"), false);
});

/* --- the decision --------------------------------------------------------- */

test("orderApprovalDecision: anything that is not an order tool is none of our business", () => {
  // null, not allow: the caller must delegate to next(), leaving other
  // listeners' decisions intact rather than overriding them with an allow.
  assert.equal(orderApprovalDecision("mcp__alpaca-kit__orders", "ask"), null);
  assert.equal(orderApprovalDecision("bash", "ask"), null);
});

test("orderApprovalDecision: an order under policy `ask` raises a card", () => {
  const decision = orderApprovalDecision("mcp__alpaca-kit__place_order", "ask");
  assert.equal(decision?.kind, "ask");
});

test("orderApprovalDecision: under policy `never` it denies ITSELF, and says nobody was asked", () => {
  // Returning `ask` here would be worse than useless: ApprovalService
  // short-circuits on `never` before any answerer runs, and dsh-tools renders
  // that as `the user rejected tool "..."` - false, because nobody was asked.
  const decision = orderApprovalDecision("mcp__alpaca-kit__place_order", "never");
  assert.equal(decision?.kind, "deny");
  const reason = decision?.kind === "deny" ? decision.reason : "";
  assert.match(reason, /nobody was asked/i);
  assert.doesNotMatch(reason, /the user rejected/i);
  // It must name the way out, or the operator is stuck with a refusal they cannot explain.
  assert.match(reason, /danger-full-access/);
});

/* --- the policy this all turns on ----------------------------------------- */

test("effectiveApprovalPolicy: override wins, then config, then `ask`", () => {
  const session = {};
  assert.equal(
    effectiveApprovalPolicy({ overrideOf: () => "never", config: { policy: "ask" } }, session),
    "never",
  );
  assert.equal(
    effectiveApprovalPolicy({ overrideOf: () => undefined, config: { policy: "never" } }, session),
    "never",
  );
  assert.equal(effectiveApprovalPolicy({ overrideOf: () => undefined }, session), "ask");
});

test("effectiveApprovalPolicy: a runtime switch to danger-full-access disarms the card, so it denies", () => {
  // The whole reason the policy is read per call rather than once at boot.
  const approval = { overrideOf: () => "never" as const, config: { policy: "ask" as const } };
  const policy = effectiveApprovalPolicy(approval, {});
  assert.equal(orderApprovalDecision("mcp__alpaca-kit__place_order", policy)?.kind, "deny");
});

/* --- the registry cross-check --------------------------------------------- */

test("auditOrderTools: reports the covered order tools", () => {
  const audit = auditOrderTools([
    { name: "mcp__alpaca-kit__place_order", description: "submit a PAPER order (operator-gated)" },
    { name: "mcp__alpaca-kit__cancel_order", description: "cancel a paper order by id (operator-gated)" },
    { name: "mcp__alpaca-kit__orders", description: "list orders" },
    { name: "bash", description: "run a command" },
  ]);
  assert.deepEqual(audit.gated, ["mcp__alpaca-kit__place_order", "mcp__alpaca-kit__cancel_order"]);
  assert.deepEqual(audit.ungated, []);
});

test("auditOrderTools: a renamed operator-gated tool is reported as ungated, not silently missed", () => {
  // The failure the boot assertion exists for: alpaca-kit still marks it, but
  // the name no longer matches, so the gate would cover nothing while the face
  // came up healthy.
  const audit = auditOrderTools([
    { name: "mcp__alpaca-kit__submit_order", description: "submit a PAPER order (operator-gated)" },
  ]);
  assert.deepEqual(audit.gated, []);
  assert.deepEqual(audit.ungated, ["mcp__alpaca-kit__submit_order"]);
});

test("auditOrderTools: an order tool whose description lost the marker is still gated", () => {
  // The other direction of the cross-check: the name is what enforces.
  const audit = auditOrderTools([{ name: "mcp__alpaca-kit__place_order", description: "submit" }]);
  assert.deepEqual(audit.gated, ["mcp__alpaca-kit__place_order"]);
  assert.deepEqual(audit.ungated, []);
});

test("auditOrderTools: an empty registry is empty, not an error", () => {
  // Orders are OFF today - the flag is unset - so this is the normal case, and
  // it must not trip the boot assertion.
  assert.deepEqual(auditOrderTools([]), { gated: [], ungated: [] });
  assert.deepEqual(
    auditOrderTools([{ name: "mcp__alpaca-kit__account", description: "account snapshot" }]),
    { gated: [], ungated: [] },
  );
});
