# Polymarket API Landscape

**Purpose**: Unified reference for all Polymarket data sources -- what each provides, what Spyhop uses today, and what gaps remain for V3+.

**Last updated**: 2026-03-07 (post-V2, informed by 3 spike scripts + CLAUDE.md)

---

## 1. RTDS WebSocket (Live Firehose)

**URL**: `wss://ws-live-data.polymarket.com`
**Auth**: None (public)
**Rate limit**: N/A (push-based)

Every trade on Polymarket, in real time. This is Spyhop's primary data source.

### Fields per `orders_matched` payload

| Field | Type | Description |
|-------|------|-------------|
| `proxyWallet` | string | Trader's proxy wallet address |
| `name` | string | Display name (may be empty) |
| `pseudonym` | string | Pseudonym (may be empty) |
| `bio` | string | User bio text |
| `profileImage` | string | Profile image URL |
| `profileImageOptimized` | string | Optimized profile image URL |
| `conditionId` | string | Market condition ID |
| `asset` | string | CLOB token ID |
| `eventSlug` | string | Parent event slug |
| `slug` | string | Market slug |
| `title` | string | Human-readable market question |
| `outcome` | string | "Yes" or "No" |
| `outcomeIndex` | int | 0 or 1 |
| `side` | string | "BUY" or "SELL" |
| `size` | float | Token quantity (NOT USDC) |
| `price` | float | Unit price (0-1) |
| `transactionHash` | string | On-chain tx hash |
| `icon` | string | Market icon URL |

**USDC value** = `size * price`

### Spyhop usage

| Status | Fields |
|--------|--------|
| **Using (V1+V2)** | proxyWallet, name, pseudonym, side, size, price, conditionId, asset, transactionHash, title |
| **Not using** | bio, profileImage, profileImageOptimized, eventSlug, slug, outcome, outcomeIndex, icon |

### Notable gaps

- **`outcome`** (YES/NO) and **`outcomeIndex`** -- needed by V3 SizeAnomaly detector to know which side of the order book was hit. Currently discarded.
- **`eventSlug`** -- could link related sub-markets for correlated insider detection (Phase 2).

### Protocol quirks (discovered empirically)

- Must subscribe with `type: "*"` -- `type: "trades"` receives nothing
- Actual message type is `orders_matched`
- `filters` must be omitted or empty string `""` -- empty object `{}` causes 400
- Application-level `PING` text frame every 5s (not WS-level ping)
- Known bug: data freezes after ~20 min -- 5-min silence timeout triggers reconnect
- Cloudflare-fronted (CF-RAY: SEA datacenter)

---

## 2. Data API (Per-Wallet History)

**Base URL**: `https://data-api.polymarket.com`
**Auth**: None (public)
**Rate limit**: ~60 req/min (no rate-limit headers observed in spike)

### 2a. `/trades` -- Clean trade records

**Params**: `user`, `conditionId`, `limit`, `offset`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Trade ID |
| `conditionId` | string | Market condition ID |
| `title` | string | Market question |
| `outcome` | string | YES/NO |
| `outcomeIndex` | int | 0/1 |
| `side` | string | BUY/SELL |
| `size` | float | Token quantity (NOT USDC) |
| `price` | float | Unit price |
| `timestamp` | int | Unix epoch seconds |
| `matchTime` | string | ISO timestamp |
| `transactionHash` | string | On-chain tx hash |
| `name` | string | Display name |
| `pseudonym` | string | Pseudonym |

**No `usdcSize`** -- must compute `size * price`.

**Pagination**: `limit` + `offset` only. The `before` param exists but is broken (ignored by server -- confirmed spike 3). Max limit tested: 500.

**Spyhop usage**: V2 wallet profiler uses `/trades?user=X` for shallow (limit=6) and deep (limit=200, paginated) fetches. Also used for `spyhop wallet` recent trades display.

**Also supports**: Global queries by `conditionId` -- useful for V3 NicheMarket detector ("how many traders in this market?").

### 2b. `/activity` -- Richer records with noise

**Params**: `user`, `limit`, `offset`, `type` (filter untested)

Everything `/trades` has, PLUS:

| Extra Field | Type | Description |
|-------------|------|-------------|
| `usdcSize` | float | Pre-computed USDC value |
| `type` | string | Record type: "TRADE", "SPLIT", possibly others |
| `bio` | string | User bio |
| `profileImage` | string | Profile image URL |
| `profileImageOptimized` | string | Optimized image URL |

**Trade-off**: Has `usdcSize` (convenient), but includes SPLIT noise that inflates trade counts. V2 chose `/trades` over `/activity` for this reason.

### 2c. `/positions` -- Current open positions

**Params**: `user`, `limit`, `offset`

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Market question |
| `conditionId` | string | Market condition ID |
| `outcome` | string | YES/NO |
| `size` | float | Position size |
| `currentValue` | float | Current market value |
| `cashPnl` | float | Realized P&L |
| `redeemable` | bool | Can be redeemed (market resolved) |
| `mergeable` | bool | Can be merged |

**Spyhop usage**: Not used yet.

**V3 value**: High. Enables:
- "Balanced exposure" false-positive filter -- wallet with equal YES/NO on same market is likely market-making, not insider trading
- Portfolio concentration signal -- all-in on one market vs diversified
- Win rate calculation from resolved positions (redeemable + cashPnl)

### 2d. `/profiles` -- DEAD (404)

Confirmed non-existent in spike 1. Tried `user`, `address`, `wallet` params -- all 404. Profile data is embedded in `/activity` and `/trades` responses instead. RTDS also sends name/pseudonym in every payload.

---

## 3. Gamma API (Market Metadata)

**Base URL**: `https://gamma-api.polymarket.com`
**Auth**: None (public)
**Rate limit**: ~60 req/min

### Endpoints

| Endpoint | Params | Returns |
|----------|--------|---------|
| `GET /markets` | `condition_id`, `limit`, `offset` | Paginated market list |
| `GET /markets/{id}` | -- | Single market detail |
| `GET /events` | `limit`, `offset` | Paginated event list |
| `GET /events/{id}` | -- | Single event with sub-markets |

### Key fields per market

| Field | Type | Description |
|-------|------|-------------|
| `conditionId` | string | Primary key |
| `question` | string | Market question text |
| `slug` | string | URL slug |
| `description` | string | Full market description |
| `clobTokenIds` | list | Token IDs for CLOB API |
| `volume` | float | All-time volume |
| `volume24hr` | float | 24-hour volume |
| `openInterest` | float | Total money locked in market |
| `outcomePrices` | list | Current YES/NO prices |

### Spyhop usage

| Status | Fields |
|--------|--------|
| **Using (V1)** | conditionId, question, slug, volume, volume24hr, outcomePrices (via MarketCache) |
| **Not using** | description, clobTokenIds, openInterest, events endpoint |

### Notable gaps

- **`openInterest`** -- total money locked in the market. Combined with `volume24hr`, gives a liquidity picture without needing CLOB order book data. Could serve as a lightweight proxy for book depth.
- **`description`** -- full text that could feed keyword-based market category tagging (SYNTHESIS: "geopolitical/military = CRITICAL risk category").
- **`/events`** endpoint -- groups related sub-markets under one event. Useful for detecting correlated insider activity across YES/NO sub-markets of the same event.

---

## 4. CLOB API (Order Books)

**Base URL**: `https://clob.polymarket.com`
**Auth**: None for Level 0 (read-only)
**Rate limit**: ~60 req/min
**SDK**: `py-clob-client` Level 0 (unauthenticated)

### Endpoints

| Endpoint | Params | Returns |
|----------|--------|---------|
| `GET /book` | `token_id` | Full order book (bids + asks) |
| `GET /prices` | `token_id` | Current prices |
| `GET /midpoints` | `token_id` | Midpoint prices |
| `GET /spreads` | `token_id` | Bid-ask spreads |
| `GET /last-trade-price` | `token_id` | Most recent trade price |

### Spyhop usage

**Not used yet.** This is the biggest gap for V3.

### V3 value -- Critical

The SizeAnomaly detector needs order book depth to answer: "Did this whale trade consume a significant portion of the visible order book?"

- `GET /book?token_id=X` returns the full bid/ask ladder
- Sum visible depth at +/- N levels from midpoint
- Compare whale's trade size to that depth
- SYNTHESIS threshold: `orderbook_impact_pct = 0.02` (2% of visible book = suspicious)

**Note**: Requires mapping `conditionId` -> `clobTokenIds` via Gamma API. The MarketCache should store `clobTokenIds` to enable this lookup.

---

## 5. Goldsky Subgraphs (Historical/On-Chain)

**Protocol**: GraphQL
**Auth**: None (free tier: 100K queries/month)

### Five specialized subgraphs

| Subgraph | URL | Use Case |
|----------|-----|----------|
| Activity | `https://api.goldsky.com/.../activity-subgraph/0.0.4/gn` | Deep wallet archaeology |
| Positions | `https://api.goldsky.com/.../positions-subgraph/0.0.7/gn` | Historical position tracking |
| Orders | (similar pattern) | Order history |
| Open Interest | (similar pattern) | Historical OI |
| PnL | (similar pattern) | Profit/loss tracking |

### Spyhop usage

**Not used yet.** Phase 2 material.

### Future value

- Historical win-rate analysis (detect Magamyman/AlphaRaccoon patterns -- SYNTHESIS §1.4 priority 3)
- Funding chain tracing (where did wallet funds come from?)
- Deep backfill for paper trading validation

---

## Summary: What Spyhop Uses Today vs. What's Available

| Source | V1 | V2 | V3 (planned) | Phase 2 |
|--------|----|----|---------------|---------|
| **RTDS WebSocket** | Trade stream | + name/pseudonym | + outcome/outcomeIndex | -- |
| **Data API /trades** | -- | Wallet profiling | + by conditionId (market-level) | -- |
| **Data API /activity** | -- | -- | Maybe (has usdcSize) | -- |
| **Data API /positions** | -- | -- | Balanced exposure filter | Win rate |
| **Gamma API /markets** | Market cache | -- | + openInterest, description, clobTokenIds | Category tagging |
| **Gamma API /events** | -- | -- | -- | Correlated detection |
| **CLOB API /book** | -- | -- | SizeAnomaly (order book depth) | Live trading |
| **Goldsky subgraphs** | -- | -- | -- | Win rate, funding chains |

## Gap Priorities for V3

| Priority | Gap | Source | Detector |
|----------|-----|--------|----------|
| 1 | **Order book depth** | CLOB `/book` | SizeAnomaly -- "did this trade eat the book?" |
| 2 | **Wallet positions** | Data API `/positions` | False-positive filter -- "is this wallet hedged?" |
| 3 | **`outcome` from RTDS** | Already arriving | SizeAnomaly -- which side of the book was hit |
| 4 | **`openInterest` from Gamma** | Already available | Lightweight liquidity proxy (alternative to CLOB) |
| 5 | **Market-level trades** | Data API `/trades?conditionId=X` | NicheMarket -- recent activity count |
| 6 | **`clobTokenIds` from Gamma** | Already available | Required to call CLOB `/book` |
