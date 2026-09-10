import test from "node:test";
import assert from "node:assert/strict";
import {
  BRIEF_SCHEMA, formatBrief, formatDiscussionSummary, MEMBER_VIEW_INSTRUCTIONS, normalizeBrief, parseMemberView,
  type DiscussionSummary, type MemberView, type StructuredBrief,
} from "../src/room-contract.ts";

const roster = ["value", "news", "macro"];
const fence = (value: unknown, prose = "My answer."): string => `${prose}${prose ? "\n\n" : ""}\`\`\`room-view\n${JSON.stringify(value)}\n\`\`\``;
const emptyView = (position = "Wait for evidence."): MemberView => ({ position, evidence: [], uncertainties: [], changeConditions: [], disagreements: [] });

test("brief keeps legacy text intact and accepts a structured question without inventing fields", () => {
  assert.equal(normalizeBrief("  What would falsify this?\n"), "  What would falsify this?\n");
  assert.deepEqual(normalizeBrief({ question: "What would falsify this?" }), { question: "What would falsify this?" });
  const source: StructuredBrief = {
    question: "增长能持续吗？", context: "当前结论尚待查证。", evidence: ["FY 2025 filing, published 2026-02-15"],
    falsification: "客户留存显著下降。", output: "独立判断、证据和改判条件。",
  };
  const brief = normalizeBrief(source);
  assert.deepEqual(brief, source);
  assert.notEqual(brief, source);
  assert.notEqual((brief as StructuredBrief).evidence, source.evidence, "caller mutation cannot change the normalized array");
  assert.equal(formatBrief("original"), "original");
  const rendered = formatBrief(source);
  for (const text of [source.question, source.context!, source.evidence![0], source.falsification!, source.output!]) assert.ok(rendered.includes(text));
  assert.equal(formatBrief({ question: "q", context: "", evidence: [] }), "Question: q");
});

test("brief rejects unknown keys and type mismatches, including malformed optional fields", () => {
  for (const value of [null, [], 3, "", " \n", {}, { question: "" }, { question: "q", typo: "x" },
    { question: "q", context: 3 }, { question: "q", output: null }, { question: "q", evidence: "source" },
    { question: "q", evidence: [" "] }, { question: "q", evidence: [3] }, { question: "q", evidence: undefined },
    new Date(), JSON.parse('{"question":"q","__proto__":"x"}')]) {
    assert.throws(() => normalizeBrief(value), Error, JSON.stringify(value));
  }
});

test("brief enforces field, evidence count and combined budgets with Unicode character lengths", () => {
  assert.equal(normalizeBrief("🌱".repeat(4_000)), "🌱".repeat(4_000));
  assert.throws(() => normalizeBrief("x".repeat(4_001)), /4,000/);
  assert.throws(() => normalizeBrief({ question: "q", context: "x".repeat(4_001) }), /4,000/);
  assert.throws(() => normalizeBrief({ question: "q", evidence: ["x".repeat(2_001)] }), /2,000/);
  assert.throws(() => normalizeBrief({ question: "q", evidence: Array(11).fill("source") }), /10 items/);
  assert.deepEqual(normalizeBrief({ question: "q", evidence: Array(10).fill("source") }), { question: "q", evidence: Array(10).fill("source") });
  const full = { question: "q".repeat(4_000), context: "c".repeat(4_000), output: "o".repeat(4_000), falsification: "f".repeat(4_000) };
  assert.deepEqual(normalizeBrief(full), full);
  assert.throws(() => normalizeBrief({ ...full, evidence: ["x"] }), /combined text/);
  assert.deepEqual(BRIEF_SCHEMA.anyOf[1].required, ["question"]);
  assert.equal(BRIEF_SCHEMA.anyOf[1].additionalProperties, false);
});

test("member view is optional: ordinary prose, pass, inline and nonterminal fences stay unchanged", () => {
  const samples = ["A natural answer.", "(pass)", "", 'inline ```room-view\n{"position":"x"}\n```',
    `${fence({ position: "x" })}\nA final qualification.`, '```room-view\n{"position":"x"}',
    '```json\n{"position":"x"}\n```', `${fence({ position: "x" })}\nMore prose.\n\`\`\`json\n{}\n\`\`\``];
  for (const text of samples) assert.deepEqual(parseMemberView(text, roster, "value"), { prose: text });
});

test("member view strips only the final valid fence, defaults lists, and preserves the prose", () => {
  assert.deepEqual(parseMemberView(fence({ position: "Cautious." }, "  Natural answer."), roster, "value"), {
    prose: "  Natural answer.", view: emptyView("Cautious."),
  });
  assert.deepEqual(parseMemberView(fence({ position: "Cautious." }, ""), roster, "value"), { prose: "", view: emptyView("Cautious.") });
  const crlf = `${fence({ position: "Cautious." }).replaceAll("\n", "\r\n")}\r\n  `;
  assert.equal(parseMemberView(crlf, roster, "value").view?.position, "Cautious.");
  const earlier = `${fence({ position: "Earlier quoted claim." })}\nThen I changed my mind.`;
  assert.equal(parseMemberView(fence({ position: "Later claim." }, earlier), roster, "value").prose, earlier);
});

test("member view retains evidence, uncertainty, change conditions, and a real peer target", () => {
  const view: MemberView = {
    position: "Do not infer recurring growth from a single contract.",
    evidence: ["Company filing published 2026-02-15, FY 2025: revenue grew."],
    uncertainties: ["Renewal rate is not disclosed."], changeConditions: ["Two further periods of retention data."],
    disagreements: [{ with: "news", point: "The cited contract supports a sale, not repeatability." }],
  };
  assert.deepEqual(parseMemberView(fence(view), roster, "value"), { prose: "My answer.", view });
});

test("invalid member contracts preserve the whole answer and expose an issue", () => {
  const invalid = [null, [], {}, { position: " " }, { position: "x", future: true },
    { position: "x", evidence: null }, { position: "x", evidence: [9] }, { position: "x", uncertainties: [""] },
    { position: "x", changeConditions: "y" }, { position: "x", disagreements: {} },
    { position: "x", disagreements: [{ with: "value", point: "Self" }] },
    { position: "x", disagreements: [{ with: "absent", point: "Not present" }] },
    { position: "x", disagreements: [{ with: "news", point: " " }] },
    { position: "x", disagreements: [{ with: "news", point: "p", extra: "bad" }] },
    { position: "x", disagreements: [null] }];
  for (const value of invalid) {
    const text = fence(value);
    const parsed = parseMemberView(text, roster, "value");
    assert.equal(parsed.prose, text);
    assert.equal(parsed.view, undefined);
    assert.ok(parsed.issue, JSON.stringify(value));
  }
  const badJson = "The claim still matters.\n```room-view\n{bad json}\n```";
  assert.equal(parseMemberView(badJson, roster, "value").prose, badJson);
  assert.ok(parseMemberView(badJson, roster, "value").issue);
});

test("member contract budgets bound position, list entries/count, disagreements and whole block", () => {
  for (const value of [
    { position: "x".repeat(2_001) }, { position: "x", evidence: ["e".repeat(1_501)] },
    { position: "x", uncertainties: Array(7).fill("u") }, { position: "x", changeConditions: Array(7).fill("c") },
    { position: "x", disagreements: Array(7).fill({ with: "news", point: "p" }) },
    { position: "x", disagreements: [{ with: "news", point: "p".repeat(1_501) }] },
    { position: "x".repeat(2_000), evidence: Array(6).fill("e".repeat(1_500)), uncertainties: Array(6).fill("u".repeat(1_500)) },
  ]) {
    const text = fence(value);
    const parsed = parseMemberView(text, roster, "value");
    assert.equal(parsed.prose, text);
    assert.ok(parsed.issue);
  }
  const valid = { position: "🌱".repeat(2_000), evidence: Array(6).fill("e".repeat(1_500)) };
  assert.ok(parseMemberView(fence(valid), roster, "value").view, "Unicode counts match the schema limits");
});

test("instructions permit pass and prohibit fabricated sources and unseen parallel disagreements", () => {
  assert.match(MEMBER_VIEW_INSTRUCTIONS, /exact \(pass\)/);
  assert.match(MEMBER_VIEW_INSTRUCTIONS, /Do not invent evidence, sources, dates/);
  assert.match(MEMBER_VIEW_INSTRUCTIONS, /fresh parallel round/);
  assert.match(MEMBER_VIEW_INSTRUCTIONS, /actual view that you have seen in this round/);
  assert.match(MEMBER_VIEW_INSTRUCTIONS, /empty disagreements list does not establish agreement/);
});

test("summary preserves disagreement distinctions and sends unstructured answers back to their originals", () => {
  const summary: DiscussionSummary = {
    brief: { question: "Is growth repeatable?", falsification: "Renewals fall." },
    views: [
      { bot: "value", name: "Value", sessionId: "s1", turn: 2, view: {
        ...emptyView("Wait."), uncertainties: ["Retention unknown."], changeConditions: ["Renewal disclosure."],
        disagreements: [{ with: "news", point: "A sale is not recurring growth." }],
      } },
      { bot: "news", name: "News", sessionId: "s2", view: emptyView("The contract was announced.") },
    ],
    unstructuredBots: ["macro"],
  };
  const text = formatDiscussionSummary(summary);
  for (const expected of ["Is growth repeatable?", "Renewals fall.", "Value (@value), turn 2", "Wait.",
    "With @news: A sale is not recurring growth.", "Retention unknown.", "Renewal disclosure.", "@macro", "Read their original answers",
    "not evidence of consensus", "facts, interpretation, and risk preferences", "next evidence to check"]) assert.ok(text.includes(expected), expected);
});

test("summary remains below 12,000 characters and covers each voice without mutating stored views", () => {
  const summary: DiscussionSummary = {
    brief: { question: "q".repeat(4_000), context: "c".repeat(4_000), evidence: Array(4).fill("e".repeat(2_000)) },
    views: Array.from({ length: 10 }, (_, index) => ({
      bot: `bot-${index}`, name: `Voice ${index}`, sessionId: `session-${index}`, turn: index + 1,
      view: { position: "p".repeat(2_000), evidence: Array(6).fill("e".repeat(1_500)), uncertainties: Array(6).fill("u".repeat(1_500)),
        changeConditions: Array(6).fill("c".repeat(1_500)), disagreements: Array(6).fill({ with: "another", point: "d".repeat(1_500) }) },
    })),
    unstructuredBots: ["legacy"],
  };
  const before = JSON.stringify(summary);
  const text = formatDiscussionSummary(summary);
  assert.ok(Array.from(text).length <= 12_000, `length: ${Array.from(text).length}`);
  assert.match(text, /\[abridged\]/);
  assert.match(text, /Read the original answers/);
  for (let index = 0; index < 10; index++) assert.ok(text.includes(`Voice ${index} (@bot-${index})`));
  assert.equal(text.match(/Conditions for changing view:/g)?.length, 10);
  assert.equal(text.match(/Uncertainties:/g)?.length, 10);
  assert.equal(text.match(/Declared disagreements/g)?.length, 10);
  assert.equal(JSON.stringify(summary), before);
});
