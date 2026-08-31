/* ═══════════════════════════════════════════════════════════════
   KAIROS · R3 — SESSION TIMELINE KIT (shared renderer)

   window.renderSessionTimeline(containerEl) builds the ENTIRE
   session timeline DOM from window.KAIROS_SESSION: session header
   (strategy, id, date, attendance stamp, runtime, SAMPLE plate,
   raw linkback) → numbered turns T·1… in three voice registers →
   the one inert composer.

   Pure DOM construction — every data value lands via textContent
   or an attribute setter, never string-concatenated markup. Danger
   state comes from the data's `danger` flag only. Null readings
   render as .null em-dashes; nothing ever prints NaN.

   Layout variants call this once into a container they size
   (560–900px wide) and lay panes around it. See TIMELINE-NOTES.md.
   ═══════════════════════════════════════════════════════════════ */
(function(){
"use strict";

var MINUS = "−", DASH = "—", MDOT = " · ";

/* ── tiny DOM helpers ── */
function el(tag, cls, text){
  var n = document.createElement(tag);
  if(cls) n.className = cls;
  if(text != null) n.textContent = text;
  return n;
}
function nullSpan(){
  var s = el("span", "null", DASH);
  s.title = "no reading";
  return s;
}
/* append a value that may be null: text when present, em-dash when not */
function val(parent, str){
  if(str == null) parent.appendChild(nullSpan());
  else parent.appendChild(document.createTextNode(str));
  return parent;
}

/* ── formatting — null in, null out; never NaN, typographic minus ── */
function isNum(x){ return typeof x === "number" && isFinite(x); }
function fmt(n, d){
  if(!isNum(n)) return null;
  return n.toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d})
          .replace(/-/g, MINUS);
}
function fmtInt(n){ return fmt(n, 0); }
function signedInt(n){ if(!isNum(n)) return null; return (n > 0 ? "+" : "") + fmt(n, 0); }
function pct01(n, d){ if(!isNum(n)) return null; return fmt(n * 100, d) + "%"; }
function signedPctPts(n, d){ if(!isNum(n)) return null; return (n > 0 ? "+" : "") + fmt(n, d) + "%"; }
function orDash(s){ return s == null ? DASH : s; }
function prevSub(s){ return s == null ? null : "prev " + s; }

/* ── the producer signature (shell .sig) = the raw linkback ── */
function sig(producer, monogram, raw){
  var a = el("a", "sig");
  a.href = "#";
  a.addEventListener("click", function(e){ e.preventDefault(); });
  a.title = "raw ▸ " + (raw || DASH);
  var mg = monogram;
  if(!mg){
    var letters = String(producer || "").replace(/[^A-Za-z]/g, "");
    mg = letters ? letters.slice(0, 2).toUpperCase() : "??";
  }
  var mono = el("span", "sig-mono", mg);
  mono.setAttribute("aria-hidden", "true");
  var body = el("span", "sig-body");
  body.appendChild(el("span", "sig-fn", producer || DASH));
  body.appendChild(el("span", "sig-raw", raw || DASH));
  a.appendChild(mono);
  a.appendChild(body);
  return a;
}

/* ── compressed plaque ── */
function plq(k, v, sub, dir){
  var d = el("div", "tl-plq");
  d.appendChild(el("span", "k", k));
  var vv = el("span", "v" + (dir ? " " + dir : ""));
  val(vv, v);
  d.appendChild(vv);
  if(sub != null) d.appendChild(el("span", "s", sub));
  return d;
}

/* ── honesty cell (delistings / discarded — first-class) ── */
function honCell(k, v, treatment, flag){
  var d = el("div", "tl-hon" + (flag ? " tl-hon-flag" : ""));
  d.appendChild(el("span", "k", k));
  var vv = el("span", "v");
  if(v == null) vv.appendChild(nullSpan()); else vv.textContent = v;
  d.appendChild(vv);
  if(treatment) d.appendChild(el("span", "s", treatment));
  return d;
}

/* ── card shell: a shell details.fold, signed in its foot ──
   Routine cards render OPEN and fold by hand; danger (from DATA
   only) adds the alert class and forces disclosure — a danger
   state is never rendered closed. */
function card(kindWord, sumText, opts){
  var d = document.createElement("details");
  d.className = "fold tl-card" + (opts.kindClass ? " " + opts.kindClass : "");
  var s = document.createElement("summary");
  var lamp = el("span", "lamp"); lamp.setAttribute("aria-hidden", "true");
  s.appendChild(lamp);
  s.appendChild(el("span", "word", kindWord));
  s.appendChild(el("span", "tl-sum", orDash(sumText)));
  var caret = el("span", "caret", "▾"); caret.setAttribute("aria-hidden", "true");
  s.appendChild(caret);
  d.appendChild(s);
  var body = el("div", "fold-body");
  var instr = el("div", "tl-instr");
  body.appendChild(instr);
  var foot = el("div", "tl-card-foot");
  foot.appendChild(sig(opts.producer, opts.monogram, opts.raw));
  foot.appendChild(el("span", "spacer"));
  if(opts.note) foot.appendChild(el("span", "foot-note", opts.note));
  body.appendChild(foot);
  d.appendChild(body);
  d.open = true;
  if(opts.danger === true){
    d.classList.add("danger");
    d.open = true; /* danger forces disclosure — never rendered closed */
  }
  return {root: d, instr: instr};
}

/* ── card bodies per kind ── */
function breadthBody(instr, p, rule){
  p = p || {};
  var prev = p.prev || {};
  var grid = el("div", "tl-plqs");

  var ad = (fmtInt(p.advances) != null && fmtInt(p.declines) != null)
    ? fmtInt(p.advances) + " / " + fmtInt(p.declines) : null;
  var adPrev = (fmtInt(prev.advances) != null && fmtInt(prev.declines) != null)
    ? fmtInt(prev.advances) + " / " + fmtInt(prev.declines) : null;
  var decLed = isNum(p.advances) && isNum(p.declines) && p.declines > p.advances;
  grid.appendChild(plq("adv / dec", ad, prevSub(adPrev), decLed ? "down" : null));

  var nnhDir = isNum(p.net_new_highs) ? (p.net_new_highs < 0 ? "down" : "up") : null;
  grid.appendChild(plq("net new highs", signedInt(p.net_new_highs),
    prevSub(signedInt(prev.net_new_highs)), nnhDir));

  grid.appendChild(plq("% above 200dma", pct01(p.pct_above_200dma, 1),
    prevSub(pct01(prev.pct_above_200dma, 1)), null));

  instr.appendChild(grid);
  if(rule) instr.appendChild(el("p", "tl-ruleline", rule));
}

function backtestBody(instr, p){
  p = p || {};
  /* arms table */
  var arms = p.arms || [];
  var box = el("div", "tl-arms");
  var scroll = el("div", "table-scroll");
  var table = el("table", "ledger");
  var thead = document.createElement("thead");
  var hr = document.createElement("tr");
  [["arm", true], ["trades", false], ["win rate", false], ["gross", false], ["max dd", false]]
    .forEach(function(c){
      var th = el("th", c[1] ? "l" : null, c[0]);
      hr.appendChild(th);
    });
  thead.appendChild(hr);
  table.appendChild(thead);
  var tbody = document.createElement("tbody");
  arms.forEach(function(arm){
    var tr = document.createElement("tr");
    var name = el("td", "l");
    name.appendChild(el("span", "sym", arm.name || DASH));
    tr.appendChild(name);
    tr.appendChild(val(el("td"), fmtInt(arm.trades)));
    tr.appendChild(val(el("td"), pct01(arm.win_rate, 0)));
    var g = el("td" ); val(g, signedPctPts(arm.gross_return_pct, 1));
    if(isNum(arm.gross_return_pct)) g.className = arm.gross_return_pct >= 0 ? "up" : "down";
    tr.appendChild(g);
    var dd = el("td"); val(dd, signedPctPts(arm.max_drawdown_pct, 1));
    if(isNum(arm.max_drawdown_pct) && arm.max_drawdown_pct < 0) dd.className = "down";
    tr.appendChild(dd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  scroll.appendChild(table);
  box.appendChild(scroll);
  instr.appendChild(box);

  /* honesty fields — first-class, never buried */
  var hon = el("div", "tl-honesty");
  hon.appendChild(honCell("delistings hit", fmtInt(p.delistings_hit),
    p.delisting_treatment || null, isNum(p.delistings_hit) && p.delistings_hit > 0));
  hon.appendChild(honCell("discarded days", fmtInt(p.discarded_days),
    p.discarded_treatment || null, false));
  instr.appendChild(hon);

  /* thin-sample caveat */
  if(p.caveat) instr.appendChild(el("p", "tl-caveat", p.caveat));

  /* window + maturity note */
  var w = p.window || {};
  var win = el("p", "tl-window");
  win.appendChild(document.createTextNode("window "));
  win.appendChild(el("b", null, orDash(w.start) + " → " + orDash(w.end)));
  if(w.note) win.appendChild(el("span", "note", w.note));
  instr.appendChild(win);
}

function diffBlock(lines, draft){
  var d = el("div", "tl-diff" + (draft ? " tl-diff-draft" : ""));
  (lines || []).forEach(function(ln){
    d.appendChild(el("div", "tl-diff-line", String(ln)));
  });
  if(!lines || !lines.length){
    var empty = el("div", "tl-diff-line");
    empty.appendChild(nullSpan());
    d.appendChild(empty);
  }
  return d;
}

function arenaWriteBody(instr, p){
  p = p || {};
  instr.appendChild(diffBlock(p.diff_add, false));
  var cm = el("span", "tl-commit");
  if(p.commit){ cm.textContent = "git " + "· " + p.commit; }
  else cm.appendChild(nullSpan());
  cm.title = "committed to the arena — git is the record, not a gate";
  instr.appendChild(cm);
}

function proposalBody(instr, p){
  p = p || {};
  var row = el("div", "tl-draft-row");
  var plate = el("span", "tl-draft", p.status || "draft");
  plate.title = "a draft diff awaiting operator judgment — nothing is committed";
  row.appendChild(plate);
  instr.appendChild(row);
  instr.appendChild(diffBlock(p.diff_add, true));
}

function genericBody(instr, p){
  var d = el("div", "tl-generic");
  var keys = Object.keys(p || {});
  keys.forEach(function(k){
    var v = p[k];
    var s = (v == null) ? DASH : (typeof v === "object" ? JSON.stringify(v) : String(v));
    d.appendChild(el("div", "tl-generic-line", k + MDOT + s));
  });
  if(!keys.length){
    var line = el("div", "tl-generic-line");
    line.appendChild(nullSpan());
    d.appendChild(line);
  }
  instr.appendChild(d);
}

/* ── summary lines (visible even when a routine card is folded) ── */
function summaryFor(turn){
  var p = turn.payload || {};
  switch(turn.kind){
    case "breadth":
      return "A " + orDash(fmtInt(p.advances)) + " / D " + orDash(fmtInt(p.declines)) +
        MDOT + "NNH " + orDash(signedInt(p.net_new_highs)) +
        MDOT + orDash(pct01(p.pct_above_200dma, 1)) + " >200dma";
    case "backtest":
      var w = p.window || {};
      return "arms " + ((p.arms || []).length || DASH) +
        MDOT + orDash(w.start) + " → " + orDash(w.end);
    case "arena_write":
      return orDash(p.file) + MDOT + (p.commit ? "git " + p.commit : DASH);
    case "proposal":
      return orDash(p.file) + MDOT + orDash(p.status);
    default:
      return turn.producer || DASH;
  }
}
var KIND_WORD = {
  breadth: "breadth", backtest: "backtest probe",
  arena_write: "arena write", proposal: "proposal"
};
var KIND_NOTE = {
  backtest: "scored under the five honest-eval rules · docs/backtest-rules.md",
  arena_write: "record, not gate — the arena is Kairos's to write",
  proposal: "not committed — the operator is the only teacher"
};

/* ── one turn ── */
function turnLi(turn){
  var role = turn.role === "operator" || turn.role === "kairos" || turn.role === "tool"
    ? turn.role : "tool";
  var li = el("li", "tl-turn tl-turn-" + role);

  var gut = el("div", "tl-gut");
  gut.appendChild(el("span", "tl-no",
    "T·" + (turn.n != null ? String(turn.n) : DASH)));
  var spine = el("span", "tl-spine"); spine.setAttribute("aria-hidden", "true");
  gut.appendChild(spine);
  li.appendChild(gut);

  var body = el("div", "tl-body");
  var head = el("div", "tl-thead");
  head.appendChild(el("span", "tl-time mono", turn.t || DASH));
  if(role === "tool"){
    head.appendChild(el("span", "tl-role", "instrument"));
    if(turn.producer) head.appendChild(el("span", "tl-prod", turn.producer));
  } else {
    head.appendChild(el("span", "tl-role", role));
  }
  body.appendChild(head);

  if(role === "operator"){
    body.appendChild(el("p", "tl-text-op", turn.text || DASH));
  } else if(role === "kairos"){
    body.appendChild(el("p", "tl-text-k", turn.text || DASH));
  } else {
    var c = card(KIND_WORD[turn.kind] || (turn.kind || "instrument"), summaryFor(turn), {
      kindClass: turn.kind ? "tl-card-" + turn.kind : null,
      producer: turn.producer, monogram: turn.monogram, raw: turn.raw,
      note: KIND_NOTE[turn.kind] || null,
      danger: turn.danger === true
    });
    var p = turn.payload;
    if(turn.kind === "breadth")          breadthBody(c.instr, p, turn.danger_rule || null);
    else if(turn.kind === "backtest")    backtestBody(c.instr, p);
    else if(turn.kind === "arena_write") arenaWriteBody(c.instr, p);
    else if(turn.kind === "proposal")    proposalBody(c.instr, p);
    else                                  genericBody(c.instr, p);
    body.appendChild(c.root);
  }
  li.appendChild(body);
  return li;
}

/* ── session header ── */
function headerBlock(S){
  var s = S.session || {};
  var h = el("header", "tl-session");

  var r1 = el("div", "tl-session-row1");
  r1.appendChild(el("span", "eyebrow", "research session"));
  r1.appendChild(el("span", "tl-sid mono", s.id || DASH));
  r1.appendChild(el("span", "spacer"));
  var sample = el("span", "stamp-plate", "sample — fabricated transcript");
  sample.title = S.note ||
    "fabricated transcript — rendered under sample marking";
  r1.appendChild(sample);
  h.appendChild(r1);

  var r2 = el("div", "tl-session-row2");
  r2.appendChild(el("h2", "tl-session-name", s.strategy || DASH));
  r2.appendChild(el("span", "tl-session-date mono", s.date || DASH));
  r2.appendChild(el("span", "spacer"));
  var att = el("span", "tl-attend",
    "attendance " + "· " + (s.attendance || DASH));
  if(s.attendance_note) att.title = s.attendance_note;
  r2.appendChild(att);
  h.appendChild(r2);

  var r3 = el("div", "tl-session-foot");
  var rt = el("span", "tl-runtime", "runtime · ");
  rt.appendChild(el("b", null, s.runtime || DASH));
  r3.appendChild(rt);
  r3.appendChild(el("span", "spacer"));
  var raw = el("span", "raw tl-rawline", s.raw || DASH);
  raw.title = "raw ▸ " + (s.raw || DASH);
  r3.appendChild(raw);
  h.appendChild(r3);

  return h;
}

/* ── the inert composer — the only write-shaped control ── */
function composerBlock(){
  var c = el("div", "tl-composer");
  var row = el("div", "tl-composer-row");
  var ta = document.createElement("textarea");
  ta.className = "tl-input";
  ta.readOnly = true;                 /* focusable, not editable */
  ta.setAttribute("aria-disabled", "true");
  ta.rows = 2;
  ta.placeholder = "speak to the session — the dialogue is the work";
  ta.title = "inert — prototype composer, not wired to the harness";
  row.appendChild(ta);
  var btn = document.createElement("button");
  btn.className = "tl-send";
  btn.type = "button";
  btn.disabled = true;
  btn.textContent = "send";
  btn.title = "inert — prototype composer, not wired to the harness";
  row.appendChild(btn);
  c.appendChild(row);
  c.appendChild(el("p", "tl-composer-note",
    "composer inert — round-3 prototype, not wired · the live session runs in the DeepSeek Harness (dsh); this page renders its ledger"));
  return c;
}

/* ── public: render the whole timeline into a container ── */
window.renderSessionTimeline = function(containerEl){
  if(!containerEl) return;
  containerEl.textContent = "";           /* idempotent */
  var root = el("section", "tl");
  root.setAttribute("aria-label", "Session timeline");
  var S = window.KAIROS_SESSION || null;
  if(!S || !S.session){
    root.appendChild(el("p", "tl-empty",
      "— no session data (window.KAIROS_SESSION missing) — dashes stand, never fake"));
    containerEl.appendChild(root);
    return;
  }
  root.appendChild(headerBlock(S));
  var ol = el("ol", "tl-turns");
  (S.turns || []).forEach(function(turn){ ol.appendChild(turnLi(turn)); });
  root.appendChild(ol);
  root.appendChild(composerBlock());
  containerEl.appendChild(root);
};

})();
