# R3 — Session-timeline kit · contract for the layout variants

You are building ONE variant page (`strategy-3pane.html` / `strategy-page.html` /
`strategy-immersive.html`) in `r3/`, laying panes AROUND the shared conversation ledger.
The kit renders the ENTIRE session — header, turns T·1…T·12, and the one inert composer —
you render none of it yourself. This is what makes the three-way comparison honest: the
content is literally shared, only the layout moves.

## Tags — exact, in this order (paths relative to `r3/`)

In `<head>` (shell first, kit second):

```html
<link rel="stylesheet" href="../r2/shell.css">
<link rel="stylesheet" href="timeline.css">
```

At the end of `<body>`, before your own page script:

```html
<script src="../data/market_mock.js"></script>
<script src="../data/workbench_mock.js"></script>
<script src="../data/session_mock.js"></script>
<script src="timeline.js"></script>
```

`market_mock.js` + `workbench_mock.js` first (masthead bed facts + dossier numbers, same as
R2 — the shell-fill snippet and any dossier panes read them), `session_mock.js` next so
`window.KAIROS_SESSION` exists, `timeline.js` last. `timeline.js` only defines the renderer;
it renders nothing on load.

## The one call

```html
<div id="timeline"></div>
…
<script>
  renderSessionTimeline(document.getElementById("timeline"));
</script>
```

One call, one container (any block element), after the four scripts. The renderer clears the
container (idempotent — calling again re-renders) and builds: session header (strategy name,
id, date, engraved attendance stamp, runtime line, SAMPLE plate, raw linkback) → all turns →
the inert composer. If `KAIROS_SESSION` is missing it renders an honest em-dash empty state,
never a fake.

## Container sizing — you own the box, the kit fills it

- The timeline is **width-fluid, designed for 560–900px** of content width. Give the
  container a width in that range (fixed, flexed, or clamped); the kit fills 100% of it.
- The kit never causes horizontal page scroll: wide internals (the backtest arms table, diff
  lines) scroll inside their own sub-containers.
- Vertical behavior is yours: full-page flow, a scrolling pane (put `overflow-y:auto` on
  your pane, not on `.tl`), sticky siblings, floating cards over it — all fine.

## What you MAY style

Page layout, panes/rails/grids, the masthead + footer (copy the R2 skeleton and shell-fill
snippet per `../r2/SHELL-NOTES.md` — the kit does NOT fill the masthead), the dossier
(numbers from `window.KAIROS_FACES.strategies`, tt-breakout), breadcrumbs, docked/pinned
cards, entrance motion on your own panes, and the timeline **container itself** — its width,
margin, position, background, overflow. The outer box only.

## What you may NOT touch

- Anything inside the rendered timeline: **no CSS selector may target `.tl-*`**, nor shell
  classes as they appear inside the container (`#timeline .sig`, `#timeline details.fold`,
  `#timeline .ledger`, …). Nothing. If a spacing/width need arises, solve it on the container.
- No reimplementing or duplicating turns/cards, no hiding or reordering turns, no reading
  `KAIROS_SESSION` into markup of your own (dossier reads `KAIROS_FACES`, not the session).
- No second composer and no other write affordance anywhere on the page.
- No copies or forks of `timeline.css` / `timeline.js` — link the shared files.

## Behavior already baked into the kit (don't re-add it)

- **Danger comes from the data** (`turn.danger`): the breadth card renders alerted
  (danger lamp/border) and forced open, with its rule line printed. Routine cards render
  open and can be folded by hand — their summary line stays an honest one-line reading.
- **The composer is present, focusable, and inert** (readonly textarea + disabled send +
  honest note). It is the page's only write-shaped control.
- **Fabrication marking**: the session header carries the SAMPLE plate for the whole
  transcript; every tool card is signed (`.sig` monogram = raw linkback) with its own raw
  pointer — the 2026-07-08 breadth reading is real and its signature says so.
- **Arena writes vs proposals**: committed writes show `+` diff lines and an engraved git
  commit plate (record, not gate); the proposal shows a dashed amber `±` draft awaiting
  operator judgment. Both arcs are in the data — do not editorialize around them.
- Nulls render as `.null` em-dashes; numbers use the typographic minus; nothing prints NaN.
