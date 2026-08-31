/** `/market` — the captured bed, rendered live. Data: `/data/market.json`.
 *
 * A read-only instrument over ONE producer payload. It holds no state, keeps
 * no timer, and asks nothing of the harness: every reading on the page is a
 * field of the last fetch, and a re-read is the same fetch again.
 *
 * THE HONESTY RULES THIS FILE IMPLEMENTS, and what each is defending against:
 *
 *   1. Missing is never zero. `null` renders as an em-dash, and a null in a
 *      series LIFTS THE PEN (see {@link runs}) instead of being bridged by a
 *      straight line — breadth's `pct_above_200dma` is null for every day the
 *      200DMA is still immature, and a bridge would draw readings nobody took.
 *   2. Immature is not missing. The bed's bars start AT its window start, so
 *      long indicators mature late. {@link maturity} draws the FULL bed window
 *      with those spans hatched, under the charted span — so a chart that
 *      starts late reads as "the bed could not say yet", not as "the market
 *      began here". A bed whose warmup boundaries are unknown says so instead
 *      of borrowing the shipped bed's dates.
 *   3. Truncation is disclosed. The producer caps each screen at 40 rows; when
 *      a screen comes back exactly full, the page says the cap was hit rather
 *      than presenting the head of a list as the list.
 *   4. Two clocks, both shown. `assembled_at` is when the bed walk ran (the
 *      producer's disk cache can be much older than this page load) and
 *      `generated_at` is when it was served; `stale: true` means the serve was
 *      a re-play of the last good payload after a failure.
 *   5. Every panel keeps its raw pointer — the code that produced it, quoted
 *      from the payload, so a number on screen can be traced back by hand.
 *
 * No framework, no imports: hand-rolled SVG and the DOM API, same as chat.js.
 * @module
 */

const $ = (s) => document.querySelector(s);

/** Rendered in place of a value the producer did not give us. */
const EM = "—";

/** Said while the fetch is open. A COLD payload is a full bed walk (minutes);
 * the endpoint holds the response for it rather than failing fast, so the page
 * must not imply that a long wait means something is wrong. */
const LOADING = "loading — a first-ever assembly can take a few minutes";

const NS = "http://www.w3.org/2000/svg";

/** Vertical breathing room inside a spark's viewBox, in viewBox units. */
const PAD = 5;

/** How many rows the producer keeps per screen. Mirrors `face_data.py`'s
 * `screen_limit`; a screen that comes back exactly this long was cut. */
const SCREEN_LIMIT = 40;

/** Format a value, or the em-dash when the producer had nothing to say. */
const fmt = (v, f = (x) => String(x)) => (v === null || v === undefined ? EM : f(v));

/** A number with an explicit sign, so a fall never reads as a rise at a glance. */
const signed = (v, unit = "%") => `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}${unit}`;

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function stat(label, value) {
  const s = el("div", "inst-stat");
  s.append(el("div", "inst-stat-label", label), el("div", "inst-stat-value mono", value));
  return s;
}

/** A quiet line carrying the payload's own words. Absent text renders nothing
 * at all — an empty note would be a line of page furniture claiming a caveat
 * that was never made. */
function note(text, cls = "inst-note") {
  return typeof text === "string" && text !== "" ? el("div", cls, text) : null;
}

/** Append every argument that is an element; `null` (an absent note) is
 * skipped, so a caller can build a card in one call without branching. */
function put(parent, ...kids) {
  for (const kid of kids) if (kid) parent.append(kid);
  return parent;
}

/** An ISO stamp trimmed to whole seconds, UTC as the producer wrote it.
 * Unparseable text is shown exactly as it arrived rather than guessed at. */
function stamp(s) {
  if (typeof s !== "string" || s === "") return EM;
  const t = Date.parse(s);
  return Number.isNaN(t) ? s : `${new Date(t).toISOString().replace("T", " ").slice(0, 19)}Z`;
}

/**
 * Split (index, value) readings into drawable runs, scaled to a viewBox.
 *
 * A null is a GAP, not a value: it ends the current run and starts a new one,
 * so the line is drawn only where readings exist. `x` stays the reading's
 * position in the FULL series, which keeps each gap its true width. A series
 * whose readings are all equal is drawn flat down the middle rather than
 * pinned to the floor by a divide-by-zero fallback.
 * @returns an array of runs, each an array of `[x, y]`; empty when nothing is
 * drawable.
 */
function runs(rows, value, w, h, pad = PAD) {
  const nums = rows.map((r) => {
    const v = value(r);
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  });
  const seen = nums.filter((v) => v !== null);
  if (rows.length < 2 || seen.length === 0) return [];
  const lo = Math.min(...seen);
  const hi = Math.max(...seen);
  const span = hi - lo;
  const y = (v) => (span === 0 ? h / 2 : h - pad - ((v - lo) / span) * (h - pad * 2));
  const out = [];
  let run = [];
  nums.forEach((v, i) => {
    if (v === null) {
      if (run.length) out.push(run);
      run = [];
      return;
    }
    run.push([(i / (rows.length - 1)) * w, y(v)]);
  });
  if (run.length) out.push(run);
  return out;
}

/** One `<svg>` holding one polyline per run. A run of a SINGLE reading is a
 * dot: a lone measurement is not a line, and dropping it would hide it. */
function svgLine(segs, w, h, cls) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  for (const seg of segs) {
    if (seg.length === 1) {
      const dot = document.createElementNS(NS, "circle");
      dot.setAttribute("cx", seg[0][0].toFixed(2));
      dot.setAttribute("cy", seg[0][1].toFixed(2));
      dot.setAttribute("r", "1.6");
      dot.setAttribute("fill", "currentColor");
      svg.append(dot);
      continue;
    }
    const poly = document.createElementNS(NS, "polyline");
    poly.setAttribute("fill", "none");
    poly.setAttribute("stroke", "currentColor");
    poly.setAttribute("stroke-width", "1.5");
    poly.setAttribute("points", seg.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" "));
    svg.append(poly);
  }
  return svg;
}

/** A spark, or an honest line saying why there isn't one. */
function spark(rows, value, w, h, cls) {
  const segs = runs(rows, value, w, h);
  return segs.length ? svgLine(segs, w, h, cls) : el("p", "inst-note", "not plottable — fewer than two readings");
}

/**
 * The maturity rail: the bed's whole window, with each long indicator's
 * immature span hatched and the charted span bracketed underneath.
 *
 * Rendered ONLY when the payload carries real warmup boundaries. A bed the
 * producer could not date (`warmup_note` instead of `warmup`) gets that note
 * and no rail — drawing the shipped bed's dates over a foreign bed would be
 * the exact lie this instrument exists to prevent.
 */
function maturity(bed, chartStart, chartEnd) {
  const warmup = bed?.warmup;
  const t0 = Date.parse(bed?.window?.start ?? "");
  const t1 = Date.parse(bed?.window?.end ?? "");
  if (!warmup || Number.isNaN(t0) || Number.isNaN(t1) || t1 <= t0) {
    return note(bed?.warmup_note ?? "warmup boundaries unknown for this bed");
  }
  const pct = (d) => {
    const t = Date.parse(d ?? "");
    if (Number.isNaN(t)) return null;
    return `${(Math.min(Math.max((t - t0) / (t1 - t0), 0), 1) * 100).toFixed(1)}%`;
  };

  const rail = el("div", "inst-rail");
  const track = el("div", "inst-track");
  for (const [key, label] of [["sma200_valid_from", "200DMA"], ["week52_valid_from", "52wk"], ["trend_template_valid_from", "trend-t"]]) {
    const from = warmup[key];
    const lane = el("div", "inst-lane");
    const width = pct(from);
    if (width !== null) {
      const hatch = el("div", "inst-lane-immature");
      hatch.style.width = width;
      hatch.title = `${label} immature before ${from} — immature, not missing`;
      lane.append(hatch);
    }
    lane.append(el("span", "inst-lane-label", `${label} · ${fmt(from)}`));
    track.append(lane);
  }
  const left = pct(chartStart);
  const right = pct(chartEnd);
  if (left !== null && right !== null) {
    const bracket = el("div", "inst-lane-bracket");
    bracket.style.left = left;
    bracket.style.width = `calc(${right} - ${left})`;
    bracket.title = `charted span · ${chartStart} → ${chartEnd}`;
    track.append(bracket);
  }
  rail.append(track);
  put(rail, note(`bed window ${bed.window.start} → ${bed.window.end}; hatched = immature`), note(warmup.note));
  return rail;
}

function tapeCard(tape, bed) {
  const s = Array.isArray(tape?.series) ? tape.series : [];
  const last = s[s.length - 1];
  const card = el("section", "inst-card");
  put(card,
      el("h2", "inst-card-title", "The tape"),
      el("div", "inst-note", `${s.length} sessions · 100 = ${s[0]?.date ?? EM} · last ${fmt(last?.level, (v) => Number(v).toFixed(1))} on ${last?.date ?? EM} · ${fmt(last?.n)} members`),
      spark(s, (r) => r.level, 720, 160, "spark tape"),
      maturity(bed, s[0]?.date, last?.date),
      note(tape?.note),
      note(`raw · ${tape?.raw ?? EM}`, "inst-note inst-raw"));
  return card;
}

function breadthCard(breadth) {
  const s = Array.isArray(breadth?.series) ? breadth.series : [];
  const last = s[s.length - 1] ?? {};
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "Breadth"));
  const grid = el("div", "inst-grid");
  grid.append(stat("% > 200DMA", fmt(last.pct_above_200dma, (v) => `${(v * 100).toFixed(1)}%`)),
              stat("net new highs", fmt(last.net_new_highs)),
              stat("advances", fmt(last.advances)),
              stat("declines", fmt(last.declines)));
  put(card,
      el("div", "inst-note", `${s.length} sessions · latest ${last.date ?? EM}`),
      grid,
      spark(s, (r) => r.pct_above_200dma, 720, 64, "spark"),
      note(breadth?.note),
      note(`raw · ${breadth?.raw ?? EM}`, "inst-note inst-raw"));
  return card;
}

/** One screen's table. The columns are the producer's own fields; a row cell
 * is never computed here beyond formatting. */
function screenTable(rows) {
  const t = el("table", "inst-table");
  const head = el("tr");
  for (const c of ["symbol", "close", "Δ%", "gap%", "rs", "last 60"]) head.append(el("th", "", c));
  t.append(head);
  for (const r of rows) {
    const row = el("tr");
    row.append(el("td", "mono", r.symbol ?? EM),
               el("td", "mono", fmt(r.close, (v) => Number(v).toFixed(2))),
               el("td", `mono ${sign(r.pct_change)}`, fmt(r.pct_change, (v) => signed(v))),
               el("td", `mono ${sign(r.gap_pct)}`, fmt(r.gap_pct, (v) => signed(v))),
               el("td", "mono", fmt(r.rs_percentile, (v) => Number(v).toFixed(1))));
    /* The row spark is 80x20 of ink in a table cell: too small for the
     * "not plottable" sentence {@link spark} would put there, so an
     * undrawable one is the em-dash every other empty cell uses. */
    const cell = el("td");
    const segs = Array.isArray(r.spark) ? runs(r.spark, (v) => v, 80, 20, 3) : [];
    if (segs.length) cell.append(svgLine(segs, 80, 20, "spark row"));
    else cell.textContent = EM;
    row.append(cell);
    t.append(row);
  }
  const scroller = el("div", "inst-scroll");
  scroller.append(t);
  return scroller;
}

/** Green/red only where the sign is a real reading; a null gets neither. */
function sign(v) {
  return typeof v === "number" && Number.isFinite(v) ? (v >= 0 ? "pos" : "neg") : "";
}

function screensCard(screens) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "Screens"));
  const kinds = Object.entries(screens ?? {});
  if (!kinds.length) card.append(el("p", "inst-note", `no screens in this payload ${EM}`));
  for (const [kind, data] of kinds) {
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    put(card,
        el("h3", "inst-sub", `${kind} · ${rows.length}`),
        /* The cap is disclosed, never silent: a full 40 is the head of a list
         * whose tail the payload never carried. */
        rows.length === SCREEN_LIMIT
          ? note(`top ${SCREEN_LIMIT} by the screen's own order — the payload caps here, so this is not the whole screen`)
          : null,
        rows.length ? screenTable(rows) : el("p", "inst-note", "no names passed this screen on the as-of day"),
        note(`raw · ${data?.raw ?? EM}`, "inst-note inst-raw"));
  }
  return card;
}

/** Wipe the header readings. Called before every fetch and on every failure:
 * an as-of line left over from a previous payload would date a page that is
 * no longer showing it. */
function clearHead() {
  $("#asof").textContent = "";
  $("#stamp").textContent = "";
  $("#stamp").classList.remove("inst-stale");
}

/** True while a fetch is open — the refresh button is disabled for the same
 * span, so a cold assembly cannot be piled up on by an impatient click. */
let inflight = false;

async function load() {
  if (inflight) return;
  inflight = true;
  const root = $("#root");
  const button = $("#refresh");
  button.disabled = true;
  clearHead();
  root.replaceChildren(el("p", "inst-note", LOADING));
  try {
    const res = await fetch("/data/market.json");
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`HTTP ${res.status} — the response was not JSON`);
    }
    if (!data.ok) {
      root.replaceChildren(el("p", "inst-note", `no reading — ${data.error ?? "producer failed"}`));
      return;
    }
    const bed = data.bed ?? {};
    const counts = [
      bed.symbols === undefined ? null : `${bed.symbols} sym`,
      bed.captured_days === undefined ? null : `${bed.captured_days} sessions`,
    ].filter((p) => p !== null);
    $("#asof").textContent = [`as of ${data.as_of ?? EM}`, `bed ${bed.root ?? EM}`, ...counts].join(" · ");
    /* Both clocks: the walk can predate the serve by days (the producer caches
     * a static bed on disk), so one stamp alone would misdate the reading. */
    $("#stamp").textContent = `${data.stale ? "STALE · " : ""}assembled ${stamp(data.assembled_at)} · served ${stamp(data.generated_at)}`;
    $("#stamp").classList.toggle("inst-stale", Boolean(data.stale));
    root.replaceChildren(tapeCard(data.tape ?? {}, bed), breadthCard(data.breadth ?? {}), screensCard(data.screens));
  } catch (err) {
    clearHead();
    root.replaceChildren(el("p", "inst-note", `no reading — ${err}`));
  } finally {
    inflight = false;
    button.disabled = false;
  }
}

$("#refresh").onclick = () => void load();
void load();
