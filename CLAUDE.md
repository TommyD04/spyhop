# Spyhop — Polymarket Whale & Insider Tracker

> A spyhop is when a whale pokes its head above the waterline to observe its surroundings.
> This tool watches whale traders surface in prediction markets.

## Project Overview

Local-first Python CLI that monitors Polymarket for suspicious "whale" trading behavior that could indicate insider information. Uses only public APIs and on-chain data — blockchain forensics, not private data access.

## Architecture

```
CLI (Rich live table + history view)
    ↑
DETECTOR (composite scorer)
    ├─ FreshWalletDetector (< 5 prior trades)
    ├─ SizeAnomalyDetector (outsized vs 24h volume)
    └─ NicheMarketDetector (low-volume market bets)
    ↑
PROFILER (wallet + market + event metadata)
    ├─ WalletCache  (Data API → trade count, freshness)
    ├─ MarketCache  (Gamma API → volume, prices)
    └─ EventCache   (Gamma API → category tags)
    ↑
INGESTOR (RTDS WebSocket)
    ↑
STORAGE (SQLite: trades, markets, wallets, events, signals)
```

Pipeline: `ingestor → profiler → detector → cli`

Each stage has a single responsibility. Detectors are independent and pluggable.

## Tech Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | `tomllib` in stdlib |
| HTTP | `httpx` | Async-capable, used by official Polymarket SDK |
| WebSocket | `websockets` | Lightweight, well-maintained |
| CLI output | `rich` | Tables, live displays, spinners |
| TUI (Phase 2) | `textual` | Full TUI when ready |
| Persistence | `sqlite3` | stdlib, zero external deps |
| Config | TOML | Python-native in 3.11+ |
| Market data | Gamma API direct | No SDK needed for metadata |
| Order books | `py-clob-client` Level 0 | Official SDK, unauthenticated read-only |

### Minimal Dependencies
```
httpx
websockets
rich
py-clob-client
```

Avoid heavy deps (no PostgreSQL, Redis, Docker, web3 unless needed).

## Polymarket API Reference

### Three REST APIs (all unauthenticated for read-only)

**Gamma API** — Market discovery & metadata
- Base: `https://gamma-api.polymarket.com`
- `GET /markets` — paginated market list (limit/offset)
- `GET /markets/{id}` — single market details
- `GET /events` — paginated event list
- `GET /events/{id}` — single event
- Returns: question, slug, description, condition_id, clob_token_ids, volume, open_interest, outcome_prices
- Rate limit: ~60 req/min

**CLOB API** — Order books & pricing
- Base: `https://clob.polymarket.com`
- `GET /book` — order book by token_id
- `GET /prices`, `/midpoints`, `/spreads` — pricing data
- `GET /last-trade-price` — most recent trade per token
- `py-clob-client` Level 0 wraps these (no auth needed)
- Rate limit: ~60 req/min

**Data API** — Per-wallet trade history & profiles
- Base: `https://data-api.polymarket.com`
- `GET /activity?wallet=<addr>` — wallet trade history (the key endpoint for profiling)
- `GET /positions?wallet=<addr>` — current positions
- `GET /trades` — trade history (filterable by user or market)
- `GET /profiles` — public user profiles
- Returns: proxyWallet, usdcSize, timestamp, conditionId, side, price, transactionHash
- Rate limit: ~60 req/min, 100 results/page

### Two WebSocket Systems (no auth for public channels)

**RTDS WebSocket** — Global trade firehose (PRIMARY for live detection)
- URL: `wss://ws-live-data.polymarket.com`
- Subscribe: `{"action": "subscribe", "subscriptions": [{"topic": "activity", "type": "*"}]}`
- **IMPORTANT**: `type: "trades"` receives NO data. Must use `"*"` wildcard. Actual messages arrive as `type: "orders_matched"`.
- **IMPORTANT**: `filters` field must be omitted or empty string `""`. Empty object `{}` causes validation error.
- Requires application-level `PING` text frame every 5s (not WebSocket-level ping). Responds with text `PONG`.
- Known bug: data stream freezes after ~20 min. Implement 5-min silence timeout → reconnect.
- Message envelope: `{"topic": "activity", "type": "orders_matched", "timestamp": <epoch_ms>, "payload": {...}, "connection_id": "..."}`
- Payload fields: `asset`, `conditionId`, `eventSlug`, `slug`, `title`, `outcome`, `outcomeIndex`, `proxyWallet`, `pseudonym`, `name`, `side`, `size` (token qty, NOT USDC), `price`, `transactionHash`, `icon`, `bio`, `profileImage`
- USDC value = `size * price` (size is outcome token quantity)
- `title` field contains human-readable market question (no Gamma API needed for basic display)
- Cloudflare-fronted; no special headers required
- Official client: `@polymarket/real-time-data-client` (TypeScript; we implement our own in Python)

**CLOB WebSocket** — Per-market price events
- URL: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Subscribe with specific `assets_ids` (token IDs)
- Events: `book` (full snapshot), `price_change`, `last_trade_price`
- Useful for monitoring specific markets, not global scanning

### Goldsky Subgraphs (Phase 2 — historical backfill)

Five specialized GraphQL subgraphs hosted on Goldsky:
- **Activity**: `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.4/gn`
- **Positions**: `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/positions-subgraph/0.0.7/gn`
- Also: Orders, Open Interest, PnL subgraphs
- Free tier: 100K queries/month via The Graph Network
- Best for: deep wallet archaeology, historical P&L, position tracking

## Critical Implementation Notes

### Proxy Wallet Gotcha
Polymarket uses **proxy wallet addresses** for on-chain settlement, NOT users' EOA wallets. A "fresh proxy" might belong to an experienced crypto user. Check trade count *on Polymarket* via the Data API, not raw Polygon transaction count.

### Condition ID Mapping
Subgraphs and CLOB return `conditionId` values, not human-readable market names. Always cross-reference with Gamma API to resolve to market questions. Cache this mapping aggressively.

### Pagination Patterns
- Gamma API: offset-based (`limit` + `offset`)
- CLOB API: cursor-based (`next_cursor`, terminal value `"LTE="`)
- Data API: ~100 results/page, requires pagination loops
- The Graph: max 1000 entities per query (`first` + `skip`)

## Detection Signals (Composite Scoring)

Each detector returns a 0-N sub-score. Combined into a 0-10 composite. Signals should **compound**, not just add (fresh + large + niche = exponentially more suspicious).

| Signal | What to Look For | Threshold (configurable) |
|---|---|---|
| Fresh wallet | < N prior Polymarket trades | Default: 5 trades |
| Size anomaly | Trade size vs market daily volume | Default: > 2% of orderbook depth |
| Niche market | Low-volume market targeted | Default: < $50K daily volume |
| Timing cluster (Phase 2) | DBSCAN clustering of coordinated entries | Multiple wallets, short window |
| Win rate anomaly (Phase 2) | Statistically improbable win streaks | Requires historical data |

Alert threshold: score >= 7 out of 10.

## Strategy Detection (Future Workstream)

Beyond raw suspicion scoring, Spyhop needs to **classify** detected trades into strategy types. Each type implies a different investment response.

### Strategy Types

| Label | What It Is | Spyhop Action | Investment Response |
|-------|-----------|---------------|---------------------|
| `FARM` | Reward/airdrop farming | Filter out (noise) | Ignore — no directional signal |
| `INSIDER` | True insider information | High-confidence alert | Aggressive counter-trade: follow the position, size up, tight timeframe |
| `INFORMED` | Edge from public info analysis | Moderate-confidence alert | Moderate counter-trade: follow direction, smaller size, wider timeframe |

### FARM Detection

Scripted buy-sell round-trips to inflate volume for $POLY airdrop qualification.

**Heuristic**: Tag as `FARM` when ALL of:
- Same wallet (proxy address)
- Same market (condition_id)
- Opposite side (BUY ↔ SELL)
- Time delta ≤ 120 seconds

**Extended signals**:
- Wallet cluster detection (multiple wallets with identical trading cadence, e.g. 61s intervals)
- Round-trip P&L ≈ 0 or slightly negative (spread loss only)
- Concentration on sports markets (45% of sports volume is wash trading per Columbia study)
- Near-certainty markets (price > 95¢) with no directional conviction

**See**: `research/REWARD_FARMING.md` for full analysis.

### INSIDER Detection

True non-public information — someone knows the outcome before the market does.

**Distinguishing signals**:
- Fresh wallet + large position + niche market (the current composite scorer)
- **One-directional**: no hedging, no round-trip — conviction trade
- **Timing**: position taken shortly before resolution or major news
- **Market category**: Politics carries higher insider risk than Sports (Sports outcomes are harder to know in advance outside match-fixing). Crypto is excluded — empirical data shows 91% of crypto signals are 5-min binary micro-markets with no insider edge (see V4b Q5).
- **Win rate anomaly**: statistically improbable accuracy across resolved markets (Phase 2, requires Goldsky backfill)
- **Funding chain**: wallet funded shortly before trade, from a mixer or fresh source (Phase 2)

### INFORMED Detection

Edge derived from superior analysis of public information — not illegal, but still profitable to follow.

**Distinguishing signals**:
- **Established wallet** with moderate trade history (NOT fresh — they have a track record)
- **Concentrated position**: large size on a specific outcome, but from a wallet with proven accuracy
- **Category expertise**: wallet history shows specialization (e.g., only trades French politics, or only specific sports leagues). Note: Crypto excluded from paper trading (V4b Q5) — no informed-trader signal in micro-binary markets.
- **Pre-event timing**: position taken hours/days before resolution, not minutes (insiders trade late; informed traders trade early when odds are mispriced)
- **Historical P&L**: positive returns across resolved markets, but not impossibly so (60-70% accuracy vs insider's 90%+)

### Resolution Proximity — Time-to-Resolve as a Signal Modifier

The closer a market is to resolution, the more suspicious a high-scoring trade becomes. Insider information is **perishable** — it only exists when someone already knows the outcome. A fresh wallet betting $15K on "Iran ceasefire by June 30" in March is speculative; the same bet placed 48 hours before an announced deal is a red flag.

**Proposed time bands**:

| Time to Resolution | Label | Score Modifier | Rationale |
|--------------------|-------|----------------|-----------|
| > 30 days | `SPECULATIVE` | Dampen (0.5x) | Too far out for insider knowledge to exist; thesis-driven |
| 7–30 days | `EARLY` | Neutral (1.0x) | Informed trader sweet spot — mispricing + analysis edge |
| 1–7 days | `HOT` | Boost (1.5x) | Insider sweet spot — information exists, not yet public |
| < 24 hours | `IMMINENT` | Boost (2.0x) | Highest insider risk, but also front-running public news |

**Implementation considerations**:
- Requires resolution date from Gamma API (`end_date_iso` or `closed` fields on the event/market)
- Many markets don't have fixed end dates (e.g., "Will X happen by Y?" could resolve early on a YES outcome at any time)
- For open-ended markets, use the stated deadline as the upper bound
- Sports markets have known game times — high-precision resolution dates available
- Political markets often have fixed dates (election day, hearing date) — moderate precision
- Geopolitical/speculative markets ("ceasefire by June 30") — only the deadline is known, actual resolution could be any time before

**Interaction with strategy types**:
- `SPECULATIVE` + fresh wallet = likely just a gambler, not an insider. Dampen score.
- `HOT` + fresh wallet + niche market = the classic insider pattern. Boost score.
- `EARLY` + established wallet + category expertise = textbook `INFORMED`. Don't dampen — this is the signal you want to follow with moderate sizing.
- `IMMINENT` + any wallet = could be insider OR someone reading breaking news faster. Requires cross-referencing with news timestamps to disambiguate.

### Classification Priority

1. **FARM filter first** — suppress the noise (highest volume of false positives today)
2. **Resolution proximity second** — dampen speculative long-dated bets, boost trades near resolution (requires market end-date data)
3. **INSIDER vs INFORMED separation third** — requires wallet history depth (Goldsky backfill) and win-rate tracking (resolution poller)
4. **Category weighting fourth** — Crypto excluded entirely (V4b Q5); future: score multipliers by remaining event categories (Politics insider risk > Sports)

## Phasing

### Phase 1 — MVP (complete)
- [x] V1: RTDS WebSocket connection + trade streaming
- [x] V1: USD threshold filter, default $10K
- [x] V1: Market metadata cache via Gamma API
- [x] V1: Rich CLI `spyhop watch` live table
- [x] V1: SQLite persistence (trades + markets)
- [x] V1: TOML config file with layered defaults
- [x] V2: Wallet profiling via Data API (trade count, history, freshness)
- [x] V2: `spyhop wallet <addr>` deep lookup command
- [x] V3: 3 detectors (fresh wallet, size anomaly, niche market)
- [x] V3: Multiplicative composite scorer (0–10 scale)
- [x] V3: Signals table + `spyhop history` command
- [x] V3: F/S/N multiplier columns + Score column in watch table
- [x] Event category tracking via Gamma `/events` API (EventCache)
- [x] Cat column in dashboard (Politics, Sports, Crypto, Economy)
- [x] Outcome display in market column (e.g. "O/U 6.5 → Under")

### V4b — Market-Maker (MM) Filter (CURRENT PRIORITY — week of 2026-03-14)

**Must complete before advancing to V5 or any other Phase 2 work.**

Both-side trading — whether professional market-making, reward farming, or in-play hedging — contaminates the signal pipeline. None of these behaviors express directional conviction, which is the foundation of the insider/informed thesis. Empirical analysis of 9 days of data identified 39 hedge pairs across 20 wallets, overwhelmingly on live sports markets. Two wallets alone account for ~60% of hedged volume ($4.2M combined) and are professional-scale operators (400–800+ trades, 175–442 unique markets).

See `research/V4B_FARM_DETECTION.md` for full analysis, behavioral clusters, and proposed heuristics.

**Completed work (signal quality improvements):**
- [x] Q1: Bumped shallow wallet profile limit from 6 to 25 (single API call, enables MM vs. newcomer distinction). Invalidated 1,619 stale cache entries.
- [x] Q2: Fix event category slug mismatch — two-step lookup (exact then prefix) in EventCache.get_event() and db.get_event_by_prefix(). Coverage: 29% → 69%.
- [x] Q3: Resolution proximity filter — hard 30-day cutoff (`max_days_to_resolution` in config.toml). Markets table stores `end_date` from Gamma API `endDateIso`. PaperTrader rejects trades on markets resolving >30 days out.
- [x] Q5: Category blocklist — `blocked_categories = ["Crypto"]` in config.toml. Crypto is 91% 5-minute binary micro-markets (BTC/SOL/ETH Up or Down) at $0.99 avg price — no insider edge, pure noise.

**Proposed MM filter (three-layer defense) — NOT YET APPROVED FOR IMPLEMENTATION:**

The following plan unifies the original two-layer FARM defense with the anti-hedge filter (previously Phase 2). All three address the same root problem: both-side activity at different levels.

- [ ] **Layer 0 — Portfolio anti-hedge**: Prevent the paper trader from holding both sides of the same market. Currently `risk.py` only blocks duplicate `condition_id + outcome`; a second whale on the *opposite* outcome passes through, guaranteeing a spread loss. Proposed fix: reject if any open position shares the same `condition_id`, regardless of outcome.
- [ ] **Layer 1 — Real-time lookback**: Before paper trade entry, check if the incoming wallet has traded the opposite outcome on the same `condition_id` within a configurable window (e.g., 30 min). If yes, this wallet is MM-ing, not expressing conviction. Reject.
- [ ] **Layer 2 — Wallet reputation**: When Layer 1 catches a wallet on 2+ distinct markets, flag the wallet as a serial MM operator. Suppress all future paper trades from flagged wallets.
- [ ] Re-validate thresholds after 3 weeks of data collection.

**Open reservations (must resolve before implementing):**

1. **Layer 0 is arbitrary.** Blocking the second side while keeping the first open is a coin flip — the first entry might be the wrong side. This could randomly increase risk rather than reduce it. Need to think through: should we close the *first* position instead? Should we block both and take neither? Does the score of the second trade matter (higher score = stronger conviction = maybe the first was wrong)?

2. **Execution timing is underspecified.** Layers 1 and 2 imply the paper trader has time to "look back" before executing, but the current flow is synchronous: trade arrives → score → maybe_trade → done. There's no explicit delay, but the lookback query adds a dependency on *previous* trades being already persisted. Need to map the exact data flow: when does the incoming trade get inserted vs. when does the lookback query run? Could we miss a hedge pair if both sides arrive in the same batch? The logic and sequencing need to be clearly articulated before writing code.

3. **Serial MM detection needs more exploration.** The 2-market threshold for Layer 2 is proposed but not validated. Questions: How many wallets in the current DB would be flagged? What's the false positive rate (legitimate traders who hedged twice)? Do flagged wallets ever produce genuine insider signals? Should the flag decay over time? Should we run a retrospective analysis against existing data before building the persistence layer?

**Deferred (separate workstream):**
- [ ] Q4: Niche market low-odds outsized bets — undeveloped thesis on tailing high-conviction low-probability signals. Would be a different thesis engine, not this filter.

**Data limitation**: Current analysis covers 2026-03-06 to 2026-03-15 (9 days). Continue collecting data during implementation to validate pattern persistence.

### Phase 2 — Enhanced Detection (next — after V4b)
- [x] V4: Paper trading (risk engine + PaperExecutor)
- [ ] V5: P&L tracking (resolution poller)
- [ ] DBSCAN temporal clustering (coordinated wallet timing)
- [ ] Funding chain tracing (Polygon RPC: where did wallet funds come from?)
- [ ] Historical win-rate analysis via Goldsky subgraphs
- [ ] Wallet tagging / watchlist system
- [x] Reward farmer / MM detection: subsumed into V4b MM filter (see V4b section). Reward farming is one behavior within the broader both-side trading pattern that the MM filter addresses.
- [x] **Anti-hedge filter**: pulled into V4b as Layer 0 of the MM filter (see V4b section). Not yet implemented — open reservations on approach.
- [x] **Resolution proximity filter**: hard 30-day cutoff implemented in V4b Q3. `max_days_to_resolution = 30` in config.toml. Score dampening (SPECULATIVE/EARLY/HOT/IMMINENT bands) deferred to future refinement.
- [ ] Per-category exposure limits (max 20% of bankroll per category — prevents correlated bets, e.g., all UFC fights resolving same night). Source: RQ4 §6.2, SYNTHESIS.md §1.1
- [ ] Daily/weekly loss circuit breakers (10%/20% of bankroll) and consecutive-loss pause (3 losses). Requires V5 resolution data
- [ ] Category-weighted scoring (Crypto already excluded via V4b Q5; future: Politics insider risk > Sports score adjustments)
- [ ] Tag-based filtering (e.g., "only show Politics")

### Phase 3 — TUI & Live Trading
- [ ] V6: Live trading (CLOB Level 2)
- [ ] Textual TUI with live updating tables
- [ ] Discord / Telegram / Slack webhook alerts
- [ ] Market-specific monitoring mode
- [ ] Export suspicious wallet reports

## Project Structure

```
spyhop/
├── CLAUDE.md
├── CONFIG_REFERENCE.md      # Every config.toml parameter: how it works, tuning guidance, research citations
├── pyproject.toml
├── config.toml              # User-configurable thresholds
├── src/
│   └── spyhop/
│       ├── __init__.py
│       ├── __main__.py       # CLI entry (watch / wallet / history)
│       ├── cli.py            # Rich live display + handle_trade loop
│       ├── config.py         # TOML config loader
│       ├── ingestor/
│       │   ├── __init__.py
│       │   └── rtds.py       # RTDS WebSocket client
│       ├── profiler/
│       │   ├── __init__.py
│       │   ├── wallet.py     # Wallet history & profile (Data API)
│       │   ├── market.py     # Market metadata cache (Gamma API)
│       │   └── event.py      # Event category cache (Gamma API)
│       ├── detector/
│       │   ├── __init__.py   # build_scorer() factory
│       │   ├── base.py       # Protocol, DetectionContext, ScoreResult
│       │   ├── fresh_wallet.py
│       │   ├── size_anomaly.py
│       │   ├── niche_market.py
│       │   └── scorer.py     # Multiplicative composite scoring
│       └── storage/
│           ├── __init__.py
│           └── db.py         # SQLite schema & queries
└── tests/
```

## Reference Repositories

- **pselamy/polymarket-insider-tracker** — Most mature OSS insider tracker. Pipeline architecture (ingestor→profiler→detector→alerter), DBSCAN temporal clustering, funding chain tracing, PostgreSQL+Redis. Good patterns but heavyweight.
- **NickNaskida/polymarket-insider-bot** — Lighter alternative. Async Python, SQLite, Slack. Simpler 0-10 scoring. Reportedly AI-generated.
- **Polymarket/py-clob-client** — Official Python SDK for CLOB API. Level 0 = unauthenticated read-only. Current version 0.34.6.
- **Polymarket/agents** — Official AI agent framework. Good Pydantic models and Gamma API patterns. 170 deps (too heavy for us).

## Coding Conventions

- Use `httpx` for all HTTP requests (async-capable)
- Use `asyncio` for WebSocket + concurrent profiling
- Type hints on all public functions
- Pydantic models for API response parsing
- Config-driven thresholds (no magic numbers in detection logic)
- SQLite via stdlib `sqlite3` (no ORM needed for MVP)
- `rich` for all terminal output (tables, progress, logs)

## Operational Notes

### Use the spyhop CLI for data queries
Before writing ad-hoc Python to query the SQLite database, check if an existing CLI command already does it:
- `spyhop history --min-score 7` — show scored signals
- `spyhop wallet <addr>` — deep wallet lookup
- `spyhop watch` — live stream

### Config loading & CWD sensitivity
- `load_config()` searches: `./config.toml` → project root → user config dir → built-in defaults
- When installed via `pip install -e .` and run from a different CWD, `./config.toml` won't match — the project-root fallback (`_project_root()`) handles this
- `config.py` logs at INFO which file was loaded, or WARNING if falling through to defaults — check startup logs if config values seem wrong
- Silent fallback to defaults is the most common cause of "paper trading won't enable" — `paper.enabled` defaults to `False`

### Windows environment quirks
- **User's shell is PowerShell** — always give PowerShell-compatible commands, not Unix/bash (e.g., `Get-Content file -Wait` not `tail -f`, `Select-String` not `grep`)
- No `sqlite3` CLI available — use Python's `sqlite3` module or the spyhop CLI
- When running inline Python via bash, use heredoc (`python3 << 'PYEOF'`) to avoid f-string/dict-key quoting conflicts
- DB path: `C:/Users/thoma/AppData/Local/spyhop/spyhop.db`
