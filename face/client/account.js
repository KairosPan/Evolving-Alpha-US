/** `/account` — the trading account, read-only. Data: `/data/account.json`.
 *
 * The sibling instrument to market.js, and the same machine: no state, no
 * timer, no harness call. Every reading is a field of the last fetch and a
 * re-read is that fetch again. What differs is what this page must be honest
 * ABOUT:
 *
 *   1. Absence is not failure. No APCA keys in the face's environment makes the
 *      producer answer `ok: true, available: false` with a reason AND the gate
 *      block it can still compute from that same environment. That is a real
 *      reading of a real configuration, so it renders as the reason plus the
 *      gate strip — never as an empty account, and never as an error. Both
 *      branches take the SAME path through {@link gateCard}: this page holds no
 *      copy of the producer's gate rule, so it has none that can drift from it.
 *   2. ONE clock, not two. Unlike `/market` there is no producer disk cache and
 *      no `assembled_at`: an account payload is read from the broker on the
 *      spawn that served it, so `generated_at` IS the reading's time. `stale:
 *      true` means the endpoint re-served its last good body after a failed
 *      spawn — the only way this page can show something older than its stamp.
 *   3. The orders table is labelled by the PRODUCER's sentence (`orders_note`,
 *      "Alpaca's most recent 50 orders, all statuses"). `get_orders` is called
 *      with `status="all"`, which returns a most-recent window of every status;
 *      calling that "recent orders" or "open orders" in this file would be the
 *      page characterising a scope it never measured. No note in the payload
 *      means no claim on the page.
 *   4. The two order gates are drawn from the payload's COMPUTED state as a
 *      series circuit — order intent → GATE 1 → GATE 2 → the trading host. A
 *      wire is drawn intact only when BOTH gates it touches (the one before it
 *      and the one after it) are passed, so an unpassed gate cuts every path
 *      through it rather than only the span behind it. A flag that is not a
 *      boolean reads as unknown and leaves those wires cut: the strip may never
 *      draw a closed circuit it cannot prove.
 *   5. The host is a READING, not a claim: `data.host` is the parsed hostname
 *      the producer's own reads went to. It is NOT the paper pin — that pin
 *      guards MUTATING calls in `alpaca_kit.account` — so the two appear
 *      separately: the host on the summary, the pin quoted from the gate
 *      block's `paper_pin` beneath the circuit.
 *
 * No framework, no imports: the DOM API, same as chat.js and market.js. The few
 * helpers shared in spirit with market.js (`el`, `stat`, `note`, `put`,
 * `stamp`) are re-declared here rather than imported — market.js exports
 * nothing, and neither page may take a load-order dependency on the other.
 * @module
 */

const $ = (s) => document.querySelector(s);

/** Rendered in place of a value the producer did not give us. */
const EM = "—";

/** Said while the fetch is open. An account read is one REST round trip behind
 * a 30s spawn timeout, so no cold-assembly wording is warranted here. */
const LOADING = "loading…";

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
 * at all — an empty note would be page furniture claiming a caveat that was
 * never made. */
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
 * A number the broker sent as a STRING (Alpaca quotes every money field), in the
 * account's own currency, or the em-dash.
 *
 * The finite check is one load-bearing half: `Number("")` is 0 and
 * `Number("n/a")` is NaN, and both would otherwise print — as `$0.00`, a balance
 * nobody reported, and as `$NaN`, a balance that cannot exist.
 *
 * The currency is the other. `$` is written ONLY for a USD account (or one whose
 * payload named no currency at all, which is the only case where the default
 * carries no assertion); anything else gets its ISO code spelled out in front of
 * the amount. Printing a EUR balance with a dollar sign would be a wrong
 * reading, and knowing the symbol for every code on earth is not this page's
 * business.
 * @param v - the amount, as the broker sent it.
 * @param currency - the ACCOUNT's `currency` field; positions and orders carry
 * none of their own, so the account's is the only currency in the payload.
 */
function money(v, currency) {
  if (v === null || v === undefined || v === "") return EM;
  const n = Number(v);
  if (!Number.isFinite(n)) return EM;
  const amount = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
  return code === "" || code === "USD" ? `$${amount}` : `${code} ${amount}`;
}

/** A fraction rendered as a percentage. Same guards as {@link money}. A gain
 * carries an explicit `+` so a loss never reads as a gain at a glance — but a
 * flat position gets NO sign and no color: zero is neither, and dressing it as a
 * gain would be a reading nobody took. */
function pct(v) {
  if (v === null || v === undefined || v === "") return EM;
  const n = Number(v);
  if (!Number.isFinite(n)) return EM;
  return `${n > 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
}

/** Green/red only where the sign is a real, non-zero reading; anything else —
 * absent, unparseable, or exactly flat — gets neither. */
function sign(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "pos" : "neg";
}

/** A field the payload may not carry, as text. */
const text = (v) => (v === null || v === undefined || v === "" ? EM : String(v));

/* ── the cards ───────────────────────────────────────────────────────────── */

function summaryCard(account, host, raw) {
  const card = el("section", "inst-card");
  const grid = el("div", "inst-grid");
  grid.append(stat("equity", money(account.equity, account.currency)),
              stat("cash", money(account.cash, account.currency)),
              stat("buying power", money(account.buying_power, account.currency)));
  return put(card,
             el("h2", "inst-card-title", "Account"),
             /* The host the producer's OWN reads went to, parsed by it from the
              * client's base URL — a reading, like the balances, and the em-dash
              * when the payload did not carry one. The heading says "Account"
              * rather than "Paper account" for the same reason: paper-ness is
              * whatever this host is, not a word chosen here. */
             el("div", "inst-note", `host · ${text(host)} · status ${text(account.status)} · currency ${text(account.currency)}`),
             grid,
             note(`raw · ${text(raw)}`, "inst-note inst-raw"));
}

/**
 * One table card.
 * @param title - the heading; a word this page owns, never a scope claim.
 * @param subnote - the producer's own sentence about what the rows ARE, or
 * `undefined` when the payload made no such claim (then nothing is said).
 * @param rows - the payload's rows, verbatim.
 * @param cols - `[label, render, cls?]` triples; `cls` colors the cell.
 * @param empty - what an empty list means, in words.
 */
function tableCard(title, subnote, rows, cols, empty) {
  const card = el("section", "inst-card");
  put(card, el("h2", "inst-card-title", title), note(subnote));
  if (!rows.length) {
    card.append(el("p", "inst-note", empty));
    return card;
  }
  const t = el("table", "inst-table");
  const head = el("tr");
  for (const [label] of cols) head.append(el("th", "", label));
  t.append(head);
  for (const r of rows) {
    const tr = el("tr");
    for (const [, render, cls] of cols) tr.append(el("td", cls ? `mono ${cls(r)}` : "mono", render(r)));
    t.append(tr);
  }
  const scroller = el("div", "inst-scroll");
  scroller.append(t);
  card.append(scroller);
  return card;
}

/**
 * The double order gate, as a severed circuit.
 *
 * The light translation of R2's severed-circuit sketch, not a replica: four
 * chips and three wires, no motion and no alarm ink. A face that dramatizes its
 * own safety interlocks teaches the operator to read them as decoration.
 *
 * The state under each chip is also written in WORDS, from the payload's own
 * `gate1_rule` / `gate2_note` — the strip's shape carries no meaning a
 * text-only reading would lose. A rule the payload did not carry is simply not
 * quoted: the state word stands alone rather than trailing an em-dash at a
 * caveat that was never made.
 *
 * The SAME function serves both payload branches — keyed and keyless. The
 * producer computes `orders_gate` from the environment either way, so this page
 * holds no copy of that rule and cannot drift from it.
 * @param gate - the payload's `orders_gate` block.
 */
function gateCard(gate) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "The order gates"));
  /* Both branches of a current producer carry the block; an older one that does
   * not says so rather than getting a strip this page invented. */
  if (gate === null || typeof gate !== "object") {
    card.append(el("p", "inst-note", "gate state absent from this payload"));
    return card;
  }
  /* Fail-closed reading: only a literal `true` passes. An absent or malformed
   * flag is unknown, and an unknown gate is drawn (and worded) as one an order
   * cannot cross. */
  const g1 = gate.gate1_registered === true;
  const g2 = gate.gate2_validated === true;
  const said = (v, yes, no) => (typeof v === "boolean" ? (v ? yes : no) : "unknown");

  const chip = (label, on, why) => {
    const n = el("div", `inst-gate-node ${on ? "on" : "off"}`);
    const glyph = el("div", "inst-gate-glyph", on ? "◈" : "⊘");
    glyph.setAttribute("aria-hidden", "true");
    n.append(glyph, el("div", "inst-gate-label", label));
    if (typeof why === "string" && why !== "") n.title = why;
    return n;
  };
  /* One series circuit, not three independent links: a wire is intact only when
   * the gates on BOTH sides of it are passed, so an unpassed gate leaves no
   * intact wire on any path through it — including the one that leads into it. */
  const wire = (severed) => {
    const w = el("div", `inst-gate-wire${severed ? " severed" : ""}`, severed ? "⊘" : "");
    if (severed) w.setAttribute("aria-hidden", "true");   // decorative, like the chip glyph
    return w;
  };
  /* The state word stands alone when the payload carried no rule to quote. */
  const clause = (rule) => (typeof rule === "string" && rule !== "" ? ` — ${rule}` : "");

  const strip = el("div", "inst-circuit");
  strip.append(el("div", "inst-gate-node src", "order intent"),
               wire(!g1),
               chip("Gate 1 · registration", g1, gate.gate1_rule),
               wire(!g1 || !g2),
               chip("Gate 2 · human approval", g2, gate.gate2_note),
               wire(!g1 || !g2),
               el("div", "inst-gate-node host mono", "the trading host"));

  return put(card,
             strip,
             el("div", "inst-note", `gate 1 · ${said(gate.gate1_registered, "registered", "not registered")}${clause(gate.gate1_rule)}`),
             el("div", "inst-note", `gate 2 · ${said(gate.gate2_validated, "validated", "not validated")}${clause(gate.gate2_note)}`),
             note(`raw · ${text(gate.paper_pin)}`, "inst-note inst-raw"));
}

/* ── the fetch ───────────────────────────────────────────────────────────── */

/** Wipe the header reading. Called before every fetch and on every failure: a
 * stamp left over from a previous payload would date a page that is no longer
 * showing it. */
function clearHead() {
  $("#stamp").textContent = "";
  $("#stamp").classList.remove("inst-stale");
}

/** True while a fetch is open; the refresh button is disabled for the same
 * span, so clicks cannot pile spawns up behind each other. */
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
    const res = await fetch("/data/account.json");
    const body = await res.text();
    let data;
    try {
      data = JSON.parse(body);
    } catch {
      throw new Error(`HTTP ${res.status} — the response was not JSON`);
    }
    if (!data.ok) {
      root.replaceChildren(el("p", "inst-note", `no reading — ${text(data.error ?? "producer failed")}`));
      return;
    }
    /* One stamp: `generated_at` is when this payload was read from the broker.
     * STALE means the endpoint re-served its last good body. */
    $("#stamp").textContent = `${data.stale ? "STALE · " : ""}served ${stamp(data.generated_at)}`;
    $("#stamp").classList.toggle("inst-stale", Boolean(data.stale));

    /* The keyless view: the producer's reason, and its gate — computed from the
     * same environment that made the account unreadable, so it is served here
     * exactly as it is on the keyed branch. */
    if (data.available === false) {
      root.replaceChildren(
        el("p", "inst-note", `not available — ${text(data.reason)}`),
        gateCard(data.orders_gate),
      );
      return;
    }
    const positions = Array.isArray(data.positions) ? data.positions : [];
    const orders = Array.isArray(data.orders) ? data.orders : [];
    const account = data.account ?? {};
    /* Positions carry no currency of their own; the account's is the payload's
     * only one, so every money cell on the page is denominated by it. */
    const cur = account.currency;
    root.replaceChildren(
      summaryCard(account, data.host, data.raw),
      tableCard("Positions", undefined, positions, [
        ["symbol", (r) => text(r.symbol)],
        ["qty", (r) => text(r.qty)],
        ["avg entry", (r) => money(r.avg_entry_price, cur)],
        ["value", (r) => money(r.market_value, cur)],
        ["unrl %", (r) => pct(r.unrealized_plpc), (r) => sign(r.unrealized_plpc)],
      ], "no open positions"),
      /* The heading is a noun; the scope claim under it is the producer's
       * sentence or nothing at all (rule 3). */
      tableCard("Orders", data.orders_note, orders, [
        ["symbol", (r) => text(r.symbol)],
        ["side", (r) => text(r.side)],
        ["qty", (r) => text(r.qty)],
        ["status", (r) => text(r.status)],
        ["submitted", (r) => stamp(r.submitted_at)],
      ], "no orders came back on this read"),
      gateCard(data.orders_gate),
    );
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
