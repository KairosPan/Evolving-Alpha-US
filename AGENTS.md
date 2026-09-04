# AGENTS.md — Evolving-Alpha-US workspace

Three layers: MARKET + ACCOUNT live in the alpaca_kit package; STRATEGY (you) works in
strategies/.

- alpaca_kit/ — data + account library AND the MCP server you already have tools from.
  For backtests, import it directly (alpaca_kit.replay.replay_days); MCP tools are for
  interactive queries only. Prices are RAW/unadjusted. The PIT guard is the caller's job:
  replay_days and the MCP tools wrap it for you, a bare make_source() does NOT — it returns
  a RAW source by contract. Never read one directly in a backtest; go through replay_days,
  or wrap it yourself in GuardedSource with an AsOfGuard for the day.
- strategies/<name>/ — one directory per strategy: THESIS.md, screen.py, backtest.py,
  backtests/, journal.md, status.yaml. Lifecycle, declared in status.yaml:
  idea | researching | validated | paper | retired — paper is a reserved forward-testing
  state, meaningful only once the order gate opens. status.yaml also carries three optional
  headline keys the face's channel landing page renders when present: one_line (the current
  conclusion, one sentence), next (the next step), numbers (free key-value figures) — none
  required; fill them in when there is something worth a line. Copy strategies/_template to start one.
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

Never edit: data/pit/ contents, dsh/ profile installed copies, or anything under docs/research/.
