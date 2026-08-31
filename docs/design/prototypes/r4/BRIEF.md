# Face Design — Round 4: Minimal Chat First (2026-08-30)

**Operator's Round-3 verdict:** all three R3 layouts read as too complex. **Start simple, add
later** — the reference the operator showed is a plain messenger app: a conversation list in a
left sidebar, message bubbles, rich results rendered inline in the agent's reply, a simple
composer. Round 4 designs that starting point. R2/R3's instrument grammar is not discarded —
it is the "add later" reservoir; this round defines v1.

**Deliverable:** one minimal chat kit + two palette variants of the same page:

| File | What |
|---|---|
| `chat.css` + `chat.js` | the minimal kit: token-driven styles + `renderChat(el)` rendering `window.KAIROS_SESSION` |
| `chat-light.html` | the messenger-clean light variant (closest to the operator's reference) |
| `chat-dark.html` | the identical layout in the Observatory palette — tests whether "simple" and the chosen voice coexist |

**Authority: zero**, as always.

## The translation — simple, not dishonest

The messenger metaphor maps onto our objects:

- **Conversations = strategies.** The sidebar lists the five strategies from
  `window.KAIROS_FACES.strategies.rows` as conversation rows: name, a tiny status chip, and the
  `journal_tail` truncated as the "last message" preview. tt-breakout is the active
  conversation (this session); the rest are inert.
- **Bubbles carry the voices, lightly.** Operator = right-aligned dark bubble (their own words,
  as in any messenger). Kairos = left-aligned light bubble with a small name label. The serif /
  mono / sans register system relaxes to: prose in the UI face, machine numbers in mono. No
  engraved plates, no entry numbers, no monograms.
- **Tool results are compact inline cards** inside the flow, not instruments: the breadth
  reading as a small stat row card, the backtest probe as a small two-row table, arena writes
  as a slim "journal.md · commit 1f3a9e2" line card with the added lines, the proposal as the
  same card with a "draft — awaiting judgment" tag. A card is one visual notch quieter than a
  bubble.
- **Honesty survives at small size — this is the line that does not move:**
  - the danger reading keeps a visible warn accent (thin amber edge + its rule line, shown, not
    folded);
  - every card keeps a small `raw` link (plain text link, not a signature plate);
  - the session header row keeps `SAMPLE` and the `interactive` stamp as small quiet tags;
  - null = em-dash; the thin-sample caveat line stays on the backtest card.
- **The composer is present and inert** ("Message Kairos…", disabled, small honest note).
- Date/time separators like a messenger ("2026-07-08 09:41").

## Hard constraints

- Same transcript, byte-identical content across both variants; only tokens differ.
- Both variants read `../data/session_mock.js` + `../data/workbench_mock.js`. No shell.css —
  the kit is self-standing (this round intentionally does not import the R2 shell; fonts:
  system stack or one Google Fonts family, keep it plain).
- Read-only beyond the inert composer; SAMPLE marking; no vendor numbers; desktop-first
  1280–1440, no horizontal body scroll; `@dsCard` first line per file.
- Keep it genuinely small: the whole kit should be a fraction of R3's (target: chat.css +
  chat.js together well under half of timeline.css + timeline.js).

## Files

```
docs/design/prototypes/r4/
  BRIEF.md  chat.css  chat.js
  chat-light.html  chat-dark.html
```

---

## Verdict (2026-08-30, operator)

**`chat-light` chosen.** The light minimal chat is the v1 definition of the Strategy face.
The dark variant stays as the record of the palette question; the R2/R3 instrument grammar
remains the add-later reservoir. Next: the implementation brainstorm — the wiring question
(our face driving dsh headless vs. coexisting with dsh's own UI) is now unavoidable, since
the chosen face carries a live composer by intent.
