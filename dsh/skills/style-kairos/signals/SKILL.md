# Signals — operator setups

> **Scope: operator style, not market law.** These are the operator's personal
> investment rules and preferences. Follow them by default — but when research findings
> conflict with an entry here, REPORT the conflict; do not silently defer.


## breakout_entry — Base Breakout Entry
*pattern · active · phases: stock:base, stock:advance*
- **Trigger:** a base pivot breaks on volume confirmation, or the first pullback retests and holds the pivot
- **Entry:** buy the pivot-breakout / first-retest reclaim, no higher than 5% above the pivot
- **Exit/stop:** exit per stop_discipline (hard stop 7-8% below entry, tightened per market-clock) and derisk_on_breakdown; this skill defines entry only
- **Taboo:**
  - chase more than 5% above the pivot
  - buy a breakout while the market state forbids new entries

## follow_through_day — Follow-Through Day
*feature · active · phases: market:confirmed_uptrend*
- **Trigger:** a strong higher-volume index up day several sessions into a rally attempt confirms a new uptrend
- **Taboo:**
  - call an uptrend confirmed without a follow-through day

## distribution_day_cluster — Distribution Day Cluster
*failure_detector · active · phases: market:under_pressure, market:correction*
- **Trigger:** five or more high-volume down days in the index within 25 sessions
- **Exit/stop:** downgrade the market state; no new positions, tighten stops
- **Taboo:**
  - add risk into a distribution-day cluster

## leader_breakdown — Leader Breakdown
*failure_detector · active · phases: stock:top, stock:decline*
- **Trigger:** a held leader trades at two times or more its 20-day average volume and closes below the 50-day line
- **Exit/stop:** force a theme-clock re-read; cut to the core position
- **Taboo:**
  - add to a leader breaking down on volume
  - let a cadence table excuse ignoring a leader breakdown

## laggard_launch — Laggard Launch Timer
*failure_detector · incubating · phases: theme:public_laggard*
- **Trigger:** three or more non-leader names in a theme surge on abnormal volume the same day
- **Exit/stop:** read it as a public_laggard timer; do not chase, tighten discipline on the leaders
- **Taboo:**
  - chase a laggard catch-up move in the public phase
- **Depends on:** theme_breadth

## climax_run — Climax Run
*failure_detector · active · phases: stock:top*
- **Trigger:** a parabolic late-stage acceleration far above the moving averages with climactic volume
- **Exit/stop:** trim into the climax; do not add
- **Taboo:**
  - add into a climax run
  - read a climax as a fresh breakout
