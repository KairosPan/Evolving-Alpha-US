/** `/account` — the paper account, read-only. Data: `/data/account.json`.
 *
 * The sibling instrument to market.js, and the same machine: no state, no
 * timer, no harness call. Every reading is a field of the last fetch and a
 * re-read is that fetch again. What differs is what this page must be honest
 * ABOUT:
 *
 *   1. Absence is not failure. No APCA keys in the face's environment makes the
 *      producer answer `ok: true, available: false` with a reason. That is a
 *      real reading of a real configuration, so it renders as the reason plus
 *      the gate strip — never as an empty account, and never as an error.
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
 *      series circuit — order intent → GATE 1 → GATE 2 → the trading host — and
 *      the wire downstream of an unpassed gate is drawn severed. A flag that is
 *      not a boolean reads as unknown and leaves the wire cut: the strip may
 *      never draw a closed circuit it cannot prove.
 *   5. No host is stamped. The payload carries no base URL, and the paper pin
 *      in `alpaca_kit.account` guards MUTATING calls only, so the circuit's
 *      terminal is labelled generically and the pin is quoted from the
 *      payload's own `paper_pin` rather than asserted as this session's host.
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

/** A number the broker sent as a STRING (Alpaca quotes every money field), or
 * the em-dash. The finite check is the load-bearing half: `Number("")` is 0 and
 * `Number("n/a")` is NaN, and both would otherwise print — as `$0.00`, a
 * balance nobody reported, and as `$NaN`, a balance that cannot exist. */
function money(v) {
  if (v === null || v === undefined || v === "") return EM;
  const n = Number(v);
  return Number.isFinite(n)
    ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : EM;
}

/** A fraction rendered as a signed percentage. Same guard as {@link money}, and
 * the sign is always explicit so a loss never reads as a gain at a glance. */
function pct(v) {
  if (v === null || v === undefined || v === "") return EM;
  const n = Number(v);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${(n * 100).toFixed(2)}%` : EM;
}

/** Green/red only where the sign is a real reading; anything else gets neither. */
function sign(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  return Number.isFinite(n) ? (n >= 0 ? "pos" : "neg") : "";
}

/** A field the payload may not carry, as text. */
const text = (v) => (v === null || v === undefined || v === "" ? EM : String(v));

/* ── the cards ───────────────────────────────────────────────────────────── */

function summaryCard(account, raw) {
  const card = el("section", "inst-card");
  const grid = el("div", "inst-grid");
  grid.append(stat("equity", money(account.equity)),
              stat("cash", money(account.cash)),
              stat("buying power", money(account.buying_power)));
  return put(card,
             el("h2", "inst-card-title", "Paper account"),
             /* Status and currency are the broker's own fields. The base URL is
              * NOT in the payload, so no host is named here — see rule 5. */
             el("div", "inst-note", `status ${text(account.status)} · currency ${text(account.currency)}`),
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
 * text-only reading would lose.
 * @param gate - the payload's `orders_gate` block.
 * @param provenance - said when the block was not in the payload at all.
 */
function gateCard(gate, provenance) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "The order gates"));
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
  /* A break anywhere upstream cuts everything after it: this is one series
   * circuit, not three independent links. */
  const wire = (severed) => el("div", `inst-gate-wire${severed ? " severed" : ""}`, severed ? "⊘" : "");

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
             el("div", "inst-note", `gate 1 · ${said(gate.gate1_registered, "registered", "not registered")} — ${text(gate.gate1_rule)}`),
             el("div", "inst-note", `gate 2 · ${said(gate.gate2_validated, "validated", "not validated")} — ${text(gate.gate2_note)}`),
             note(provenance),
             note(`raw · ${text(gate.paper_pin)}`, "inst-note inst-raw"));
}

/** The gate as it must read when the producer never computed one.
 *
 * A keyless payload (`available: false`) carries no `orders_gate`, but its
 * gate state is not unknown: `gate_state` in scripts/face_data.py (lines
 * 162-171) computes gate 1 as `ALPACA_KIT_ENABLE_ORDERS == "1" AND both APCA
 * keys present`, so no keys means gate 1 CANNOT be registered, and gate 2 is
 * hard-coded False there until the drill passes. The strings below are that
 * function's, quoted verbatim, and {@link gateCard} is told to SAY on the page
 * that this block was reconstructed here rather than served — a page-authored
 * gate that presented itself as a producer reading would be the one lie this
 * instrument exists to prevent.
 */
function keylessGate() {
  return {
    gate1_registered: false,
    gate1_rule: "ALPACA_KIT_ENABLE_ORDERS=1 AND APCA keys present",
    gate2_validated: false,
    gate2_note: "per-order human approval - intent until the drill in face/README.md passes on a live face",
    paper_pin: "hostname == paper-api.alpaca.markets enforced in code",
  };
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

    if (data.available === false) {
      root.replaceChildren(
        el("p", "inst-note", `not available — ${text(data.reason)}`),
        gateCard(keylessGate(), "reconstructed on this page: a keyless payload carries no gate block, and the producer's own rule cannot register gate 1 without keys"),
      );
      return;
    }
    const positions = Array.isArray(data.positions) ? data.positions : [];
    const orders = Array.isArray(data.orders) ? data.orders : [];
    root.replaceChildren(
      summaryCard(data.account ?? {}, data.raw),
      tableCard("Positions", undefined, positions, [
        ["symbol", (r) => text(r.symbol)],
        ["qty", (r) => text(r.qty)],
        ["avg entry", (r) => money(r.avg_entry_price)],
        ["value", (r) => money(r.market_value)],
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
