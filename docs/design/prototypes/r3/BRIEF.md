# Face Design — Round 3: The Conversational Strategy Face (2026-08-30)

**Operator's Round-2 verdict:** the Strategy side works primarily as a **conversation with the
agent** — the shelf is sediment, the dialogue is the work. The layout question (how conversation
and dossier share the screen) goes to a visual comparison: **three variants, one transcript**.

**Deliverable:** three layout variants of the conversational Strategy face, all in the Round-2
shell (Observatory + ledger graft), all rendering the SAME mock session, so only the layout
differs:

| File | Variant |
|---|---|
| `strategy-3pane.html` | **Three-pane workbench**: left rail = strategy switcher (the R2 shelf compressed to a lifecycle nav), center = the conversation ledger, right rail = the live dossier (thesis, kill-line, backtest instruments) of the strategy in session |
| `strategy-page.html` | **Full-width conversation page**: breadcrumb back to the shelf (`strategy.html`), the dossier as a collapsible strip above the timeline, conversation gets the full measure |
| `strategy-immersive.html` | **Immersive**: conversation fills the viewport dsh-style, the dossier floats as pinned/dockable cards over the timeline |

**Authority: zero**, as always. `Kairos-Design.md` and the skeleton spec win every conflict.

## The design translation — conversation as instrument, not chat app

The dialogue face inherits the whole voice system; it must NOT read as a message stream:

- **The transcript is a ledger timeline.** Turns are numbered entries in the session's own
  sequence (`T·1, T·2…` or the page's entry vocabulary), not bubbles. No avatars.
- **Three voices land literally** (the shell's registers):
  - operator turns — sans, the operator's own authority; Chinese in the mock (a live register
    choice: the operator speaks their language);
  - Kairos turns — serif, argued prose, *read critically*;
  - tool/machine turns — **mono instrument cards**: a breadth reading, a backtest probe, a file
    diff — each a signed entry (producer monogram + raw linkback), the R2 entry-plate system
    living inside the conversation.
- **Danger forces disclosure inside the timeline.** The mock's breadth card carries
  `danger: true` + its rule — it renders auto-opened/alerted; routine cards may fold.
- **Arena writes are records, not approvals.** `arena_write` cards show the diff and the git
  commit — Kairos writes its own arena freely; git is the record, not a gate. The `proposal`
  card is different: a draft diff *awaiting operator judgment* (which the operator then
  declines in the mock — render that arc honestly; the operator is the only teacher).
- **The attendance stamp is visible** (`session.attendance: "interactive"`) and never blurred.
- **The composer is present but inert** — a real composer control at the timeline's end
  (styled, focusable, disabled with an honest note: prototype, not wired). No other write
  affordance exists.

## Hard constraints

All Round 1 + Round 2 constraints bind (shell conformance, read-only beyond the inert
composer, SAMPLE marking on fabricated content, null = em-dash, desktop-first 1280–1440,
`@dsCard` first line, self-contained except shared scripts/`shell.css`/fonts). Plus:

- The three variants render the SAME `window.KAIROS_SESSION` transcript with the same card
  components — a reviewer comparing variants must see the layout move, not the content change.
- The transcript's real readings (the 2026-07-08 breadth card embeds real bed numbers) keep
  their raw linkbacks; the fabricated dialogue sits under the session's SAMPLE marking.
- Where a variant shows the dossier, its numbers come from `window.KAIROS_FACES.strategies`
  (tt-breakout) — same source as R2's shelf.

## Data

- `../data/session_mock.js` → `window.KAIROS_SESSION` (fabricated transcript, labeled; real
  embedded readings — see the file's `note`)
- `../data/workbench_mock.js` → `window.KAIROS_FACES` (dossier numbers)
- `../data/market_mock.js` → `window.KAIROS_DATA` (masthead bed facts)
- `../shell.css` → wait — no: `r3` pages link the shell as `../r2/shell.css` (the shell is
  Round 2's artifact; Round 3 conforms to it, it does not fork it)

## Files

```
docs/design/prototypes/r3/
  BRIEF.md
  timeline.css  timeline.js  TIMELINE-NOTES.md   the shared conversation kit (built first)
  strategy-3pane.html  strategy-page.html  strategy-immersive.html
```

**The kit rule:** `timeline.js` renders `window.KAIROS_SESSION` into a container
(`renderSessionTimeline(el)`), `timeline.css` styles the turns/cards in shell vocabulary.
Variants call the renderer and lay out panes around it — they may NOT reimplement or restyle
the turn/card components. This is what makes the comparison honest: the content is literally
shared, only the layout moves.
