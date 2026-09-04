/** The channel landing page: what a channel has produced, before you enter it.
 *
 * Assembly only. Every judgement — is this thesis still the untouched
 * template, which backtest is newest, what the journal says — was made
 * server-side in channels.ts, where it is unit-tested; this file must not
 * re-derive any of it. No innerHTML anywhere, same as the rest of the client.
 * @module
 */
import { renderMarkdown } from "./markdown.js";

/** @param {string} tag @param {string|null} [cls] @param {string} [text] */
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

/** Bytes as the file list shows them. @param {number} n */
const size = (n) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`);

/**
 * A JSON value flattened to dotted paths, so a nested backtest result shows
 * its `discarded` and `score_stats` blocks instead of dropping them. Arrays
 * become a count plus a short preview; nothing is filtered silently.
 * @param {unknown} value @param {string} [prefix] @param {[string, string][]} [out]
 * @returns {[string, string][]}
 */
function flatten(value, prefix = "", out = []) {
  if (value === null || typeof value !== "object") {
    out.push([prefix, String(value)]);
  } else if (Array.isArray(value)) {
    const preview = value.slice(0, 3).map((v) => (v === null || typeof v !== "object" ? String(v) : "{…}")).join(", ");
    out.push([prefix, `${value.length} items${value.length === 0 ? "" : `: ${preview}${value.length > 3 ? ", …" : ""}`}`]);
  } else {
    for (const [k, v] of Object.entries(value)) flatten(v, prefix === "" ? k : `${prefix}.${k}`, out);
  }
  return out;
}

/** @param {[string, string][]} rows @returns {HTMLElement} */
function kvTable(rows) {
  const table = el("table", "viz-table");
  const body = document.createElement("tbody");
  for (const [k, v] of rows) {
    const tr = document.createElement("tr");
    tr.append(el("td", "ch-k", k), el("td", "ch-v", v));
    body.append(tr);
  }
  table.append(body);
  return table;
}

/**
 * Build the whole page into `inner`.
 * @param {HTMLElement} inner
 * @param {Record<string, any>} payload - `/data/channels/overview`'s body,
 *   plus the client's own `allBins` and `sessions` (see `openChannel`).
 * @param {{onRename(title: string): void, onToggleAgent(bin: string, on: boolean): void,
 *   onNewRound(): void, onOpenSession(id: string): void}} actions
 */
export function renderChannelPage(inner, payload, actions) {
  const { channel, status, body, agents } = payload;

  /* 1 - header */
  const head = el("div", "ch-head");
  const title = el("h2", "ch-title", channel.title);
  title.title = "click to rename";
  title.addEventListener("click", () => {
    const next = window.prompt("channel title", channel.title);
    if (next !== null && next.trim() !== "" && next !== channel.title) void actions.onRename(next.trim());
  });
  head.append(title);
  if (status.status) {
    const badge = el("span", "ch-badge", status.status);
    badge.dataset.status = status.status;
    head.append(badge);
  }
  if (channel.missingDir) head.append(el("span", "ch-warn", "directory missing"));
  head.append(el("div", "ch-path", channel.dir));

  const chips = el("div", "ch-chips");
  chips.append(el("span", "ch-chips-label", "agents in this channel"));
  for (const bin of payload.allBins ?? agents) {
    const on = agents.includes(bin);
    const chip = el("button", on ? "ch-chip on" : "ch-chip", bin);
    chip.type = "button";
    chip.addEventListener("click", () => { void actions.onToggleAgent(bin, !on); });
    chips.append(chip);
  }
  if ((payload.allBins ?? agents).length === 0) chips.append(el("span", "ch-none", "no agents connected"));
  head.append(chips);
  inner.append(head);

  /* 2 - headline */
  if (status.one_line || status.next || status.numbers) {
    const card = el("div", "ch-card");
    if (status.one_line) card.append(el("p", "ch-oneline", status.one_line));
    if (status.next) card.append(el("p", "ch-next", `next: ${status.next}`));
    if (status.numbers) {
      const row = el("div", "ch-numbers");
      for (const [k, v] of Object.entries(status.numbers)) {
        const fig = el("div", "ch-fig");
        fig.append(el("div", "ch-fig-v", v), el("div", "ch-fig-k", k));
        row.append(fig);
      }
      card.append(row);
    }
    inner.append(card);
  }

  /* 3 - thesis */
  const thesis = el("section", "ch-sec");
  thesis.append(el("h3", null, "thesis"));
  if (body.thesis === null) thesis.append(el("p", "ch-none", "no THESIS.md yet"));
  else if (body.thesis.isTemplate) thesis.append(el("p", "ch-none", "no thesis yet - THESIS.md is still the template"));
  else thesis.append(renderMarkdown(body.thesis.markdown).node);
  inner.append(thesis);

  /* 4 - latest evidence; the FULL json always stays reachable, parseable or not */
  const ev = el("section", "ch-sec");
  ev.append(el("h3", null, "latest evidence"));
  if (body.latest === null) {
    ev.append(el("p", "ch-none", body.backtests.length === 0 ? "no backtests yet" : "the newest backtest could not be parsed"));
  } else {
    ev.append(el("div", "ch-file", body.latest.file));
    const wrap = el("div", "viz-scroll detail-table");
    wrap.append(kvTable(flatten(body.latest.json)));
    ev.append(wrap);
    const raw = document.createElement("details");
    raw.append(el("summary", null, "full JSON"));
    raw.append(el("pre", "ch-raw", JSON.stringify(body.latest.json, null, 2)));
    ev.append(raw);
  }
  for (const b of body.backtests) ev.append(el("div", "ch-file dim", `${b.file} · ${size(b.bytes)}`));
  inner.append(ev);

  /* 5 - journal */
  if (body.journal.length > 0) {
    const jr = el("section", "ch-sec");
    jr.append(el("h3", null, "journal"));
    for (const entry of body.journal.slice(0, 5)) {
      const row = el("div", "ch-journal");
      row.append(el("span", "ch-date", entry.date), el("span", null, entry.text));
      jr.append(row);
    }
    if (body.journal.length > 5) {
      const more = document.createElement("details");
      more.append(el("summary", null, `${body.journal.length - 5} earlier entries`));
      for (const entry of body.journal.slice(5)) {
        const row = el("div", "ch-journal");
        row.append(el("span", "ch-date", entry.date), el("span", null, entry.text));
        more.append(row);
      }
      jr.append(more);
    }
    inner.append(jr);
  }

  /* 6 - files */
  const files = el("section", "ch-sec");
  files.append(el("h3", null, "files"));
  for (const f of body.files) files.append(el("div", "ch-file dim", `${f.name} · ${size(f.bytes)} · ${f.mtime.slice(0, 10)}`));
  if (body.files.length === 0) files.append(el("p", "ch-none", "empty"));
  inner.append(files);

  /* 7 - sessions */
  const sessions = el("section", "ch-sec");
  sessions.append(el("h3", null, "conversations"));
  const start = el("button", "ch-new", "new round");
  start.type = "button";
  start.addEventListener("click", () => { void actions.onNewRound(); });
  sessions.append(start);
  for (const row of payload.sessions ?? []) {
    const line = el("div", row.archived ? "ch-session archived" : "ch-session");
    line.setAttribute("role", "button");
    line.tabIndex = 0;
    line.append(el("span", "ch-session-title", row.title ?? "untitled"));
    line.addEventListener("click", () => { void actions.onOpenSession(row.sessionId); });
    line.addEventListener("keydown", (event) => {
      const key = /** @type {KeyboardEvent} */ (event).key;
      if (key !== "Enter" && key !== " ") return;
      event.preventDefault();
      void actions.onOpenSession(row.sessionId);
    });
    sessions.append(line);
  }
  if ((payload.sessions ?? []).length === 0) sessions.append(el("p", "ch-none", "no conversations yet"));
  inner.append(sessions);
}
