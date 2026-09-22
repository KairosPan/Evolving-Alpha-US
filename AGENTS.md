# AGENTS.md — Evolving-Alpha-US workspace

Three layers: MARKET + ACCOUNT live in the alpaca_kit package; STRATEGY (you) works in
strategies/.

- alpaca_kit/ — data + account library AND the MCP server you already have tools from.
  For backtests, import it directly (alpaca_kit.replay.replay_days); MCP tools are for
  interactive queries only. Prices are RAW/unadjusted. The PIT guard is the caller's job:
  replay_days and the MCP tools wrap it for you, a bare make_source() does NOT — it returns
  a RAW source by contract. Never read one directly in a backtest; go through replay_days,
  or wrap it yourself in GuardedSource with an AsOfGuard for the day.
- AKShare MCP (`mcp__akshare__*`) — A-share and other public market queries in
  Kairos. Use `akshare_discover` to find the method and its category tool. These
  vendor reads have NO PIT guard; do not use them as replay/backtest evidence.
  `stock_zh_a_spot_tx` is the verified Tencent A-share snapshot method; Eastmoney
  and Xueqiu endpoints may fail or require a valid login. Check returned errors,
  timestamps and `truncated`: the default response limit is 500 rows, so a
  truncated result is not the whole market. Retrieval time is not exchange time.
- strategies/<name>/ — one directory per strategy: THESIS.md, screen.py, backtest.py,
  backtests/, journal.md, status.yaml. Lifecycle, declared in status.yaml:
  idea | researching | validated | paper | retired — paper is a reserved forward-testing
  state, meaningful only once the order gate opens. status.yaml also carries three optional
  headline keys the face's channel landing page renders when present: one_line (the current
  conclusion, one sentence), next (the next step), numbers (free key-value figures) — none
  required; fill them in when there is something worth a line. Copy strategies/_template to start one,
  named as the face's create box names them: opening on a letter or digit in any script, then letters,
  digits, - and _, at most 41 code points, no spaces or dots. The name becomes a path you write into
  shell by hand and has to stay one word: a space makes zsh read `cd x y` as its two-argument form (x
  replaced by y in $PWD) — usually an error, but where the substituted path exists it lands you in the
  wrong directory with exit 0 (`cd aaa/bbb/ccc; cd bbb xxx` ends in `aaa/xxx/ccc`).
  Commit your own iterations; git log is the audit trail.
  A new strategy starts with one batched ask_user_question, not with code: the thesis
  and the falsification terms that would retire it, which bed and which window (warmup
  moves the honest start), and what the operator wants measured. A brief that already
  answers those is the answer. Decide the rest yourself.
- data/pit/ — offline PIT beds (~800 symbols). Two usable windows, and only these:
  data/pit/2yr = 2024-06-03 .. 2026-07-09 (526 trading days), data/pit/broad =
  2025-11-17 .. 2026-03-27 (90 days). Each bed's trading_calendar() runs back to 2016 with no
  snapshots there, and the beds fail differently outside the window: a snapshot read raises
  SnapshotMissingError, while bar and corp-action reads return an EMPTY frame silently. Stay
  inside the window. The beds also carry NO warmup: bars start AT the window start, so long
  indicators are blind at first. The full window is replayable, but on 2yr the 200DMA is valid
  only from 2025-03-20 and 52-week metrics from 2025-06-04 (trend_template returns zero names
  before 2025-06-05); broad, at 90 days, never satisfies either. Set
  ALPHA_PIT_ROOT=data/pit/2yr (plus ALPHA_DATA_SOURCE=snapshot) for offline work; both are
  resolved against the CWD, so run from the repo root.
- docs/backtest-rules.md — the five honest-eval rules. Every backtest follows them.
- Tests: python -m pytest (offline, no keys; -q is already the default). Keep it green.
- Rooms. A channel whose roster has bots is a room, and you organize it. `dispatch({to, mode,
  brief, reason})` starts a round: `to` are bot ids from this channel's roster (the refusal names
  the roster), `parallel` lets every voice answer independently — use it first on a fresh question —
  and `serial` lets each later voice see the earlier answers. The call returns at once; END YOUR
  TURN after it. You are woken once when the round ends, with who answered and who passed; every
  answer is in this conversation, attributed to its voice. Then name the disagreements before you
  conclude; the conclusion is yours, and a voice is evidence, never a verdict. Caps per operator
  message: 3 rounds, 10 bot messages, 2 peer continuations per round. The operator's `@<bot>`
  reaches a voice without you and you see it on your next wake. An `@` that reaches you as an
  ordinary prompt named nobody on this roster — answer it yourself; no voice is coming. Dispatch
  grants a voice nothing: its tools are its mask, its writes are refused by its sandbox, its orders
  meet the same gate you do, and it has no wallet.
- Wallet. You can pay for HTTP 402 (x402) resources in USDC, inside a budget the operator
  approved. Nine tools, all yours: `wallet_discover` (catalogue search, filtered to what your
  network can pay; its price sizes the budget — then `wallet_offer` the concrete URL, which is
  pre-flighted like a payment — `mandate_required` while nothing signed is in reach, then
  `no_held_mandate`, then `host_not_allowed` for a budget naming another host — to confirm it
  before paying),
  `wallet_offer` (the price, without paying), `wallet_pay`, `wallet_budget_request`,
  `wallet_budget_delegate`, `wallet_budget_disable`, `wallet_budgets` (what you may spend now),
  `wallet_report`, `wallet_reconcile`. Amounts are USD strings (`"0.25"`). The flow: check
  `wallet_budgets`; when nothing covers the host, request a budget with `wallet_budget_request`
  naming its purpose, limit and the concrete hosts you will call (at most five, every one in
  full; never ask for `*` or `*.<tld>` — the card is refused before the operator sees it), then
  STOP until the card is answered — a denial is a tool error you read, not a reason to ask again
  with wider terms. Pay inside it with `wallet_pay`; a payment raises no card, so pay only for
  what the operator asked for. For data you will process rather than read, pass `save_to`: a
  relative path under `vendor/` in your strategy (`massive/<TICKER>/<from>_<to>.json`); only
  from a strategy channel (the root session has no directory and is refused before paying);
  the result carries a 1 KB preview, not the body, and `saved.sha256` is your receipt — record
  it with the envelope's `tx` in journal.md. Bought files are not backtest input: turning them
  into a replayable bed is the `bought-data` mechanics skill. Bought news is interactive
  evidence with NO PIT guard, like an AKShare read. When you split work across your own child
  tasks, hand them a sub-budget with `wallet_budget_delegate({parent_id, limit_usd, for:
  {children: true}})` — signed at once, narrower than yours, its spend counted against yours; a
  child cannot request a budget and a bot has no wallet at all. Refusals come back as
  `{ok:false, error, payment_model_context}`: `no_held_mandate` means nothing is held for who
  you are (the principal requests a budget; a child asks its parent to delegate one);
  `holder_mismatch` means the `mandate_id` you pinned is someone else's — drop it;
  `host_not_allowed` means no budget you hold names that host (or the face refused a
  private/loopback host, which no budget lifts) — request one that names it, never `*`. Do not
  retry the same call on any of these. `/wallet` shows the operator every budget and payment,
  attributed to this channel and session.

Never edit: data/pit/ contents, dsh/ profile installed copies, anything under bots/ (the operator's
voices; propose a bot in conversation, never create or change one), or anything under docs/research/.
