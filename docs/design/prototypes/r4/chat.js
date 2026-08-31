/* R4 — Minimal Chat kit.
   window.renderChat(sidebarEl, mainEl) builds the whole page from
   window.KAIROS_SESSION + window.KAIROS_FACES via DOM APIs only
   (createElement/textContent — no unescaped innerHTML of data).
   Null anywhere renders an em-dash. Zero authority; read-only. */
(function () {
  "use strict";

  var EM = "—";

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function dash(v) {
    return (v === null || v === undefined || v === "") ? EM : String(v);
  }
  function pct(v, digits) {
    if (v === null || v === undefined) return EM;
    return (v * 100).toFixed(digits === undefined ? 1 : digits) + "%";
  }
  function signedPct(v) {
    if (v === null || v === undefined) return EM;
    return (v > 0 ? "+" : "") + v + "%";
  }
  function rawLink(title) {
    var a = el("a", "raw", "raw");
    a.title = dash(title);
    return a;
  }

  /* ---------- sidebar: conversations = strategies ---------- */

  function buildSidebar(root, faces, session) {
    root.appendChild(el("div", "side-brand", "Kairos"));
    root.appendChild(el("div", "side-search", "Search"));

    var list = el("div", "conv-list");
    var rows = (faces && faces.strategies && faces.strategies.rows) || [];
    rows.forEach(function (row) {
      var active = session && row.name === session.strategy;
      var conv = el("div", "conv" + (active ? " active" : ""));

      var top = el("div", "conv-top");
      top.appendChild(el("span", "conv-name", dash(row.name)));
      top.appendChild(el("span", "conv-date", dash(row.journal_last)));
      conv.appendChild(top);

      var sub = el("div", "conv-sub");
      var chip = el("span", "chip", dash(row.status));
      chip.setAttribute("data-status", dash(row.status));
      sub.appendChild(chip);
      sub.appendChild(el("span", "conv-tail", dash(row.journal_tail)));
      conv.appendChild(sub);

      list.appendChild(conv);
    });
    root.appendChild(list);

    root.appendChild(el("div", "side-foot", "prototype · zero authority"));
  }

  /* ---------- tool cards: one notch quieter than bubbles ---------- */

  var KIND_LABELS = { breadth: "breadth", backtest: "backtest", arena_write: "arena write", proposal: "proposal" };

  function stat(label, value, prev) {
    var s = el("div", "stat");
    s.appendChild(el("div", "l", label));
    s.appendChild(el("div", "v", value));
    s.appendChild(el("div", "p", prev));
    return s;
  }

  function metaLine(p) {
    var commit = (p && p.commit) ? "commit " + p.commit : EM;
    return el("div", "meta", dash(p && p.file) + " · " + commit);
  }

  function diffBlock(lines) {
    var d = el("div", "diff");
    ((lines || [])).forEach(function (line) {
      d.appendChild(el("div", "diff-line", "+ " + dash(line)));
    });
    if (!lines || !lines.length) d.appendChild(el("div", "diff-line", EM));
    return d;
  }

  function breadthBody(card, p) {
    p = p || {};
    var prev = p.prev || {};
    var stats = el("div", "stats");
    stats.appendChild(stat("% > 200dma", pct(p.pct_above_200dma), "prev " + pct(prev.pct_above_200dma)));
    stats.appendChild(stat("net new highs", dash(p.net_new_highs), "prev " + dash(prev.net_new_highs)));
    stats.appendChild(stat("adv / dec", dash(p.advances) + " / " + dash(p.declines),
      "prev " + dash(prev.advances) + " / " + dash(prev.declines)));
    card.appendChild(stats);
  }

  function backtestBody(card, p) {
    p = p || {};
    var w = p.window || {};
    card.appendChild(el("div", "card-line",
      dash(w.start) + " → " + dash(w.end) + (w.note ? " · " + w.note : "")));

    var wrap = el("div", "tablewrap");
    var table = el("table", "bt");
    var thead = el("thead");
    var hrow = el("tr");
    ["arm", "trades", "win rate", "gross", "max dd"].forEach(function (h) {
      hrow.appendChild(el("th", null, h));
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = el("tbody");
    (p.arms || []).forEach(function (arm) {
      var tr = el("tr");
      tr.appendChild(el("td", null, dash(arm.name)));
      tr.appendChild(el("td", null, dash(arm.trades)));
      tr.appendChild(el("td", null, pct(arm.win_rate, 0)));
      var g = el("td", (arm.gross_return_pct || 0) >= 0 ? "pos" : "neg", signedPct(arm.gross_return_pct));
      tr.appendChild(g);
      tr.appendChild(el("td", "neg", signedPct(arm.max_drawdown_pct)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);

    card.appendChild(el("div", "footnote",
      "delistings " + dash(p.delistings_hit) + " (" + dash(p.delisting_treatment) + ") · " +
      "discarded " + dash(p.discarded_days) + " (" + dash(p.discarded_treatment) + ")"));
    card.appendChild(el("div", "caveat", dash(p.caveat)));
  }

  function arenaWriteBody(card, p) {
    p = p || {};
    card.appendChild(metaLine(p));
    card.appendChild(diffBlock(p.diff_add));
  }

  function proposalBody(card, p) {
    p = p || {};
    card.appendChild(metaLine(p));
    card.appendChild(el("span", "tag tag-draft", dash(p.status)));
    card.appendChild(diffBlock(p.diff_add));
  }

  function toolCard(turn) {
    var card = el("article", "card card-" + (turn.kind || "tool"));
    if (turn.danger) card.classList.add("danger");

    var head = el("div", "card-head");
    head.appendChild(el("span", "kind", KIND_LABELS[turn.kind] || dash(turn.kind)));
    head.appendChild(el("span", "producer", dash(turn.producer)));
    head.appendChild(rawLink(turn.raw));
    card.appendChild(head);

    var p = turn.payload;
    if (turn.kind === "breadth") breadthBody(card, p);
    else if (turn.kind === "backtest") backtestBody(card, p);
    else if (turn.kind === "arena_write") arenaWriteBody(card, p);
    else if (turn.kind === "proposal") proposalBody(card, p);
    else card.appendChild(el("div", "card-line", p ? JSON.stringify(p) : EM));

    if (turn.danger_rule) card.appendChild(el("div", "rule", "flag · " + dash(turn.danger_rule)));
    return card;
  }

  /* ---------- main pane ---------- */

  function buildTopbar(main, session) {
    var bar = el("header", "topbar");
    bar.appendChild(el("span", "topbar-name", dash(session && session.strategy)));
    bar.appendChild(el("span", "tag tag-sample", "sample"));
    bar.appendChild(el("span", "tag", dash(session && session.attendance)));
    bar.appendChild(rawLink(session && session.raw));
    main.appendChild(bar);
  }

  function buildFlow(main, session) {
    var flow = el("div", "flow");
    var inner = el("div", "flow-inner");
    var lastT = null;
    ((session && session.turns) || []).forEach(function (turn) {
      if (turn.t !== lastT) {
        var label = (lastT === null)
          ? dash(session.date) + " " + dash(turn.t)
          : dash(turn.t);
        inner.appendChild(el("div", "sep", label));
        lastT = turn.t;
      }
      if (turn.role === "operator") {
        var op = el("div", "msg op");
        op.appendChild(el("div", "bubble", dash(turn.text)));
        inner.appendChild(op);
      } else if (turn.role === "kairos") {
        var k = el("div", "msg k");
        k.appendChild(el("div", "who", "Kairos"));
        k.appendChild(el("div", "bubble", dash(turn.text)));
        inner.appendChild(k);
      } else if (turn.role === "tool") {
        inner.appendChild(toolCard(turn));
      }
    });
    flow.appendChild(inner);
    main.appendChild(flow);
  }

  function buildComposer(main) {
    var comp = el("footer", "composer");
    var row = el("div", "composer-row");
    var input = el("input", "composer-input");
    input.type = "text";
    input.placeholder = "Message Kairos…";
    input.disabled = true;
    row.appendChild(input);
    comp.appendChild(row);
    comp.appendChild(el("div", "composer-note",
      "prototype - not wired; the live session runs in the DeepSeek Harness"));
    main.appendChild(comp);
  }

  window.renderChat = function (sidebarEl, mainEl) {
    var sessionData = window.KAIROS_SESSION || {};
    var session = sessionData.session || {};
    session.turns = sessionData.turns;
    var faces = window.KAIROS_FACES || {};

    sidebarEl.textContent = "";
    mainEl.textContent = "";
    buildSidebar(sidebarEl, faces, session);
    buildTopbar(mainEl, session);
    buildFlow(mainEl, session);
    buildComposer(mainEl);
  };
})();
