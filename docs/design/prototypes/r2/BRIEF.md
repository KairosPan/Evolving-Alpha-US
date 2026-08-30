# Face Design — Round 2: The Chosen Direction, Full Set (2026-08-30)

**Operator's Round-1 verdict:** direction **a-Observatory** wins, **grafting b-Ledger's
entry-numbering + producer-initialing system** (every panel a numbered ledger entry, signed
by the function that produced it). Round 2 builds the full face set in that hybrid voice.

**Deliverable:** four pages sharing one visual shell —

| Page | Content |
|---|---|
| `landing.html` | Round-1 Observatory landing evolved: live nav tiles to the three faces, the entry-plate graft introduced |
| `market.html` | Round-1 Observatory market evolved into the shell + entry-plate graft |
| `strategy.html` | NEW — the strategy shelf: lifecycle rail (idea → researching → validated → paper → retired), per-strategy entries with thesis, falsification line, journal freshness, honest backtest summary, equity spark |
| `account.html` | NEW — the paper account: equity/cash/buying-power, positions (by strategy), closed-trades ledger, exposure, the double order gate rendered read-only |

**Authority: zero**, as in Round 1. `Kairos-Design.md` and the skeleton spec win every conflict.

## The graft, translated

Ledger's rubber stamps and paper do NOT come along — the Observatory's near-black engraved
world stays. What crosses over is the **bookkeeping skeleton**:

- **Every panel is a numbered entry**: `E 526.1`, `E 526.2`… (526 = the bed's session count,
  the day-number of record). Faces number their own entries; numbering is per-page.
- **Every entry is signed by its producer**: an engraved monogram/initial mark carrying the
  producing function or file (`market_breadth`, `build_universe`, `status.yaml`…) — the
  Observatory translation of Ledger's initialed footer. This *is* the raw-linkback affordance
  (BRIEF R1's rule), promoted from furniture to signature.
- **Fabricated blocks carry the SAMPLE stamp** in the same engraved voice.

## Shared shell (built first, faces conform)

One masthead (KAIROS · face-name · as-of · bed facts · ORDERS UNARMED chip), one nav
(Market / Strategy / Account as real relative links: `market.html`, `strategy.html`,
`account.html`; landing linked from the wordmark), one footer, one token sheet
(`shell.css`): the Round-1 Observatory palette/typography (Fraunces roman for argued voice,
IBM Plex Mono for machine fact, Archivo for operator controls; brass = interactive chrome;
thermal spectrum = phase semantics) plus the entry-plate components. Faces load it via
`<link rel="stylesheet" href="shell.css">` (build step inlines for the design-project sync,
same as the data script).

## Hard constraints (all of Round 1's, plus)

- Round 1 BRIEF constraints all bind: read-only faces, warmup honesty, raw linkbacks (now via
  producer signatures), no vendor numbers, null = em-dash, labeled fabrication, desktop-first
  1280–1440, self-contained except shared scripts/fonts, `<!-- @dsCard group="…" -->` first line.
- **Backtest panels speak the five honest-eval rules**: the strategy face renders
  `delistings_hit` with its terminal −1.0 treatment and `discarded_days` with its
  counted-not-hidden treatment as first-class fields, not footnotes. A backtest window's start
  states its maturity reason (the mock carries `window.note`).
- **Lifecycle is a one-way rail**: idea → researching → validated → paper → retired. `retired`
  is an honored terminal state (the retired strategy's lesson is displayed, not hidden).
- **No approval machinery**: gate states display; nothing operates them.

## Data

- `../data/market_mock.js` → `window.KAIROS_DATA` (REAL, Round 1's bed extract) — market face,
  masthead bed facts.
- `../data/workbench_mock.js` → `window.KAIROS_FACES` (FABRICATED, labeled) — strategy +
  account faces. Shape mirrors the real `strategies/_template` contract and the honest-eval
  vocabulary; see the file's own `note`.

## Files

```
docs/design/prototypes/r2/
  BRIEF.md  shell.css  SHELL-NOTES.md
  landing.html  market.html  strategy.html  account.html
```
