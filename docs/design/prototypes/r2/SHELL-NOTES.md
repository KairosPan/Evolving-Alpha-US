# R2 Shell — usage contract for the face agents

You are building one face (`market.html` / `strategy.html` / `account.html`) in
`docs/design/prototypes/r2/`. The shared shell is `shell.css` (tokens + components + Google
Fonts via `@import` — you add NO font links of your own). `landing.html` is the reference
implementation.

**The one rule:** faces may add page-local CSS for their own charts/tables/layout, but may
NOT restyle shell components or fork tokens. Use the shell classes as-is; use `var(--…)`
tokens for every page-local color/font. If a shell component almost fits, wrap it — don't
override it.

## Page skeleton (copy byte-for-byte; ⟨slots⟩ are the only variation points)

First line of the file: the exact `@dsCard` comment your task names.

```html
<!-- @dsCard group="⟨as your task names⟩" -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KAIROS · ⟨FACE⟩ — R2</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%2305070b'/%3E%3Cpath d='M8 2 L11 8 L8 14 L5 8 Z' fill='%23c8a552'/%3E%3C/svg%3E">
<link rel="stylesheet" href="shell.css">
<style>/* page-local styles only — see the one rule */</style>
</head>
<body>

<header class="masthead">
  <div class="wrap mast-top">
    <a class="wordmark" href="landing.html"><span class="dia" aria-hidden="true"></span>KAIROS</a>
    <span class="facename">⟨FACE⟩</span>
    <span class="spacer"></span>
    <span class="seg">as of <b id="k-asof" class="mono">—</b></span>
    <span class="seg">bed <b id="k-bed" class="mono">—</b></span>
    <span class="seg">window <b id="k-window" class="mono">—</b></span>
    <span class="seg"><b id="k-symbols" class="mono">—</b> sym · <b id="k-days" class="mono">—</b> sessions</span>
    <span class="seal" id="k-gate" title="orders_gate — read-only display">orders —</span>
    <span class="stamp-sample" title="gate readout comes from account_mock, a labeled fabricated block">sample</span>
  </div>
  <nav class="wrap mast-nav" aria-label="Faces">
    <a class="nav-link" href="market.html"><span class="nav-idx">01</span>Market</a>
    <a class="nav-link" href="strategy.html"><span class="nav-idx">02</span>Strategy</a>
    <a class="nav-link" href="account.html"><span class="nav-idx">03</span>Account</a>
    <span class="spacer"></span>
    <span class="gem" aria-hidden="true" title="the six-phase thermal spectrum — washout · recovery · ignition · trend · distribution · flush"><i style="background:var(--washout)"></i><i style="background:var(--recovery)"></i><i style="background:var(--ignition)"></i><i style="background:var(--trend)"></i><i style="background:var(--distribution)"></i><i style="background:var(--flush)"></i></span>
  </nav>
</header>

<main class="wrap">
  ⟨page content⟩
</main>

<footer class="foot-band">
  <div class="wrap foot">
    <span>KAIROS · <b>⟨FACE⟩</b> — round-2 face prototype · zero authority · read-only</span>
    <span class="spacer"></span>
    <span>intent · <b>Kairos-Design.md</b></span>
    <span>mechanism · <b>the skeleton spec &amp; code</b></span>
  </div>
</footer>

⟨data script(s)⟩
<script> ⟨the shell-fill snippet, verbatim, then your page code⟩ </script>
</body>
</html>
```

Slots: `⟨FACE⟩` = `MARKET` / `STRATEGY` / `ACCOUNT` (uppercase in `<title>`, `.facename`,
and the footer). Add `aria-current="page"` to YOUR face's `.nav-link` — nothing else in the
masthead/nav/footer changes.

Data scripts (relative to `r2/`):

- `market.html` → `<script src="../data/market_mock.js"></script>` only.
- `strategy.html` and `account.html` → BOTH, in this order:
  `<script src="../data/market_mock.js"></script>` (masthead bed facts + gate) then
  `<script src="../data/workbench_mock.js"></script>` (`window.KAIROS_FACES`, FABRICATED —
  everything rendered from it carries a SAMPLE stamp).

## Shell-fill snippet (copy verbatim, first thing in your page script)

Fills the masthead and auto-numbers every entry plate. If data is missing, dashes stand —
no reading, never fake.

```js
/* ── shell fill — shared across all R2 faces ── */
(function(){
  "use strict";
  var D = window.KAIROS_DATA || null;
  if(!D) return; // dashes stand: no reading, never fake
  function t(id, s){ var el = document.getElementById(id); if(el) el.textContent = s; }
  t("k-asof", D.as_of);
  t("k-bed", D.bed.root);
  t("k-window", D.bed.window.start + " → " + D.bed.window.end);
  t("k-symbols", String(D.bed.symbols));
  t("k-days", String(D.bed.captured_days));
  var g = D.account_mock && D.account_mock.orders_gate;
  var gateEl = document.getElementById("k-gate");
  if(g && gateEl){
    gateEl.textContent = "orders " + ((g.gate1_registered || g.gate2_validated) ? "partially armed" : "unarmed");
    gateEl.title = "gate 1 registered: " + g.gate1_registered + " · gate 2 validated: " + g.gate2_validated +
      " — read-only display · readout from account_mock (fabricated block)";
  }
  document.querySelectorAll("[data-entry]").forEach(function(el, i){
    el.textContent = "E " + D.bed.captured_days + "." + (i + 1);
  });
})();
```

## The graft: entry plate + producer signature

Every panel is a numbered entry signed by its producing function.

**Entry plate** — first child of every `.panel-head` (or of a section head). Never
hand-write the number; the snippet numbers all `[data-entry]` plates in DOM order as
`E 526.N` (526 = `bed.captured_days`, the day-number of record; numbering is per-page):

```html
<span class="entry-no" data-entry>E —.—</span>
```

**Producer signature** — first child of every `.panel-foot`. It IS the raw-linkback
affordance (there is no separate raw link for a panel's own reading). Monogram = 2 letters
you pick from the producer name (`MB` for market_breadth, `BU` for build_universe, `AK` for
alpaca_kit bed extracts, `SY` for status.yaml, …). `.sig-fn` = the producing function/file;
`.sig-raw` = the raw pointer from the data (also mirrored in `title`); fill both from the
data's `raw` field via JS where one exists:

```html
<a class="sig" href="#" onclick="return false" title="raw ▸ ⟨pointer⟩">
  <span class="sig-mono" aria-hidden="true">MB</span>
  <span class="sig-body">
    <span class="sig-fn">market_breadth</span>
    <span class="sig-raw">alpaca_kit.features.breadth.market_breadth</span>
  </span>
</a>
```

**Panel skeleton** (the standard entry):

```html
<section class="panel">
  <header class="panel-head">
    <span class="entry-no" data-entry>E —.—</span>
    <span class="eyebrow">⟨kind · span⟩</span>
    <h2>⟨Title⟩</h2>
    <span class="spacer"></span>
    <span class="eyebrow">⟨optional right note⟩</span>
  </header>
  <div class="panel-body">…</div>
  <footer class="panel-foot">
    ⟨.sig as above⟩
    <span class="spacer"></span>
    <span class="foot-note">⟨optional honesty note⟩</span>
  </footer>
</section>
```

**SAMPLE stamps** (engraved voice): every readout rendered from `KAIROS_FACES` or
`account_mock` is fabricated. A wholly fabricated panel puts
`<span class="stamp-plate">sample — fabricated shape</span>` in its `.panel-head` (before
the trailing eyebrow); a single fabricated readout inside an otherwise-real context gets an
inline `<span class="stamp-sample">sample</span>` beside it.

**Disclosure fold** (danger forces disclosure; routine stays folded):

```html
<details class="fold" id="x-fold">
  <summary>
    <span class="lamp" aria-hidden="true"></span>
    <span class="word" id="x-word">⟨watch name⟩</span>
    <span id="x-line">—</span>
    <span class="caret" aria-hidden="true">▾</span>
  </summary>
  <div class="fold-body">…</div>
</details>
```

When your danger/warn condition holds, JS does BOTH:
`el.classList.add("danger")` (or `"warn"`) AND `el.open = true`. When it doesn't, the fold
stays neutral and closed (openable by hand). Never render a danger state closed.

## Class inventory (one-line usage rules)

| Class | Use |
|---|---|
| `.wrap` | width-constrained row (masthead rows, `main`, footer inner) |
| `.spacer` | flex spring inside any shell flex row |
| `.mono` | tabular mono numbers/dates inline |
| `.eyebrow` | tiny mono label, margin-0 inline — panel heads, captions |
| `.rule` | engraved horizontal groove (an `<hr>`) |
| `.null` | wrap every rendered em-dash for a null reading (`<span class="null" title="no reading in this bed">—</span>`) |
| `.up` / `.down` | direction color on inline values; on `.plaque .v` too |
| `.masthead` `.mast-top` `.mast-nav` `.wordmark` `.facename` `.seg` `.seal` `.gem` | masthead — copy the skeleton, don't improvise |
| `.nav-link` `.nav-idx` | nav — `aria-current="page"` marks your face |
| `.foot-band` `.foot` | footer — copy the skeleton |
| `.panel` `.panel-head` `.panel-body` `.panel-foot` `.foot-note` | the entry chrome |
| `.entry-no` + `[data-entry]` | the engraved entry number plate |
| `.sig` `.sig-mono` `.sig-fn` `.sig-raw` | the producer signature = raw linkback |
| `.raw` | auxiliary inline raw pointer only (bed files, checksums inside a body) |
| `.stamp-sample` / `.stamp-plate` | fabrication marks — inline / whole-panel |
| `.plaques` (+`--row`) `.plaque` (`.k` `.v` `.s`) | stat plaques |
| `.chip` + `.chip-trend_template/gap_up/gainer/loser` | screen status chips |
| `.chip-idea/researching/validated/paper/retired` | strategy lifecycle chips (one-way rail; retired = quiet, never hidden) |
| `.chip-dim` `.chip-warn` `.chip-danger` | generic state chips |
| `details.fold` (+`.warn`/`.danger`) `.lamp` `.word` `.caret` `.fold-body` | disclosure fold |
| `.tabs` `.tab` (+`.n`) | tab switchers (buttons with `role="tab"`/`aria-selected`) |
| `.table-scroll` `table.ledger` (`th.l` `td.l` `.sym`) | data tables — numbers right, text `.l` left |
| `.chart` `.axis` `.gridline` `.zeroline` `.spark` | hand-rolled SVG chart helpers |
| `.settle` (+`.d1..d3`) | entrance motion, respects reduced-motion |

Tokens: palette (`--ground/--dome/--dome-2/--line/--line-2/--fg/--fg-dim/--faint`), brass
chrome (`--brass/--brass-hi/--brass-dim/--brass-soft`), the six-phase spectrum
(`--washout/--recovery/--ignition/--trend/--distribution/--flush`) plus aliases
`--up/--down/--warn/--danger`, type stacks (`--serif/--mono/--sans`). Voices: mono =
machine fact · serif = argued prose (panel `h2`, theses) · sans = operator labels/controls.

## Chart honesty idioms (page-local SVG, shared discipline)

Immature-before-warmup regions are hatched and labeled — immature, not missing. Put this
`<defs>` in any SVG that needs it (ids are per-SVG; suffix if you have several):

```html
<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="rgba(109,155,209,.28)" stroke-width="1.4"/></pattern></defs>
```

Null readings lift the pen (no point, no bar, no zero). Every table cell with no reading
renders the `.null` em-dash. Backtest panels (strategy face) render `delistings_hit`
(terminal −1.0 treatment) and `discarded_days` (counted, not hidden) as first-class fields,
and a window's start states its maturity reason (`window.note` in the mock).

## Hard reminders (from the briefs — violating one is a bug)

Read-only faces: no order/edit affordances anywhere; gate states display only. Desktop-first
1280–1440, no horizontal body scroll (wide tables go inside `.table-scroll`). No frameworks,
no CDN libs; Google Fonts arrives via shell.css alone. Hand-rolled SVG charts. Null renders
as em-dash, never zero. Everything fabricated sits under a SAMPLE marking.
