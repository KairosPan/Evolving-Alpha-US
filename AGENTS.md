# AGENTS.md — Evolving-Alpha-US workspace

Three layers: MARKET + ACCOUNT live in the alpaca_kit package; STRATEGY (you) works in
strategies/.

- alpaca_kit/ — data + account library AND the MCP server you already have tools from.
  For backtests, import it directly (alpaca_kit.replay.replay_days); MCP tools are for
  interactive queries only. RAW prices; PIT guard is mandatory (the lib enforces it).
- strategies/<name>/ — one directory per strategy: THESIS.md, screen.py, backtest.py,
  backtests/, journal.md, status.yaml. Copy strategies/_template to start one. Commit
  your own iterations; git log is the audit trail.
- data/pit/ — offline PIT beds (~800 symbols). Two usable windows, and only these:
  data/pit/2yr = 2024-06-03 .. 2026-07-09 (526 trading days), data/pit/broad =
  2025-11-17 .. 2026-03-27 (90 days). Each bed's trading_calendar() runs back to 2016 but
  has no snapshots there — a date outside the window raises SnapshotMissingError. Set
  ALPHA_PIT_ROOT=data/pit/2yr (plus ALPHA_DATA_SOURCE=snapshot) for offline work.
- docs/backtest-rules.md — the five honest-eval rules. Every backtest follows them.
- Tests: python -m pytest (offline, no keys; -q is already the default). Keep it green.

Never edit: data/pit/ contents, dsh/ profile installed copies, or anything under docs/research/.
