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
    if (lane === "k") wrap.append(el("div", "who", "Kairos"));
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
 * Settle an answered gate's card: the buttons go, the outcome stays.
 * @param {HTMLElement} node @param {string} outcome - what was sent, in the operator's words.
 */
function settle(node, outcome) {
  node.classList.add("answered");
  node.querySelector(".card-actions")?.replaceWith(el("div", "card-line", `answered · ${outcome}`));
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
  head.append(el("span", "kind", "kairos asks"));
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
    if (options.length > 0) {
      const row = el("div", "opt-row");
      for (const option of options) {
        // Options are objects; the ANSWER sends the option's label.
        const label = typeof option?.label === "string" ? option.label : String(option);
        const btn = el("button", "opt", label);
        /** @type {HTMLButtonElement} */ (btn).type = "button";
        if (option?.description) btn.title = String(option.description);
        btn.addEventListener("click", () => {
          const on = pick.selected.has(label);
          if (question?.multiSelect !== true) {
            pick.selected.clear();
            for (const other of row.children) other.classList.remove("on");
          }
          if (on) pick.selected.delete(label);
          else pick.selected.add(label);
          btn.classList.toggle("on", pick.selected.has(label));
          sync();
        });
        row.append(btn);
      }
      block.append(row);
    }

    // A question with no options is free text; so is the "other" box beside a
    // menu, which `custom` exists for.
    const input = el("input", "ask-input");
    const field = /** @type {HTMLInputElement} */ (input);
    field.type = "text";
    field.placeholder = options.length > 0 ? "other…" : "your answer";
    field.addEventListener("input", () => {
      pick.custom = field.value;
      sync();
    });
    block.append(input);
    node.append(block);
  });

  submit.addEventListener("click", async () => {
    submitBtn.disabled = true;
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
  if (view.sessionId !== undefined && view.sessionId !== activeSession) {
    // Flag the row instead — once, however many times the mux replays the gate.
    const sub = convRows.get(view.sessionId)?.querySelector(".conv-sub");
    if (sub && sub.querySelector(".chip.waiting") === null) sub.prepend(waitingChip());
    return;
  }
  renderGate(view);
}

/** @returns {HTMLElement} the sidebar's "this session is waiting on you" chip. */
function waitingChip() {
  return el("span", "chip waiting", "waiting");
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

/** What each live block opening reads as on the status line. */
const PULSE_TEXT = {
  reasoning: "Kairos is thinking…",
  text: "Kairos is writing…",
  "tool-call": "Kairos is preparing a tool call…",
};

/** Whether the status line currently shows a pulse — so the reset on the next
 * settled frame only ever overwrites a pulse's own text, never "sent" or an
 * error the operator should still be reading. */
let pulsing = false;

/** @param {string|undefined} mode - the block kind that just opened. */
function pulse(mode) {
  status(PULSE_TEXT[mode ?? ""] ?? "Kairos is working…");
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
  if ([...gates.values()].some((gate) => gate.sessionId === id)) sub.append(waitingChip());
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

/** Refetch the sidebar. Out-of-order answers are dropped, not rendered. */
async function refreshSessions() {
  const token = ++listSeq;
  let value;
  try {
    value = await rpc("session.list");
  } catch (err) {
    failed(err, "session.list");
    return;
  }
  if (token !== listSeq) return;
  const list = $("#conv-list");
  convRows.clear();
  list.replaceChildren();
  /* Group by strategy (derived from each session's cwd); archived sessions
   * fold into their own group at the BOTTOM regardless of recency. Items
   * arrive updatedAt-desc, so live group order is the recency of each group's
   * freshest session, and rows inside a group keep that order too.
   * @type {Map<string, Record<string, any>[]>} */
  const buckets = new Map();
  for (const summary of value?.items ?? []) {
    if (deletedSet.has(String(summary.sessionId))) continue; // a host-memory ghost
    // Attached sessions list with a projections block — seed the usage store.
    seedProjections(String(summary.sessionId), summary.projections);
    const label = archivedSet.has(String(summary.sessionId)) ? "archived" : strategyLabel(summary.cwd);
    let bucket = buckets.get(label);
    if (bucket === undefined) {
      bucket = [];
      buckets.set(label, bucket);
    }
    bucket.push(summary);
  }
  const order = [...buckets.keys()].filter((label) => label !== "archived");
  if (buckets.has("archived")) order.push("archived");
  for (const label of order) {
    const bucket = buckets.get(label) ?? [];
    const box = el("div");
    list.append(groupHeader(label, bucket.length, box), box);
    for (const summary of bucket) {
      const row = convRow(summary);
      row.dataset.title = titleOf(summary);
      convRows.set(String(summary.sessionId), row);
      box.append(row);
    }
  }
  markActive();
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
  activeSession = id;
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
}

/** Start a fresh conversation. No session is created until the first prompt —
 * a session created by a button that is then abandoned is a blank row forever. */
function newSession() {
  openSeq += 1; // orphan any in-flight history load
  closeDetail();
  loadingSession = null;
  activeSession = null;
  pendingCwd = undefined;
  resetFlow();
  markActive();
  status("new session · pick a strategy, then type below");
  void showStrategyPicker();
}

/* ---------- the strategy picker: a session's workspace IS a strategy ---------- */

/** `/data/strategies.json`'s last good answer — `{root, strategies}` — used by
 * the picker and by sidebar grouping. @type {Record<string, any>|null} */
let strategyIndex = null;

/** The `cwd` the NEXT `session.create` carries; `undefined` is the host
 * default — the workbench repo root. @type {string|undefined} */
let pendingCwd;

async function loadStrategyIndex() {
  try {
    const res = await fetch("/data/strategies.json");
    const body = await res.json();
    if (body?.ok === true) strategyIndex = body;
  } catch { /* grouping degrades to path basenames; the picker says so */ }
  return strategyIndex;
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

/** Sidebar groups the operator folded — view state, per browser. The archive
 * group starts folded the first time it ever appears. @type {Set<string>} */
const collapsedGroups = new Set(/** @type {string[]} */ ((() => {
  try {
    return JSON.parse(localStorage.getItem("face.collapsed-groups") ?? '["archived"]');
  } catch {
    return ["archived"];
  }
})()));

function persistCollapsed() {
  try {
    localStorage.setItem("face.collapsed-groups", JSON.stringify([...collapsedGroups]));
  } catch { /* view state only — losing it costs a click */ }
}

/** One clickable group header: chevron · label · count. Toggling folds the
 * given box locally; no refetch. */
function groupHeader(label, count, box) {
  const head = el("div", "conv-group");
  const chev = el("span", "chev", collapsedGroups.has(label) ? "▸" : "▾");
  head.append(chev, el("span", "conv-group-name", label), el("span", "conv-group-n", String(count)));
  box.hidden = collapsedGroups.has(label);
  head.addEventListener("click", () => {
    if (collapsedGroups.has(label)) collapsedGroups.delete(label);
    else collapsedGroups.add(label);
    persistCollapsed();
    box.hidden = collapsedGroups.has(label);
    chev.textContent = box.hidden ? "▸" : "▾";
  });
  return head;
}

/** Which sidebar group a session's cwd belongs to. */
function strategyLabel(cwd) {
  if (typeof cwd !== "string" || cwd === "") return "elsewhere";
  const root = strategyIndex?.root;
  if (typeof root === "string") {
    if (cwd === root) return "workbench";
    const prefix = `${root}/strategies/`;
    if (cwd.startsWith(prefix)) {
      const name = cwd.slice(prefix.length).split("/")[0];
      if (name !== "") return name;
    }
  }
  return cwd.split("/").filter((part) => part !== "").pop() ?? "elsewhere";
}

/** One selectable row of the picker. @param {string|undefined} cwd - the
 * workspace it stands for; undefined = the workbench default. */
function pickerRow(label, cwd, badge, picker) {
  const row = el("div", "pick-row");
  row.setAttribute("role", "button");
  row.tabIndex = 0;
  row.append(el("span", "pick-name", label));
  if (badge) row.append(el("span", "chip", badge));
  const choose = () => {
    pendingCwd = cwd;
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

/** Offer the strategies as workspaces for the next session. The first prompt
 * creates the session with the picked cwd; until then nothing exists. */
async function showStrategyPicker() {
  const index = await loadStrategyIndex();
  if (activeSession !== null || flow().querySelector(".picker") !== null) return;
  const picker = el("div", "picker");
  picker.append(el("div", "picker-title", "workspace — the strategy this session works"));
  const rows = el("div", "picker-rows");
  for (const s of index?.strategies ?? []) rows.append(pickerRow(s.name, s.cwd, s.status, picker));
  rows.append(pickerRow("workbench", undefined, "repo root", picker));
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
    picker.append(el("div", "picker-note", "strategy list unavailable — sessions fall back to the workbench"));
  } else {
    const form = el("div", "picker-new");
    const input = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    input.type = "text";
    input.placeholder = "new strategy (a-z 0-9 - _) — copies strategies/_template";
    const create = /** @type {HTMLButtonElement} */ (el("button", "picker-btn", "create"));
    create.type = "button";
    create.addEventListener("click", async () => {
      const name = input.value.trim();
      if (name === "") return;
      create.disabled = true;
      try {
        const res = await fetch("/data/strategies", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name }),
        });
        const body = await res.json();
        if (body?.ok !== true) throw new Error(String(body?.error ?? `HTTP ${res.status}`));
        const row = pickerRow(body.name, body.cwd, body.status, picker);
        rows.insertBefore(row, rows.lastElementChild); // above the workbench row
        row.click();
        input.value = "";
      } catch (err) {
        failed(err, "create strategy");
      } finally {
        create.disabled = false;
      }
    });
    form.append(input, create);
    picker.append(form);
  }
  flow().append(picker);
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
      const created = await rpc("session.create", pendingCwd === undefined ? {} : { cwd: pendingCwd });
      const id = created?.sessionId;
      if (typeof id !== "string") throw new Error("session.create returned no sessionId");
      activeSession = id;
      pendingCwd = undefined;
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
  else if (phase === "disabled") dot.classList.add("off");
  dot.title = phase ?? "not mounted";
  return dot;
}

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
  kairos.append(el("span", "sp-count", dash(mainInfo?.runtime)));
  panel.append(indexRow(kairos, () => void openAgentMain(mainInfo)));

  /* -- local agents: what else is installed beside Kairos -- */
  panel.append(spGroup("local agents"));
  if (rosterErr !== null) {
    panel.append(panelError(rosterErr, "agents"));
  } else {
    const local = Array.isArray(roster?.local) ? roster.local : [];
    for (const agent of local) {
      const line = el("div", "sp-plug");
      const found = agent.found === true;
      const dot = phaseDot(found ? "active" : "disabled");
      dot.title = found ? "installed" : "not installed";
      line.append(dot, el("span", "sp-plug-name", String(agent.label)));
      line.append(el("span", "sp-count", found ? dash(agent.version) : "not installed"));
      if (!found) line.classList.add("off");
      panel.append(indexRow(line, () => openLocalAgent(agent)));
    }
    if (local.length === 0) panel.append(el("div", "sp-note", "no local agents probed"));
  }

  /* -- a2a network: declared, not yet open -- */
  panel.append(spGroup("a2a network", "pending"));
  const a2a = el("div", "sp-plug off");
  a2a.append(phaseDot("disabled"), el("span", "sp-plug-name", "A2A network"));
  panel.append(indexRow(a2a, openA2A));
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

/** One local agent's page: a directory entry — presence, version, binary.
 * @param {Record<string, any>} agent - a roster `local` row. */
function openLocalAgent(agent) {
  const found = agent.found === true;
  openDetail(`${String(agent.label)} · local agent`, (inner) => {
    inner.append(el("div", "detail-title", String(agent.label)));
    inner.append(el("div", "detail-sub", found ? "local agent · installed on this machine" : "local agent · not installed"));
    const card = panelCard("probe");
    kvRow(card, "status", found ? "installed" : "not installed");
    kvRow(card, "binary", String(agent.bin));
    if (found) kvRow(card, "version", dash(agent.version));
    inner.append(card);
    inner.append(el("div", "sp-note", found
      ? `Probed host-side as "${agent.bin} --version" on the face process's PATH; answers cache for a minute.`
      : `No "${agent.bin}" binary answered on the face process's PATH.`));
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
