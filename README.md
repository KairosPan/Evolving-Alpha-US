# Sonia-Kairos-US-Stock

*Formerly **Evolving-Alpha-US** — renamed 2026-07-09 to align with the sibling Sonia-Kairos design
charter. **Sonia** teaches; **Kairos** acts.*

A **self-evolving US speculative-momentum decision-support co-pilot**, adapted from the
[Evolving-Alpha](https://github.com/KairosPan/Evolving-Alpha) A-share system. Two named agents:
**Sonia**, the teacher/meta-agent that owns the live brain and applies only user-accepted edits
through the gate, and **Kairos**, the conversational worker face with a tiered tool surface.

Built on the Continual Harness `H=(p,G,K,M)` two-loop architecture (paper
[2605.09998](https://arxiv.org/abs/2605.09998), Princeton/ARISE/DeepMind). The harness edits its
own playbook each day via meta-tool CRUD — the only sustainable response to alpha decay and
market reflexivity.

> **Disclaimer:** This is a research and decision-support tool only. It is **not financial
> advice**. It does not submit live orders at any phase. All `DecisionPackage` outputs require
> explicit human confirmation. Past simulated performance does not imply future results.
> Speculative momentum trading carries substantial risk of loss.

---

## Status

**All four build phases (US-0 … US-3) are complete**, plus the arcs that followed them: the
PIT data layer and firewall, harness + eval + sizing + guard, the LLM agent + inner loop, the
web console, the Sonia teaching service, the Kairos conversational face + arena tool surface,
PIT episodic memory, and the HCH-vs-Hexpert verdict harness. ~919 fully-offline tests.
The single live backlog is the repo-root [ROADMAP.md](ROADMAP.md); the what's-built log is
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

---

## What It Does

The system is a **co-pilot** for US speculative-momentum trading. Each day at close it:

1. Screens the market universe for gainers, gap-ups, multi-day runners, and high relative-volume
   candidates using strict point-in-time (PIT) data — no future leakage.
2. Computes a `MarketState` capturing regime (Washout/Recovery/Heating/Trend/Distribution/
   Exhaustion), gainer breadth, runner echelon (consecutive-up-days tiers), and failed-breakout rate.
3. Runs the LLM agent to produce a `DecisionPackage`: ranked candidates, per-candidate
   size tier, fill-feasibility check, guard/veto checks, and rationale.
4. Presents the `DecisionPackage` to a human for confirmation. The human's
   confirm/reject/modify response doubles as a DAgger expert label for future training.
5. The Refiner reads the day's trajectory, identifies failure signatures, and
   edits the harness (`p/G/K/M`) via meta-tool CRUD — self-evolving the playbook daily.

**No automatic orders at any phase.** The co-pilot is a research and decision-support tool.

---

## Architecture

See [docs/blueprint.md](docs/blueprint.md) for the full authoritative architecture reference.

Brief overview:

```
data (L0) → features → regime (G_cycle, read-only) → universe →
agent (L2, master-dispatch + G sub-agents) →
sizing (L3: position/correlation/portfolio) →
guard (L4: stops/veto/circuit-breaker) →
DecisionPackage → human confirmation
```

The `H=(p,G,K,M)` harness wraps this pipeline. The Refiner edits `H` daily (inner loop). The outer
loop (LoRA / θ update) is deferred to US-2+.

---

## Quickstart

### Prerequisites

- Python ≥ 3.11
- `pytest`, `pandas`, `pydantic`, `pyarrow` available in the active interpreter
- (Optional, for live data) Alpaca account with `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`

### Install

```bash
git clone https://github.com/KairosPan/Evolving-Alpha-US.git
cd Evolving-Alpha-US

# Install in editable mode (no venv required if deps already present)
pip install -e ".[dev]"

# Install with live-data extras (alpaca-py + pandas-market-calendars)
pip install -e ".[dev,live]"
```

### Run Tests

```bash
# Full test suite (all offline, no network needed)
python -m pytest -q

# Four firewall-surface acceptance tests only
python -m pytest \
  tests/data/test_source.py::test_guarded_source_blocks_future_snapshot \
  tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit \
  tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted \
  tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -v
```

Expected output: all tests pass.

---

## Web Console (`alpha_web`)

A local, read-only **"Regime Instrument"** dashboard onto the co-pilot's evolving mind and its
outputs. It renders the real seeds (doctrine / memory / skills), a day's `DecisionPackage`, and the
HCH-vs-Hexpert verdict. Decision-support only — it shows, it never trades.

```bash
pip install -e ".[web]"     # fastapi + uvicorn + jinja2 (offline; no build step)
python -m alpha_web         # serves http://127.0.0.1:8100  (ALPHA_WEB_HOST / ALPHA_WEB_PORT to override)
```

The **Deck** opens on the six-phase regime cycle (the signature phase ring) and live brain counts;
**Doctrine / Memory / Skills** browse the seeds with in-place filters; **Decisions / Verdict /
Evolution** render real artifacts when wired, else a clearly-badged SAMPLE built from the real models.

Produce real artifacts from a captured PIT window, then point the console at them:

```bash
python scripts/capture_window.py 2026-01-02 2026-01-31 snap AAPL MSFT NVDA TSLA AMD   # market data only

python scripts/save_decisions.py snap 2026-01-02 2026-01-31 decisions   # a DecisionPackage per day
python scripts/run_verdict.py    snap 2026-01-02 2026-01-31 --json verdict.json   # the HCH-vs-Hexpert verdict
python scripts/save_evolution.py snap 2026-01-02 2026-01-31 evolution.json   # the Refiner's edit trajectory

ALPHA_WEB_DECISIONS_DIR=decisions \
ALPHA_WEB_VERDICTS_DIR=verdicts \
ALPHA_WEB_EVOLUTION=evolution.json \
  python -m alpha_web
```

`save_decisions` / `save_evolution` / `run_verdict` need the agent (and, for the verdict/evolution,
refiner) LLM keys; see `scripts/run_verdict.py`. The Decisions and Verdict pages get a picker to browse
by date / run; a single-file `ALPHA_WEB_DECISION` / `ALPHA_WEB_VERDICT` overrides its directory.

---

## Sonia teaching cockpit (two processes)

The **Sonia meta-agent** is a standalone FastAPI service (port 8810) that owns the live brain and
all gated apply/rollback operations. The **web console** (`alpha_web`, port 8100) acts as a thin
chat client: it calls Sonia over HTTP and reads the brain read-only.

```bash
pip install -e '.[web,sonia]'

# terminal 1 — the meta-agent (needs DEEPSEEK_API_KEY, or ALPHA_SONIA_PROVIDER=mock for offline):
DEEPSEEK_API_KEY=... python -m sonia                       # :8810

# terminal 2 — the console (chat cockpit at /):
ALPHA_SONIA_URL=http://127.0.0.1:8810 python -m alpha_web  # :8100
```

Sonia (`deepseek-v4-pro` by default, text-only) owns the live brain and the gated apply/rollback;
the console is a thin chat client that calls Sonia over HTTP and reads the brain read-only.

**Mock / offline mode** (no LLM key required):

```bash
ALPHA_SONIA_PROVIDER=mock \
  ALPHA_MOCK_RESPONSE='{"ops":[{"action":"update_skill","name":"test","content":"hello"}]}' \
  python -m sonia &

ALPHA_SONIA_URL=http://127.0.0.1:8810 python -m alpha_web
```

Type a message → an assistant bubble with an edit card appears → click **Accept** → the brain
badge `edit_count` increments → click **Rollback** → it decrements.

**Manual real-key smoke** (requires `DEEPSEEK_API_KEY` and external paid calls — not run in CI):
send one real teaching message and confirm a coherent prose reply.

---

## Kairos workbench (conversational face)

**Kairos** is the worker: a persisted conversational face over the same brain, with a tiered
computer-use tool surface (`alpha/arena/` — decide/read/write/shell, **no order tool**, every call
through the fail-closed `ActivityPolicy` choke point).

```bash
pip install -e '.[web,sonia]'
ALPHA_CONVERSE_MODEL=deepseek-chat DEEPSEEK_API_KEY=... python -m workbench   # :8820
```

---

## Data Setup (Offline Backtesting)

The system ships with a `FakeSource` for fully offline tests. For real data, use Alpaca:

### 1. Set Environment Variables

```bash
export APCA_API_KEY_ID=your_key_id
export APCA_API_SECRET_KEY=your_secret_key
```

### 2. Smoke-Test the Alpaca Connection

```bash
# Requires [live] extras and Alpaca credentials
python scripts/smoke_alpaca.py AAPL 2026-06-01 2026-06-12
```

### 3. Build an Offline PIT Snapshot Database

```bash
# Captures bars for a symbol set into a local parquet store at ./snap/
python scripts/capture_window.py 2026-06-01 2026-06-12 snap AAPL MSFT NVDA TSLA
```

The `PITStore` at `./snap/` can then be used as an offline `SnapshotSource` for backtesting.
All prices are stored **raw/unadjusted** (PIT-correct for level features).

**Alpaca free-tier caveat:** the free tier uses the IEX feed, which is adequate for OHLCV history
(available to ~2016) but thin for full-market gainer screening. Universe completeness is the
primary free-tier limitation, not history depth. A broader snapshot source is a US-3 enhancement.

---

## Key Design Decisions

- **All English.** Code, comments, and documentation. `reference/cn/` is read-only algorithmic
  reference for the rebuild, not production code.
- **Frozen pydantic models** for all value objects (`StockSnapshot`, `MarketState`, `RunnerRung`).
- **Four firewall surfaces** enforced by regression tests: date-lookahead, corp-action ex-date PIT,
  split-vintage raw-PIT, windowed-rank trailing-only.
- **Gross eval.** All backtested expectancy is gross (no cost/slippage). This is stated, not
  assumed away. A cost model ships in US-3.
- **Delist = terminal loss.** Delistings/halts-to-zero are scored as `return = −1.0`, never
  silently dropped.
- **Human confirmed.** The `DecisionPackage` requires explicit human confirmation at every phase.
  The confirmation doubles as DAgger expert labeling for future outer-loop training.

---

## Documentation

| File | Contents |
|---|---|
| [docs/blueprint.md](docs/blueprint.md) | Architecture blueprint for the perception/eval layers (v1.0, 2026-06-13 — predates the harness/agent build-out, arena, and the three services) |
| [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) | The append-only what's-built log (identity, locked decisions, tech stack, milestones) |
| [ROADMAP.md](ROADMAP.md) | The single live backlog — what's left, prioritized (the historical four-phase plan lives in git history of `docs/ROADMAP.md`) |
| [docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md](docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md) | Full design spec (v1.1, post adversarial self-review) |

---

## License

Research use only. No license file yet — all rights reserved until one is added. No financial
advice. No automatic order execution.
