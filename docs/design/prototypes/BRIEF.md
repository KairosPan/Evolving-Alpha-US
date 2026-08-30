# Face Design — Round 1: Direction Exploration (2026-08-30)

**Deliverable:** three visual directions for the workbench's future faces, each rendered as
two interactive HTML prototypes — a **landing page** (carries the direction's full character:
name, signature graphic, narrative typography) and a **Market instrument** (the same real
dataset rendered in that direction's voice, so the three "instrument feels" compare directly).
Synced to a claude.ai/design project for the operator to browse; committed here as the design
record.

**Authority: zero.** Prototypes are ideation artifacts. Nothing here decides architecture;
`Kairos-Design.md` (intent) and the skeleton spec (mechanism) win every conflict.

## Lineage (inherited principles, not inherited pixels)

From the 2026-07-07 SoniaKairos face round (recovered from the design repo's git history):

1. **Narrative lives on the landing; instruments stay terse.** The operator's own feedback —
   "every face has too many words" — root cause: faces narrating the system instead of letting
   structure, type, and stamps carry meaning.
2. **Danger forces disclosure; routine stays folded.** Detail collapses by default and
   auto-opens when a warning state is present. Danger is never hidden, routine is never noisy.
3. **Typographic voices.** mono = machine-verifiable fact · serif = argued prose, read
   critically · sans = the operator's own controls/labels. Use the register split, not
   necessarily those exact stacks.
4. **Instrument, not chat.** The face is a cockpit of readings, never a message stream.

From alpha_web ("Regime Instrument", recovered from origin/main): the six-phase thermal-ring
idea — colour as a semantic spectrum bound to market phase, not a single accent.

## The three directions

| Key | Name | Character |
|---|---|---|
| `a-observatory` | **Observatory** | dark precision instrument: astronomical/nautical bearing, engraved scales, luminous data on near-black, the regime ring's orthodox descendant. Quiet authority. |
| `b-ledger` | **Field Ledger** | paper-and-ink laboratory notebook: warm light ground, ruled lines, stamped dates, the honesty apparatus (PIT stamps, checksums, window bounds) as visible bookkeeping. The backtest bed as a lab record. |
| `c-terminal` | **Terminal** | pure mono, TUI density, zero ornament: box-drawing structure, data-ink only, the operator-at-the-prompt lineage. Everything earns its pixels. |

Each direction should be pushed to its own extreme — the point of the round is contrast.

## Hard constraints (violating one is a bug, not an idea)

- **Read-only faces.** No order buttons, no edit affordances, no write path anywhere. Gate
  state (`orders_gate` in the data) is *displayed*, never operable.
- **The bed's honesty is visible.** The data window is 2024-06-03..2026-07-09 with **no
  warmup**: 200DMA readings are immature before 2025-03-20, 52-week metrics before
  2025-06-04 (`bed.warmup` in the data). Charts that cross those boundaries must show the
  immature region as visually distinct (muted/hatched/annotated) — *immature, not missing*.
- **Every reading links back to raw.** Each data block carries a `raw` pointer (file path or
  producing function). Render a linkback affordance; no face is ever the only narrator.
- **No vendor/marketing numbers.** Only bed-derived facts.
- **The fabricated block is labeled.** `account_mock` is invented shape-data; if a direction's
  landing or market face shows account fragments, they carry the prototype's SAMPLE marking.

## Data contract

All prototypes load the same real dataset (extracted read-only from the 2yr PIT bed by
`scripts`-grade code; see `data/market_mock.json`):

```html
<script src="../data/market_mock.js"></script>  <!-- defines window.KAIROS_DATA -->
```

Shape (lengths are real, not illustrative):

- `bed` — root, window {start,end}, warmup {sma200_valid_from, week52_valid_from,
  trend_template_valid_from, note}, symbols=797, captured_days=526, raw {snapshot, calendar,
  checksums}
- `as_of` — "2026-07-09" (the bed's last captured day; faces render *as of* this day)
- `breadth.series[60]` — {date, pct_above_200dma (0..1), net_new_highs, advances, declines}
- `tape.series[250]` — {date, level (eq-weight composite, 100 = window start), n}
- `screens.trend_template.rows[40]`, `screens.gainer.rows[33]` — {symbol, status, close,
  prev_close, pct_change, gap_pct, volume, rs_percentile, spark[≤60] (closes normalized to
  the window's first close), … } — several enrichment fields (rvol, short_interest,
  free_float…) are `null` in this bed: render the absence honestly (em-dash), never fake.
- `account_mock` — labeled fabricated; includes `orders_gate` {gate1_registered:false,
  gate2_validated:false}.

`null` semantics everywhere: *no reading*, never zero.

## Technical constraints

- One self-contained HTML file per prototype (inline CSS/JS); the ONLY external references
  allowed are the shared `../data/market_mock.js` script (a build step inlines it before the
  design-project sync) and Google Fonts stylesheets.
- First line of every file: `<!-- @dsCard group="<Direction name>" -->` (the design pane's
  card index reads it).
- Desktop-first, designed at 1280–1440 wide; no horizontal body scroll.
- No frameworks, no CDN libraries. Hand-rolled SVG/canvas charts are expected and welcome.
- A direction commits to its own palette (light or dark); paint the body background
  explicitly.

## Files

```
docs/design/prototypes/
  BRIEF.md                      this file
  data/market_mock.{json,js}    the shared real dataset
  a-observatory/{landing,market}.html
  b-ledger/{landing,market}.html
  c-terminal/{landing,market}.html
```
