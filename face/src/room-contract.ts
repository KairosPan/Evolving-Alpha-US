/** The room's optional, bounded contracts. Natural-language discussion remains
 * usable when a member does not produce (or cannot satisfy) the view contract. */

export type StructuredBrief = {
  question: string;
  context?: string;
  evidence?: string[];
  falsification?: string;
  output?: string;
};
export type RoomBrief = string | StructuredBrief;

const BRIEF_FIELD_LIMIT = 4_000;
const BRIEF_TOTAL_LIMIT = 16_000;
const VIEW_BLOCK_LIMIT = 16_000;

/** JSON Schema cannot express the aggregate text budget; normalizeBrief does. */
export const BRIEF_SCHEMA = {
  anyOf: [
    { type: "string", minLength: 1, maxLength: BRIEF_FIELD_LIMIT },
    {
      type: "object",
      additionalProperties: false,
      required: ["question"],
      properties: {
        question: { type: "string", minLength: 1, maxLength: BRIEF_FIELD_LIMIT },
        context: { type: "string", maxLength: BRIEF_FIELD_LIMIT },
        evidence: {
          type: "array", maxItems: 10,
          items: { type: "string", minLength: 1, maxLength: 2_000 },
        },
        falsification: { type: "string", maxLength: BRIEF_FIELD_LIMIT },
        output: { type: "string", maxLength: BRIEF_FIELD_LIMIT },
      },
      description: "A focused question, relevant context and evidence, conditions that would falsify the thesis, and the requested output. All text combined must be at most 16,000 characters.",
    },
  ],
  description: "A non-empty question or a structured discussion brief. A legacy string is limited to 4,000 characters.",
};

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function onlyKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length > 0) throw new Error(`${label} has unknown field(s): ${unknown.join(", ")}.`);
}

/** Count Unicode characters, consistently with JSON Schema's maxLength. */
function charCount(value: string): number { return Array.from(value).length; }

function stringField(value: unknown, label: string, limit: number, nonEmpty = true): string {
  if (typeof value !== "string" || (nonEmpty && value.trim() === "")) {
    throw new Error(`${label} must be ${nonEmpty ? "a non-empty" : "a"} string.`);
  }
  if (charCount(value) > limit) throw new Error(`${label} must be at most ${limit.toLocaleString("en-US")} characters.`);
  return value;
}

function stringList(value: unknown, label: string, maxItems: number, maxLength: number): string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array of strings.`);
  if (value.length > maxItems) throw new Error(`${label} must have at most ${maxItems} items.`);
  return value.map((item, index) => stringField(item, `${label}[${index}]`, maxLength));
}

export function normalizeBrief(value: unknown): RoomBrief {
  if (typeof value === "string") return stringField(value, "brief", BRIEF_FIELD_LIMIT);
  const source = record(value, "brief");
  onlyKeys(source, ["question", "context", "evidence", "falsification", "output"], "brief");
  const brief: StructuredBrief = {
    question: stringField(source.question, "brief.question", BRIEF_FIELD_LIMIT),
  };
  for (const field of ["context", "falsification", "output"] as const) {
    if (Object.hasOwn(source, field)) brief[field] = stringField(source[field], `brief.${field}`, BRIEF_FIELD_LIMIT, false);
  }
  if (Object.hasOwn(source, "evidence")) brief.evidence = stringList(source.evidence, "brief.evidence", 10, 2_000);
  const text = [brief.question, brief.context ?? "", brief.falsification ?? "", brief.output ?? "", ...(brief.evidence ?? [])];
  if (text.reduce((total, part) => total + charCount(part), 0) > BRIEF_TOTAL_LIMIT) {
    throw new Error("brief's combined text must be at most 16,000 characters.");
  }
  return brief;
}

export function formatBrief(brief: RoomBrief): string {
  if (typeof brief === "string") return brief;
  const sections = [`Question: ${brief.question}`];
  if (brief.context) sections.push(`Context: ${brief.context}`);
  if (brief.evidence?.length) sections.push(`Evidence to examine:\n${brief.evidence.map((item) => `- ${item}`).join("\n")}`);
  if (brief.falsification) sections.push(`Falsification conditions: ${brief.falsification}`);
  if (brief.output) sections.push(`Requested output: ${brief.output}`);
  return sections.join("\n\n");
}

export type MemberView = {
  position: string;
  evidence: string[];
  uncertainties: string[];
  changeConditions: string[];
  disagreements: { with: string; point: string }[];
};

function normalizeMemberView(value: unknown, rosterIds: readonly string[], self: string): MemberView {
  const source = record(value, "room-view");
  onlyKeys(source, ["position", "evidence", "uncertainties", "changeConditions", "disagreements"], "room-view");
  const view: MemberView = {
    position: stringField(source.position, "room-view.position", 2_000),
    evidence: [], uncertainties: [], changeConditions: [], disagreements: [],
  };
  for (const field of ["evidence", "uncertainties", "changeConditions"] as const) {
    if (Object.hasOwn(source, field)) view[field] = stringList(source[field], `room-view.${field}`, 6, 1_500);
  }
  if (Object.hasOwn(source, "disagreements")) {
    if (!Array.isArray(source.disagreements)) throw new Error("room-view.disagreements must be an array.");
    if (source.disagreements.length > 6) throw new Error("room-view.disagreements must have at most 6 items.");
    view.disagreements = source.disagreements.map((item, index) => {
      const label = `room-view.disagreements[${index}]`;
      const disagreement = record(item, label);
      onlyKeys(disagreement, ["with", "point"], label);
      const withId = stringField(disagreement.with, `${label}.with`, 1_500);
      if (withId === self || !rosterIds.includes(withId)) throw new Error(`${label}.with must name another bot on this channel's roster.`);
      return { with: withId, point: stringField(disagreement.point, `${label}.point`, 1_500) };
    });
  }
  return view;
}

/** Accept only a final, standalone room-view fence. A malformed contract is
 * diagnostic metadata, never a reason to discard the member's answer. */
export function parseMemberView(text: string, rosterIds: readonly string[], self: string): { view?: MemberView; prose: string; issue?: string } {
  const starts = [...text.matchAll(/(^|\r?\n)```room-view[ \t]*\r?\n/g)];
  const last = starts.at(-1);
  if (!last) return { prose: text };
  const start = last.index! + last[1].length;
  const tail = text.slice(start);
  const bodyStart = last[0].length - last[1].length;
  const bodyAndClose = tail.slice(bodyStart);
  const close = /(^|\r?\n)```[ \t]*(?=\r?\n|$)/.exec(bodyAndClose);
  if (!close || !/^(?:[ \t]|\r?\n)*$/.test(bodyAndClose.slice(close.index + close[0].length))) return { prose: text };
  try {
    if (charCount(tail) > VIEW_BLOCK_LIMIT) throw new Error("room-view block must be at most 16,000 characters.");
    const view = normalizeMemberView(JSON.parse(bodyAndClose.slice(0, close.index)) as unknown, rosterIds, self);
    return { view, prose: text.slice(0, start).trimEnd() };
  } catch (error) {
    return { prose: text, issue: error instanceof Error ? error.message : "Invalid room-view block." };
  }
}

export const MEMBER_VIEW_INSTRUCTIONS = `Give your normal answer in your own role's voice. Then append exactly one final fenced block named room-view containing a JSON object:
\`\`\`room-view
{"position":"Your present conclusion","evidence":["Source, publication/as-of date, and what it supports"],"uncertainties":["What remains unknown"],"changeConditions":["Evidence that would make you revise your conclusion"],"disagreements":[{"with":"another bot's roster id","point":"The specific point you dispute"}]}
\`\`\`
Position is required, non-empty, and at most 2,000 characters. Arrays may be omitted or empty; each has at most 6 entries. Each text entry and disagreement point is at most 1,500 characters. The entire block is at most 16,000 characters. Use only the named fields and valid JSON. Do not invent evidence, sources, dates, or certainty; leave arrays empty when unknown. Distinguish a publication date from the date the evidence describes.
Declare disagreements only with another roster member's actual view that you have seen in this round. In a fresh parallel round you have not seen the other independent answers: do not anticipate or invent their views. An empty disagreements list does not establish agreement.
The UI consumes this block as a comparison table; the raw JSON is not intended as the displayed answer. If you have nothing to add, an exact (pass) remains allowed; do not append a block to it.`;

export type RoundView = { bot: string; name: string; sessionId: string; turn?: number; view: MemberView };
export type DiscussionSummary = { brief?: RoomBrief; views: RoundView[]; unstructuredBots: string[] };

function excerpt(text: string, limit: number): string {
  const chars = Array.from(text);
  if (chars.length <= limit) return text;
  const suffix = " … [abridged]";
  return chars.slice(0, Math.max(0, limit - charCount(suffix))).join("") + suffix.slice(0, limit);
}

/** Labels describe reported claims, not independently verified facts. */
export function formatDiscussionSummary(summary: DiscussionSummary): string {
  const head = ["Discussion comparison (member-reported claims; these are evidence, not a verdict)."];
  if (summary.brief !== undefined) head.push(`Round brief:\n${excerpt(formatBrief(summary.brief), 1_500)}`);
  const foot: string[] = [];
  if (summary.unstructuredBots.length) {
    foot.push(`Answers without a valid structured view: ${excerpt(summary.unstructuredBots.map((id) => `@${id}`).join(", "), 1_000)}. Read their original answers in this conversation; they remain part of the discussion.`);
  }
  foot.push("This summary uses excerpts and may omit evidence or details. Read the original answers in this conversation for the full positions; [abridged] marks a shortened excerpt.");
  foot.push("Kairos: compare the members' actual claims before drawing your own conclusion. Name disagreements in facts, interpretation, and risk preferences; distinguish missing evidence from opposing evidence. No declared disagreement is not consensus, and the number of voices is not a vote. Then give your conclusion and the next evidence to check, including what could change that conclusion.");
  const fixedLength = charCount([...head, ...foot].join("\n\n"));
  const rowBudget = Math.max(0, Math.floor((12_000 - fixedLength - summary.views.length * 2) / Math.max(1, summary.views.length)));
  const fieldBudget = Math.min(180, Math.max(12, Math.floor((rowBudget - 650) / 7)));
  const rows = summary.views.map((row) => {
    const lines = [`${excerpt(row.name, 80)} (@${excerpt(row.bot, 80)})${row.turn === undefined ? "" : `, turn ${row.turn}`}:`, `Position: ${excerpt(row.view.position, fieldBudget * 2)}`];
    if (row.view.evidence.length) lines.push(`Evidence cited (excerpt):\n- ${excerpt(row.view.evidence[0], fieldBudget)}`);
    lines.push(row.view.disagreements.length
      ? `Declared disagreements (excerpts):\n${row.view.disagreements.slice(0, 2).map((item) => `- With @${excerpt(item.with, 80)}: ${excerpt(item.point, fieldBudget)}`).join("\n")}`
      : "Declared disagreements: none supplied (not evidence of consensus).");
    lines.push(`Uncertainties: ${row.view.uncertainties.length ? `\n- ${excerpt(row.view.uncertainties[0], fieldBudget)}` : "none supplied (not evidence of certainty)."}`);
    lines.push(`Conditions for changing view: ${row.view.changeConditions.length ? `\n- ${excerpt(row.view.changeConditions[0], fieldBudget)}` : "none supplied."}`);
    return excerpt(lines.join("\n"), rowBudget);
  });
  return [...head, ...rows, ...foot].join("\n\n");
}
