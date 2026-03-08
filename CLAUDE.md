# Spyhop — Polymarket Whale & Insider Tracker

> A spyhop is when a whale pokes its head above the waterline to observe its surroundings.
> This tool watches whale traders surface in prediction markets.

## Project Overview

Local-first Python CLI that monitors Polymarket for suspicious "whale" trading behavior that could indicate insider information. Uses only public APIs and on-chain data — blockchain forensics, not private data access.

## Architecture

```
CLI (Rich)  ←  ALERTER (ranked table)
                  ↑
              DETECTOR (composite scorer)
                  ├─ FreshWalletDetector (< 5 prior trades)
                  ├─ SizeAnomalyDetector (outsized vs liquidity)
                  └─ NicheMarketDetector (low-volume market bets)
                  ↑
              PROFILER (wallet history + market metadata)
                  ↑
              INGESTOR (RTDS WebSocket + Data API fallback)
                  ↑
              STORAGE (SQLite)
```

Pipeline: `ingestor → profiler → detector → alerter`

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

## Phasing

### Phase 1 — MVP (current)
- [x] RTDS WebSocket connection + trade streaming (V1 — complete)
- [x] USD threshold filter, default $10K (V1 — complete)
- [x] Market metadata cache via Gamma API (V1 — complete)
- [x] Rich CLI: `spyhop watch` live table (V1 — complete)
- [x] SQLite persistence: trades + markets (V1 — complete)
- [x] TOML config file with layered defaults (V1 — complete)
- [ ] Wallet profiling via Data API (trade count, history)
- [ ] 3 detectors: fresh wallet, size anomaly, niche market
- [ ] Composite scoring with configurable thresholds
- [ ] Rich CLI output (ranked suspicious activity table)

### Phase 2 — Enhanced Detection
- [ ] DBSCAN temporal clustering (coordinated wallet timing)
- [ ] Funding chain tracing (Polygon RPC: where did wallet funds come from?)
- [ ] Historical win-rate analysis via Goldsky subgraphs
- [ ] Wallet tagging / watchlist system
- [ ] Reward farmer detection: tag matched buy-sell pairs (same wallet, same market, <N min apart) as `FARM` to filter noise from genuine directional trades. Observed pattern: rotating wallets doing single round-trips on high-reward near-certainty markets (e.g., Fed rate at 99.8¢), losing ~0.1¢/token to harvest `clobRewards` liquidity incentives.

### Phase 3 — TUI & Alerts
- [ ] Textual TUI with live updating tables
- [ ] Discord / Telegram / Slack webhook alerts
- [ ] Market-specific monitoring mode
- [ ] Export suspicious wallet reports

## Project Structure

```
spyhop/
├── CLAUDE.md
├── pyproject.toml
├── config.toml              # User-configurable thresholds
├── src/
│   └── spyhop/
│       ├── __init__.py
│       ├── __main__.py       # CLI entry point
│       ├── config.py         # TOML config loader
│       ├── ingestor/
│       │   ├── __init__.py
│       │   ├── rtds.py       # RTDS WebSocket client
│       │   └── polling.py    # Data API polling fallback
│       ├── profiler/
│       │   ├── __init__.py
│       │   ├── wallet.py     # Wallet history & profile lookup
│       │   └── market.py     # Market metadata cache (Gamma API)
│       ├── detector/
│       │   ├── __init__.py
│       │   ├── fresh_wallet.py
│       │   ├── size_anomaly.py
│       │   ├── niche_market.py
│       │   └── scorer.py     # Composite scoring engine
│       ├── alerter/
│       │   ├── __init__.py
│       │   └── cli.py        # Rich table output
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
