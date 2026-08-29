# Doctrine — operator trading rules

> **Scope: operator style, not market law.** These are the operator's personal
> investment rules and preferences. Follow them by default — but when research findings
> conflict with an entry here, REPORT the conflict; do not silently defer.


## stop_discipline (red-line)
*Regime: all*
Non-event price deterioration triggers the hard stop with no exception; baseline stop is 7-8% below entry, tightened per the market-clock action rule; never average down.

## one_correlated_bet (red-line)
*Regime: all*
All names in one theme are a single bet: net their exposure as one position (one theme, one bet), never stack them as independent bets.

## loss_circuit_breaker (red-line)
*Regime: all*
Halt new entries when the single-day, consecutive-loss, single-name, or market-wide loss breaker trips.

## survivorship_pit (red-line)
*Regime: all*
Use only point-in-time data; a delisting or halt-to-zero during a hold is a terminal loss, never dropped.

## fill_feasibility (red-line)
*Regime: all*
Do not rank an unbuyable name ahead of a buyable one; model the realistic entry, not a fantasy fill. Carries executability while no liquidity floor is set.

## panic_state_ban (red-line)
*Regime: all*
In a panic state (bear-market signal + high volatility + a sharp index rebound) take no new long in any 'strong' leader until a fresh base, a follow-through day, and a new leadership list appear. Prose red-line; L4 guard enforcement is pending (guard action work).

## thesis_first (red-line)
*Regime: all*
Every pick's primary reason must cite a thesis card; a pick whose primary reason is an indicator (RS, price, moving average) is invalid.

## earnings_checklist_gate (red-line)
*Regime: all*
Holding through an earnings event requires the thesis checklist completed by T-3 (verification-node expectation logged, counter-thesis re-checked, this quarter's disproving number named); an incomplete checklist means do not hold. Automation is pending the earnings feed (P5).

## scale_disambiguation (red-line)
*Regime: all*
When the user speaks in cycle terms (freeze, ferment, divergence, ebb, leader, laggard), confirm which scale is meant — market, theme, or stock — before interpreting; a cycle word is meaningless without its clock.

## cycle_eye
*Regime: all*
For any object — market, theme, or stock — first ask which phase of its cycle it is in, then discuss buying or selling. Price leads narrative; the cycle sets the posture.

## market_three_states
*Phases: market:confirmed_uptrend, market:under_pressure, market:correction*
The market answers one question: is attack allowed now. Confirmed uptrend may attack; under pressure defends and does not expand; correction holds cash as a position. Code decides the state (follow-through and distribution-day counts), not eyeballing.

## panic_state
*Phases: market:panic_state*
After a large decline with high volatility and a sharp rebound, 'strong stays strong' fails systemically: the bounce is led by beaten-down losers and the old leaders lag badly (a momentum crash). Do not buy leaders in the panic bounce; wait for a new base, a new follow-through, and a new leadership list — the next cycle's leaders are usually not the last one's.

## theme_lifecycle
*Phases: theme:emerging, theme:institutional, theme:public_laggard, theme:exhaustion*
Read holdings composition — who is buying now — not crowd emotion. emerging: industry facts first, insiders and early money build, leaders surface; institutional: institutions relay and earnings start delivering (the main battlefield); public_laggard: the crowd arrives and laggards catch up (the timer rings); exhaustion: rotation accelerates, fringe names dance, delivery no longer moves price.

## theme_confluence
*Phases: theme:emerging, theme:institutional*
A theme's size is its confluence count: industry fact (earnings delivery) x institutional consensus (holdings/ratings) x public participation x policy/macro tailwind x cross-market confirmation. More confluence, bigger theme; heat with zero confluence is a chip game, not a theme.

## stock_stage
*Phases: stock:base, stock:advance, stock:top, stock:decline*
Go long only in advance (Stage 2). A base is the morphological evidence of institutional accumulation over weeks; a top speaks in high-volume stalling and distribution days, not 'divergence-to-consensus for one more leg'; a climax run far above the moving averages is trim language, not add language.

## clock_cadence
*Regime: all*
Read the market state daily, review the theme lifecycle weekly, decide the stock stage weekly. A higher scale vetoes a lower scale's action (authority flows down); a lower scale does not score a higher one.

## event_reread
*Regime: all*
Evidence flows up through one dedicated channel: designated events (a held leader breaking down on volume, laggards launching en masse, breadth collapse, a post-earnings gap that does not fill against the thesis) force an immediate re-read of the higher clock, overriding any cadence table. Trigger enforcement lands in the P2 classifier successor.

## intraday_burial
*Regime: all*
The old book's strongest reflex — intraday sentiment reading — has no home at a week-to-month horizon. Demote it to a noise filter with two residual uses only: entry timing on a breakout day, and panic-state detection support.

## market_state_actions
*Phases: market:confirmed_uptrend, market:under_pressure, market:correction*
confirmed_uptrend: may open and add, baseline stops. under_pressure: no new positions, halve add-ons, tighten existing stops to 5-6%. correction: no new positions, no adds, only reduce, tighten stops to 3-4%, cash is a position. State set by follow-through day (confirms uptrend) and distribution-day count (>=5 in 25 days downgrades). The tightening bands are literature defaults pending verdict calibration; code enforcement is the P2 classifier successor.

## theme_origin
*Phases: theme:emerging*
A real theme is a real industry inflection: a technology cost-curve break, adoption entering the steep part of the S-curve, a platform-scale new category, or a strong policy cycle. Price heat is not a theme; the theme precedes the price, and price only confirms it.

## s_curve_position
*Phases: theme:emerging, theme:institutional*
The same theme at different S-curve positions is a different investment: introduction buys possibility (high mortality, watch-list size only), the steep phase buys delivery (where the main position sits), the plateau buys share and margin (a different valuation language). Answer 'where on the curve' before 'what to buy'.

## value_chain_profit
*Phases: theme:emerging, theme:institutional*
Trace whose budget the money leaves, which links it passes, and where it settles as profit — profit attribution decides who the leader is. Early in a demand surge profit settles at the bottleneck link (sell the shovels first); the bottleneck migrates, profit follows it, and the position follows the profit.

## read_through
*Phases: theme:institutional*
Up-and-down-chain reasoning is the cleanest positive transfer: one link delivers, forecast the next link's orders and capacity — the US way is read-through via earnings (a customer's capex guide is the supplier's revenue lead). Draw the horizontal (peers) and vertical (chain) extension map on a quarterly timescale.

## thesis_card_format
*Regime: all*
Every invested theme gets one card, answered in prose to four questions (no fill-in fields): (1) what is the thesis — name specific customers, competitors, bottleneck links, never market language; (2) why now — inflection evidence, not 'eventually'; (3) what does the smart short say — no smart short case means you do not understand the industry; (4) if the thesis is true, what does the world show first — a pre-registered surprise.

## thesis_card_lifecycle
*Regime: all*
A card has a lifecycle: draft, invested (occupies a theme slot), verifying, closed (delivered-exit or disproven-exit, both written into the review). The invested-card count cap is the portfolio structure rule.

## verification_nodes
*Regime: all*
Each card's verification nodes must be calendar-anchored to external events (earnings, product launches, industry data, competitor read-through) with a prior expectation attached; a node reached must be re-checked, or 'hold while the thesis holds' decays into 'never checked, so always holds'.

## price_freeze_test
*Regime: all*
A disproof condition must pass the price-freeze test: if the price were frozen, could this still trigger? Only then is it a thesis disproof (e.g. 'a competitor won the key account', 'capex guides cut across the board'). Price conditions belong to the stop domain and are banned from the card.

## pead_humility
*Phases: theme:institutional*
Post-earnings-announcement drift is for mechanism understanding only, not return expectation — large-cap drift has been arbitraged away over two decades. The edge comes from industry insight, not anomaly arbitrage.

## theme_portfolio
*Regime: all*
The number of themes understood deeply at once has a hard cap (for humans and LLMs alike); better three themes ten layers deep than ten themes one layer deep. The number is in the portfolio structure rule.

## portfolio_structure
*Regime: all*
Hold 2-3 invested themes, 1-3 names each; all names in one theme count as a single bet (one theme, one bet; the existing correlation netting carries it).

## leader_definition
*Phases: theme:institutional, stock:advance*
A leader is industry-profit bearer x market confirmation, both required. Candidates come only from the thesis card's profit-attribution chain (any market cap); market confirmation without profit-bearing is a chip game, profit-bearing without confirmation is a value trap or wrong timing.

## rs_as_jury
*Phases: stock:advance*
Relative strength and the Trend Template are the jury, not the judge — they only confirm or reject the candidates the thesis produces; they never generate a candidate and never rank. Screen parameters live in the universe layer (trend template).

## strength_surprise
*Phases: stock:advance*
'Refusing to weaken is strength' still holds at the weekly scale: a fast reclaim after a shakeout, undercut-and-rally, an earnings gap-up that does not fill — all are the language of institutions supporting. But it confirms an existing thesis candidate; it is not a way to discover new ones.

## leader_breakdown
*Phases: stock:top, stock:decline*
A leader breaking a key moving average on volume is the number-one signal of that theme's cycle turning. Leader stands, theme lives; leader falls, force a theme-clock re-read (via event_reread) before discussing the stock.

## laggard_timer
*Phases: theme:public_laggard*
Laggards and back-row names launching en masse is evidence the theme clock has turned to public_laggard — a timer, not a target. Chasing laggards in the public phase is the momentum-crash catch-up trap; burying into the value chain's second profit-bearer in the emerging phase is the legitimate variant.

## sell_matrix_pointer
*Regime: all*
The hardest cell is 'thesis intact + price deteriorating'. The only arbiter is the thesis-price matrix: first split event vs non-event, then execute per the table — no improvising at the tape.

## thesis_price_matrix
*Regime: all*
The sole arbitration table: thesis intact + price good -> hold/add per rules; thesis intact + price bad (event gap) -> earnings-gap discipline; thesis intact + price bad (non-event) -> confirmed breakdown reduces to core, the hard stop overrides unconditionally; thesis broken + price good -> disciplined exit (a good price is the exit, not a reason to stay); thesis broken + price bad -> exit all immediately. This table has top priority; any entry conflicting with it yields to it.

## earnings_gap_discipline
*Regime: all*
Applies only to earnings-event gaps (non-event drift or technical breakdown goes to the stop and derisk rules). From T-3 the thesis checklist is mandatory; incomplete means do not hold. A gap against the thesis that triggers a disproof condition executes next day per the thesis-price matrix, not waiting for a technical level. The single-night gap risk of holding through earnings is confirmed by the user at approval (no single-name cap is set). Automation is pending the earnings feed (P5).

## derisk_on_breakdown
*Phases: stock:top, stock:decline*
A held leader trading >=2x its 20-day average volume and closing below the 50-day line triggers an event re-read and a cut to the core position (half the original). Suggested values, pending user ratification. Guard/sizing has no trim action vocabulary yet, so until it lands this is prose-level discipline enforced by human approval.
