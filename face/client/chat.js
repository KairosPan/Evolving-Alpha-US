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
 * THE RPC SURFACE IS CLOSED: `session.list/create/history/prompt/cancel`,
 * `respond`, and `events.mux`. Answering a gate goes through `respond`, never
 * `rpc` — a different envelope entirely (see api.js).
 * @module
 */
import { rpc, respond, openMux } from "./api.js";
import { mapFrame } from "./mapper.js";
import { renderResult } from "./render.js";

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
    const bubble = el("div", "bubble pre", dash(view.text));
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
  top.append(el("span", "conv-date", when(summary.updatedAt)));
  row.append(top);

  const sub = el("div", "conv-sub");
  if ([...gates.values()].some((gate) => gate.sessionId === id)) sub.append(waitingChip());
  if (summary.running === true) sub.append(el("span", "chip", "running"));
  sub.append(el("span", "conv-tail", dash(summary.cwd ?? id)));
  row.append(sub);

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
  const row = activeSession === null ? undefined : convRows.get(activeSession);
  $("#topbar-name").textContent = activeSession === null ? "new session" : row?.dataset.title ?? "untitled";
  $("#topbar-raw").title = dash(activeSession);
  /** @type {HTMLButtonElement} */ ($("#stop")).disabled = activeSession === null;
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
  for (const summary of value?.items ?? []) {
    const row = convRow(summary);
    row.dataset.title = titleOf(summary);
    convRows.set(String(summary.sessionId), row);
    list.append(row);
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
  loadingSession = null;
  activeSession = null;
  resetFlow();
  markActive();
  status("new session · type below");
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
      const created = await rpc("session.create", {});
      const id = created?.sessionId;
      if (typeof id !== "string") throw new Error("session.create returned no sessionId");
      activeSession = id;
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

/* ---------- wiring ---------- */

$("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  void send();
});
$("#new-session").addEventListener("click", () => newSession());
$("#stop").addEventListener("click", () => void stopTurn());

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
void refreshSessions();
