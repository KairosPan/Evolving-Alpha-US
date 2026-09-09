/** The working page: sessions sidebar, transcript, composer, answerable cards.
 *
 * The impure half of the client. `mapper.js` decides what a frame MEANS;
 * this module decides where it goes on screen and what the operator can do
 * about it. It holds every piece of state the flow needs and nothing else.
 *
 * THE FOUR THINGS A DUMB APPENDER WOULD GET WRONG, and how this one does not:
 *
 *   1. `surfaceOp`. A compaction checkpoint arrives as an ordinary bubble
 *      carrying `{op:'replace', start, end}` — an instruction to STOP showing
 *      the inclusive seq range it summarizes. Rendered nodes are therefore
 *      indexed by seq (`bySeq`) so the shadowed range can be dropped before the
 *      summary lands. Ignore it and the page shows the summary AND everything
 *      it replaced.
 *   2. `interrupted`. A cancelled turn logs the PREFIX that had arrived, not an
 *      answer. Such a bubble renders cut (an em-dash and a marker tag) so a
 *      half-sentence can never be read as Kairos's finished reply.
 *   3. `source`. A `user/message` is not automatically the operator's: plugins
 *      inject file-change notices, skill content and cron wake-ups through the
 *      same event. Anything whose source is not `user` renders as a quiet
 *      centred note, never as an operator bubble.
 *   4. Ordering and duplication. History backfill and the live stream deliver
 *      the same events; frames that arrive mid-backfill are QUEUED and flushed
 *      after it, and `seen` (sessionId:seq) drops the overlap. Appending a live
 *      frame before the backfill it precedes would put the transcript out of
 *      order for the rest of the page's life.
 *
 * THE RPC SURFACE IS CLOSED:
 * `session.list/create/history/prompt/cancel/rename/fork`,
 * `host.pickDirectory` (the strategy picker's native folder dialog),
 * `host.describe` / `settings.describe` / `credentials.describe` (the agent
 * panel's three reads), `respond`, and `events.mux`. Answering a gate goes
 * through `respond`, never `rpc` — a different envelope entirely (see api.js).
 * @module
 */
import { rpc, respond, openMux } from "./api.js";
import { mapFrame } from "./mapper.js";
import { renderResult } from "./render.js";
import { renderMarkdown } from "./markdown.js";
import { renderChannelPage } from "./channels.js";
import { ARCHIVED_KEY, bucketFor, isBotKey, UNGROUPED_KEY } from "./grouping.js";
import { proposeBotId } from "./botId.js";
import { foldChannelName } from "./channelName.js";
import { HOST_NAME, speakerFor } from "./speaker.js";
import { avatarGlyph, foldMembers, roundEndLine, stripChips } from "./room.js";

/** Rendered in place of a value the host did not give us. */
const EM = "—";

/** How long the sidebar waits after the last rendered event before refetching.
 * Titles, `updatedAt` and `running` are list-only facts: the title projection
 * lands seconds after a first prompt and would otherwise sit stale until a
 * reload. Trailing edge, so a busy turn costs exactly one call. */
const LIST_REFRESH_MS = 1200;

/** Autoscroll only while the operator is already at the tail; scrolling someone
 * back down mid-read is worse than a missed frame. */
const STICK_PX = 120;

/* ---------- state ---------- */

/** @type {string|null} The session on screen; `null` is an unsaved new one — no
 * session exists until the first prompt, so the "+ new" button litters nothing. */
let activeSession = null;
/** Dedupe key set, `sessionId:seq`, across backfill and stream. @type {Set<string>} */
const seen = new Set();
/** seq → the node it rendered, the index `surfaceOp: replace` needs. @type {Map<number, HTMLElement>} */
const bySeq = new Map();
/** callId → its card, so a `tool/result` completes the call's card instead of
 * opening a nameless second one (the result event carries no tool name).
 * @type {Map<string, HTMLElement>} */
const toolCards = new Map();
/** rpcId → the still-unanswered approval/question view, for EVERY session. The
 * mux replays pending gates on reconnect but history never does, so this is
 * what survives a session switch. @type {Map<string, Record<string, any>>} */
const gates = new Map();
/** rpcId → its card in the CURRENT flow; cleared on every session switch. @type {Map<string, HTMLElement>} */
const gateNodes = new Map();

/** rpcIds this tab is answering right now. The host broadcasts a gate's
 * resolution from INSIDE its respond handler, before the HTTP receipt is even
 * serialized, so the echo normally reaches {@link acceptGateResolved} while the
 * clicking handler is still awaiting `respond()`. Without this the echo would
 * settle the card first, in the WIRE's vocabulary - an approval's outcome is an
 * ApprovalOutcome and never the string `answered`, so a card the operator just
 * approved would read `closed · allowed-once`, and `closed` is the word this
 * client uses for a gate that died with nobody answering it. Whoever answered
 * owns the wording. */
const answering = new Set();
/** sessionId → its sidebar row. @type {Map<string, HTMLElement>} */
const convRows = new Map();
/** Live frames held while a history page is in flight. @type {unknown[]} */
const queued = [];
/** The session whose history is loading, or null. Frames queue while it is set. @type {string|null} */
let loadingSession = null;
/** Open-session generation; a stale continuation must not touch a newer flow. */
let openSeq = 0;
/** session.list generation, so a slow answer cannot overwrite a fresh list. */
let listSeq = 0;
/** Trailing-edge handle for the sidebar refresh. @type {ReturnType<typeof setTimeout>|null} */
let listTimer = null;
/** sessionId → (projection key → {seq, value}): the whole-value store the
 * `session/projection` frames and history/list projection blocks feed. Every
 * session's units are kept, not just the active one's — the agent panel reads
 * whichever session is on screen when it renders. @type {Map<string, Map<string, {seq: number, value: unknown}>>} */
const projStore = new Map();

/* ---------- the participants strip ---------- */

/** The room on screen, from `/data/rooms/state`: the channel's bot roster and
 * the members the engine has driven this boot. `null` when the active session
 * is in no channel. @type {{roster: any[], members: Record<string, any>}|null} */
let roomInfo = null;
/** Live fine states of member sessions (thinking / writing / tool) from their
 * own pulses; cleared at their turn boundaries. Presence, not truth. @type {Map<string, string>} */
const fineStates = new Map();

/** The member session ids of the room on screen: the header fold ∪ what the engine reports. */
function memberSessionIds() {
  const ids = new Set((memberFold.rooms.get(activeSession ?? "") ?? []).map((m) => String(m.sessionId)));
  for (const m of Object.values(roomInfo?.members ?? {})) if (typeof m?.sessionId === "string") ids.add(m.sessionId);
  return ids;
}

/** Refetch the room state for the session on screen; a session in no channel reads `null`. */
async function loadRoomInfo() {
  const id = activeSession;
  if (id === null) { roomInfo = null; renderStrip(); return; }
  try {
    const body = await panelData("/data/rooms/state", { sessionId: id });
    if (activeSession !== id) return;
    roomInfo = { roster: Array.isArray(body.roster) ? body.roster : [], members: body.members ?? {} };
  } catch {
    if (activeSession !== id) return;
    roomInfo = null; // 404: not in a channel - no strip
  }
  renderStrip();
}

/** Kairos's own chip says `organizing` or nothing at all: the host is not a
 * called voice, so the bots' vocabulary would misread on it. */
const KAIROS_STATES = { organizing: "organizing", idle: "" };
/** Draw the strip for the session on screen, or hide it. */
function renderStrip() {
  const strip = $("#strip");
  const projection = activeSession === null ? undefined : projStore.get(activeSession)?.get("room")?.value;
  const isRoom = projection !== null && typeof projection === "object" && /** @type {any} */ (projection).kind === "room";
  if (roomInfo === null || (roomInfo.roster.length === 0 && !isRoom)) { strip.hidden = true; strip.replaceChildren(); return; }
  const running = lastSessions.find((s) => String(s.sessionId) === activeSession)?.running === true;
  const chips = stripChips({
    roster: roomInfo.roster.filter((b) => b.id !== "kairos"),
    projection,
    members: roomInfo.members,
    gates: new Set([...gates.values()].map((g) => g.sessionId)),
    fine: fineStates,
    running,
    kairosName: HOST_NAME,
  });
  strip.replaceChildren();
  for (const chip of chips) {
    const node = el("span", chip.kairos ? "strip-chip kairos" : "strip-chip");
    node.dataset.state = chip.state;
    if (!chip.kairos) node.append(el("span", "avatar", avatarGlyph(chip.id)));
    node.append(el("span", "strip-name", chip.name));
    node.append(el("span", "strip-state", chip.kairos ? (KAIROS_STATES[chip.state] ?? chip.state) : chip.state));
    if (chip.broken) { node.classList.add("broken"); node.title = `dsh cannot mount this bot: ${chip.broken}`; }
    if (chip.sessionId) {
      node.title = `session ${chip.sessionId}`;
      node.classList.add("open");
      node.addEventListener("click", () => void openSession(String(chip.sessionId)));
    }
    strip.append(node);
  }
  strip.hidden = false;
}

/* ---------- dom helpers ---------- */

/** @param {string} sel @returns {HTMLElement} the element, which the page guarantees exists. */
const $ = (sel) => /** @type {HTMLElement} */ (document.querySelector(sel));

/**
 * Build one element. Text always goes through `textContent`: every string here
 * is host data, and the page has no `innerHTML` path at all.
 * @param {string} tag @param {string|null} [cls] @param {string} [text] @returns {HTMLElement}
 */
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** @param {unknown} value @returns {string} the value as text, em-dash when absent or blank. */
function dash(value) {
  return value === null || value === undefined || value === "" ? EM : String(value);
}

/** @returns {HTMLElement} the message column (content), whose scroller is `#scroll`. */
const flow = () => $("#flow");

/** @returns {boolean} whether the transcript is scrolled to (or near) its tail. */
function atTail() {
  const box = $("#scroll");
  return box.scrollHeight - box.scrollTop - box.clientHeight < STICK_PX;
}

/** Pin the transcript to its tail. */
function toTail() {
  const box = $("#scroll");
  box.scrollTop = box.scrollHeight;
}

/**
 * Say something on the composer's note line — the page's one status channel.
 * @param {unknown} message - text, or an Error whose message is shown.
 * @param {boolean} [bad] - render it as a failure.
 */
function status(message, bad = false) {
  const note = $("#status");
  note.textContent = message instanceof Error ? message.message : String(message);
  note.classList.toggle("err", bad);
}

/** @param {unknown} err @param {string} what - the operation that failed. */
function failed(err, what) {
  status(`${what}: ${err instanceof Error ? err.message : String(err)}`, true);
}

/* ---------- transcript: placement ---------- */

/**
 * Obey a view's surface intent, dropping every node the event shadows.
 *
 * `replace` is inclusive on both ends and names SEQS, not nodes: a range can
 * cover events that rendered nothing (log-only ones) and events that rendered
 * into a shared node (a tool result merged into its call). Nodes are collected
 * first and removed by identity, so a shared node is dropped once and every seq
 * pointing at it is forgotten.
 * @param {Record<string, any>} view - the arriving view.
 */
function honourSurfaceOp(view) {
  const op = view.surfaceOp;
  if (!op || op === "append") return;
  /** @type {Set<HTMLElement>} */
  const doomed = new Set();
  for (const [seq, node] of bySeq) {
    if (seq >= op.start && seq <= op.end) doomed.add(node);
  }
  if (doomed.size === 0) return;
  for (const node of doomed) node.remove();
  for (const [seq, node] of [...bySeq]) if (doomed.has(node)) bySeq.delete(seq);
  for (const [callId, node] of [...toolCards]) if (doomed.has(node)) toolCards.delete(callId);
}

/**
 * Append a node for one session event and index it by seq.
 * @param {Record<string, any>} view @param {HTMLElement} node
 */
function place(view, node) {
  const stick = atTail();
  flow().append(node);
  index(view, node);
  if (stick) toTail();
}

/** Record which node rendered a seq, for a later `replace`. @param {Record<string, any>} view @param {HTMLElement} node */
function index(view, node) {
  if (typeof view.seq === "number") bySeq.set(view.seq, node);
}

/* ---------- transcript: bubbles ---------- */

/**
 * One message bubble.
 *
 * Three shapes, not two. `op` and `k` are the operator and Kairos; `note` is a
 * user-ROLE message the operator did not write (source `plugin`/`tool`/`model`)
 * — a file-change notice, injected skill content, a cron wake-up. It is quiet
 * and centred precisely so it cannot be mistaken for something the operator said.
 * @param {Record<string, any>} view @returns {HTMLElement}
 */
function bubbleNode(view) {
  /* A member's answer: the bot's own lane and name, an avatar glyph the eye
   * learns, markdown like Kairos's. Attribution is per MESSAGE here - the
   * room log carries several voices - which is what `speaker` (per session)
   * could never say (R12's last mile). */
  if (view.role === "bot") {
    const wrap = el("div", "msg k bot");
    const who = el("div", "who");
    who.append(el("span", "avatar", avatarGlyph(String(view.bot))), el("span", "who-name", String(view.name ?? view.bot)));
    wrap.append(who);
    const bubble = el("div", "bubble md-bubble");
    const md = renderMarkdown(String(view.text ?? ""));
    bubble.append(md.node);
    if (md.doc) wrap.classList.add("doc");
    wrap.append(bubble);
    return wrap;
  }
  const operator = view.role === "operator";
  const injected = operator && typeof view.source === "string" && view.source !== "user";
  if (injected) return contextRow(view);
  const lane = operator ? "op" : "k";

  const wrap = el("div", `msg ${lane}`);
  /* Thinking rides the same message but is never chat text: a collapsed row
   * above the bubble, the bubble itself untouched. A reasoning-only step (the
   * model thought, then went straight to tools) is a think row with no bubble. */
  if (lane === "k" && typeof view.thinking === "string" && view.thinking !== "") {
    wrap.append(thinkRow(view.thinking));
  }
  const hasText = typeof view.text === "string" && view.text !== "";
  if (hasText) {
    if (lane === "k") wrap.append(el("div", "who", speaker));
    /* Kairos writes markdown; the operator's own words render exactly as
     * typed. A markdown answer with document structure (headings, tables)
     * widens its lane — a chat-sized reply keeps the bubble. */
    let bubble;
    if (lane === "k") {
      bubble = el("div", "bubble md-bubble");
      const md = renderMarkdown(view.text);
      bubble.append(md.node);
      if (md.doc) wrap.classList.add("doc");
    } else {
      bubble = el("div", "bubble pre", dash(view.text));
    }
    if (view.interrupted === true) {
      // A cancelled turn logged only the prefix that had arrived. Mark the cut
      // INSIDE the bubble, so the truncation travels with the text itself.
      bubble.classList.add("cut");
      bubble.append(el("span", "cut-mark", ` ${EM}`));
    }
    wrap.append(bubble);
  }
  if (view.interrupted === true) wrap.append(el("span", "tag tag-cut", "interrupted"));
  return wrap;
}

/* ---------- transcript: collapsed process rows ---------- */

/**
 * Head of a collapsible row: chevron · kind · one-line summary (+ trailing
 * spans the caller adds). Clicking the head toggles the node's `collapsed`
 * class; clicks on `.raw` are the raw toggle's own and do not bubble here.
 * @param {HTMLElement} node @param {string} kind @returns {HTMLElement} the head
 */
function collapsibleHead(node, kind) {
  node.classList.add("collapsible", "collapsed");
  const head = el("div", "card-head");
  head.append(el("span", "chev", "▸"));
  head.append(el("span", "kind", kind));
  head.append(el("span", "sum", ""));
  head.addEventListener("click", (ev) => {
    if (ev.target instanceof HTMLElement && ev.target.classList.contains("raw")) return;
    node.classList.toggle("collapsed");
  });
  node.append(head);
  return head;
}

/**
 * An injected user-role message (source plugin/tool/model — AGENTS.md and
 * skill-catalog context, file-change notices, cron wake-ups) as one collapsed
 * line, dsh-style: the injection is a fact worth a row, not a wall of text.
 * @param {Record<string, any>} view @returns {HTMLElement}
 */
function contextRow(view) {
  const text = dash(view.text);
  const node = el("article", "card ctx");
  const head = collapsibleHead(node, `context · ${view.source}`);
  // Prefer the sources the injection itself names; else its first content line.
  const named = [...text.matchAll(/Instructions from: (\S+)/g)].map((m) => m[1]);
  const firstLine = text.split("\n").find((l) => l.trim() !== "" && !l.startsWith("<system-reminder>")) ?? "";
  const sum = head.querySelector(".sum");
  if (sum) sum.textContent = named.length ? named.join(", ") : firstLine.slice(0, 160);
  node.append(el("pre", "tool-out", text));
  return node;
}

/**
 * A message's reasoning as one collapsed line — the operator sees THAT Kairos
 * thought and the first line of what about; the full text is one click away.
 * @param {string} text @returns {HTMLElement}
 */
function thinkRow(text) {
  const node = el("article", "card think");
  const head = collapsibleHead(node, "think");
  const firstLine = text.split("\n").find((l) => l.trim() !== "") ?? "";
  const sum = head.querySelector(".sum");
  if (sum) sum.textContent = firstLine.slice(0, 160);
  node.append(el("pre", "tool-out think-out", text));
  return node;
}

/** A room fact as one quiet centred line: the round end today. @param {Record<string, any>} view */
function roomLineNode(view) {
  const node = el("div", "room-line");
  node.append(el("span", "room-line-text", view.line === "round-end" ? roundEndLine(view) : dash(view.text)));
  node.title = dash(view.text);
  return node;
}

/* ---------- transcript: tool cards ---------- */

/**
 * A tool card in its pending state: named, running, no result yet.
 * @param {Record<string, any>} card - the view's `card` payload.
 * @returns {HTMLElement}
 */
function toolCardNode(card) {
  const node = el("article", "card tool");
  if (typeof card.name === "string") node.dataset.tool = card.name;
  const head = collapsibleHead(node, dash(card.name ?? card.title ?? "tool"));
  head.append(el("span", "producer", "running…"));
  const raw = el("span", "raw", "raw");
  raw.title = dash(card.callId);
  /* pretty ⇄ raw: inert unless a pretty view exists (.has-pretty gates the css). */
  raw.addEventListener("click", () => node.classList.toggle("show-raw"));
  head.append(raw);
  return node;
}

/**
 * Complete a card with its result. Idempotent per node: a re-delivered result
 * replaces the body rather than stacking a second one.
 * @param {HTMLElement} node @param {Record<string, any>} card
 */
function fillResult(node, card) {
  const producer = node.querySelector(".producer");
  if (producer) producer.textContent = card.title ?? (card.isError ? "failed" : "done");
  node.classList.toggle("danger", card.isError === true);
  node.querySelector(".tool-out")?.remove();
  node.querySelector(".viz")?.remove();
  /* Pretty view when the tool and shape are both recognized; the raw pre stays
   * in the DOM as the fallback and as the head's `raw` toggle target. Errors
   * never render pretty. */
  const pretty = card.isError === true ? null : renderResult(node.dataset.tool ?? "", card.text);
  node.classList.toggle("has-pretty", pretty !== null);
  if (pretty) node.append(pretty);
  const out = el("pre", "tool-out", dash(card.text));
  if (card.isError === true) out.classList.add("err");
  node.append(out);
  /* the collapsed row's one-line summary: the pretty view's own meta line when
   * there is one, else the result's first content line (errors included — the
   * row should say what went wrong without a click). */
  const sum = node.querySelector(".card-head .sum");
  if (sum) {
    const meta = pretty?.querySelector(".viz-meta")?.textContent;
    const firstLine = dash(card.text).split("\n").find((l) => l.trim() !== "") ?? "";
    sum.textContent = (meta ?? firstLine).slice(0, 160);
  }
  if (node.dataset.tool === "dispatch") node.classList.add("dispatch");
}

/**
 * Render a `tool/call` or `tool/result` view.
 *
 * A result completes the card its call opened, which is also the only way the
 * result gets a NAME: `tool/result` carries the message, never the tool name.
 * A result whose call is unknown (or whose card a compaction just dropped)
 * opens its own card rather than being lost.
 * @param {Record<string, any>} view
 */
function acceptCard(view) {
  const card = view.card ?? {};
  if (card.phase === "result" && typeof card.callId === "string") {
    const open = toolCards.get(card.callId);
    if (open && open.isConnected) {
      const stick = atTail();
      fillResult(open, card);
      index(view, open); // the result's seq shares the call's node
      if (stick) toTail();
      return;
    }
  }
  const node = toolCardNode(card);
  if (card.phase === "result") fillResult(node, card);
  place(view, node);
  if (card.phase === "call" && typeof card.callId === "string") toolCards.set(card.callId, node);
}

/* ---------- gates: approvals and questions ---------- */

/**
 * Settle a gate's card: the buttons go, the outcome stays. Idempotent — the
 * host echoes a resolution for the answer this client just sent, and by then
 * there is no `.card-actions` left to replace.
 * @param {HTMLElement} node @param {string} outcome - what was sent, in the operator's words.
 * @param {string} [verb] - `answered` when we answered it; `closed` when the host settled it for us.
 */
function settle(node, outcome, verb = "answered") {
  node.classList.add("answered");
  // A question's outcome IS the verb ("answered"), so it is said once.
  const line = verb === outcome ? verb : `${verb} · ${outcome}`;
  node.querySelector(".card-actions")?.replaceWith(el("div", "card-line", line));
}

/**
 * The approval card: the Gate-2 surface. Two outcomes and only two —
 * `cancelled` and `unavailable` are host-side and no client may send them.
 * @param {Record<string, any>} view - an `approval` view.
 * @returns {HTMLElement}
 */
function approvalNode(view) {
  const node = el("article", "card ask");
  const head = el("div", "card-head");
  head.append(el("span", "kind", "approval"));
  head.append(el("span", "producer", dash(view.toolName)));
  const raw = el("span", "raw", "raw");
  raw.title = `approvalId ${dash(view.approvalId)} · callId ${dash(view.callId)}`;
  head.append(raw);
  node.append(head);
  if (view.reason) node.append(el("div", "card-line", view.reason));

  const actions = el("div", "card-actions");
  /** @param {string} label @param {"allowed-once"|"rejected"} outcome @param {string} cls */
  const button = (label, outcome, cls) => {
    const btn = el("button", `ask-btn ${cls}`, label);
    /** @type {HTMLButtonElement} */ (btn).type = "button";
    btn.addEventListener("click", async () => {
      const buttons = [.../** @type {NodeListOf<HTMLButtonElement>} */ (actions.querySelectorAll("button"))];
      for (const b of buttons) b.disabled = true;
      answering.add(view.id); // claim the wording before the host can echo it back
      try {
        await respond(view.id, {
          sessionId: view.sessionId ?? activeSession,
          approvalId: view.approvalId,
          outcome,
        });
        gates.delete(view.id);
        settle(node, label.toLowerCase());
        status(`approval ${outcome}`);
      } catch (err) {
        // A refused answer ("not-pending", a dead socket) must leave the gate
        // answerable: re-enable and say why rather than stranding the turn.
        answering.delete(view.id);
        for (const b of buttons) b.disabled = false;
        failed(err, "respond");
      }
    });
    return btn;
  };
  actions.append(button("Approve", "allowed-once", "allow"));
  actions.append(button("Deny", "rejected", "deny"));
  node.append(actions);
  return node;
}

/**
 * The question card. One `ask()` is one card and ONE answer: the batch is
 * answered as a whole, never split per question, so the card collects every
 * question's picks and submits them together.
 * @param {Record<string, any>} view - a `question` view.
 * @returns {HTMLElement}
 */
function questionNode(view) {
  const node = el("article", "card ask");
  const head = el("div", "card-head");
  // `.kind` is `text-transform: uppercase` (chat.css), so the case written
  // here never reaches the screen - the name goes in as the roster spells it.
  head.append(el("span", "kind", `${speaker} asks`));
  head.append(el("span", "producer", ""));
  node.append(head);

  const questions = Array.isArray(view.questions) ? view.questions : [];
  /** One editable answer per question, in the order the batch declared them.
   * @type {{id: string, selected: Set<string>, custom: string}[]} */
  const picks = questions.map((q, i) => ({
    id: typeof q?.id === "string" ? q.id : String(i),
    selected: new Set(),
    custom: "",
  }));

  const actions = el("div", "card-actions");
  const submit = el("button", "ask-btn allow", "Send");
  const submitBtn = /** @type {HTMLButtonElement} */ (submit);
  submitBtn.type = "button";

  /** Every question needs an answer before the batch can go. */
  const sync = () => {
    submitBtn.disabled = picks.some((p) => p.selected.size === 0 && p.custom.trim() === "");
  };

  questions.forEach((question, i) => {
    const pick = picks[i];
    const block = el("div", "ask-q");
    if (question?.header) block.append(el("div", "ask-q-head", String(question.header)));
    block.append(el("div", "ask-q-text", dash(question?.question)));
    if (question?.detail) block.append(el("div", "ask-q-detail", String(question.detail)));

    const options = Array.isArray(question?.options) ? question.options : [];
    /* On a SINGLE-select question the host rejects an answer that carries both
     * a selection and `custom` (apiproxy `matchesQuestions`), and it rejects it
     * as a bare `bad-response` with no reason — so the two clear each other
     * here rather than becoming an error the operator cannot read. Multi-select
     * is the case where they legitimately coexist: there `custom` SUPPLEMENTS
     * the labels. Both handlers need both halves, so the row and the field are
     * built before either is wired. */
    const single = question?.multiSelect !== true;
    const row = options.length > 0 ? el("div", "opt-row") : undefined;
    // A question with no options is free text; so is the "other" box beside a
    // menu, which `custom` exists for.
    const input = el("input", "ask-input");
    const field = /** @type {HTMLInputElement} */ (input);
    field.type = "text";
    field.placeholder = options.length > 0 ? "other…" : "your answer";

    if (row) {
      for (const option of options) {
        // Options are objects; the ANSWER sends the option's label.
        const label = typeof option?.label === "string" ? option.label : String(option);
        const btn = el("button", "opt", label);
        /** @type {HTMLButtonElement} */ (btn).type = "button";
        if (option?.description) btn.title = String(option.description);
        btn.addEventListener("click", () => {
          const on = pick.selected.has(label);
          if (single) {
            pick.selected.clear();
            for (const other of row.children) other.classList.remove("on");
          }
          if (on) pick.selected.delete(label);
          else pick.selected.add(label);
          btn.classList.toggle("on", pick.selected.has(label));
          if (single && pick.selected.size > 0 && pick.custom !== "") {
            pick.custom = "";
            field.value = "";
          }
          sync();
        });
        row.append(btn);
      }
      block.append(row);
    }

    field.addEventListener("input", () => {
      pick.custom = field.value;
      // Typing IS the answer: on a single-select it replaces the pick.
      if (single && field.value.trim() !== "" && pick.selected.size > 0) {
        pick.selected.clear();
        if (row) for (const other of row.children) other.classList.remove("on");
      }
      sync();
    });
    block.append(input);
    node.append(block);
  });

  submit.addEventListener("click", async () => {
    submitBtn.disabled = true;
    answering.add(view.id); // as in approvalNode: whoever answers owns the wording
    try {
      await respond(view.id, {
        sessionId: view.sessionId ?? activeSession,
        answer: {
          answers: picks.map((p) => {
            const answer = { id: p.id, selected: [...p.selected] };
            if (p.custom.trim() !== "") answer.custom = p.custom.trim();
            return answer;
          }),
        },
      });
      gates.delete(view.id);
      settle(node, "answered");
      status("answer sent");
    } catch (err) {
      answering.delete(view.id);
      submitBtn.disabled = false;
      failed(err, "respond");
    }
  });
  actions.append(submit);
  node.append(actions);
  sync();
  return node;
}

/**
 * Take one approval/question view: remember it while it is pending, and show it
 * if it belongs to the session on screen.
 *
 * A gate for another session is NOT dropped — it is held in `gates` and its
 * sidebar row is flagged, so switching to that session still finds it. The
 * agent is blocked until someone answers; a gate that only existed on the tab
 * that happened to be open would strand the turn.
 * @param {Record<string, any>} view
 */
function acceptGate(view) {
  if (typeof view.id !== "string") return; // unanswerable without the wire id
  gates.set(view.id, view);
  renderStrip(); // a member's ask reads as `waiting for you` on its chip
  if (view.sessionId !== undefined && view.sessionId !== activeSession) {
    // Flag the row instead — once, however many times the mux replays the gate.
    const sub = convRows.get(view.sessionId)?.querySelector(".conv-sub");
    if (sub && sub.querySelector(".chip.waiting") === null) sub.prepend(waitingChip());
    /* The row flag above is the gated session's OWN row and nothing else. The
     * aggregated marks — the room row's chip for a folded member, the channel
     * header's dot, the landing page's chip — are rebuilt only by
     * `refreshSessions`, and no frame for another session reaches the render
     * path that schedules it. Without this the mark on the row the operator
     * actually navigates by would wait for an unrelated refresh; it also
     * covers the case where the row does not exist yet (a member session the
     * sidebar has not listed). Same rebuild `acceptGateResolved` relies on. */
    scheduleListRefresh();
    return;
  }
  renderGate(view);
}

/**
 * A gate the HOST settled without us: the turn was cancelled, the session was
 * disposed, or another answerer got there first. This frame is the only signal
 * — without it `gates` keeps the entry forever, so the dead card is re-appended
 * by {@link openSession} on every session switch and by the mux on every
 * reconnect, its Send button stays live for a request that no longer exists
 * (answering it earns a bare `respond: not-pending`), and the sidebar row keeps
 * a "waiting" chip for a session waiting on nothing.
 * @param {Record<string, any>} view - a `gate-resolved` view.
 */
function acceptGateResolved(view) {
  /* A question's resolution names the wire id directly. An approval's names
   * only the audit id — approvals.d.ts keeps those deliberately separate — so
   * its gate is found by the `approvalId` it was rendered with. The type check
   * on that id is load-bearing, not defensive noise: a QUESTION view has no
   * `approvalId` field at all, so a frame that arrived without one would match
   * `undefined === undefined` against the first pending question and close
   * somebody else's card. The host's schema makes `approvalId` required, which
   * is why this is cheap insurance rather than a live bug. */
  let id = typeof view.id === "string" ? view.id : undefined;
  if (id === undefined && typeof view.approvalId === "string") {
    id = [...gates.entries()].find(([, gate]) => gate.approvalId === view.approvalId)?.[0];
  }
  if (id === undefined) return; // already answered here, or never ours
  gates.delete(id);
  renderStrip(); // the chip drops back to its coarse state
  const node = gateNodes.get(id);
  /* The host echoes the resolution for an answer THIS tab sent too, and it
   * normally wins the race against `respond()` returning. Such a card is left
   * to its own handler, which settles it in the operator's words —
   * "answered · deny", the string the Gate-2 drill documents — where this path
   * has only the wire's (`rejected`, `allowed-once`, `answered`). An
   * ApprovalOutcome is never the string `answered`, so deriving the verb from
   * the outcome here would relabel every approval the operator just answered.
   * `closed` then means exactly one thing: the gate died and nobody here
   * answered it. */
  if (node?.isConnected && !answering.has(id)) {
    for (const button of node.querySelectorAll("button")) button.disabled = true;
    settle(node, typeof view.outcome === "string" ? view.outcome : "closed", "closed");
  }
  scheduleListRefresh(); // the sidebar rebuilds its waiting chips from `gates`
}

/** @returns {HTMLElement} the sidebar's "this session is waiting on you" chip. */
function waitingChip() {
  return el("span", "chip waiting", "waiting");
}

/** A session needs the operator when a gate is pending on it or on any of its
 * members: a member's ask is answered inside its own session, but the operator
 * navigates by the ROOM, so the room row has to carry the mark or a folded
 * member's question waits unseen.
 * @param {string} sessionId @returns {boolean} */
function needsYou(sessionId) {
  const ids = new Set([sessionId, ...(memberFold.rooms.get(sessionId) ?? []).map((m) => String(m.sessionId))]);
  return [...gates.values()].some((gate) => ids.has(gate.sessionId));
}

/**
 * Draw a pending gate at the tail of the flow, once.
 * @param {Record<string, any>} view
 */
function renderGate(view) {
  const already = gateNodes.get(view.id);
  if (already && already.isConnected) return; // the mux replays pending gates on every reconnect
  const node = view.kind === "approval" ? approvalNode(view) : questionNode(view);
  const stick = atTail();
  flow().append(node);
  gateNodes.set(view.id, node);
  if (stick) toTail();
}

/* ---------- frame intake ---------- */

/** What each live block opening reads as on the status line — the PHRASE only.
 * The name in front of it is read from `speaker` at pulse time, not baked in
 * here, so a bot's turn pulses under the bot's name (R12): the status line is
 * the fourth naming surface, alongside the `who` element, the ask card's head
 * and the composer placeholder. */
const PULSE_PHRASE = {
  reasoning: "thinking…",
  text: "writing…",
  "tool-call": "preparing a tool call…",
};

/** Whether the status line currently shows a pulse — so the reset on the next
 * settled frame only ever overwrites a pulse's own text, never "sent" or an
 * error the operator should still be reading. */
let pulsing = false;

/** @param {string|undefined} mode - the block kind that just opened. */
function pulse(mode) {
  status(`${speaker} is ${PULSE_PHRASE[mode ?? ""] ?? "working…"}`);
  pulsing = true;
}

/** Settle the status line back once something real lands. */
function clearPulse() {
  if (!pulsing) return;
  pulsing = false;
  status(activeSession === null ? "connected" : `session ${activeSession}`);
}

/** The live thinking indicator, dsh-style: while a reasoning block is OPEN, one
 * ephemeral line at the tail — a pulsing mark and elapsed time, never content.
 * The thinking itself appears only once settled, as the think row. One at a
 * time; not seq-indexed; removed by the next settled frame or non-reasoning
 * block. @type {{node: HTMLElement, timer: ReturnType<typeof setInterval>}|null} */
let thinkLive = null;

/** @param {number} ms @returns {string} elapsed as 47s / 2m45s. */
function elapsed(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${s % 60}s`;
}

function showThinkLive() {
  if (thinkLive !== null && thinkLive.node.isConnected) return;
  hideThinkLive();
  const node = el("div", "think-live");
  const secs = el("span", "think-live-secs", "0s");
  node.append(el("span", "think-live-dot", "◐"), el("span", null, "thinking…"), secs);
  const t0 = Date.now();
  const timer = setInterval(() => { secs.textContent = elapsed(Date.now() - t0); }, 1000);
  const stick = atTail();
  flow().append(node);
  if (stick) toTail();
  thinkLive = { node, timer };
}

function hideThinkLive() {
  if (thinkLive === null) return;
  clearInterval(thinkLive.timer);
  thinkLive.node.remove();
  thinkLive = null;
}

/**
 * Render one already-decoded view of the active session.
 * @param {Record<string, any>} view
 */
function accept(view) {
  clearPulse();
  hideThinkLive();
  honourSurfaceOp(view);
  if (view.kind === "bubble") place(view, bubbleNode(view));
  else if (view.kind === "card") acceptCard(view);
  else if (view.kind === "room-line") place(view, roomLineNode(view));
}

/**
 * The single intake for every frame, live or backfilled.
 * @param {unknown} frame - a mux envelope, a bare MuxFrame, or a history entry.
 */
function acceptFrame(frame) {
  if (loadingSession !== null) {
    // Mid-backfill: hold it. Appending now would put this frame BEFORE the
    // history it follows, and nothing later would reorder the transcript.
    queued.push(frame);
    return;
  }
  const view = mapFrame(frame);
  if (view.kind === "ignore") return;
  if (view.kind === "pulse") {
    // Live liveness only — no node, no seq, no dedupe. Replayed through a
    // backfill it still lands in order, so the final status is the true one.
    if (view.sessionId === undefined || view.sessionId === activeSession) {
      pulse(view.mode);
      if (view.mode === "reasoning") showThinkLive();
      else hideThinkLive();
    }
    if (view.sessionId !== undefined && memberSessionIds().has(view.sessionId)) {
      fineStates.set(view.sessionId, view.mode === "reasoning" ? "thinking" : view.mode === "tool-call" ? "tool" : "writing");
      renderStrip();
    }
    return;
  }
  if (view.kind === "turn") {
    // A member's turn boundary: its fine state ends with the turn; the coarse
    // state (answered / passed / …) arrives on the room's projection.
    if (view.sessionId !== undefined && memberSessionIds().has(view.sessionId)) {
      if (view.phase === "end") fineStates.delete(view.sessionId);
      else fineStates.set(view.sessionId, "thinking");
      renderStrip();
    }
    return;
  }
  if (view.kind === "projection") {
    // Stored for EVERY session (the agent panel reads on demand), never
    // seq-deduped with the transcript: a projection is state, not an event.
    acceptProjection(view);
    return;
  }
  if (view.kind === "approval" || view.kind === "question") {
    acceptGate(view);
    return;
  }
  if (view.kind === "gate-resolved") {
    acceptGateResolved(view);
    return;
  }
  if (view.sessionId !== undefined && view.sessionId !== activeSession) return;
  if (typeof view.seq === "number") {
    const key = `${view.sessionId ?? activeSession}:${view.seq}`;
    if (seen.has(key)) return;
    seen.add(key);
  }
  accept(view);
  scheduleListRefresh();
}

/** Drain the frames held during a backfill, in arrival order. */
function flushQueued() {
  const held = queued.splice(0, queued.length);
  for (const frame of held) acceptFrame(frame);
}

/* ---------- sessions ---------- */

/** Wipe everything that belongs to the session leaving the screen. */
function resetFlow() {
  hideThinkLive();
  flow().replaceChildren();
  seen.clear();
  bySeq.clear();
  toolCards.clear();
  gateNodes.clear();
  answering.clear();
  queued.length = 0;
}

/** @param {number} at - epoch ms. @returns {string} a short local stamp. */
function when(at) {
  if (typeof at !== "number" || !Number.isFinite(at)) return EM;
  const date = new Date(at);
  const day = date.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit" });
  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${day} ${time}`;
}

/**
 * The title the list carries, or a stand-in. The title is a PROJECTION value,
 * not a summary field: it lands asynchronously after the first prompt, which is
 * why the sidebar refreshes itself while a turn runs.
 * @param {Record<string, any>} summary @returns {string}
 */
function titleOf(summary) {
  const title = summary?.projections?.values?.title;
  return typeof title === "string" && title !== "" ? title : "untitled";
}

/** @param {Record<string, any>} summary @returns {HTMLElement} one sidebar row. */
function convRow(summary) {
  const id = String(summary.sessionId);
  const row = el("div", "conv conv-pick");
  row.setAttribute("role", "button");
  row.tabIndex = 0;

  const top = el("div", "conv-top");
  top.append(el("span", "conv-name", titleOf(summary)));
  row.append(top);

  const sub = el("div", "conv-sub");
  if (needsYou(id)) sub.append(waitingChip());
  if (summary.running === true) sub.append(el("span", "chip", "running"));
  row.append(sub);
  /* Path and last-touch live on hover; the group header carries the identity
   * and the row keeps just the title (operator direction: no date column). */
  row.title = `${dash(summary.cwd ?? id)}\n${when(summary.updatedAt)}`;

  /* Row actions, revealed on hover: rename and fork are the host's own RPCs;
   * archive and delete are the face's /data routes (the host has neither at
   * this pin). Delete is permanent and gated by a confirm — and never offered
   * on a running session. */
  const actions = el("span", "conv-actions");
  const act = (glyph, label, fn) => {
    const btn = el("button", "conv-act", glyph);
    btn.type = "button";
    btn.title = label;
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      void fn();
    });
    actions.append(btn);
  };
  act("✎", "rename", async () => {
    const current = titleOf(summary);
    const title = window.prompt("rename session", current === "untitled" ? "" : current);
    if (title === null || title.trim() === "" || title.trim() === current) return;
    try {
      await rpc("session.rename", { sessionId: id, title: title.trim() });
      await refreshSessions();
    } catch (err) {
      failed(err, "session.rename");
    }
  });
  act("⑂", "fork — a new session continuing from this one", async () => {
    try {
      const made = await rpc("session.fork", { sessionId: id });
      await refreshSessions();
      if (typeof made?.sessionId === "string") void openSession(made.sessionId);
    } catch (err) {
      failed(err, "session.fork");
    }
  });
  const archived = archivedSet.has(id);
  act(archived ? "↩" : "⊟", archived ? "unarchive" : "archive", async () => {
    try {
      const res = await fetch("/data/sessions/archive", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sessionId: id, archived: !archived }),
      });
      const body = await res.json();
      if (body?.ok !== true) throw new Error(String(body?.error ?? `HTTP ${res.status}`));
      archivedSet = new Set(body.archived);
      await refreshSessions();
    } catch (err) {
      failed(err, "archive");
    }
  });
  if (summary.running !== true) {
    act("×", "delete permanently — no undo", async () => {
      if (!window.confirm(`Delete "${titleOf(summary)}" permanently? There is no undo.`)) return;
      try {
        const res = await fetch("/data/sessions/delete", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ sessionId: id }),
        });
        const body = await res.json();
        if (body?.ok !== true) throw new Error(String(body?.error ?? `HTTP ${res.status}`));
        if (Array.isArray(body.archived)) archivedSet = new Set(body.archived);
        if (Array.isArray(body.deleted)) deletedSet = new Set(body.deleted);
        if (activeSession === id) newSession();
        await refreshSessions();
      } catch (err) {
        failed(err, "delete session");
      }
    });
  }
  row.append(actions);

  row.addEventListener("click", () => void openSession(id));
  row.addEventListener("keydown", (event) => {
    const key = /** @type {KeyboardEvent} */ (event).key;
    if (key !== "Enter" && key !== " ") return;
    event.preventDefault();
    void openSession(id);
  });
  return row;
}

/** The members folded under a room row: one indented row per member, the bot's
 * name as its label, collapsed by default. The count is on the head, so a
 * folded room still SAYS how many sessions it holds — hiding them behind a
 * silent chevron would be the one thing Rule 5 forbids.
 * @param {Record<string, any>} roomSummary @param {Record<string, any>[]} members @returns {HTMLElement} */
function memberBox(roomSummary, members) {
  const key = `room:${String(roomSummary.sessionId)}`;
  const box = el("div", "conv-members");
  const head = el("div", "conv-members-head");
  const chev = el("span", "chev", collapsedGroups.has(key) ? "▸" : "▾");
  head.append(chev, el("span", "conv-members-n", `${members.length} member${members.length === 1 ? "" : "s"}`));
  const list = el("div");
  list.hidden = collapsedGroups.has(key);
  head.addEventListener("click", () => {
    if (collapsedGroups.has(key)) collapsedGroups.delete(key); else collapsedGroups.add(key);
    persistCollapsed();
    list.hidden = collapsedGroups.has(key);
    chev.textContent = list.hidden ? "▸" : "▾";
  });
  for (const m of members) {
    const row = el("div", "conv conv-pick conv-member");
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    const top = el("div", "conv-top");
    top.append(el("span", "conv-name", botOf(m)?.label ?? String(m.agentPreset)));
    row.append(top);
    const sub = el("div", "conv-sub");
    if (needsYou(String(m.sessionId))) sub.append(waitingChip());
    if (m.running === true) sub.append(el("span", "chip", "running"));
    row.append(sub);
    row.title = `${dash(m.cwd)}\n${when(m.updatedAt)}`;
    row.addEventListener("click", () => void openSession(String(m.sessionId)));
    row.addEventListener("keydown", (event) => {
      const k = /** @type {KeyboardEvent} */ (event).key;
      if (k !== "Enter" && k !== " ") return;
      event.preventDefault();
      void openSession(String(m.sessionId));
    });
    convRows.set(String(m.sessionId), row);
    row.dataset.title = botOf(m)?.label ?? String(m.agentPreset);
    list.append(row);
  }
  box.append(head, list);
  return box;
}

/** Mark the row of the session on screen, and name it in the topbar. The title
 * comes off the row the last `session.list` built — the sidebar is the one
 * place titles are known, so the topbar reads it rather than calling again. */
function markActive() {
  for (const [id, row] of convRows) row.classList.toggle("active", id === activeSession);
  /* In detail mode the topbar names the open detail, not the session. */
  if (!detailOpen) {
    const row = activeSession === null ? undefined : convRows.get(activeSession);
    $("#topbar-name").textContent = activeSession === null ? "new session" : row?.dataset.title ?? "untitled";
    $("#topbar-raw").title = dash(activeSession);
  }
  /** @type {HTMLButtonElement} */ ($("#stop")).disabled = activeSession === null;
  renderAgentSession(); // the usage card follows the session on screen
}

/** Refetch the sidebar. Out-of-order answers are dropped, not rendered. The
 * channel index is refreshed alongside `session.list` on every call — a rename
 * or a newly attached session must show up without a separate reload. */
async function refreshSessions() {
  const token = ++listSeq;
  let value;
  try {
    [value] = await Promise.all([rpc("session.list"), loadChannelIndex(), loadBotIndex()]);
  } catch (err) {
    failed(err, "session.list");
    return;
  }
  if (token !== listSeq) return;
  const list = $("#conv-list");
  convRows.clear();
  list.replaceChildren();
  /* Group by channel membership (the host's own index, reconciled from the
   * workspace registry — never a path guess); archived sessions fold into
   * their own group at the BOTTOM regardless of recency, and a session no
   * channel claims folds into "ungrouped" — counted and shown, never dropped
   * (charter Rule 5). Items arrive updatedAt-desc, so live group order is the
   * recency of each group's freshest session, and rows inside a group keep
   * that order too.
   *
   * Keyed by `bucketFor`'s `key` (a `workspaceId`, or the `__archived`/
   * `__ungrouped` sentinel) — NEVER by the channel's display `label` (M2): a
   * title is renameable and carries no identity, so two channels renamed to
   * the same string used to merge into one group here, one silently hiding
   * the other's sessions behind its own header.
   * @type {Map<string, {channel: Record<string, any>|null, label: string, items: Record<string, any>[]}>} */
  const buckets = new Map();
  /* The effective archive set: the face's own reversible `archivedSet` UNION
   * the host's one-way `channelIndex.archived`. */
  const hostArchived = new Set(channelIndex?.archived ?? []);
  lastSessions = (value?.items ?? []).filter((summary) => !deletedSet.has(String(summary.sessionId)));
  /* The room fold, recomputed from the list that just landed: a member never
   * files under a bucket of its own (it would leave its room, and read as a
   * second conversation the operator has to hunt for) — it renders indented
   * under the room row, counted there (charter Rule 5: folded, never hidden). */
  const fold = foldMembers(lastSessions);
  memberFold = fold; // module state the strip and the gates read
  /* Re-derive the active session's voice from the list that just landed. Two
   * races need it, and neither is reachable from `setSpeaker`'s own call sites:
   * a mux reconnect reopens the active session against the PRE-reconnect
   * snapshot (`onOpen` fires `refreshSessions` and `openSession` back to back,
   * and only the latter is synchronous), and the roster — `loadBotIndex`, in
   * the same `Promise.all` above — may only now have arrived to turn a bare
   * `buffett-type` into `Buffett Type`. A session this list does not carry is
   * left alone: keep the label on screen rather than reset it to the host. */
  const activeRow = lastSessions.find((s) => String(s.sessionId) === activeSession);
  if (activeRow !== undefined) setSpeaker(activeRow);
  for (const summary of value?.items ?? []) {
    const id = String(summary.sessionId);
    if (deletedSet.has(id)) continue; // a host-memory ghost
    // Attached sessions list with a projections block — seed the usage store.
    seedProjections(id, summary.projections);
    if (fold.members.has(id)) continue; // folded under its room instead
    const archived = archivedSet.has(id) || hostArchived.has(id);
    const { key, label, channel } = bucketFor(channelOf(id), archived, botOf(summary), false);
    let bucket = buckets.get(key);
    if (bucket === undefined) {
      bucket = { channel, label, items: [] };
      buckets.set(key, bucket);
    }
    bucket.items.push(summary);
  }
  const order = [...buckets.keys()].filter((key) => key !== UNGROUPED_KEY && key !== ARCHIVED_KEY && !isBotKey(key));
  order.push(...[...buckets.keys()].filter((key) => isBotKey(key)).sort());
  if (buckets.has(UNGROUPED_KEY)) order.push(UNGROUPED_KEY);
  if (buckets.has(ARCHIVED_KEY)) order.push(ARCHIVED_KEY);
  for (const key of order) {
    const bucket = buckets.get(key);
    const box = el("div");
    const needs = bucket.items.some((s) => needsYou(String(s.sessionId)));
    list.append(groupHeader(key, bucket.label, bucket.items.length, box, bucket.channel, needs), box);
    for (const summary of bucket.items) {
      const id = String(summary.sessionId);
      const row = convRow(summary);
      row.dataset.title = titleOf(summary);
      convRows.set(id, row);
      box.append(row);
      if (fold.rooms.has(id)) box.append(memberBox(summary, fold.rooms.get(id)));
    }
  }
  markActive();
  renderStrip(); // the member fold and `running` may both have moved
  syncPickerFolders(); // a picker already on screen learns the folders the list just revealed
}

/** Refetch the sidebar shortly, coalescing a whole turn's worth of events. */
function scheduleListRefresh() {
  if (listTimer !== null) clearTimeout(listTimer);
  listTimer = setTimeout(() => {
    listTimer = null;
    void refreshSessions();
  }, LIST_REFRESH_MS);
}

/**
 * Put a session on screen: clear, backfill its history, then resume the stream.
 *
 * Two things make this safe to call at any moment, including on every mux
 * reconnect (the documented recovery is "reopen the stream + refetch history"):
 * live frames queue while the page is in flight, and a generation token makes a
 * superseded load return without touching a flow that now belongs to someone else.
 * @param {string} id @returns {Promise<void>}
 */
async function openSession(id) {
  const token = ++openSeq;
  closeDetail(); // picking a session always brings the chat back
  const previousActive = activeSession;
  activeSession = id;
  /* Before the history replay, not after: every bubble the replay builds reads
   * `speaker` as it renders, so a session opened cold would otherwise write
   * the PREVIOUS session's name over a whole transcript. The summary is the
   * sidebar's own row - a session the list has not caught up with yet is the
   * host, which is what an unknown session was already labelled.
   *
   * The exception is REOPENING the session already on screen (the mux's
   * reconnect path): its label was set from a summary the list may not carry
   * yet - `openBotHome` arms a preset before any session exists, and a
   * reconnect's `session.list` has not landed. Resetting it to the host there
   * would relabel a live bot transcript as Kairos, so a same-session reopen
   * with no row keeps what is on screen; `refreshSessions` heals it when the
   * list does land. */
  const row = lastSessions.find((s) => String(s.sessionId) === id);
  if (row !== undefined || id !== previousActive) setSpeaker(row ?? null);
  resetFlow();
  markActive();
  loadingSession = id;

  /** @type {any} */
  let page;
  try {
    page = await rpc("session.history", { sessionId: id });
  } catch (err) {
    if (token !== openSeq) return;
    loadingSession = null;
    failed(err, "session.history");
    return;
  }
  if (token !== openSeq) return; // a newer open owns the flow now
  loadingSession = null;

  /* The tail page carries a projections baseline `{asOfSeq, values}` — the
   * agent panel's seed for a session opened cold, before any live frame. */
  seedProjections(id, page?.projections);
  for (const entry of page?.events ?? []) {
    // A history entry has no envelope and no frame type; the mapper takes it as
    // a session/event so a backfilled transcript is identical to a streamed one.
    acceptFrame({ type: "session/event", sessionId: id, ...entry });
  }
  flushQueued();
  for (const gate of gates.values()) if (gate.sessionId === id) renderGate(gate);
  toTail();
  status(`session ${id}`);
  void loadRoomInfo();
}

/** Start a fresh conversation. No session is created until the first prompt —
 * a session created by a button that is then abandoned is a blank row forever. */
function newSession() {
  openSeq += 1; // orphan any in-flight history load
  closeDetail();
  loadingSession = null;
  activeSession = null;
  pendingCwd = undefined;
  pendingWorkspaceId = undefined;
  pendingAgentPreset = undefined;
  setSpeaker(null); // no preset pending, no session: the host
  resetFlow();
  markActive();
  status("new session · pick a strategy, then type below");
  void loadRoomInfo(); // no session, no room: the strip hides
  void showStrategyPicker();
}

/* ---------- the strategy picker: a session's workspace IS a channel ---------- */

/** `/data/channels.json`'s last good answer —
 * `{ok, root, channels, ungrouped, archived}` — used by the picker and by
 * sidebar grouping. @type {Record<string, any>|null} */
let channelIndex = null;

/** The `cwd` the NEXT `session.create` carries; `undefined` is the host
 * default — the workbench repo root. Only takes effect when
 * `pendingWorkspaceId` is unset — see below. @type {string|undefined} */
let pendingCwd;

/** The workspace the NEXT `session.create` joins. Set by a channel row;
 * `undefined` falls back to `pendingCwd`, which is how an OS-picked folder
 * still works. `session.create` accepts workspaceId OR cwd, never both.
 * @type {string|undefined} */
let pendingWorkspaceId;

/** The agent preset the NEXT `session.create` names: a bot's id for its home
 * session, `undefined` for Kairos (the gateway then mounts the default).
 * Set with `pendingCwd = <bot>.homeCwd` by openBotHome; reset wherever the
 * other two pendings are. @type {string|undefined} */
let pendingAgentPreset;

/** The last `session.list` answer (ghosts dropped): the picker derives the
 * local folders sessions have worked in from it. @type {Record<string, any>[]} */
let lastSessions = [];

/** The header fold: room id → member rows; every member id. @type {{rooms: Map<string, any[]>, members: Set<string>}} */
let memberFold = { rooms: new Map(), members: new Set() };

/**
 * Folders sessions have already worked in that belong to no channel — the
 * local folders picked through the OS dialog, which the channel index
 * cannot know about. Keyed by cwd, labelled by basename (the same label the
 * sidebar groups them under), most recently used first. Empty until the
 * channel index has loaded: without it, membership can't be told from a
 * plain folder.
 * @returns {Map<string, string>} cwd → label
 */
function knownFolders() {
  /** @type {Map<string, string>} */
  const out = new Map();
  if (channelIndex === null) return out;
  /* A directory-identity check, not `channelOf(sessionId) !== null`: the
   * host's "live" session tree (what the reconcile sees) can lag the fuller
   * history the sidebar shows, so a channel directory's own session can be
   * unattached yet — checking membership there would offer that same
   * directory a second time, as a "local folder", right below its real
   * channel row. */
  const dirs = new Set((channelIndex.channels ?? []).map((c) => c.dir));
  for (const summary of lastSessions) {
    const cwd = summary.cwd;
    if (typeof cwd !== "string" || cwd === "" || dirs.has(cwd)) continue;
    if (channelIndex.root && cwd.startsWith(`${channelIndex.root}/bots/`)) continue; // a bot's home, not a folder
    const name = cwd.split("/").filter((part) => part !== "").pop();
    if (name !== undefined && !out.has(cwd)) out.set(cwd, name);
  }
  return out;
}

/** Offer every known folder in the picker on screen, once each — the same
 * row the browse button makes, so picking one again reselects it. */
function syncPickerFolders() {
  const picker = flow().querySelector(".picker");
  const rows = picker?.querySelector(".picker-rows");
  const browse = rows?.querySelector(".pick-browse");
  if (!picker || !rows || !browse) return;
  const offered = new Set([...rows.querySelectorAll(".pick-row")]
    .map((row) => /** @type {HTMLElement} */ (row).dataset.cwd));
  for (const [cwd, name] of knownFolders()) {
    if (offered.has(cwd)) continue;
    const row = pickerRow(name, cwd, "local", picker);
    row.dataset.cwd = cwd;
    row.title = cwd;
    rows.insertBefore(row, browse);
  }
}

/** Fetch the reconciled channel listing. Swallow-and-degrade: a failed
 * listing must leave the sidebar usable, not blank — grouping falls back to
 * an all-"ungrouped" sidebar and the picker says the list is unavailable. */
async function loadChannelIndex() {
  try {
    const res = await fetch("/data/channels.json");
    const body = await res.json();
    if (body?.ok === true) channelIndex = body;
  } catch { /* grouping degrades to "ungrouped"; the picker says so */ }
  return channelIndex;
}

/** `/data/bots.json`'s last good `bots` array - id, name, homeCwd, soul, broken?, isDefault, listed. @type {Record<string, any>[]} */
let botIndex = [];
async function loadBotIndex() {
  try {
    const body = await panelData("/data/bots.json");
    botIndex = Array.isArray(body.bots) ? body.bots : [];
  } catch { /* the sidebar labels a bot by id instead of name */ }
  return botIndex;
}
/** The bot a session belongs to, from its own header: `agentPreset` names one
 * and it is not the default. `null` for Kairos and for a preset-less session. */
function botOf(summary) {
  const id = summary?.agentPreset;
  if (typeof id !== "string" || id === "kairos") return null;
  const bot = botIndex.find((b) => b.id === id);
  return { id, label: bot?.name ?? id };
}

/** The name the transcript writes over the ACTIVE session's turns: a bot's
 * display name for its own session, `Kairos` for the host's. Per session, not
 * per message — `speakerFor` reads the same `agentPreset` header `botOf`
 * buckets the sidebar by, so the label and the bucket can never disagree.
 * @type {string} */
let speaker = HOST_NAME;

/** Point the four naming surfaces at one session's voice. Three read `speaker`
 * at the moment they render — the `who` element over an assistant bubble
 * (`bubbleNode`), the ask card's `… asks` head (`questionNode`) and the status
 * pulse (`pulse`) — so they need nothing but the assignment below. The fourth,
 * the composer placeholder, is rewritten here because it is the one surface
 * already on screen when the voice changes. Call it BEFORE anything renders
 * for a session; `null` means no session, which is the host.
 * @param {{agentPreset?: unknown}|null|undefined} summary */
function setSpeaker(summary) {
  speaker = speakerFor(summary, botIndex);
  /** @type {HTMLInputElement} */ ($("#composer-input")).placeholder = `Message ${speaker}…`;
}

/** Session ids the operator archived — face metadata from
 * `/data/sessions-meta.json`, host-side so it survives any browser.
 * @type {Set<string>} */
let archivedSet = new Set();

/** Tombstones: sessions deleted on disk that host memory may still list until
 * a restart — never shown. @type {Set<string>} */
let deletedSet = new Set();

async function loadSessionsMeta() {
  try {
    const body = await (await fetch("/data/sessions-meta.json")).json();
    if (body?.ok === true) {
      if (Array.isArray(body.archived)) archivedSet = new Set(body.archived);
      if (Array.isArray(body.deleted)) deletedSet = new Set(body.deleted);
    }
  } catch { /* the archive fold degrades to "nothing archived" */ }
}

/** Sidebar groups the operator folded — view state, per browser, keyed by
 * `bucketFor`'s `key` (a `workspaceId`, or the `__archived`/`__ungrouped`
 * sentinel — M2). The two synthetic buckets start folded the first time they
 * ever appear; the operator's own fold choices past that always win.
 *
 * MIGRATION DECISION (M2 changed what this Set is keyed by): a pre-fix
 * install may have `"archived"`/`"ungrouped"` (the old sentinel spelling, no
 * leading `__`) sitting in this key from before the split, or a real
 * channel's OLD TITLE (a per-channel bucket used to be keyed by its
 * renameable title, which is exactly the bug M2 fixes). The two sentinels
 * are migrated below, one time, to their new spelling — losing that fold
 * choice would be a visible regression for no reason. A title-keyed entry is
 * NOT migrated: there is no way to recover which `workspaceId` it meant (the
 * title was never a stable identity — that is the bug), so it is simply
 * dropped. That channel's group opens expanded once — a one-time, harmless
 * view-state reset, not data loss: nothing the operator curated lives here,
 * only which groups happen to be visually collapsed.
 * @type {Set<string>} */
const collapsedGroups = new Set(/** @type {string[]} */ ((() => {
  let raw;
  try {
    raw = JSON.parse(localStorage.getItem("face.collapsed-groups") ?? `["${ARCHIVED_KEY}","${UNGROUPED_KEY}"]`);
  } catch {
    return [ARCHIVED_KEY, UNGROUPED_KEY];
  }
  if (!Array.isArray(raw)) return [ARCHIVED_KEY, UNGROUPED_KEY];
  // A workspaceId is a UUID (dsh-workspace mints it via randomUUID()) - a
  // surviving non-UUID, non-sentinel entry can only be a pre-M2 title, and
  // per the decision above it is dropped rather than carried forward as dead
  // weight that can never match a bucket key again.
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return raw
    .map((k) => (k === "archived" ? ARCHIVED_KEY : k === "ungrouped" ? UNGROUPED_KEY : k))
    // `room:<sessionId>` is the second grammar this Set carries: a room's own
    // member fold, keyed by the room session — same per-browser view state.
    .filter((k) => typeof k === "string" && (k === ARCHIVED_KEY || k === UNGROUPED_KEY || UUID_RE.test(k) || isBotKey(k)
      || /^room:session-[0-9a-f-]{36}$/.test(k)));
})()));

function persistCollapsed() {
  try {
    localStorage.setItem("face.collapsed-groups", JSON.stringify([...collapsedGroups]));
  } catch { /* view state only — losing it costs a click */ }
}

/** One clickable group header: chevron · label · count. The chevron always
 * folds; a real channel's name instead opens its page (`channel` given) —
 * losing the fold gesture there would be a regression, so the chevron keeps
 * it. The synthetic `archived` and `ungrouped` headers have no channel, so
 * their name folds too, same as before this split.
 *
 * `key` (a `workspaceId`, or the `__archived`/`__ungrouped` sentinel) is the
 * collapse-state identity; `label` is only ever DISPLAYED — never used to
 * look anything up. Two channels can render the identical label and still
 * fold independently, which is the entire fix (M2).
 * `needs` marks the whole group when any session under it is waiting on the
 * operator — the mark has to survive the fold, or collapsing a channel hides
 * the one thing that needs an answer.
 * @param {string} key @param {string} label @param {number} count @param {HTMLElement} box
 * @param {Record<string, any>|null} [channel] @param {boolean} [needs] */
function groupHeader(key, label, count, box, channel, needs) {
  const head = el("div", "conv-group");
  const chev = el("span", "chev", collapsedGroups.has(key) ? "▸" : "▾");
  const name = el("span", "conv-group-name", label);
  head.append(chev, name);
  if (needs === true) {
    const mark = el("span", "needs-you", "●");
    mark.title = "a session in this channel is waiting on you";
    head.append(mark);
  }
  head.append(el("span", "conv-group-n", String(count)));
  box.hidden = collapsedGroups.has(key);
  const fold = () => {
    if (collapsedGroups.has(key)) collapsedGroups.delete(key);
    else collapsedGroups.add(key);
    persistCollapsed();
    box.hidden = collapsedGroups.has(key);
    chev.textContent = box.hidden ? "▸" : "▾";
  };
  chev.addEventListener("click", fold);
  if (channel === undefined || channel === null) {
    name.addEventListener("click", fold);
  } else {
    name.classList.add("conv-group-link");
    name.addEventListener("click", () => { void openChannel(channel); });
  }
  return head;
}

/** Which channel a session belongs to, from the host's own membership index.
 * The old version reverse-engineered this from a path prefix, which is why
 * foreign projects appeared as strategies and were offered in the picker. */
function channelOf(sessionId) {
  for (const channel of channelIndex?.channels ?? []) {
    if (channel.sessionIds.includes(sessionId)) return channel;
  }
  return null;
}

/** One selectable row of the picker. @param {string|undefined} cwd - the
 * plain folder it stands for, used only when `workspaceId` is unset.
 * @param {string} [workspaceId] - set for a channel row: choosing it joins
 * that workspace directly (the branch that auto-attaches the new session),
 * never alongside `cwd`. */
function pickerRow(label, cwd, badge, picker, workspaceId) {
  const row = el("div", "pick-row");
  row.setAttribute("role", "button");
  row.tabIndex = 0;
  row.append(el("span", "pick-name", label));
  /* The row is the name (operator direction): a channel's status, "repo
   * root", "local" stay on hover only — callers with a path put that there. */
  if (badge) row.title = badge;
  const choose = () => {
    pendingWorkspaceId = workspaceId;
    pendingCwd = workspaceId === undefined ? cwd : undefined;
    pendingAgentPreset = undefined;
    setSpeaker(null); // a folder or channel is Kairos's, whatever was armed before
    for (const other of picker.querySelectorAll(".pick-row")) other.classList.toggle("sel", other === row);
    status(`new session · ${label} · type below`);
  };
  row.addEventListener("click", choose);
  row.addEventListener("keydown", (event) => {
    const key = /** @type {KeyboardEvent} */ (event).key;
    if (key !== "Enter" && key !== " ") return;
    event.preventDefault();
    choose();
  });
  return row;
}

/** Offer the channels as workspaces for the next session. The first prompt
 * creates the session with the picked workspace (or cwd); until then nothing
 * exists. */
async function showStrategyPicker() {
  const index = await loadChannelIndex();
  if (activeSession !== null || flow().querySelector(".picker") !== null) return;
  const picker = el("div", "picker");
  picker.append(el("div", "picker-title", "workspace — the channel this session works"));
  const rows = el("div", "picker-rows");
  /* `channels` already carries the workbench (isRoot, name "workbench") —
   * no separate hardcoded row needed when the listing succeeded. */
  for (const c of index?.channels ?? []) {
    rows.append(pickerRow(c.title, undefined, c.isRoot ? "repo root" : c.status, picker, c.workspaceId));
  }
  if (index === null) {
    // the listing failed — offer the bare workbench default so a session can
    // still be created (no workspaceId: session.create falls back to the host default cwd)
    rows.append(pickerRow("workbench", undefined, "repo root", picker));
  }
  /* Any local folder, through the OS's own dialog — dsh's native
   * directory-picker capability, which the face's tree already mounts
   * (overlay.ts, directory-picker-auto). Cancel returns null and changes
   * nothing; a deployment without the native capability reports instead. */
  const browse = el("div", "pick-row pick-browse");
  browse.setAttribute("role", "button");
  browse.tabIndex = 0;
  browse.append(el("span", "pick-icon", "📂"), el("span", "pick-name", "choose a local folder…"));
  const pickFolder = async () => {
    status("choose a folder in the system dialog…");
    try {
      const answer = await rpc("host.pickDirectory", {});
      const path = answer?.path;
      if (typeof path !== "string" || path === "") {
        status("new session · pick a strategy, then type below");
        return;
      }
      const name = path.split("/").filter((part) => part !== "").pop() ?? path;
      /* One row per distinct folder: picking the same one again reselects it. */
      const existing = [...picker.querySelectorAll(".pick-row")]
        .find((row) => /** @type {HTMLElement} */ (row).dataset.cwd === path);
      if (existing instanceof HTMLElement) {
        existing.click();
        return;
      }
      const row = pickerRow(name, path, "local", picker);
      row.dataset.cwd = path;
      row.title = path;
      rows.insertBefore(row, browse);
      row.click();
    } catch (err) {
      failed(err, "host.pickDirectory");
    }
  };
  browse.addEventListener("click", () => void pickFolder());
  browse.addEventListener("keydown", (event) => {
    const key = /** @type {KeyboardEvent} */ (event).key;
    if (key !== "Enter" && key !== " ") return;
    event.preventDefault();
    void pickFolder();
  });
  rows.append(browse);
  picker.append(rows);
  if (index === null) {
    picker.append(el("div", "picker-note", "channel list unavailable — sessions fall back to the workbench"));
  } else {
    const form = el("div", "picker-new");
    const input = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    input.type = "text";
    input.placeholder = "new channel name (letters · digits · - _ · spaces become -) — copies strategies/_template";
    const create = /** @type {HTMLButtonElement} */ (el("button", "picker-btn", "create"));
    create.type = "button";
    create.addEventListener("click", async () => {
      /* Spaces fold to dashes before the POST — the rule refuses them and the
       * operator should get the channel they meant, not a 400 to retype their
       * way out of. Written back into the box so what is being created is
       * visible, including when the create then fails for some other reason. */
      const name = foldChannelName(input.value);
      if (name === "") return;
      input.value = name;
      create.disabled = true;
      try {
        const res = await fetch("/data/channels", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name }),
        });
        const body = await res.json();
        if (body?.ok !== true) throw new Error(String(body?.error ?? `HTTP ${res.status}`));
        // the route already reconciled and adopted it — reload to learn its workspaceId
        const fresh = await loadChannelIndex();
        const made = fresh?.channels?.find((c) => c.dir === body.dir);
        const row = pickerRow(made?.title ?? body.name, undefined, made?.isRoot ? "repo root" : made?.status, picker, made?.workspaceId);
        rows.insertBefore(row, browse); // above the "choose a local folder…" row
        row.click();
        input.value = "";
      } catch (err) {
        failed(err, "create channel");
      } finally {
        create.disabled = false;
      }
    });
    form.append(input, create);
    picker.append(form);
  }
  flow().append(picker);
  /* Folders earlier sessions worked in come back as rows of their own — the
   * sidebar already groups their sessions, so the picker must offer them. */
  syncPickerFolders();
}

/** @returns {string|undefined} the browser's IANA zone, which the host records
 * on the user message it admits. */
function timeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

/** Send the composer's text, creating the session if this is the first prompt. */
async function send() {
  const input = /** @type {HTMLInputElement} */ ($("#composer-input"));
  const text = input.value;
  if (text.trim() === "") return;
  input.value = "";
  try {
    if (activeSession === null) {
      const payload = pendingWorkspaceId !== undefined
        ? { workspaceId: pendingWorkspaceId }
        : (pendingCwd === undefined ? {} : { cwd: pendingCwd });
      if (pendingAgentPreset !== undefined) payload.agentPreset = pendingAgentPreset;
      const created = await rpc("session.create", payload);
      const id = created?.sessionId;
      if (typeof id !== "string") throw new Error("session.create returned no sessionId");
      activeSession = id;
      /* The new session's voice, from the summary the host just answered with
       * — `created.agentPreset`, which `bots-smoke.test.ts` pins on a real tree
       * for both branches: a bot's id, and the literal `kairos` for the host.
       * The host's answer, not the pending we sent:
       * if the two ever disagreed the host's is the session that exists. This
       * one call covers both the bot case and the reset the other three sites
       * do, so no `setSpeaker(null)` follows the pendings below. */
      setSpeaker(created);
      pendingCwd = undefined;
      pendingWorkspaceId = undefined;
      pendingAgentPreset = undefined;
      flow().querySelector(".picker")?.remove();
      await refreshSessions();
      markActive();
    }
    const accepted = await rpc("session.prompt", {
      sessionId: activeSession,
      mode: "queue",
      content: [{ type: "text", text }],
      clientTimeZone: timeZone(),
    });
    // A prompt that is exactly one '/'-prefixed text block is a slash command:
    // the host runs it and it never reaches the model, so its only feedback is here.
    status(accepted?.command?.text ?? "sent");
  } catch (err) {
    // Hand the text back rather than losing it — unless the operator has
    // already started typing the next one.
    if (input.value === "") input.value = text;
    failed(err, "prompt");
  }
}

/** Stop the active turn. Queued work survives and resumes in FIFO order. */
async function stopTurn() {
  if (activeSession === null) return;
  try {
    await rpc("session.cancel", { sessionId: activeSession });
    status("cancel requested");
  } catch (err) {
    failed(err, "session.cancel");
  }
}

/* ---------- the master rail: strategy · agent · memory · plugin ----------
   One sidebar, four faces, one pattern (operator direction 2026-09-01): the
   sidebar is always an INDEX — rows, never content — and clicking a row opens
   that item's content in the RIGHT pane, in place of the chat. `strategy`
   indexes sessions and its content is the chat itself; `agent` indexes the
   main agent (Kairos), the local coding CLIs, and the A2A placeholder;
   `memory` indexes the skill packs; `plugin` indexes MCP servers and the
   composed row tree. Picking a session (or "+ new") always brings the chat
   back. Data: `agent` over RPC the client already reaches plus the
   projection store; `memory`/`plugin` over the face's own /data panel routes
   (in-process reads of the booted tree — see src/panels.ts). Read-only. */

/** The sidebar face on screen. @type {"strategy"|"agent"|"memory"|"plugin"} */
let activePanel = "strategy";

/** Whether the right pane is showing a detail view instead of the chat. */
let detailOpen = false;
/** Detail generation: an async builder that finished after the operator moved
 * on (another detail, or back to chat) must not touch the pane. */
let detailSeq = 0;

/**
 * Show one detail view in the right pane: the flow and composer step aside,
 * the topbar names the item. `build` fills the readable-width inner column.
 * @param {string} title @param {(inner: HTMLElement) => void} build
 * @returns {number} this view's generation — compare to `detailSeq` before a
 *   later async re-render.
 */
function openDetail(title, build) {
  detailSeq += 1;
  const inner = el("div", "detail-inner");
  build(inner);
  $("#detail").replaceChildren(inner);
  document.querySelector(".main")?.classList.add("detail-mode");
  detailOpen = true;
  $("#topbar-name").textContent = title;
  $("#topbar-raw").title = title;
  return detailSeq;
}

/** Bring the chat back. Safe to call when no detail is open. */
function closeDetail() {
  detailSeq += 1; // orphan any in-flight detail build
  if (!detailOpen) return;
  detailOpen = false;
  document.querySelector(".main")?.classList.remove("detail-mode");
  $("#detail").replaceChildren();
  markActive(); // restore the session's name to the topbar
}

/**
 * Open one channel's landing page: what it has produced, before you enter it.
 * Everything shown was derived server-side by `channels.ts` (Task 4) and
 * handed over whole by `POST /data/channels/overview` — this only fetches,
 * joins the session rows to the sidebar's own titles, and hands the result to
 * `renderChannelPage`, which draws it (Task 11's contract). The two-phase
 * `openDetail` (a loading placeholder, then the real page once the fetch
 * settles) is the same idiom `openAgentMain`/`openSkill` already use, guarded
 * by the same `token !== detailSeq` check: a slow fetch that loses the race
 * to a later navigation renders into a detached, never-shown node instead of
 * clobbering whatever the operator moved on to.
 * @param {Record<string, any>} channel - a `ChannelRow` from `channelIndex.channels`.
 */
async function openChannel(channel) {
  const token = openDetail(channel.title, (inner) => {
    inner.append(el("div", "detail-title", channel.title));
    inner.append(el("div", "detail-path", channel.dir));
    inner.append(el("div", "sp-note", "loading…"));
  });

  /** @type {Record<string, any>} */
  let payload;
  try {
    payload = await panelData("/data/channels/overview", { workspaceId: channel.workspaceId });
    /* `/data/agents.json` answers {main, local, candidates}; only a `local`
     * row with a `tool` can ever become an `agent_<bin>` call, so only those
     * are offerable on the channel's roster — a chip for a bin with no exec
     * recipe would be a lie the operator could click and nothing would answer. */
    payload.allBins = ((await panelData("/data/agents.json")).local ?? [])
      .filter((row) => row.tool !== undefined).map((row) => row.bin);
  } catch (err) {
    if (token !== detailSeq) return; // the operator moved on mid-fetch
    openDetail(channel.title, (inner) => {
      inner.append(el("div", "detail-title", channel.title));
      inner.append(panelError(err, "channel overview"));
    });
    return;
  }
  if (token !== detailSeq) return; // the operator moved on mid-fetch

  /* The effective archive fold: the face's own reversible set UNION the
   * host's one-way one (a host-archived session can never be un-archived at
   * this pin — same rule `refreshSessions` applies to the sidebar). Session
   * TITLES come from the sidebar's last `session.list` (`lastSessions`), the
   * one place titles are known; a channel session not yet in that snapshot
   * (freshly attached) shows as "untitled" rather than blocking the page. */
  const hostArchived = new Set(channelIndex?.archived ?? []);
  payload.sessions = payload.channel.sessionIds.map((id) => {
    const summary = lastSessions.find((s) => String(s.sessionId) === id);
    return {
      sessionId: id,
      title: summary === undefined ? undefined : titleOf(summary),
      archived: archivedSet.has(id) || hostArchived.has(id),
      waiting: needsYou(id),
    };
  });

  openDetail(channel.title, (inner) => {
    renderChannelPage(inner, payload, {
      onRename: async (title) => {
        try {
          await rpc("workspace.rename", { workspaceId: channel.workspaceId, title });
          await loadChannelIndex();
          await refreshSessions();
          void openChannel({ ...channel, title });
        } catch (err) {
          failed(err, "workspace.rename");
        }
      },
      onToggleAgent: async (bin, on) => {
        try {
          const next = on ? [...payload.agents, bin] : payload.agents.filter((b) => b !== bin);
          await panelData("/data/channels/agents", { workspaceId: channel.workspaceId, agents: next });
          void openChannel(channel);
        } catch (err) {
          failed(err, "channel agents");
        }
      },
      onNewRound: () => {
        /* Same reset `newSession()` does for the "+ new" button, minus the
         * picker: `activeSession` must go back to null here, or `send()`'s
         * `if (activeSession === null)` branch never runs and a prompt
         * silently continues whatever session was on screen before the
         * operator opened this channel page, instead of creating a fresh one
         * attached to THIS channel — the opposite of what "new round" says. */
        openSeq += 1; // orphan any in-flight history load
        loadingSession = null;
        activeSession = null;
        pendingWorkspaceId = channel.workspaceId;
        pendingCwd = undefined;
        pendingAgentPreset = undefined;
        setSpeaker(null); // a channel round is Kairos's, even opened from a bot's page
        closeDetail();
        resetFlow();
        markActive();
        status(`new session · ${channel.title} · type below`);
        void loadRoomInfo(); // no session yet: the strip hides until the first prompt
      },
      onOpenSession: (id) => { closeDetail(); void openSession(id); },
    });
  });
}

/** Mark one index row selected within its panel. @param {HTMLElement} row */
function selRow(row) {
  const panel = row.closest(".side-panel");
  if (panel === null) return;
  for (const other of panel.querySelectorAll(".sel")) other.classList.remove("sel");
  row.classList.add("sel");
}

/** One clickable index row: builds, wires click/keyboard, marks selection.
 * @param {HTMLElement} row @param {() => void} open @returns {HTMLElement} */
function indexRow(row, open) {
  row.setAttribute("role", "button");
  row.tabIndex = 0;
  const pick = () => {
    selRow(row);
    open();
  };
  row.addEventListener("click", pick);
  row.addEventListener("keydown", (event) => {
    const key = /** @type {KeyboardEvent} */ (event).key;
    if (key !== "Enter" && key !== " ") return;
    event.preventDefault();
    pick();
  });
  return row;
}

/** Store one projection value, higher seq winning, and keep the agent panel's
 * usage card live when it is the one on screen.
 * @param {Record<string, any>} view - `{sessionId, key, value, seq?}`. */
function acceptProjection(view) {
  const id = String(view.sessionId);
  let units = projStore.get(id);
  if (units === undefined) {
    units = new Map();
    projStore.set(id, units);
  }
  const seq = typeof view.seq === "number" ? view.seq : -1;
  const prev = units.get(view.key);
  if (prev !== undefined && prev.seq > seq) return;
  units.set(view.key, { seq, value: view.value });
  if (id === activeSession && (view.key === "tokenUsage" || view.key === "contextPressure")) {
    renderAgentSession();
  }
  if (id === activeSession && view.key === "room") renderStrip(); // the coarse states live here
}

/** Seed the store from a `{asOfSeq, values}` projections block (history tail
 * page, or an attached session's list row). Absent or malformed blocks seed
 * nothing. @param {string} sessionId @param {unknown} block */
function seedProjections(sessionId, block) {
  if (block === null || typeof block !== "object") return;
  const { asOfSeq, values } = /** @type {Record<string, any>} */ (block);
  if (values === null || typeof values !== "object") return;
  for (const [key, value] of Object.entries(values)) {
    acceptProjection({ sessionId, key, value, seq: typeof asOfSeq === "number" ? asOfSeq : -1 });
  }
}

/** Show one sidebar face and refresh its content. */
function setPanel(name) {
  activePanel = name;
  for (const btn of document.querySelectorAll(".rail-btn")) {
    btn.classList.toggle("active", /** @type {HTMLElement} */ (btn).dataset.panel === name);
  }
  $(".sidebar").dataset.panel = name;
  $("#conv-list").hidden = name !== "strategy";
  for (const panel of ["agent", "memory", "plugin"]) $(`#panel-${panel}`).hidden = panel !== name;
  if (name === "agent") void refreshAgentPanel();
  else if (name === "memory") void refreshMemoryPanel();
  else if (name === "plugin") void refreshPluginPanel();
}

/* -- shared panel furniture -- */

/** @param {string} title @returns {HTMLElement} one panel card with its title row. */
function panelCard(title) {
  const card = el("div", "sp-card");
  card.append(el("div", "sp-title", title));
  return card;
}

/** Append one label → value line to a card. */
function kvRow(card, label, value) {
  const row = el("div", "sp-kv");
  row.append(el("span", "sp-k", label), el("span", "sp-v", value));
  card.append(row);
}

/** @param {unknown} err @param {string} what @returns {HTMLElement} an in-panel failure line. */
function panelError(err, what) {
  return el("div", "sp-note err", `${what}: ${err instanceof Error ? err.message : String(err)}`);
}

/** Fetch one face /data route and unwrap its `{ok:true,...}` body.
 * @param {string} path @param {Record<string, unknown>} [body] - POSTs when given.
 * @returns {Promise<Record<string, any>>} */
async function panelData(path, body) {
  const res = await fetch(path, body === undefined ? undefined : {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const parsed = await res.json();
  if (parsed?.ok !== true) throw new Error(String(parsed?.error ?? `HTTP ${res.status}`));
  return parsed;
}

/** A phase/status dot: green active, red failed, hollow otherwise.
 * @param {string|null} phase @returns {HTMLElement} */
function phaseDot(phase) {
  const dot = el("span", "sp-dot");
  if (phase === "active") dot.classList.add("on");
  else if (phase === "failed") dot.classList.add("bad");
  else if (phase === "warn") dot.classList.add("warn");
  else if (phase === "disabled") dot.classList.add("off");
  dot.title = phase ?? "not mounted";
  return dot;
}

/** The exact terminal command that signs an agent in — the Hermes idiom:
 * a refusal or a gap always names its next step. */
const LOGIN_HINTS = {
  claude: "claude /login   (or: claude setup-token)",
  codex: "codex login",
  hermes: "hermes setup",
};

/* -- agent -- */

/** @param {unknown} n @returns {string} tokens as 812 / 4.1k / 236k. */
function fmtTokens(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return EM;
  if (n < 1000) return String(n);
  const k = n / 1000;
  return `${k >= 100 ? Math.round(k) : k.toFixed(1)}k`;
}

/** @param {string} label @param {string} [count] @returns {HTMLElement} one panel group header. */
function spGroup(label, count) {
  const head = el("div", "sp-group");
  head.append(el("span", "sp-group-name", label));
  if (count !== undefined) head.append(el("span", "sp-count", count));
  return head;
}

/** The agent index: main agent (Kairos) · local agents · a2a. Rows only —
 * clicking one opens its page in the right pane. */
async function refreshAgentPanel() {
  const panel = $("#panel-agent");
  panel.replaceChildren(el("div", "sp-note", "loading…"));
  /** @type {Record<string, any>|null} */
  let roster = null;
  let rosterErr = null;
  try {
    roster = await panelData("/data/agents.json");
  } catch (err) {
    rosterErr = err;
  }
  if (activePanel !== "agent") return; // the operator moved on mid-fetch
  panel.replaceChildren();

  /* -- main agent: Kairos, owner of this whole runtime -- */
  panel.append(spGroup("main agent"));
  const mainInfo = roster?.main;
  const kairos = el("div", "sp-plug");
  kairos.append(phaseDot("active"), el("span", "sp-plug-name", String(mainInfo?.name ?? "Kairos")));
  /* Names only in this index (operator direction) — the runtime pin, versions
   * and install state live on the pages the rows open; hover keeps a hint. */
  kairos.title = dash(mainInfo?.runtime);
  panel.append(indexRow(kairos, () => void openAgentMain(mainInfo)));

  /* -- local agents: the operator's CONNECTED roster, not a fixed list -- */
  panel.append(spGroup("local agents"));
  if (rosterErr !== null) {
    panel.append(panelError(rosterErr, "agents"));
  } else {
    const local = Array.isArray(roster?.local) ? roster.local : [];
    for (const agent of local) {
      const line = el("div", "sp-plug");
      const found = agent.found === true;
      const signedOut = found && agent.auth?.state === "none";
      const dot = phaseDot(!found ? "disabled" : signedOut ? "warn" : "active");
      dot.title = !found ? "connected, but not answering" : signedOut ? "answering, but signed out" : "answering";
      line.append(dot, el("span", "sp-plug-name", String(agent.label)));
      line.title = found
        ? `${agent.bin} · ${dash(agent.version)}${signedOut ? " · signed out" : ""}`
        : `${agent.bin} · connected, but not answering`;
      if (!found) line.classList.add("off");
      const x = el("button", "sp-x", "×");
      /** @type {HTMLButtonElement} */ (x).type = "button";
      x.title = "disconnect";
      x.addEventListener("click", (event) => {
        event.stopPropagation();
        void disconnectAgent(String(agent.bin), false);
      });
      line.append(x);
      panel.append(indexRow(line, () => openLocalAgent(agent)));
    }
    if (local.length === 0) panel.append(el("div", "sp-note", "none connected yet"));
    const add = el("div", "sp-plug sp-add");
    add.append(el("span", "sp-plug-name", "+ connect an agent"));
    panel.append(indexRow(add, () => void openConnectPage()));
  }

  /* -- bots: the operator's own voices, one directory each under bots/ -- */
  panel.append(spGroup("bots"));
  const bots = await loadBotIndex();
  if (activePanel !== "agent") return; // the operator moved on mid-fetch
  const voices = bots.filter((b) => b.isDefault !== true);
  for (const bot of voices) {
    const line = el("div", "sp-plug");
    line.append(phaseDot(bot.broken ? "failed" : bot.listed === false ? "warn" : "active"), el("span", "sp-plug-name", String(bot.name)));
    line.title = bot.broken ? `broken: ${bot.broken}` : bot.listed === false ? "on disk, not reported by the preset roster" : String(bot.description ?? "");
    panel.append(indexRow(line, () => openBot(bot)));
  }
  if (voices.length === 0) panel.append(el("div", "sp-note", "no bots yet"));
  const addBot = el("div", "sp-plug sp-add");
  addBot.append(el("span", "sp-plug-name", "+ new bot"));
  panel.append(indexRow(addBot, () => openNewBot()));

  /* -- a2a network: declared, not yet open -- */
  panel.append(spGroup("a2a network"));
  const a2a = el("div", "sp-plug off");
  a2a.append(phaseDot("disabled"), el("span", "sp-plug-name", "A2A network"));
  panel.append(indexRow(a2a, openA2A));
}

/** Arm the next prompt to create this bot's HOME session: cwd = its journal
 * (the only directory the bot may write), agentPreset = its id (the gateway
 * mounts the preset). Mirrors onNewRound; no session exists until the prompt. */
function openBotHome(bot) {
  openSeq += 1;
  loadingSession = null;
  activeSession = null;
  pendingWorkspaceId = undefined;
  pendingCwd = String(bot.homeCwd);
  pendingAgentPreset = String(bot.id);
  /* Armed, before a session exists: the composer says "Message <bot>…" while
   * the operator types the first prompt, and `send()` then confirms it from
   * the summary the host answers with. The bot is a `botIndex` row, so its
   * display name resolves rather than falling back to the id. */
  setSpeaker({ agentPreset: String(bot.id) });
  closeDetail();
  resetFlow();
  markActive();
  status(`new session · ${bot.name} at home · type below`);
}

/** One bot's page: what it is, where it lives, its home sessions, its soul.
 * The soul is editable here and nowhere else in the client. */
function openBot(bot) {
  openDetail(`bot · ${bot.name}`, (inner) => {
    inner.append(el("div", "detail-title", String(bot.name)));
    inner.append(el("div", "detail-sub", `${bot.id} · ${bot.description || "no description"}`));
    if (bot.broken) inner.append(el("div", "sp-note err", `dsh cannot mount this bot: ${bot.broken}`));
    else if (bot.listed === false) inner.append(el("div", "sp-note err", "the preset roster does not report this directory - is its agent.cordis.yml present?"));
    inner.append(el("div", "detail-path", String(bot.dir)));

    const actions = el("div", "detail-actions");
    const home = el("button", "picker-btn", "open home");
    home.type = "button";
    home.disabled = Boolean(bot.broken);
    home.addEventListener("click", () => openBotHome(bot));
    actions.append(home);
    inner.append(actions);

    const homes = lastSessions.filter((s) => s.agentPreset === bot.id);
    const card = panelCard(`home sessions · ${homes.length}`);
    for (const s of homes) {
      const row = el("div", "ch-session");
      row.setAttribute("role", "button");
      row.tabIndex = 0;
      row.append(el("span", "ch-session-title", titleOf(s)));
      row.addEventListener("click", () => { closeDetail(); void openSession(String(s.sessionId)); });
      card.append(row);
    }
    if (homes.length === 0) card.append(el("div", "sp-note", "none yet - open home and say something"));
    inner.append(card);

    const soulCard = panelCard("soul");
    const soul = /** @type {HTMLTextAreaElement} */ (el("textarea", "picker-input"));
    soul.rows = 8;
    soul.value = String(bot.soul ?? "");
    const save = el("button", "picker-btn", "save soul");
    save.type = "button";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        const body = await panelData("/data/bots/soul", { id: bot.id, soul: soul.value });
        bot = body.bot;
        status(`saved soul of ${bot.name} - a fresh session will carry it (a running one keeps its prompt)`);
      } catch (err) {
        failed(err, "save soul");
      } finally {
        save.disabled = false;
      }
    });
    soulCard.append(soul, save);
    inner.append(soulCard);
  });
}

/** The New-bot form. The id is PROPOSED from the display name and stays
 * editable - a name in a script with no ASCII letters proposes nothing, and
 * the server then refuses the empty id rather than inventing one. */
function openNewBot() {
  openDetail("new bot", (inner) => {
    inner.append(el("div", "detail-title", "New bot"));
    inner.append(el("div", "detail-sub", "copies bots/_template · a voice, not a hand"));
    /* `col`: the other two `.picker-new` forms are one input beside one button,
     * which the row layout suits; this one is four fields over a button and has
     * to stack (chat.css `.picker-new.col`). */
    const form = el("div", "picker-new col");
    const name = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    name.type = "text";
    name.placeholder = "display name (any script)";
    const id = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    id.type = "text";
    id.placeholder = "id - lowercase letters, digits, - (proposed from the name)";
    name.addEventListener("input", () => { id.value = proposeBotId(name.value); });
    const description = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    description.type = "text";
    description.placeholder = "one line - the stance this voice argues";
    const soul = /** @type {HTMLTextAreaElement} */ (el("textarea", "picker-input"));
    soul.rows = 6;
    soul.placeholder = "persona (optional; the template's if empty; no {{ }})";
    const create = el("button", "picker-btn", "create");
    create.type = "button";
    create.addEventListener("click", async () => {
      create.disabled = true;
      try {
        const payload = { name: name.value.trim(), id: id.value.trim(), description: description.value.trim() };
        if (soul.value.trim() !== "") payload.soul = soul.value;
        const body = await panelData("/data/bots", payload);
        /* Open the FRESH index row, not the one the POST returned: the roster
         * re-scans on every list, so the created row carries `listed: false`
         * and its page would warn about a bot dsh reports perfectly well. */
        await refreshAgentPanel();
        openBot(botIndex.find((b) => b.id === body.bot.id) ?? body.bot);
      } catch (err) {
        failed(err, "create bot");
      } finally {
        create.disabled = false;
      }
    });
    form.append(name, id, description, soul, create);
    inner.append(form);
    inner.append(el("div", "sp-note",
      "The mask in the composition is visibility, not authority: what a bot may write is its session's sandbox, what it may order is Gate 2."));
  });
}

/** The main agent's page: identity, model, host, keys, live session usage.
 * Each card degrades alone: one failed call marks its card, not the page.
 * @param {Record<string, any>|undefined} mainInfo - the roster's main block. */
async function openAgentMain(mainInfo) {
  const name = String(mainInfo?.name ?? "Kairos");
  const title = `${name} · main agent`;
  const token = openDetail(title, (inner) => {
    inner.append(el("div", "detail-title", name));
    inner.append(el("div", "sp-note", "loading…"));
  });
  const [host, settings, creds] = await Promise.allSettled([
    rpc("host.describe"),
    rpc("settings.describe"),
    rpc("credentials.describe", { refs: ["DEEPSEEK_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"] }),
  ]);
  if (token !== detailSeq) return; // the operator moved on mid-fetch
  openDetail(title, (inner) => {
    inner.append(el("div", "detail-title", name));
    inner.append(el("div", "detail-sub", `main agent · owns this runtime · ${dash(mainInfo?.runtime)}`));
    const grid = el("div", "detail-grid");
    inner.append(grid);

    const model = panelCard("model");
    if (host.status === "fulfilled") {
      kvRow(model, "provider", dash(host.value?.provider));
      kvRow(model, "model", dash(host.value?.model));
    } else {
      model.append(panelError(host.reason, "host.describe"));
    }
    if (settings.status === "fulfilled") {
      const ns = (settings.value?.namespaces ?? []).find((n) => n?.ns === "agent-default-model");
      kvRow(model, "effort", dash(ns?.value?.reasoningEffort));
    }
    grid.append(model);

    const hostCard = panelCard("host");
    if (host.status === "fulfilled") {
      kvRow(hostCard, "cwd", dash(host.value?.cwd));
      kvRow(hostCard, "attached", dash(host.value?.attachedSessions));
      kvRow(hostCard, "home", dash(host.value?.home));
    } else {
      hostCard.append(panelError(host.reason, "host.describe"));
    }
    grid.append(hostCard);

    const keys = panelCard("keys");
    if (creds.status === "fulfilled") {
      const map = creds.value?.credentials ?? {};
      for (const ref of ["DEEPSEEK_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]) {
        const entry = map[ref];
        const set = entry?.configured === true;
        const row = el("div", "sp-kv");
        row.append(el("span", "sp-k", ref.toLowerCase().replaceAll("_", " ")));
        row.append(el("span", `sp-v ${set ? "ok" : "miss"}`, set ? `set · ${dash(entry?.source)}` : "not set"));
        keys.append(row);
      }
    } else {
      keys.append(panelError(creds.reason, "credentials.describe"));
    }
    grid.append(keys);

    const usage = panelCard("session usage");
    usage.id = "agent-session";
    grid.append(usage);
  });
  renderAgentSession();
}

/** One connected agent's page: its directory entry, plus the way out.
 * @param {Record<string, any>} agent - a roster `local` row. */
function openLocalAgent(agent) {
  const found = agent.found === true;
  openDetail(`${String(agent.label)} · local agent`, (inner) => {
    inner.append(el("div", "detail-title", String(agent.label)));
    inner.append(el("div", "detail-sub", found ? "local agent · connected" : "local agent · connected, not answering"));
    const card = panelCard("probe");
    kvRow(card, "status", found ? "answering" : "not answering");
    kvRow(card, "binary", String(agent.bin));
    if (found) kvRow(card, "version", dash(agent.version));
    inner.append(card);

    /* The Hermes-shaped second half of the handshake: is it signed in? */
    const auth = agent.auth ?? { state: "unknown" };
    const authCard = panelCard("auth");
    kvRow(authCard, "signed in", auth.state === "ok" ? "yes" : auth.state === "none" ? "NO" : "unknown");
    if (auth.detail) kvRow(authCard, "method", String(auth.detail));
    if (auth.account) kvRow(authCard, "account", String(auth.account));
    inner.append(authCard);
    if (auth.state === "none") {
      const hint = Object.hasOwn(LOGIN_HINTS, String(agent.bin)) ? LOGIN_HINTS[String(agent.bin)] : undefined;
      inner.append(el("div", "sp-note", hint !== undefined
        ? `Signed out — run in your terminal: ${hint}`
        : "Signed out — sign in from this agent's own CLI."));
    }

    /* What the connection is FOR: the tool Kairos gets in every strategy session. */
    const use = panelCard("kairos");
    if (typeof agent.tool === "string") {
      kvRow(use, "tool", agent.tool);
      use.append(el("div", "sp-note",
        `Kairos can call ${agent.tool} from any strategy session. It answers about that session's workspace and cannot run commands or edit files.`));
    } else {
      use.append(el("div", "sp-note", "connected, but the face has no recipe for this agent yet — not callable by Kairos."));
    }
    inner.append(use);

    inner.append(el("div", "sp-note", found
      ? `Probed host-side as "${agent.bin} --version" on the face process's PATH; answers cache for a minute.`
      : `No "${agent.bin}" binary answered on the face process's PATH — still on the roster until disconnected.`));
    const actions = el("div", "detail-actions");
    const gone = el("button", "picker-btn danger", "disconnect");
    /** @type {HTMLButtonElement} */ (gone).type = "button";
    const note = el("div", "sp-note err");
    gone.addEventListener("click", async () => {
      /** @type {HTMLButtonElement} */ (gone).disabled = true;
      const ok = await disconnectAgent(String(agent.bin), true);
      if (!ok) {
        /** @type {HTMLButtonElement} */ (gone).disabled = false;
        note.textContent = "disconnect failed — see the roster";
        actions.append(note);
      }
    });
    actions.append(gone);
    inner.append(actions);
  });
}

/** Drop one agent from the roster (the binary is untouched). Refreshes the
 * index; `reopenConnect` also lands on the connect page — where an installed
 * agent reappears as a candidate, ready to reconnect.
 * @param {string} bin @param {boolean} reopenConnect @returns {Promise<boolean>} */
async function disconnectAgent(bin, reopenConnect) {
  try {
    await panelData("/data/agents/disconnect", { bin });
  } catch (err) {
    failed(err, "disconnect");
    return false;
  }
  if (activePanel === "agent") void refreshAgentPanel();
  if (reopenConnect) void openConnectPage();
  return true;
}

/** The roster page ("+ connect an agent"): what is connected (each
 * removable), what auto-discovery found on this machine (connect one click
 * away, ↻ re-probes now), and connect-by-name for anything else. */
async function openConnectPage() {
  const token = openDetail(CONNECT_TITLE, (inner) => {
    inner.append(el("div", "detail-title", "local agents"));
    inner.append(el("div", "sp-note", "probing this machine…"));
  });
  /** @type {Record<string, any>} */
  let body;
  try {
    body = await panelData("/data/agents.json");
  } catch (err) {
    if (token !== detailSeq) return;
    openDetail(CONNECT_TITLE, (inner) => {
      inner.append(el("div", "detail-title", "local agents"));
      inner.append(panelError(err, "agents"));
    });
    return;
  }
  if (token !== detailSeq) return; // the operator moved on mid-probe
  renderConnectPage(body);
}

const CONNECT_TITLE = "local agents · connect";

/** Draw the roster page from one agents listing. Every action on it
 * (connect, delete, refresh) re-fetches and redraws, so the page is always
 * the host's current truth. @param {Record<string, any>} body */
function renderConnectPage(body) {
  openDetail(CONNECT_TITLE, (inner) => {
    inner.append(el("div", "detail-title", "local agents"));
    const note = el("div", "sp-note err");
    const fail = (what, err) => {
      note.textContent = `${what}: ${err instanceof Error ? err.message : String(err)}`;
    };
    /** Redraw from the host after an action changed the roster. */
    const redraw = async () => {
      if (activePanel === "agent") void refreshAgentPanel();
      try {
        renderConnectPage(await panelData("/data/agents.json"));
      } catch (err) {
        fail("agents", err);
      }
    };

    /* -- connected: the roster as it stands, each row removable -- */
    const have = panelCard("connected");
    const local = Array.isArray(body.local) ? body.local : [];
    if (local.length === 0) have.append(el("div", "sp-note", "none yet"));
    for (const agent of local) {
      const row = el("div", "connect-row");
      const found = agent.found === true;
      const signedOut = found && agent.auth?.state === "none";
      const dot = phaseDot(!found ? "disabled" : signedOut ? "warn" : "active");
      dot.title = !found ? "not answering" : signedOut ? "signed out" : "answering";
      row.append(dot, el("span", "connect-name", String(agent.label)));
      const ver = el("span", "connect-ver", found ? dash(agent.version) : "not answering");
      ver.title = String(agent.bin);
      row.append(ver);
      const del = /** @type {HTMLButtonElement} */ (el("button", "picker-btn danger", "delete"));
      del.type = "button";
      del.title = `remove ${agent.bin} from the roster (the binary is untouched)`;
      del.addEventListener("click", async () => {
        del.disabled = true;
        if (await disconnectAgent(String(agent.bin), false)) void redraw();
        else del.disabled = false;
      });
      row.append(del);
      have.append(row);
    }
    inner.append(have);

    /** @param {string} bin @param {HTMLButtonElement} btn */
    const connect = async (bin, btn) => {
      btn.disabled = true;
      note.textContent = "";
      try {
        await panelData("/data/agents/connect", { bin });
        void redraw();
      } catch (err) {
        btn.disabled = false;
        fail(`connect ${bin}`, err);
      }
    };

    /* -- detected: auto-discovery over this machine's PATH, re-probed on ↻ -- */
    const card = el("div", "sp-card");
    const head = el("div", "sp-title sp-title-row");
    head.append(el("span", null, "detected on this machine"));
    const refresh = /** @type {HTMLButtonElement} */ (el("button", "sp-title-btn", "↻ refresh"));
    refresh.type = "button";
    refresh.title = "probe this machine again now (skips the one-minute cache)";
    refresh.addEventListener("click", async () => {
      refresh.disabled = true;
      refresh.textContent = "probing…";
      try {
        const fresh = await panelData("/data/agents/rescan", {});
        if (activePanel === "agent") void refreshAgentPanel();
        renderConnectPage(fresh);
      } catch (err) {
        refresh.disabled = false;
        refresh.textContent = "↻ refresh";
        fail("refresh", err);
      }
    });
    head.append(refresh);
    card.append(head);
    const candidates = Array.isArray(body.candidates) ? body.candidates : [];
    if (candidates.length === 0) {
      card.append(el("div", "sp-note", "nothing new detected — refresh after installing one, or connect by name below"));
    }
    for (const cand of candidates) {
      const row = el("div", "connect-row");
      row.append(el("span", "connect-name", String(cand.label)));
      const version = el("span", "connect-ver", dash(cand.version));
      version.title = `${cand.bin} · ${dash(cand.version)}`;
      row.append(version);
      const btn = /** @type {HTMLButtonElement} */ (el("button", "picker-btn", "connect"));
      btn.type = "button";
      btn.addEventListener("click", () => void connect(String(cand.bin), btn));
      row.append(btn);
      card.append(row);
    }
    inner.append(card);

    /* -- by name: anything the suggestion list does not know -- */
    const form = el("div", "picker-new");
    const input = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    input.type = "text";
    input.placeholder = "connect by binary name, e.g. gemini";
    const btn = /** @type {HTMLButtonElement} */ (el("button", "picker-btn", "connect"));
    btn.type = "button";
    btn.addEventListener("click", () => {
      const bin = input.value.trim();
      if (bin !== "") void connect(bin, btn);
    });
    input.addEventListener("keydown", (event) => {
      if (/** @type {KeyboardEvent} */ (event).key !== "Enter") return;
      event.preventDefault();
      const bin = input.value.trim();
      if (bin !== "") void connect(bin, btn);
    });
    form.append(input, btn);
    inner.append(form);
    inner.append(note);
  });
}

/** The A2A placeholder page: the seat is declared, nothing is wired. */
function openA2A() {
  openDetail("A2A network · pending", (inner) => {
    inner.append(el("div", "detail-title", "A2A network"));
    inner.append(el("div", "detail-sub", "agent-to-agent network · not yet open"));
    inner.append(el("div", "sp-note",
      "Network agents land here when the A2A network opens. Nothing is wired yet — this entry declares the seat."));
  });
}

/** (Re)fill the usage card from the projection store — called on every stored
 * tokenUsage/contextPressure change and on every session switch; a no-op when
 * the agent panel has never been built. */
function renderAgentSession() {
  const card = document.querySelector("#agent-session");
  if (card === null) return;
  card.replaceChildren(el("div", "sp-title", "session usage"));
  if (activeSession === null) {
    card.append(el("div", "sp-note", "no session open"));
    return;
  }
  const units = projStore.get(activeSession);
  const usage = /** @type {Record<string, any>|undefined} */ (units?.get("tokenUsage")?.value);
  const pressure = /** @type {Record<string, any>|undefined} */ (units?.get("contextPressure")?.value);
  if (usage === undefined && pressure === undefined) {
    card.append(el("div", "sp-note", "no usage recorded yet"));
    return;
  }
  if (usage !== undefined) {
    kvRow(card, "input", fmtTokens(usage.uncachedInputTokens));
    kvRow(card, "output", fmtTokens(usage.outputTokens));
    kvRow(card, "cache read", fmtTokens(usage.cacheReadTokens));
    kvRow(card, "cache write", fmtTokens(usage.cacheWriteTokens));
  }
  const window = pressure?.contextWindow;
  const used = typeof pressure?.projectedTokens === "number" ? pressure.projectedTokens : pressure?.pressureTokens;
  if (typeof window === "number" && window > 0 && typeof used === "number") {
    const pct = Math.min(100, Math.round((used / window) * 100));
    kvRow(card, "context", `${fmtTokens(used)} / ${fmtTokens(window)} · ${pct}%`);
    const bar = el("div", "sp-bar");
    const fill = el("div", "sp-bar-fill");
    fill.style.width = `${pct}%`;
    if (pct >= 80) fill.classList.add("hot");
    bar.append(fill);
    card.append(bar);
  }
}

/* -- memory -- */

/** The skill catalog, grouped by pack: Kairos's standing knowledge. */
async function refreshMemoryPanel() {
  const panel = $("#panel-memory");
  panel.replaceChildren(el("div", "sp-note", "loading…"));
  let body;
  try {
    body = await panelData("/data/memory.json");
  } catch (err) {
    panel.replaceChildren(panelError(err, "memory"));
    return;
  }
  if (activePanel !== "memory") return;
  panel.replaceChildren();
  const groups = Array.isArray(body.groups) ? body.groups : [];
  for (const group of groups) {
    const skills = Array.isArray(group.skills) ? group.skills : [];
    panel.append(spGroup(String(group.name), String(skills.length)));
    for (const skill of skills) {
      const row = el("div", "sp-row");
      row.append(el("div", "sp-row-name", String(skill.name)));
      row.append(el("div", "sp-row-desc", dash(skill.description)));
      panel.append(indexRow(row, () => void openSkill(String(skill.name))));
    }
  }
  if (groups.length === 0) panel.append(el("div", "sp-note", "no skills discovered"));
}

/** One skill's page: the full SKILL.md body, rendered in the right pane. */
async function openSkill(name) {
  const token = openDetail(`${name} · memory`, (inner) => {
    inner.append(el("div", "detail-title", name));
    inner.append(el("div", "sp-note", "loading…"));
  });
  let detail;
  try {
    detail = await panelData("/data/memory/skill", { name });
  } catch (err) {
    if (token !== detailSeq) return;
    openDetail(`${name} · memory`, (inner) => {
      inner.append(el("div", "detail-title", name));
      inner.append(panelError(err, name));
    });
    return;
  }
  if (token !== detailSeq) return; // the operator moved on mid-fetch
  openDetail(`${String(detail.name)} · memory`, (inner) => {
    inner.append(el("div", "detail-title", String(detail.name)));
    inner.append(el("div", "detail-sub", `skill · ${dash(detail.group)} pack`));
    if (typeof detail.path === "string" && detail.path !== "") {
      inner.append(el("div", "detail-path", detail.path));
    }
    const doc = el("div", "detail-doc");
    doc.append(renderMarkdown(String(detail.content ?? "")).node);
    inner.append(doc);
  });
}

/* -- plugin -- */

/** The plugin index: one row per MCP server, one for the composed row tree —
 * each opening its table in the right pane. */
async function refreshPluginPanel() {
  const panel = $("#panel-plugin");
  panel.replaceChildren(el("div", "sp-note", "loading…"));
  let body;
  try {
    body = await panelData("/data/plugins.json");
  } catch (err) {
    if (activePanel !== "plugin") return;
    panel.replaceChildren(panelError(err, "plugins"));
    return;
  }
  if (activePanel !== "plugin") return;
  panel.replaceChildren();

  panel.append(spGroup("mcp servers"));
  const servers = Array.isArray(body.mcp) ? body.mcp : [];
  if (servers.length === 0) panel.append(el("div", "sp-note", "no MCP servers composed"));
  for (const server of servers) {
    const line = el("div", "sp-plug");
    const tools = Array.isArray(server.tools) ? server.tools : [];
    line.append(phaseDot(server.phase), el("span", "sp-plug-name", String(server.server)));
    line.append(el("span", "sp-count", `${tools.length} tools`));
    panel.append(indexRow(line, () => openMcpServer(server)));
  }

  const rows = Array.isArray(body.rows) ? body.rows : [];
  const failed = rows.filter((row) => row.phase === "failed").length;
  panel.append(spGroup("composed rows"));
  const tree = el("div", "sp-plug");
  tree.append(phaseDot(failed > 0 ? "failed" : "active"), el("span", "sp-plug-name", "the live plugin tree"));
  tree.append(el("span", "sp-count", failed > 0 ? `${rows.length} · ${failed} failed` : String(rows.length)));
  panel.append(indexRow(tree, () => openComposedRows(rows)));
}

/** A bare (thead + tbody) instrument table for a detail page.
 * @param {string[]} headers @returns {{wrap: HTMLElement, tbody: HTMLElement}} */
function detailTable(headers) {
  const wrap = el("div", "viz-scroll detail-table");
  const table = el("table", "viz-table");
  const thead = el("thead");
  const head = el("tr");
  for (const header of headers) head.append(el("th", null, header));
  thead.append(head);
  const tbody = el("tbody");
  table.append(thead, tbody);
  wrap.append(table);
  return { wrap, tbody };
}

/** One MCP server's page: its live tool roster as a table.
 * @param {Record<string, any>} server - a plugins.json `mcp` row. */
function openMcpServer(server) {
  const name = String(server.server);
  const tools = Array.isArray(server.tools) ? server.tools : [];
  openDetail(`${name} · mcp`, (inner) => {
    inner.append(el("div", "detail-title", name));
    inner.append(el("div", "detail-sub", `MCP server · ${server.phase ?? "not mounted"} · ${tools.length} tools`));
    if (tools.length === 0) {
      inner.append(el("div", "sp-note", "no tools registered — offline or still connecting"));
      return;
    }
    const { wrap, tbody } = detailTable(["tool", "description"]);
    const prefix = `mcp__${name}__`;
    for (const tool of tools) {
      const full = String(tool.name);
      const tr = el("tr");
      // Display-only trim; the full registered name stays on the tooltip.
      const cell = el("td", "sym", full.startsWith(prefix) ? full.slice(prefix.length) : full);
      cell.title = full;
      tr.append(cell, el("td", null, String(tool.description ?? "")));
      tbody.append(tr);
    }
    inner.append(wrap);
  });
}

/** The composed row tree's page: every live Loader row as a table.
 * @param {Record<string, any>[]} rows - plugins.json `rows`. */
function openComposedRows(rows) {
  const failed = rows.filter((row) => row.phase === "failed").length;
  openDetail("composed rows · plugin", (inner) => {
    inner.append(el("div", "detail-title", "composed rows"));
    inner.append(el("div", "detail-sub",
      `the live plugin tree · ${rows.length} rows${failed > 0 ? ` · ${failed} FAILED` : ""}`));
    const { wrap, tbody } = detailTable(["module", "row id", "phase"]);
    for (const row of rows) {
      const tr = el("tr");
      tr.append(el("td", "sym", String(row.module).replace(/^@deepseek-ai\//, "")));
      tr.append(el("td", null, String(row.id)));
      const phase = row.enabled === false ? "disabled" : String(row.phase ?? EM);
      const cell = el("td", null, phase);
      if (phase === "active") cell.classList.add("up");
      if (phase === "failed") cell.classList.add("down");
      tr.append(cell);
      tbody.append(tr);
    }
    inner.append(wrap);
  });
}

/* ---------- wiring ---------- */

$("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  void send();
});
$("#new-session").addEventListener("click", () => newSession());
$("#stop").addEventListener("click", () => void stopTurn());
for (const btn of document.querySelectorAll(".rail-btn")) {
  btn.addEventListener("click", () => setPanel(/** @type {HTMLElement} */ (btn).dataset.panel ?? "strategy"));
}

openMux(acceptFrame, {
  onOpen: () => {
    status("connected");
    void refreshSessions();
    // `since` is unimplemented at this pin: the contract's own recovery is to
    // reopen the stream and refetch history, which is exactly this.
    if (activeSession !== null) void openSession(activeSession);
  },
});

markActive();
status("connecting…");
/* Archive metadata first, then the list that folds by it. */
void loadSessionsMeta().then(() => refreshSessions());
/* The blank page is an unsaved new session, so it gets the picker too; the
 * index it loads also feeds the sidebar's strategy grouping. */
void showStrategyPicker();
