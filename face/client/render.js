/** Pretty renderers for alpaca-kit tool results.
 *
 * `renderResult(toolName, text)` returns a DOM node when it recognizes BOTH the
 * tool and the payload shape, and `null` for everything else — the caller keeps
 * the raw `<pre>` as the fallback and as the "raw" toggle target, so an
 * unrecognized or malformed payload is never dressed up. Same discipline as
 * chat.js: every string lands via `textContent`, no `innerHTML` path at all.
 *
 * Shapes (alpaca_kit/mcp/tools.py): rows-frames `{ok, rows, truncated?}` for
 * market_snapshot / screen / daily_bars / positions / orders / earnings /
 * corp_actions; flat objects for breadth and account; `{ok, days}` for
 * calendar. `{ok:false}` stays on the raw path.
 *
 * Color note: the up/down pair is a red–green polarity that no palette can make
 * CVD-safe (deutan ΔE ~5), so the SIGN is always printed with the number —
 * color never carries the direction alone.
 * @module
 */

const EM = "—";
const SVG = "http://www.w3.org/2000/svg";

/** Keys whose numeric values read as signed deltas: printed with +/- and colored. */
const DELTA_KEYS = new Set(["unrealized_pl", "unrealized_plpc", "unrealized_intraday_pl",
  "unrealized_intraday_plpc", "change_today", "pct_change", "chg", "delta"]);

/** @param {string} tag @param {string|null} [cls] @param {string} [text] */
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** @param {string} tag @param {Record<string, string|number>} attrs */
function sv(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** Comma-grouped, <=2 decimals (4 under a dollar so penny quotes keep shape). */
function fmtNum(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return EM;
  const frac = Math.abs(v) < 1 && v !== 0 ? 4 : 2;
  return v.toLocaleString("en-US", { maximumFractionDigits: frac });
}

/** A value cell's text: numbers formatted, null/undefined an em-dash. */
function fmtCell(v) {
  if (v === null || v === undefined || v === "") return EM;
  return typeof v === "number" ? fmtNum(v) : String(v);
}

/** Signed rendering for delta-like numbers: "+1.23" / "-0.45", never bare. */
function fmtSigned(v, suffix = "") {
  if (typeof v !== "number" || !Number.isFinite(v)) return EM;
  return (v > 0 ? "+" : "") + fmtNum(v) + suffix;
}

/** label text from a snake_case key. */
const label = (key) => key.replaceAll("_", " ");

/** The scrollable table shell every tabular renderer shares. */
function tableShell(meta, table) {
  const wrap = el("div", "viz");
  if (meta) wrap.append(el("div", "viz-meta", meta));
  const scroll = el("div", "viz-scroll");
  scroll.append(table);
  wrap.append(scroll);
  return wrap;
}

/** thead from column labels; numeric columns get the .num alignment class. */
function tableHead(cols, numeric) {
  const thead = el("thead");
  const tr = el("tr");
  for (const c of cols) tr.append(el("th", numeric.has(c) ? "num" : null, label(c)));
  thead.append(tr);
  return thead;
}

/** market_snapshot: symbol · close · Δ% vs prev_close · volume, sorted by Δ%. */
function snapshotTable(payload) {
  const rows = payload.rows.map((r) => {
    const pct = typeof r.close === "number" && typeof r.prev_close === "number" && r.prev_close !== 0
      ? ((r.close - r.prev_close) / r.prev_close) * 100 : null;
    return { ...r, pct };
  }).sort((a, b) => (b.pct ?? -Infinity) - (a.pct ?? -Infinity));
  const table = el("table", "viz-table");
  table.append(tableHead(["symbol", "close", "Δ%", "volume"], new Set(["close", "Δ%", "volume"])));
  const tbody = el("tbody");
  for (const r of rows) {
    const tr = el("tr");
    tr.append(el("td", "sym", fmtCell(r.symbol)));
    tr.append(el("td", "num", fmtCell(r.close)));
    const d = el("td", "num", r.pct === null ? EM : fmtSigned(r.pct, "%"));
    if (r.pct !== null && r.pct !== 0) d.classList.add(r.pct > 0 ? "up" : "down");
    tr.append(d);
    tr.append(el("td", "num", fmtCell(r.volume)));
    tbody.append(tr);
  }
  table.append(tbody);
  const meta = `${rows.length} rows · sorted by Δ% desc` +
    (payload.truncated ? ` · ${payload.truncated}` : "");
  return tableShell(meta, table);
}

/** Generic frame table: columns from the first row, first 8, extras stay in raw. */
function genericTable(payload) {
  const rows = payload.rows;
  if (!rows.length || typeof rows[0] !== "object" || rows[0] === null) return null;
  const all = Object.keys(rows[0]);
  const cols = all.slice(0, 8);
  const numeric = new Set(cols.filter((c) => rows.some((r) => typeof r[c] === "number")));
  const table = el("table", "viz-table");
  table.append(tableHead(cols, numeric));
  const tbody = el("tbody");
  for (const r of rows) {
    const tr = el("tr");
    for (const c of cols) {
      const v = r[c];
      const isDelta = DELTA_KEYS.has(c) && typeof v === "number";
      const td = el("td", numeric.has(c) ? "num" : c === "symbol" ? "sym" : null,
        isDelta ? fmtSigned(v) : fmtCell(v));
      if (isDelta && v !== 0) td.classList.add(v > 0 ? "up" : "down");
      tr.append(td);
    }
    tbody.append(tr);
  }
  table.append(tbody);
  const bits = [`${rows.length} rows`];
  if (all.length > cols.length) bits.push(`first ${cols.length} of ${all.length} columns — raw has the rest`);
  if (payload.truncated) bits.push(payload.truncated);
  return tableShell(bits.join(" · "), table);
}

/** Flat-object renderer: tiles when small (breadth), a kv grid when wide (account). */
function flatObject(payload) {
  const entries = Object.entries(payload).filter(([k, v]) => k !== "ok" &&
    (v === null || ["number", "string", "boolean"].includes(typeof v)));
  if (!entries.length) return null;
  const wrap = el("div", "viz");
  const isPct = (k, v) => /(^|_)pct(_|$)|plpc/.test(k) && typeof v === "number" && Math.abs(v) <= 1;
  const text = (k, v) => isPct(k, v) ? fmtNum(v * 100) + "%" : fmtCell(v);
  if (entries.length <= 8) {
    const tiles = el("div", "viz-tiles");
    for (const [k, v] of entries) {
      const tile = el("div", "viz-tile");
      tile.append(el("div", "viz-tile-label", label(k)));
      tile.append(el("div", "viz-tile-value", text(k, v)));
      tiles.append(tile);
    }
    wrap.append(tiles);
  } else {
    const grid = el("dl", "viz-kv");
    for (const [k, v] of entries) {
      grid.append(el("dt", null, label(k)));
      grid.append(el("dd", null, text(k, v)));
    }
    wrap.append(grid);
  }
  return wrap;
}

/** calendar: a count and the days, wrapped. */
function calendarDays(payload) {
  const days = payload.days;
  if (!Array.isArray(days)) return null;
  const wrap = el("div", "viz");
  wrap.append(el("div", "viz-meta", `${days.length} trading days`));
  wrap.append(el("div", "viz-days", days.join("  ")));
  return wrap;
}

/** daily_bars: close line + volume strip, inline SVG, crosshair tooltip. */
function barsChart(payload) {
  const dateKey = ["date", "day", "timestamp", "t"].find((k) => payload.rows[0]?.[k] !== undefined);
  const rows = payload.rows.filter((r) => typeof r.close === "number");
  if (!dateKey || rows.length < 2) return genericTable(payload);

  const W = 640, H = 240, padL = 46, padR = 14, padT = 10;
  const priceH = 150, volTop = padT + priceH + 12, volH = 46, axisY = volTop + volH + 16;
  const plotW = W - padL - padR;
  const closes = rows.map((r) => r.close);
  const vols = rows.map((r) => (typeof r.volume === "number" ? r.volume : 0));
  const lo = Math.min(...closes), hi = Math.max(...closes);
  const span = hi - lo || 1;
  const x = (i) => padL + (plotW * i) / (rows.length - 1);
  const y = (v) => padT + priceH - ((v - lo) / span) * priceH;
  const maxVol = Math.max(...vols, 1);

  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "viz-svg", role: "img" });

  /* recessive grid: three clean price lines with labels in muted ink */
  for (const t of [lo, lo + span / 2, hi]) {
    const gy = y(t);
    svg.append(sv("line", { x1: padL, y1: gy, x2: W - padR, y2: gy, class: "viz-grid" }));
    const tick = sv("text", { x: padL - 6, y: gy + 3, class: "viz-tick", "text-anchor": "end" });
    tick.textContent = fmtNum(t);
    svg.append(tick);
  }

  /* volume strip: thin bars with a surface gap, light sequential step */
  const bw = Math.max(plotW / rows.length - 2, 0.5);
  for (let i = 0; i < rows.length; i++) {
    const vh = (vols[i] / maxVol) * volH;
    if (vh <= 0) continue;
    svg.append(sv("rect", { x: x(i) - bw / 2, y: volTop + volH - vh, width: bw, height: vh, class: "viz-vol" }));
  }

  /* the close line and its 10% wash */
  const pts = closes.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  svg.append(sv("path", {
    d: `M${pts.join("L")}L${x(rows.length - 1).toFixed(1)},${padT + priceH}L${padL},${padT + priceH}Z`,
    class: "viz-area",
  }));
  svg.append(sv("path", { d: `M${pts.join("L")}`, class: "viz-line" }));

  /* end marker (surface ring) + end label in text ink */
  const last = rows.length - 1;
  svg.append(sv("circle", { cx: x(last), cy: y(closes[last]), r: 4, class: "viz-dot" }));
  const endLabel = sv("text", {
    x: Math.min(x(last), W - padR - 2), y: Math.max(y(closes[last]) - 8, 10),
    class: "viz-end", "text-anchor": "end",
  });
  endLabel.textContent = fmtNum(closes[last]);
  svg.append(endLabel);

  /* x axis: first and last date, muted */
  for (const [i, anchor] of [[0, "start"], [last, "end"]]) {
    const t = sv("text", { x: x(i), y: axisY, class: "viz-tick", "text-anchor": anchor });
    t.textContent = String(rows[i][dateKey]).slice(0, 10);
    svg.append(t);
  }

  /* hover: crosshair + tooltip on the nearest bar */
  const hair = sv("line", { x1: 0, y1: padT, x2: 0, y2: volTop + volH, class: "viz-hair", visibility: "hidden" });
  svg.append(hair);
  const tip = el("div", "viz-tip");
  tip.hidden = true;
  const chart = el("div", "viz viz-chart");
  svg.addEventListener("mousemove", (ev) => {
    const box = svg.getBoundingClientRect();
    const fx = ((ev.clientX - box.left) / box.width) * W;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round(((fx - padL) / plotW) * (rows.length - 1))));
    hair.setAttribute("x1", String(x(i)));
    hair.setAttribute("x2", String(x(i)));
    hair.setAttribute("visibility", "visible");
    tip.textContent = `${String(rows[i][dateKey]).slice(0, 10)} · close ${fmtNum(closes[i])}` +
      (vols[i] ? ` · vol ${fmtNum(vols[i])}` : "");
    tip.hidden = false;
    tip.style.left = `${Math.min((x(i) / W) * box.width, box.width - 170)}px`;
  });
  svg.addEventListener("mouseleave", () => {
    hair.setAttribute("visibility", "hidden");
    tip.hidden = true;
  });

  const sym = rows[0].symbol ? `${rows[0].symbol} · ` : "";
  const meta = `${sym}${rows.length} bars · ${String(rows[0][dateKey]).slice(0, 10)} → ` +
    `${String(rows[last][dateKey]).slice(0, 10)}` + (payload.truncated ? ` · ${payload.truncated}` : "");
  chart.append(el("div", "viz-meta", meta), svg, tip);
  return chart;
}

/** Balanced-brace scan for complete row objects inside elided JSON. The one
 * object the elision seam corrupts fails its own JSON.parse and is dropped;
 * everything whole survives. String-aware so braces inside values don't count. */
function salvageRows(text) {
  const rows = [];
  let i = text.indexOf("[", text.indexOf('"rows"'));
  if (i === -1) return rows;
  const n = text.length;
  while (i < n) {
    const start = text.indexOf("{", i);
    if (start === -1) break;
    let depth = 0, inStr = false, esc = false, j = start;
    for (; j < n; j++) {
      const ch = text[j];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === "\\") esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') inStr = true;
      else if (ch === "{") depth++;
      else if (ch === "}") { depth--; if (depth === 0) break; }
    }
    if (j >= n) break;
    try {
      const o = JSON.parse(text.slice(start, j + 1));
      if (o !== null && typeof o === "object" && !Array.isArray(o)) rows.push(o);
    } catch { /* the seam object — dropped, and the meta line says so */ }
    i = j + 1;
  }
  return rows;
}

/** Parse the delivered result text, tolerating dsh's spill elision: a big tool
 * result arrives as head + "(Omitted N bytes ... stored at <path>)" — sometimes
 * with the JSON still complete before the note, sometimes cut mid-row.
 * @returns {{payload: object, partial: string|null}|null}
 */
function parsePayload(text) {
  try {
    return { payload: JSON.parse(text), partial: null };
  } catch { /* fall through to the two salvage tiers */ }
  const cut = text.lastIndexOf("}");
  if (cut !== -1) {
    try {
      return { payload: JSON.parse(text.slice(0, cut + 1)), partial: "spilled result — raw notes the full-output path" };
    } catch { /* mid-row elision; salvage row by row */ }
  }
  if (/^\s*\{/.test(text) && /"ok":\s*true/.test(text)) {
    const rows = salvageRows(text);
    if (rows.length) {
      return { payload: { ok: true, rows }, partial: `harness-elided result — ${rows.length} whole rows recovered, the row cut at the seam dropped; raw notes the full-output path` };
    }
  }
  return null;
}

/**
 * @param {string} toolName - the call card's tool name (e.g. mcp__alpaca-kit__screen).
 * @param {string} text - the result text as delivered.
 * @returns {HTMLElement|null} a pretty node, or null to keep the raw pre.
 */
export function renderResult(toolName, text) {
  if (typeof toolName !== "string" || typeof text !== "string") return null;
  const parsed = parsePayload(text);
  if (parsed === null) return null;
  const { payload, partial } = parsed;
  if (payload === null || typeof payload !== "object" || payload.ok !== true) return null;
  if (partial) payload.truncated = payload.truncated ? `${payload.truncated} · ${partial}` : partial;
  const name = toolName.toLowerCase().replace(/^mcp__[a-z0-9_-]+__/, "");
  try {
    if (name === "market_snapshot" && Array.isArray(payload.rows)) return snapshotTable(payload);
    if (name === "daily_bars" && Array.isArray(payload.rows) && payload.rows.length) return barsChart(payload);
    if (name === "calendar") return calendarDays(payload);
    if (["breadth", "account"].includes(name)) return flatObject(payload);
    if (["screen", "positions", "orders", "earnings", "corp_actions"].includes(name) &&
      Array.isArray(payload.rows)) {
      return payload.rows.length ? genericTable(payload) : el("div", "viz viz-meta", "0 rows");
    }
  } catch {
    return null; // a shape surprise falls back to raw, never a half-drawn card
  }
  return null;
}
