# Spyhop — Multi-Thesis Polymarket Signal Platform

> A spyhop is when a whale pokes its head above the waterline to observe its surroundings.
> This tool watches whale traders surface in prediction markets — and decides which ones are worth following.

## Project Overview

Spyhop is a local-first Python CLI that monitors Polymarket for whale trading activity and evaluates it through multiple **investment theses**. Each thesis represents a different theory about why a large trade might be profitable to follow. The system uses only public APIs and on-chain data — blockchain forensics, not private data access.

Not all whale trades are informative. Some are insider-driven, some reflect sharp sports analysis, some are pure noise (market-making settlement, crypto micro-markets, reward farming). Spyhop's job is to classify them, score the promising ones, and paper-trade the best signals — each thesis independently, with its own detectors, thresholds, and capital pool.

## Investment Theses

Spyhop runs three thesis classifications in parallel on every whale trade:

### Insider (categories: everything except Sports and Crypto)

**Core idea:** Fresh wallets making outsized bets on obscure markets may have non-public information about the outcome.

A classic insider pattern: a brand-new Polymarket wallet places $25K on a niche political market with $15K daily volume, days before a surprise announcement. The detectors look for the combination of wallet freshness (no prior Polymarket history), trade size relative to market volume, and market obscurity.

**Detectors:**
| Detector | Signal | Multiplier Range |
|----------|--------|-----------------|
| `FreshWalletDetector` | Few or zero prior trades on Polymarket | 1.0–3.0x |
| `SizeAnomalyDetector` | Trade outsized relative to market's 24h volume | 1.0–3.0x |
| `NicheMarketDetector` | Low daily volume market (linear: smaller = more suspicious) | 1.0–2.5x |

**Scoring:** Alert threshold 7.0, critical 9.0. Max composite = 10.0.

**Empirical performance (31K trades, 2026-03-06 to 2026-03-21):** The 7.0–7.9 band is the only one with positive average returns (+1.1%). Scores 9-10 have 15% win rates because they correlate with near-certainty bets ($0.89 avg entry), not informative prices. See `scripts/backfill_resolutions.py` output and the V5 recalibration plan below.

### Sporty Investor (categories: Sports only)

**Core idea:** Experienced Polymarket bettors placing pre-game contrarian bets on moderately-thin sports markets may have an analytical edge over the market line.

The insider detectors are exactly wrong for sports: fresh wallets placing big bets on sports are usually recreational gamblers, not insiders (match-fixing aside). The profitable sports signals come from the opposite profile — wallets with 6-25 prior trades, betting at underdog prices ($0.35–$0.50) on mid-volume markets ($10K–$25K daily) before the game starts.

**Detectors:**
| Detector | Signal | Multiplier Range |
|----------|--------|-----------------|
| `TimingGateDetector` | Pre-game vs. during/after game | 1.0 (pass) or 0.0 (kill) |
| `EntryPriceDetector` | Contrarian sweet spot pricing ($0.35–$0.50) | 0.5–2.0x |
| `NicheNonlinearDetector` | Volume sweet spot — not too thin, not too efficient | 1.0–2.0x |
| `WalletExperienceDetector` | Experienced but not algorithmic (6-25 trades) | 1.0–1.8x |

**Scoring:** Alert threshold 5.0, critical 8.0. Max composite = 10.0. The lower threshold reflects that sports signals are more frequent but individually weaker than insider signals.

**Key design choice:** The timing gate is a binary kill switch, not a signal amplifier. Its `max_multiplier = 1.0` means it's excluded from the normalizer calculation — it can only block (0.0, zeroing the entire composite via multiplication), never boost. During-game and post-game trades are a fundamentally different thesis (live hedging, score-chasing) and should not score here.

**Empirical basis:** Analysis of 11K+ sports signals in `scripts/sports_thesis_validation.py` and prior analyses in `scripts/sports_hypothesis.py`, `scripts/sports_analysis.py`, `scripts/sports_timing.py`. The $0.35–$0.50 sweet spot and 6-25 trade experience band emerged from this data.

### Crypto (BLOCKED)

**Core idea:** There is no edge.

Empirical analysis (V4b Q5) showed that 91% of crypto signals on Polymarket are 5-minute binary micro-markets ("BTC Up or Down in next 5 min") at $0.99 average entry price. These are pure coin flips with no insider information possible on the timeframe. Crypto is excluded at the category level — trades are still ingested and stored (for future analysis), but never scored or paper-traded by either thesis.

## Architecture

```
RTDS WebSocket (firehose: ~2,000 trades/day above $10K)
  │
  ▼
INGESTOR ──► STORAGE (SQLite: trades table — always, all categories)
  │
  ▼
PROFILER (shared enrichment, thesis-agnostic)
  ├─ WalletCache   (Data API → trade count, history)
  ├─ MarketCache   (Gamma API → volume, prices, end_date)
  └─ EventCache    (Gamma API → event category tags)
  │
  ▼
ROUTER (category-based, mutually exclusive)
  │
  ├─ Sports ──► SPORTY INVESTOR PIPELINE
  │               ├─ Scorer (timing_gate × entry_price × niche_nonlinear × wallet_experience)
  │               ├─ Signal stored (detector_results as JSON)
  │               └─ PaperTrader ($5M pool, min_score 5.0, MM filter)
  │
  ├─ Crypto ──► BLOCKED (stored in trades table, never scored)
  │
  └─ All else ──► INSIDER PIPELINE
                    ├─ Scorer (fresh_wallet × size_anomaly × niche_market)
                    ├─ Signal stored (legacy F/S/N columns)
                    └─ PaperTrader ($5M pool, min_score 7.0, MM filter)
  │
  ▼
CLI (Rich live table: Time, Wallet, Wlt, Cat, Th, F, S, N, Score, Side, Amount, Price, Market)
```

**Key architectural properties:**
- **Fork, not diamond:** The pipeline splits at routing and never merges. Each thesis has fully independent scoring, signals, capital, and positions.
- **Enrich once, score cheaply:** Wallet/market/event lookups (HTTP calls) happen once per trade, shared across theses. Scoring is pure math — no I/O.
- **Record everything, filter late:** Trades table captures all $10K+ activity (thesis-agnostic). Signals table captures all scored trades (pre-MM-filter). Positions table captures only what passed all gates. Each layer enables retroactive analysis without re-running the live pipeline.

## Market-Maker Filter

Both theses share a three-check execution filter that blocks CLOB settlement noise from becoming paper positions. The MM filter runs **after** scoring, inside `PaperTrader.maybe_trade()` — it gates paper execution, not signal recording.

**Why this matters:** In V4b analysis, 5 of 9 paper positions (55.6%) were CLOB settlement artifacts — both counterparties of a matched fill cleared the $10K threshold and scored high enough to trade. See `research/V4B_FARM_DETECTION.md` for the full investigation (§1–§10 original findings, §12 tx_hash investigation, §13 three-check design).

### The Three Checks

**Check 1 — Matched-pair detection** (7s delay + 14s window)
Before executing a paper trade, sleep 7 seconds for settlement counterparts to arrive in the DB, then query for any directionally opposite trade on the same `condition_id` within ±14 seconds. Catches CLOB settlement pairs where both sides of a fill clear the display threshold.

**Check 2 — Same-wallet lookback** (2h window)
Query for any trade from the same wallet on the same `condition_id` with the opposite `effective_outcome` within the last 2 hours. Catches burst market-makers, reward farmers doing round-trips, and position reversals that aren't directional signals.

**Check 3 — Portfolio anti-hedge** (in RiskEngine)
Before opening a position, check if the paper trader already holds any position on the same `condition_id`. Prevents the portfolio from holding both sides of a market (guaranteed loss from spread).

### effective_outcome

In a binary market, `BUY outcome_index=0` and `SELL outcome_index=1` are the same directional bet. The effective outcome normalizes this:
```
effective = outcome_index if side == 'BUY' else 1 - outcome_index
```
Two trades are "opposite" if their effective outcomes differ.

### Config

Each thesis has its own MM filter config under `[thesis.*.detector.mm_filter]`:
```toml
[thesis.insider.detector.mm_filter]
enabled = true
settle_delay_seconds = 7
pair_max_gap_seconds = 14
wallet_lookback_minutes = 120
```

## Scoring Model

Both theses use the same `Scorer` class — a multiplicative composite model mapped to a 0–10 scale. Different detectors are plugged in per thesis.

```
product = detector1.multiplier × detector2.multiplier × ... × detectorN.multiplier
composite = log10(product) × normalizer    (clamped 0–10)
normalizer = 10.0 / log10(max_product)
```

- If `product ≤ 1.0` → composite = 0.0 (no signal worth recording)
- If any detector returns 0.0 → product = 0 → composite = 0 (multiplicative kill switch)
- Signals **compound** — fresh + large + niche is exponentially more suspicious than any single signal

| Thesis | Detectors | Max Product | Normalizer | Alert | Critical |
|--------|-----------|------------|------------|-------|----------|
| Insider | fresh(3.0) × size(3.0) × niche(2.5) | 22.5 | 7.40 | ≥ 7.0 | ≥ 9.0 |
| Sporty Investor | entry(2.0) × niche(2.0) × wallet(1.8) | 7.2 | 11.66 | ≥ 5.0 | ≥ 8.0 |

Note: The sporty investor's timing gate has `max_multiplier = 1.0` and is excluded from the normalizer — it's a gate, not an amplifier.

## Paper Trading

Each thesis runs an independent `PaperTrader` with its own capital pool, exposure limits, and position tracking. Positions are tagged with their thesis name in the DB, enabling per-thesis P&L analysis.

**Execution pipeline inside `maybe_trade()`:**
```
score ≥ min_score?  → no: reject
signal exists?      → no: reject
blocked category?   → yes: reject (Crypto)
MM filter           → Check 2 (wallet lookback) → Check 1 (matched pair)
resolution ≤ 30d?   → no: reject (too far out)
SELL → BUY normalization
RiskEngine          → duplicate? max concurrent? exposure limit? anti-hedge?
PaperExecutor       → position created, stored with thesis tag
```

**Position sizing:** `size = base_position_usd × (score / alert_threshold)`, clamped to `max_position_pct × capital`.

### Current Paper Config

| Parameter | Insider | Sporty Investor |
|-----------|---------|-----------------|
| Capital pool | $5,000,000 | $5,000,000 |
| Base position | $5,000 | $3,000 |
| Min score | 7.0 | 5.0 |
| Max position % | 10% | 5% |
| Max exposure % | 50% | 40% |
| Max concurrent | 100 | 100 |
| Max days to resolution | 30 | 30 |
| MM filter | enabled | enabled |

## Config Structure

Config uses a nested `[thesis.*]` structure. Shared infrastructure sections sit at the top level; each thesis has its own `detector`, `scorer`, and `paper` sub-sections.

```toml
# Shared infrastructure
[ingestor]
usd_threshold = 10_000
[market_cache]
[profiler]
[event_cache]
[display]

# Per-thesis config
[thesis.insider]
enabled = true
categories = []                          # empty = all non-excluded
exclude_categories = ["Crypto", "Sports"]
[thesis.insider.detector.fresh_wallet]
[thesis.insider.detector.size_anomaly]
[thesis.insider.detector.niche_market]
[thesis.insider.detector.mm_filter]
[thesis.insider.scorer]
[thesis.insider.paper]

[thesis.sporty_investor]
enabled = true
categories = ["Sports"]
exclude_categories = []
[thesis.sporty_investor.detector.timing_gate]
[thesis.sporty_investor.detector.entry_price]
[thesis.sporty_investor.detector.niche_nonlinear]
[thesis.sporty_investor.detector.wallet_experience]
[thesis.sporty_investor.detector.mm_filter]
[thesis.sporty_investor.scorer]
[thesis.sporty_investor.paper]
```

**Backward compatibility:** `_migrate_config()` in `config.py` handles bidirectional migration. Old flat configs (`[detector]`, `[scorer]`, `[paper]`) are auto-wrapped into `[thesis.insider.*]`. New thesis configs auto-populate flat keys from `thesis.insider` for backward compat. See `CONFIG_REFERENCE.md` for every parameter.

## Tech Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | `tomllib` in stdlib |
| HTTP | `httpx` | Async-capable |
| WebSocket | `websockets` | Lightweight |
| CLI output | `rich` | Tables, live displays, spinners |
| Persistence | `sqlite3` | stdlib, zero external deps |
| Config | TOML | Python-native in 3.11+ |
| Linter | `ruff` | Configured in `pyproject.toml` |

### Dependencies
```
httpx
websockets
rich
py-clob-client
```

## Polymarket API Reference

### Three REST APIs (all unauthenticated for read-only)

**Gamma API** — Market discovery & metadata
- Base: `https://gamma-api.polymarket.com`
- `GET /markets` — paginated market list (limit/offset)
- `GET /markets/{id}` — single market details
- `GET /events` — paginated event list
- `GET /events/{id}` — single event
- Returns: question, slug, description, condition_id, clob_token_ids, volume, open_interest, outcome_prices, endDateIso
- Rate limit: ~60 req/min

**CLOB API** — Order books & pricing
- Base: `https://clob.polymarket.com`
- `GET /book`, `/prices`, `/midpoints`, `/spreads`, `/last-trade-price`
- `py-clob-client` Level 0 wraps these (no auth needed)
- Rate limit: ~60 req/min

**Data API** — Per-wallet trade history & profiles
- Base: `https://data-api.polymarket.com`
- `GET /activity?wallet=<addr>` — wallet trade history (key endpoint for profiling)
- Returns: proxyWallet, usdcSize, timestamp, conditionId, side, price, transactionHash
- Rate limit: ~60 req/min, 100 results/page

### RTDS WebSocket — Global Trade Firehose

The primary data source for live detection.

- URL: `wss://ws-live-data.polymarket.com`
- Subscribe: `{"action": "subscribe", "subscriptions": [{"topic": "activity", "type": "*"}]}`

**Protocol gotchas (hard-won):**
- `type: "trades"` receives NOTHING. Must use `"*"` wildcard. Actual type is `orders_matched`.
- `filters` must be omitted or empty string `""`. Empty object `{}` causes 400.
- Requires application-level `PING` text frame every 5s (not WS-level ping).
- `size` field is token qty, NOT USDC. Calculate: `usdc_size = size * price`.
- Known bug: data freezes after ~20 min. Silence watchdog (5-min timeout) forces reconnect.
- Cloudflare-fronted (CF-RAY: SEA datacenter).

### CLOB WebSocket — Per-market price events
- URL: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Per-market subscription by `assets_ids`. Events: `book`, `price_change`, `last_trade_price`.

### Goldsky Subgraphs (future — historical backfill)
- GraphQL subgraphs for Activity, Positions, Orders, Open Interest, PnL
- Free tier: 100K queries/month via The Graph Network
- Best for: deep wallet archaeology, historical P&L

## Critical Implementation Notes

### Proxy Wallet Gotcha
Polymarket uses **proxy wallet addresses** for on-chain settlement, NOT users' EOA wallets. A "fresh proxy" might belong to an experienced crypto user. Check trade count *on Polymarket* via the Data API, not raw Polygon transaction count.

### Timezone-Aware Datetime Handling
All datetime comparisons **must** use timezone-aware objects. External APIs return a mix:
- **RTDS WebSocket**: ISO 8601 with offset (`2026-03-20T20:24:04+00:00`) — aware
- **Gamma API `endDateIso`**: Bare date strings (`2026-06-30`) — **naive**
- **Internal timestamps**: Always `datetime.now(timezone.utc)`

**Rule:** After every `datetime.fromisoformat()` call, immediately normalize:
```python
dt = datetime.fromisoformat(raw_string)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```

**Bug history:** The resolution proximity gate was silently inert for a week (2026-03-14 to 2026-03-21) because Gamma's naive `end_date` strings hit a `TypeError` in a broad `except` handler. Three positions entered at 39, 100, and 284 days out. Fixed by normalizing to UTC before subtraction.

### CLOB Batch Settlement
A single `tx_hash` contains fills from multiple independent wallets (makers + taker). Different wallets in the same TX are NOT the same operator. This is why the MM filter checks `condition_id` + `effective_outcome` + timing, not `tx_hash`.

### Resilience Patterns
- **Silence watchdog must be a separate asyncio task** — checking inside `async for msg in ws:` is dead code during actual silence.
- **Callbacks in reconnect loops need error boundaries** — unhandled exception in `on_trade` kills the reconnect loop, not just the current connection.
- **Belt-and-suspenders error boundaries**: inner (`handle_trade`) + outer (`stream_trades`) for unattended systems.

## Roadmap

### Completed

| Version | What | When |
|---------|------|------|
| V1 | RTDS ingestor → USD filter → SQLite → Rich live table | 2026-03 |
| V2 | Wallet profiling (Data API + WalletCache) | 2026-03 |
| V3 | 3 insider detectors + multiplicative composite scorer | 2026-03 |
| V4 | Paper trading (RiskEngine + PaperExecutor + PaperTrader) | 2026-03 |
| V4b | Signal quality improvements + three-check MM filter | 2026-03-21 |
| Multi-thesis | Dual insider/sporty_investor pipelines, config migration, 4 sports detectors | 2026-03-21 |

### V5 — P&L Tracking & Scoring Recalibration (CURRENT PRIORITY)

The composite scorer correctly identifies *unusual* trades but doesn't reliably identify *profitable* ones. Scores 9-10 correlate with near-certainty bets (15% win rate, negative EV), not informative insider prices. Recalibration requires resolved-outcome data we don't yet have at scale.

**Phase A — Infrastructure (build now):**
- [ ] **A1: Resolution poller** — periodic task polls Gamma API for resolved markets, closes paper positions, computes P&L
- [ ] **A2: P&L analytics** — `spyhop report` CLI command (win rate by score band, category, entry price range)
- [ ] **A3: Entry price distribution logging** — query views over trades + signals
- [ ] **A4: Backfill historical resolutions** — one-time script for existing 208 alert-signal markets

**Phase B — Recalibrate (needs ~100+ resolved signals):**
- [ ] **B1: Entry price modifier** — dampen insider score on near-certainty entries ($0.85+)
- [ ] **B2: Category-weighted scoring** — Politics has 100% resolved win rate; adjust multipliers
- [ ] **B3: Kelly integration** — replace linear sizing with empirical score-to-correctness curve
- [ ] **B4: Threshold analysis** — determine optimal alert thresholds from EV data

**Phase C — Advanced (needs months of data):**
- [ ] Per-category exposure limits, loss circuit breakers
- [ ] Win-rate-based wallet tagging ("follow the sharp" signals)
- [ ] Strategy classification: INSIDER vs INFORMED vs FARM
- [ ] Resolution proximity score modifier (SPECULATIVE/EARLY/HOT/IMMINENT bands)

### Future

- [ ] DBSCAN temporal clustering (coordinated wallet timing)
- [ ] Funding chain tracing (Polygon RPC: where did wallet funds come from?)
- [ ] Textual TUI with live updating tables
- [ ] V6: Live trading (CLOB Level 2, authenticated)
- [ ] Discord / Telegram / Slack webhook alerts

## Research & Analysis

### Research Documents
| Document | Topic |
|----------|-------|
| `research/SYNTHESIS.md` | Original detection thesis synthesis (scoring model design) |
| `research/V4B_FARM_DETECTION.md` | MM filter investigation (§1–§13): CLOB settlement, both-side trading, three-check design |
| `research/REWARD_FARMING.md` | $POLY airdrop farming patterns |
| `research/TRADING_STRATEGIES.md` | Strategy classification (FARM/INSIDER/INFORMED) |
| `research/RQ1_LANDSCAPE.md` — `RQ4_COUNTER_TRADING.md` | Original research questions |
| `research/ADDENDUM_KELLY_CRITERION.md` | Kelly criterion for position sizing |
| `research/API_LANDSCAPE.md` | Polymarket API documentation |
| `CONFIG_REFERENCE.md` | Every config.toml parameter with tuning guidance |

### Analysis Scripts
| Script | Purpose |
|--------|---------|
| `scripts/sports_thesis_validation.py` | Score 11K+ sports trades through proposed sporty_investor detectors |
| `scripts/sports_hypothesis.py` | Original sports hypothesis exploration |
| `scripts/sports_analysis.py` | Sports signal classification and win rates |
| `scripts/sports_timing.py` | Pre-game vs. in-play timing analysis |
| `scripts/backfill_resolutions.py` | One-time backfill of market resolution outcomes |

### Key Empirical Findings

**Insider scoring (31K trades):** Score 7.0–7.9 is the only positive-EV band (+1.1% avg return). Scores 9-10 have 15% win rates — they identify near-certainty bets, not informative prices. Politics has 100% resolved win rate (N=3), Sports 42.9% (N=21).

**Sports signals (11K+ sub-threshold):** Pre-game timing, contrarian entry prices ($0.35–$0.50), and moderately-thin markets ($10K–$25K daily) mark the profitable subset. Post-game and during-game trades are noise.

**CLOB settlement:** 55.6% of early paper positions were settlement artifacts. The three-check MM filter (matched-pair + wallet lookback + anti-hedge) eliminates this class.

**Crypto exclusion:** 91% of crypto signals are 5-min binary micro-markets at $0.99 avg price. No insider edge, no informed-bettor edge, pure noise.

## Project Structure

```
spyhop/
├── CLAUDE.md                    # This file
├── CONFIG_REFERENCE.md          # Full config parameter reference
├── pyproject.toml               # Build config + ruff + pytest
├── config.toml                  # User-configurable thresholds (thesis-structured)
├── research/                    # Research docs and analysis
├── scripts/                     # One-time analysis scripts
├── src/
│   └── spyhop/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry (watch / wallet / history / positions / paper-reset)
│       ├── cli.py               # Rich live display, handle_trade(), thesis routing
│       ├── config.py            # TOML config loader + _migrate_config()
│       ├── ingestor/
│       │   ├── __init__.py
│       │   └── rtds.py          # RTDS WebSocket client
│       ├── profiler/
│       │   ├── __init__.py
│       │   ├── wallet.py        # Wallet profile (Data API)
│       │   ├── market.py        # Market metadata (Gamma API)
│       │   └── event.py         # Event category (Gamma API)
│       ├── detector/
│       │   ├── __init__.py      # build_scorer() + build_sports_scorer() factories
│       │   ├── base.py          # Detector protocol, DetectionContext, ScoreResult
│       │   ├── scorer.py        # Multiplicative composite scoring (thesis-agnostic)
│       │   ├── fresh_wallet.py  # Insider: wallet freshness (0-5 trades)
│       │   ├── size_anomaly.py  # Insider: trade size vs market volume
│       │   ├── niche_market.py  # Insider: low-volume market (linear)
│       │   ├── timing_gate.py   # Sports: pre-game binary gate
│       │   ├── entry_price.py   # Sports: contrarian price sweet spot
│       │   ├── niche_nonlinear.py # Sports: volume sweet spot (non-linear)
│       │   └── wallet_experience.py # Sports: experienced wallet (inverse of fresh)
│       ├── paper/
│       │   ├── __init__.py
│       │   ├── trader.py        # PaperTrader orchestrator (thesis-scoped)
│       │   ├── risk.py          # RiskEngine (thesis-scoped capital + exposure)
│       │   └── executor.py      # PaperExecutor (DB writes)
│       └── storage/
│           ├── __init__.py
│           └── db.py            # SQLite schema, migrations, thesis-scoped queries
└── tests/
    └── test_paper_trading.py    # 38 tests (DB helpers, MM filter, risk, paper trader)
```

## Coding Conventions

- `httpx` for all HTTP requests (async-capable)
- `asyncio` for WebSocket + concurrent profiling
- Type hints on all public functions
- Config-driven thresholds (no magic numbers in detection logic)
- SQLite via stdlib `sqlite3` (no ORM)
- `rich` for all terminal output
- `ruff` for linting (configured in `pyproject.toml`, line-length 100)

## Operational Notes

### CLI Commands
```
spyhop watch                        # Live stream with scoring + paper trading
spyhop history --min-score 7        # Show scored signals
spyhop history --thesis sporty_investor  # Filter by thesis
spyhop wallet <addr>                # Deep wallet lookup
spyhop positions --refresh          # Open paper positions (with live prices)
spyhop paper-reset --confirm        # Reset paper trading portfolio
```

### Config Loading
- Search order: explicit `--config` path → `./config.toml` → project root → user config dir → built-in defaults
- `config.py` logs at INFO which file was loaded, WARNING if falling through to defaults
- Silent fallback to defaults is the most common cause of "paper trading won't enable" — `paper.enabled` defaults to `False`

### Database
- Path: `C:/Users/thoma/AppData/Local/spyhop/spyhop.db`
- Schema auto-migrates via `_migrate()` on startup (ALTER TABLE with DEFAULT for new columns)
- Key tables: `trades`, `markets`, `wallets`, `events`, `signals` (with `thesis` column), `paper_positions` (with `thesis` column)
- No `sqlite3` CLI available on this machine — use Python's `sqlite3` module or the spyhop CLI

### Windows Environment
- Shell is PowerShell — give PowerShell-compatible commands
- When running inline Python via bash, use heredoc (`python3 << 'PYEOF'`) to avoid quoting conflicts
- Scripts use `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` for Unicode table output
