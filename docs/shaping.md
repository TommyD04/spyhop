# Spyhop — Shaping Doc

## Source

> Build a CLI/TUI tool that monitors Polymarket for suspicious "whale" trading behavior
> that could indicate insider information. I want to identify these patterns and potentially
> make small strategic bets alongside (or against) them. Everything I'm doing uses public
> on-chain data — this is blockchain forensics, not accessing any private information.

> My goal by the end of this project is to have a trading tool that can identify likely
> inside traders and place small tactical bets alongside them.

> [On trading mode]: Auto-execute with guardrails. But we should plan for the trading desk
> now — I would like to prove out and test the concept with hypothetical trades first
> (likely for a period of ~30 days).

> [On direction]: Configurable per signal. Default copy, contrarian available.

> [On market scope]: All markets. Let the scoring system decide what's suspicious.

---

## Frame

### Problem

- Polymarket prediction markets have a known insider trading problem — fresh wallets placing large, confident bets on niche markets shortly before resolution
- This activity is detectable because all trades settle on Polygon (public chain), but there's no easy local-first tool to surface it in real time
- Even when insiders are identified, acting on that signal requires fast, disciplined execution — manual monitoring and trading is too slow and error-prone
- Existing tools (Polywhaler, Polysights) are hosted dashboards with no trading integration — you detect, then alt-tab to trade manually

### Outcome

- A tool that continuously monitors Polymarket for suspicious trading patterns and auto-executes small tactical bets when confidence is high
- Paper trading mode validates detection quality (~30 days) before committing real capital
- Runs locally with configurable risk guardrails as the safety net (not human approval per trade)
- Local-first, uses only public data for detection, minimal infrastructure

---

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| **R0** | Detect suspicious whale trades in real time via Polymarket's public APIs | Core goal |
| **R1** | Profile wallets on-demand: trade count, history, win rate, age on Polymarket | Core goal |
| **R2** | Score trades using multiple independent signals (fresh wallet, size anomaly, niche market) with compounding composite score | Core goal |
| **R3** | Display ranked suspicious activity with enough context to evaluate (market question, odds, wallet profile, score breakdown) | Core goal |
| **R4** | Auto-execute bets when composite score exceeds configurable threshold, subject to risk guardrails | Core goal |
| **R5** | Paper trading mode: log hypothetical trades, track simulated P&L, validate detection before real capital | Must-have |
| **R6** | Persist wallet profiles, trade history, scores, and positions locally (SQLite) | Must-have |
| **R7** | All detection thresholds and risk limits are user-configurable via config file (no magic numbers) | Must-have |
| **R8** | Risk controls: max $50/trade, $200/day, $500 total exposure (configurable) | Must-have |
| **R9** | Dual-mode: watch mode for continuous monitoring/auto-trading + CLI subcommands for queries, status, manual actions | Must-have |
| **R10** | Bet sizing scales with composite score (higher confidence = larger bet, configurable curve) | Must-have |
| **R11** | Trade direction configurable per signal: default copy (same side as insider), contrarian available | Must-have |
| **R12** | Track P&L on all positions (paper and live) with resolution tracking | Must-have |
| **R13** | Monitor all markets — no category filters, let scoring decide | Must-have |
| **R14** | Alert via external channel (Discord/Telegram/Slack) when high-score signal detected | Undecided |
| **R15** | Support "watchlist" mode — monitor specific wallets known to be suspicious | Undecided |
| **R16** | Temporal clustering detection (DBSCAN) — multiple wallets entering same position in short window | Nice-to-have |
| **R17** | Funding chain tracing — where did the wallet's USDC come from? | Nice-to-have |
| **R18** | Historical win-rate analysis via Goldsky subgraphs | Nice-to-have |

---

## Resolved Questions

1. **Trading automation** (R4) — Auto-execute with guardrails. No human approval per trade.
2. **Paper trading first** (R5) — ~30-day paper trading period to validate detection before real money.
3. **Bet sizing** (R10) — Scaled to confidence via configurable score-to-amount curve.
4. **Running mode** (R9) — Both. Watch mode (daemon-like) + CLI subcommands.
5. **Trade direction** (R11) — Configurable per signal. Default: copy insider's direction.
6. **Market scope** (R13) — All markets, no category filters.
7. **Risk guardrails** (R8) — Conservative: $50/trade, $200/day, $500 total exposure (all configurable).
8. **Polymarket account** — No account yet. Detection + paper trading first. Live trading after validation.

## Defaults (configurable in config.toml)

9. **Score-to-bet curve** (R10) — Exponential: score 7=$5, 8=$10, 9=$25, 10=$50. Conservative on borderline, aggressive on high-conviction.
10. **Minimum score for auto-trade** — Score >= 7 during paper trading (wide net for validation data). Tighten to >= 8 for live.
11. **Position deduplication** — Bet once per wallet-market pair. Subsequent trades from same wallet on same market are logged but don't trigger additional bets.
12. **Market timing** — No time-to-resolution filter (monitor all). Scoring naturally penalizes stale markets via lower anomaly scores.

---

## Shape A: Detection-First Pipeline with Pluggable Executor

The core architecture treats detection and execution as two halves of a pipeline, joined by a scoring threshold. The executor is a pluggable backend — paper or live — behind a common interface.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Ingestor**: RTDS WebSocket streams all trades; filters by USD threshold (default $10K); falls back to Data API polling if WebSocket drops | |
| **A2** | **Market cache**: Gamma API market metadata cached in SQLite; resolves conditionId → human-readable market question, volume, odds; refreshed on cache miss | |
| **A3** | **Wallet profiler**: Data API lookup on each whale wallet; returns trade count, trade history, positions, win rate; cached in SQLite with TTL | |
| **A4** | **Detector suite**: Independent detectors (FreshWallet, SizeAnomaly, NicheMarket) each return 0-N sub-score; composed in Scorer via compounding formula (not additive) | |
| **A5** | **Risk engine**: Enforces max-per-trade, daily-limit, total-exposure, per-market-limit; rejects trades that would breach any limit; tracks exposure state in SQLite | |
| **A6** | **Executor interface**: `place_bet(market, side, amount) → OrderResult`; two backends: `PaperExecutor` (writes to SQLite hypothetical_positions) and `LiveExecutor` (calls CLOB API Level 2) | ⚠️ |
| **A7** | **Position tracker**: Monitors open positions for resolution; calculates P&L (realized on resolution, unrealized via current odds); works for both paper and live | ⚠️ |
| **A8** | **CLI display**: Rich live table of recent signals + scores; subcommands: `watch`, `status`, `history`, `positions`, `config` | |
| **A9** | **Config system**: TOML file for all thresholds, risk limits, score-to-bet curve, trade direction defaults, executor mode (paper/live) | |

**Notes:**
- A6 flagged: LiveExecutor requires CLOB Level 2 auth (private key, API credentials). Need to design secure key storage. Paper mode works without any auth.
- A7 flagged: Resolution tracking requires monitoring market outcomes after bets are placed. Unclear if RTDS pushes resolution events or if we need to poll Gamma API.

---

## Data Flow

```
RTDS WebSocket
    │ (all trades)
    ▼
[USD Filter: >= $10K]
    │
    ▼
[Market Cache]──── Gamma API (on cache miss)
    │
    ▼
[Wallet Profiler]── Data API (on cache miss / TTL expired)
    │
    ▼
[Detector Suite]
    ├─ FreshWalletDetector
    ├─ SizeAnomalyDetector
    └─ NicheMarketDetector
    │
    ▼
[Scorer] → composite score (0-10)
    │
    │ score >= threshold?
    ▼
[Risk Engine] → within limits?
    │
    ▼
[Executor]
    ├─ PaperExecutor → SQLite (hypothetical_positions)
    └─ LiveExecutor  → CLOB API Level 2 (future)
    │
    ▼
[Position Tracker] → P&L on resolution
    │
    ▼
[CLI Display] ← Rich live table
[Alerts]      ← Discord/Telegram (future)
```

---

## CLI Subcommands

| Command | Purpose |
|---------|---------|
| `spyhop watch` | Start continuous monitoring + auto-trading (the daemon mode) |
| `spyhop status` | Show current state: active signals, open positions, risk utilization |
| `spyhop history` | Browse past signals with scores, trades taken, outcomes |
| `spyhop positions` | Show all positions (paper + live) with P&L |
| `spyhop wallet <addr>` | Deep-dive a specific wallet's profile and history |
| `spyhop config` | Show/edit current configuration |

---

## Fit Check (R × A)

| Req | Requirement | Status | A |
|-----|-------------|--------|---|
| R0 | Detect suspicious whale trades in real time via Polymarket's public APIs | Core goal | ✅ |
| R1 | Profile wallets on-demand: trade count, history, win rate, age on Polymarket | Core goal | ✅ |
| R2 | Score trades using multiple independent signals with compounding composite score | Core goal | ✅ |
| R3 | Display ranked suspicious activity with enough context to evaluate | Core goal | ✅ |
| R4 | Auto-execute bets when composite score exceeds configurable threshold, subject to risk guardrails | Core goal | ❌ |
| R5 | Paper trading mode: log hypothetical trades, track simulated P&L, validate detection before real capital | Must-have | ✅ |
| R6 | Persist wallet profiles, trade history, scores, and positions locally (SQLite) | Must-have | ✅ |
| R7 | All detection thresholds and risk limits are user-configurable via config file | Must-have | ✅ |
| R8 | Risk controls: max $50/trade, $200/day, $500 total exposure (configurable) | Must-have | ✅ |
| R9 | Dual-mode: watch mode for continuous monitoring + CLI subcommands for queries | Must-have | ✅ |
| R10 | Bet sizing scales with composite score (configurable curve) | Must-have | ✅ |
| R11 | Trade direction configurable per signal: default copy, contrarian available | Must-have | ✅ |
| R12 | Track P&L on all positions (paper and live) with resolution tracking | Must-have | ❌ |
| R13 | Monitor all markets — no category filters, let scoring decide | Must-have | ✅ |
| R14 | Alert via external channel when high-score signal detected | Undecided | — |
| R15 | Support "watchlist" mode — monitor specific wallets | Undecided | — |
| R16 | Temporal clustering detection (DBSCAN) | Nice-to-have | — |
| R17 | Funding chain tracing | Nice-to-have | — |
| R18 | Historical win-rate analysis via Goldsky subgraphs | Nice-to-have | — |

**Notes:**
- R4 fails: A6 (LiveExecutor) is flagged ⚠️ — we know WHAT it does but not HOW to securely store private keys and manage CLOB Level 2 auth. Paper mode (R5) passes because PaperExecutor needs no auth.
- R12 fails: A7 (Position Tracker) is flagged ⚠️ — resolution tracking mechanism is unknown. Need to confirm whether Gamma API's market `resolved` field can be polled, or if RTDS pushes resolution events.
- R14-R18 marked "—" because their status is Undecided/Nice-to-have and not blocking shape selection.

---

## Slices

Each slice ends with something demo-able. Ordered so each slice builds on the last.

### V1: Live Trade Stream + Market Cache

**Parts:** A1 (Ingestor) + A2 (Market cache) + A9 (Config) + partial A8 (CLI)

**Status:** ✅ COMPLETE

| Affordance | Mechanism |
|------------|-----------|
| RTDS WebSocket client | Connect to `wss://ws-live-data.polymarket.com`, subscribe to `activity/*` (wildcard required — `trades` type receives nothing; actual type is `orders_matched`) |
| USD filter | Drop trades below configurable threshold (default $10K). USDC value = `size * price` (RTDS sends token qty, not USDC) |
| Market cache | Gamma API metadata cached in SQLite `markets` table with TTL; RTDS also includes `title` field directly, so Gamma is fallback only |
| Config loader | Read `config.toml` with `tomllib`, layered defaults (CWD → ~/.config → built-in) |
| SQLite schema | `trades` + `markets` tables, platform-aware DB path |
| CLI: `spyhop watch` | Rich Live display showing streaming trades with market name, amount, side, wallet address |

**Protocol notes:**
- `type: "*"` wildcard is required — `type: "trades"` receives no data
- Application-level `PING` keepalive every 5s (text frame, not WS ping)
- Known server bug: data freezes after ~20 min → 5-min silence timeout forces reconnect
- Cloudflare fronts the endpoint; no special headers needed

**Demo:** Run `spyhop watch`, see large Polymarket trades streaming in real time with market name, amount, side, wallet address.

---

### V2: Wallet Profiling

**Parts:** A3 (Wallet profiler)

| Affordance | Mechanism |
|------------|-----------|
| Data API client | Fetch wallet activity by address, return trade count + history |
| Wallet cache | SQLite `wallets` table with profile data + TTL-based expiry |
| CLI: `spyhop wallet <addr>` | Rich table showing wallet's trade history, count, markets traded |
| Enriched watch display | `spyhop watch` now shows wallet trade count alongside each trade |

**Demo:** Run `spyhop wallet 0x...`, see full profile. Run `spyhop watch`, see enriched trade stream with wallet age.

---

### V3: Detection & Scoring

**Parts:** A4 (Detector suite)

| Affordance | Mechanism |
|------------|-----------|
| FreshWalletDetector | Score 0-3 based on wallet trade count (< 5 trades = max score) |
| SizeAnomalyDetector | Score 0-3 based on trade size vs market daily volume |
| NicheMarketDetector | Score 0-2 based on market volume (< $50K = max score) |
| Scorer | Compounding composite: multiply normalized sub-scores, scale to 0-10 |
| SQLite `signals` table | Persist every scored trade with sub-scores and composite |
| CLI: `spyhop watch` | Live display now shows composite score + sub-score breakdown per trade |
| CLI: `spyhop history` | Browse past signals sorted by score |

**Demo:** Run `spyhop watch`, see trades scored in real time. High-score signals highlighted. Run `spyhop history` to review past signals.

---

### V4: Paper Trading

**Parts:** A5 (Risk engine) + A6 (PaperExecutor) + A10 (Bet sizing)

| Affordance | Mechanism |
|------------|-----------|
| Score-to-bet curve | Configurable mapping: score 7=$5, 8=$10, 9=$25, 10=$50 |
| Risk engine | Check max-per-trade, daily-limit, total-exposure before execution; reject if breached |
| PaperExecutor | `place_bet()` writes to SQLite `positions` table with entry price, amount, side, market |
| Dedup guard | One bet per wallet-market pair; subsequent trades logged but not executed |
| Direction logic | Default: copy insider's side. Config override for contrarian. |
| CLI: `spyhop watch` | Now shows "[PAPER BET] $25 YES on 'Will X happen?'" when auto-executing |
| CLI: `spyhop positions` | Show all open paper positions with entry price and current odds |
| CLI: `spyhop status` | Show risk utilization: $X/$200 daily, $Y/$500 total exposure |

**Demo:** Run `spyhop watch`, see it auto-place paper bets on high-score signals. Run `spyhop positions` to see the paper portfolio. Run `spyhop status` to see risk limits.

---

### V5: P&L Tracking

**Parts:** A7 (Position tracker)

| Affordance | Mechanism |
|------------|-----------|
| Resolution poller | Periodic Gamma API poll for markets with open positions; check `resolved` field |
| P&L calculator | On resolution: mark position won/lost, calculate realized P&L |
| Unrealized P&L | For open positions: fetch current odds, calculate mark-to-market |
| CLI: `spyhop positions` | Now shows realized + unrealized P&L per position and total |
| CLI: `spyhop history` | Now shows outcome (won/lost/open) alongside each signal that triggered a trade |
| Paper trading report | Summary stats: total trades, win rate, total P&L, best/worst trade |

**Demo:** After some paper positions resolve, run `spyhop positions` to see P&L. Run `spyhop history` to see which signals were profitable. This is the 30-day validation dashboard.

---

### V6: Live Trading (future)

**Parts:** A6 (LiveExecutor)

| Affordance | Mechanism |
|------------|-----------|
| Secure key storage | Encrypted private key in local keyring or env var |
| CLOB Level 2 client | `py-clob-client` authenticated with API credentials |
| LiveExecutor | `place_bet()` calls CLOB API to place real orders |
| Mode switch | `config.toml`: `executor = "paper"` or `executor = "live"` |
| Confirmation safeguard | First-run warning when switching to live mode |

**Demo:** Switch config to live mode. Watch real USDC bets placed automatically on high-confidence signals. Same risk controls, real money.

---

## Slice Summary

|  |  |  |
|:--|:--|:--|
| **V1: LIVE TRADE STREAM + MARKET CACHE**<br>✅ COMPLETE<br><br>• RTDS WebSocket client (activity/*)<br>• USD threshold filter<br>• Gamma API market cache (SQLite TTL)<br>• SQLite schema + trade storage<br>• Config system (TOML)<br><br>*Demo: `spyhop watch` streams large trades* | **V2: WALLET PROFILING**<br>⏳ PENDING<br><br>• Data API wallet profiler<br>• Wallet cache with TTL<br>• `spyhop wallet` command<br><br>*Demo: Enriched trade stream with wallet age* | **V3: DETECTION & SCORING**<br>⏳ PENDING<br><br>• 3 independent detectors<br>• Compounding composite scorer<br>• Signals table + history<br>• Score display in watch mode<br><br>*Demo: Trades scored live, `spyhop history` reviews signals* |
| **V4: PAPER TRADING**<br>⏳ PENDING<br><br>• Score-to-bet curve<br>• Risk engine (limits)<br>• PaperExecutor + dedup<br>• Positions + status commands<br><br>*Demo: Auto paper bets on high-score signals* | **V5: P&L TRACKING**<br>⏳ PENDING<br><br>• Resolution poller (Gamma)<br>• Realized + unrealized P&L<br>• Paper trading report<br>• Win rate + summary stats<br><br>*Demo: 30-day validation dashboard* | **V6: LIVE TRADING**<br>⏳ PENDING<br><br>• Secure key storage<br>• CLOB Level 2 client<br>• LiveExecutor<br>• Paper → live mode switch<br><br>*Demo: Real USDC bets on high-conviction signals* |
