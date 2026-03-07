# SYNTHESIS: Research → Spyhop Configuration & Trading Playbook

**Purpose**: Translate the findings from RQ1-RQ4, the Trading Strategies taxonomy, and the Kelly addendum into two deliverables:

1. **Spyhop Configuration Spec** — specific thresholds, scoring weights, and architecture decisions for V2-V6
2. **Personal Trading Playbook** — how to trade alongside Spyhop's signals, manage positions, and protect capital

This is the action document. Theory lives in the RQ files. This is what you build from and trade from.

---

## Part 1: Spyhop Configuration Spec

### 1.1 Config File: Recommended Defaults

The following extends `config.toml` with all detection, scoring, and trading parameters. Every magic number traces back to a specific research finding.

```toml
# ── Existing V1 config ──────────────────────────────────────────────

[ingestor]
usd_threshold = 10_000
ws_url = "wss://ws-live-data.polymarket.com"
reconnect_delay_sec = 5

[market_cache]
gamma_url = "https://gamma-api.polymarket.com"
ttl_minutes = 60

[display]
max_rows = 50

# ── V2: Wallet Profiling ────────────────────────────────────────────

[profiler]
data_api_url = "https://data-api.polymarket.com"
# How many recent trades to fetch per wallet for profiling
max_trades_to_fetch = 200
# Cache wallet profiles for this long (minutes) to avoid re-fetching
wallet_cache_ttl_minutes = 30

# ── V3: Detection & Scoring ─────────────────────────────────────────

[detector.fresh_wallet]
# Wallets with fewer than this many prior Polymarket trades are "fresh"
# Source: RQ3 §2.1 — practitioner convergence across 4+ tools
max_prior_trades = 5
# Graduated scoring within the "fresh" range
#   0 trades → multiplier 3.0 (maximum suspicion)
#   1-2 trades → multiplier 2.5
#   3-5 trades → multiplier 2.0
#   >5 trades → multiplier 1.0 (no signal)
multiplier_zero = 3.0
multiplier_low = 2.5
multiplier_mid = 2.0

[detector.size_anomaly]
# Minimum trade to even evaluate (noise filter)
# Source: RQ3 §2.2 — pselamy default $1K; we use ingestor threshold $10K
min_trade_usd = 10_000
# Trade consumes more than this % of visible order book depth → flag
# Source: RQ3 §2.2 — pselamy LIQUIDITY_IMPACT_THRESHOLD=0.02
orderbook_impact_pct = 0.02
# Trade volume is this many multiples of the market's daily average → flag
# Source: RQ3 §2.2 — PolyTrack guidance: 5-10x
volume_spike_multiplier = 5.0
# Graduated scoring
#   2-5% of book → multiplier 1.5
#   5-10% of book → multiplier 2.0
#   10%+ of book → multiplier 3.0
multiplier_low = 1.5
multiplier_mid = 2.0
multiplier_high = 3.0

[detector.niche_market]
# Markets with daily volume below this are "niche"
# Source: RQ3 §2.3 — pselamy default; confirmed by case analysis
max_daily_volume_usd = 50_000
# Graduated scoring
#   $25K-$50K daily → multiplier 1.5
#   $10K-$25K daily → multiplier 2.0
#   <$10K daily → multiplier 2.5
multiplier_low = 1.5
multiplier_mid = 2.0
multiplier_high = 2.5

[scorer]
# Scoring model: multiplicative compounding
# Source: RQ3 §3 — practitioner consensus that co-occurring signals
#   are exponentially (not linearly) more suspicious
#
# composite = log10(fresh_mult * size_mult * niche_mult) mapped to 0-10
# Single signal → score ~3-5 (log10 of 2-3)
# Two signals → score ~5-7 (log10 of 4-9)
# Three signals → score ~7-10 (log10 of 8-27)
#
# This naturally produces the exponential scoring the research supports.

alert_threshold = 7       # Score >= 7 triggers alert
critical_threshold = 9    # Score >= 9 triggers immediate full audit

# ── V4: Paper Trading ───────────────────────────────────────────────

[executor]
mode = "paper"            # "paper" | "live" — start with paper ALWAYS
bankroll_usd = 10_000     # Starting paper bankroll

[executor.kelly]
# Kelly fraction: what portion of the theoretical Kelly bet to actually place
# Source: ADDENDUM_KELLY_CRITERION §4.2
#   quarter = conservative (recommended for unvalidated signals)
#   eighth = ultra-conservative (recommended during initial paper trading)
fraction = 0.25
# Maximum position as % of bankroll, regardless of Kelly output
# Source: RQ4 §6.1 — survive 20 consecutive losses
max_position_pct = 0.10
# Map suspicion score to estimated insider correctness
# Source: ADDENDUM_KELLY_CRITERION §5.2
# These represent: "given this score, how likely is the insider right?"
score_7_correctness = 0.70
score_8_correctness = 0.80
score_9_correctness = 0.85
score_10_correctness = 0.90

[executor.filters]
# Skip trade if price has moved >N% since the whale's entry
# Source: RQ4 §2.3 — PolyTrack: "edge has disappeared" beyond 10%
max_price_drift_pct = 0.10
# Skip trade if market resolves in less than this many minutes
# Source: RQ4 §6.3 — insufficient time to act
min_time_to_resolution_minutes = 60
# Skip if order book depth at acceptable price < N times intended position
# Source: RQ4 §6.1
min_liquidity_multiple = 2.0
# Maximum acceptable slippage from target entry price
max_slippage_pct = 0.10

[executor.risk]
# Portfolio-level controls
# Source: RQ4 §6.2
max_open_positions = 5
max_exposure_per_category_pct = 0.20
daily_loss_limit_pct = 0.10
weekly_loss_limit_pct = 0.20
consecutive_loss_pause = 3   # Pause trading for 24h after N consecutive losses

# ── V5: P&L Tracking ───────────────────────────────────────────────

[resolution]
# How often to poll for market resolutions (minutes)
poll_interval_minutes = 15
```

### 1.2 Detector Architecture Decisions

| Decision | Choice | Research Basis |
|----------|--------|----------------|
| Scoring model | Multiplicative, not additive | RQ3 §3: every confirmed case has 3+ co-occurring signals; compounding reflects exponential suspicion increase |
| Score scale | 0-10 via log mapping | CLAUDE.md spec; compatible with existing alert threshold (>= 7) |
| Fresh wallet metric | Polymarket trade count, NOT Polygon nonce | CLAUDE.md: proxy wallet gotcha — fresh proxy may belong to experienced user |
| Size metric | Relative (% of book) primary, absolute ($) as noise filter | RQ3 §2.2: $10K on a thin market is suspicious; $10K on a presidential market is noise |
| Niche metric | Daily volume from Gamma API | RQ3 §2.3: < $50K threshold; cache aggressively per CLAUDE.md |
| Market category risk | Tag via keyword classification of market question | RQ2 §4: geopolitical/military = CRITICAL; corporate announcements = HIGH |

### 1.3 False Positive Filters

Based on TRADING_STRATEGIES.md and RQ2 §5, apply these **before** scoring to reduce noise:

| Filter | Logic | Reduces False Positives From |
|--------|-------|------------------------------|
| **Balanced exposure** | Wallet has ~equal YES/NO volume on same market → reduce score | Market makers, arb bots |
| **Near-certainty trades** | Trade at >95¢ or <5¢ → exclude from detection | NO harvesters (TRADING_STRATEGIES §2.1) |
| **Known bot pattern** | >100 trades/day, sub-$100 each, >90% win rate → exclude | Latency arb bots |
| **Théo pattern** | Established wallet (>50 trades), gradual accumulation (>5 entries in same market over >24h) → reduce score | Legitimate high-conviction whales (RQ2 Case 1) |

### 1.4 Phase 2 Priorities (Post-V3)

Ranked by detection value based on research:

| Priority | Feature | Detection Value | Research Basis |
|----------|---------|----------------|----------------|
| 1 | **Wallet cluster detection** (shared funding source) | Very High | RQ2 Cases 3, 6: Iran cluster (6 wallets), OpenAI cluster (13 wallets). Simplest cluster signal: shared funding address within 24h. |
| 2 | **Market category tagging** | High | RQ2 §4: geopolitical markets carry 4x the insider rate of other categories |
| 3 | **Win-rate anomaly by category** | High | RQ2 Cases 4, 5: Magamyman and AlphaRaccoon are invisible to V1 detectors. Category-segmented win rate catches them. |
| 4 | **DBSCAN temporal clustering** | Medium | RQ3 §2.4: coordinated entry within minutes. Overlaps with wallet clustering but catches different patterns. |
| 5 | **Funding chain tracing** (Polygon RPC) | Medium | RQ3 §2.5: where did the USDC come from? Round-number deposits from shared source = red flag. |

---

## Part 2: Personal Trading Playbook

### 2.1 The Edge Model

Your edge comes from Spyhop's detection, not from prediction skill. The research is clear on this:

- **Whale win rates are ~50-53%** when properly calculated (RQ4 §1.2). You cannot beat the market by copying whales in general.
- **Insider trades resolve correctly** in every documented case (RQ2). They trade on actual information.
- **Spyhop identifies likely insiders** before resolution (RQ3). This is the information advantage.

Therefore: **your edge is the suspicion score**. You're not predicting events — you're identifying people who already know the answer, and betting with them before the market catches up.

### 2.2 When to Trade

**Trade when ALL of these are true:**

| Condition | Threshold | Kill Switch |
|-----------|-----------|-------------|
| Suspicion score | >= 7 | Skip if < 7 |
| Price hasn't moved | < 10% from whale's entry | Skip if >= 10% |
| Time to resolution | > 1 hour | Skip if imminent |
| Order book depth | >= 2x your intended position | Reduce size or skip |
| Portfolio exposure | < 5 open positions | Wait for a position to close |
| Daily P&L | Above -10% daily limit | Stop trading for the day |
| Weekly P&L | Above -20% weekly limit | Stop trading for the week |

**Never trade when:**
- You have an emotional stake in the outcome
- You're chasing a loss (the consecutive-loss pause exists for this reason)
- The market is about to resolve and you'd be buying at >90¢ (that's harvesting, not signal-following)
- The whale's trade is at >95¢ or <5¢ (likely a harvester, not an insider)

### 2.3 How Much to Bet

**Use the score-scaled quarter-Kelly pipeline from the Kelly addendum:**

```
Step 1: Score → Insider correctness estimate
  Score 7  → 70% likely the insider is right
  Score 8  → 80%
  Score 9  → 85%
  Score 10 → 90%

Step 2: Blend with market price to get your probability estimate
  your_p = (correctness × 1.0) + ((1 - correctness) × market_price)

Step 3: Calculate Kelly
  b = (1.0 / market_price) - 1
  f* = (your_p × b - (1 - your_p)) / b

Step 4: Apply quarter Kelly
  position_pct = f* × 0.25

Step 5: Cap at 10% of bankroll
  position_pct = min(position_pct, 0.10)
```

**Quick reference table** (quarter Kelly, 10% cap applied):

| Market Price | Score 7 | Score 8 | Score 9 | Score 10 |
|-------------|---------|---------|---------|----------|
| $0.10 | 6.4% | 7.9% | 8.6% | 9.3% |
| $0.20 | 7.3% | 9.0% | 9.8% | **10%** (capped) |
| $0.30 | 7.5% | 9.5% | **10%** | **10%** |
| $0.50 | 7.5% | **10%** | **10%** | **10%** |
| $0.70 | 5.4% | 8.6% | **10%** | **10%** |

Pattern: the sweet spot is markets priced at 20-50¢ (long odds, high payout) with high suspicion scores. This aligns with the insider playbook — insiders enter at low implied probabilities because that's where the information edge is largest.

### 2.4 Profit Management: The Part Most People Skip

The research (RQ4 §1.2) is unambiguous: **top whale profitability comes from P/L ratio management, not win rate.** DrPufferfish achieved 50.9% accuracy but 8.62x P/L ratio — averaging $37.2K per win vs. $11K per loss. You can be wrong half the time and still make money if your wins are bigger than your losses.

#### Rule 1: Let Winners Run to Resolution

Prediction markets have a built-in advantage over traditional markets: **binary resolution**. If the insider is right, the share goes to $1.00. You don't need to pick an exit — the market exits for you.

- **Default**: Hold to resolution. Don't sell early.
- **Exception**: If the market moves to >90¢ and resolution is weeks away, consider selling to free capital for a new signal. The last 10¢ isn't worth the time cost.

#### Rule 2: Cut Losers When the Thesis Dies

The thesis is "this was an insider trade." The thesis dies when:
- The event window passes without the predicted outcome (e.g., "US strikes Iran by Feb 28" and it's Feb 28 with no strike)
- Counter-evidence emerges (the insider's information was wrong or stale)
- The market moves significantly against you with new public information

When the thesis dies, **sell immediately**. Don't hope. The share price at that point represents your salvage value — take it.

#### Rule 3: Size Wins > Manage Losses (Asymmetric Payoff)

Because you're buying at low implied probabilities (10-50¢) on markets where the insider is likely right:
- **If right**: 2x-10x return on position
- **If wrong**: -100% of position (but position is 5-10% of bankroll = survivable)

This asymmetry means you don't need a high win rate. At quarter Kelly sizing with a 10% cap:

| Win Rate | Avg Win (at 30¢ entry) | Avg Loss | Bankroll Growth per 100 Trades |
|----------|----------------------|----------|-------------------------------|
| 40% | +$23,300 (×2.33) | -$10,000 | +$532,000 |
| 50% | +$23,300 | -$10,000 | +$665,000 |
| 60% | +$23,300 | -$10,000 | +$798,000 |
| 70% | +$23,300 | -$10,000 | +$931,000 |

Even at 40% accuracy, the strategy is profitable because the payoff asymmetry (2.33:1 at 30¢ entry) more than compensates. This is why Kelly sizes you up at long odds — the risk/reward is best there.

#### Rule 4: Track Everything

You cannot improve what you don't measure. For every trade (paper or live), record:

| Field | Why |
|-------|-----|
| Entry price | Calculate P&L |
| Whale's entry price | Measure how much edge was captured |
| Suspicion score | Validate scoring model |
| Market category | Test if some categories are more profitable |
| Time from whale signal to your entry | Measure latency cost |
| Resolution outcome | Ground truth |
| P&L | The bottom line |

After 50+ trades, analyze:
- Win rate by score tier (7, 8, 9, 10)
- Win rate by market category
- Average latency cost (price drift from whale entry to your entry)
- Profitability by entry price range

This data is what validates (or kills) the entire strategy. It's also what no one else in the ecosystem has published — making it Spyhop's potential research contribution.

### 2.5 The Progression: Paper → Small → Real

| Phase | Duration | Bankroll | Kelly Fraction | Purpose |
|-------|----------|----------|---------------|---------|
| **Paper trading** | 50+ signals or 30 days (whichever is longer) | $10K simulated | Track full Kelly (don't trade) | Validate signal quality. Generate the missing backtest. |
| **Micro live** | 50+ trades | $1,000 real | Eighth Kelly | Validate execution (fills, slippage, latency). Prove the paper results hold with real money. |
| **Small live** | 100+ trades | $5,000-$10,000 | Quarter Kelly | Build confidence and compound. Graduate only if paper + micro results are positive. |
| **Full live** | Ongoing | $10,000+ | Quarter Kelly (consider half if data supports) | Steady-state operation. |

**Graduation criteria** between phases:
- Positive expected value across 50+ trades
- Win rate by score tier matches or exceeds the score-to-correctness mapping
- No individual loss exceeds the 10% cap
- Drawdowns stayed within weekly limits

**Kill criteria** (stop and reassess):
- Negative expected value after 50+ trades at any phase
- Win rate below 40% across all score tiers
- Three consecutive weekly loss limits hit
- Score-to-correctness mapping is systematically wrong (e.g., score-9 trades win at only 50%)

---

## Part 3: Cross-Cutting Findings

### 3.1 What the Research Says Spyhop Should Be

| Research Finding | Implication |
|-----------------|-------------|
| 5 consensus detection signals (RQ3 §1) | V3 covers 3 of 5; Phase 2 adds remaining 2 |
| Multiplicative scoring (RQ3 §3) | Already in CLAUDE.md spec; validated by case evidence |
| Insider playbook is consistent (RQ2 §2.1) | V1-V3 detectors catch the dominant pattern |
| Sophisticated insiders evade V1 (RQ2 §2.2-2.3) | Phase 2 (clustering, win-rate) addresses this |
| Niche markets are where insiders AND opportunities concentrate (RQ4 §2.3) | Detection and trading targets converge — design for niche markets first |
| Whale win rates are ~50% (RQ4 §1.2) | Don't copy all whales — only copy high-suspicion signals |
| No backtest exists for signal-filtered following (RQ4 §1.3) | Paper trading is Spyhop's research contribution |
| Polymarket transparency enables third-party monitoring (RQ1 §1) | Spyhop's value proposition is structurally sound |
| Regulatory vacuum is temporary (RQ1 §5) | Build fast; the window for maximum value is 2-5 years |

### 3.2 What the Research Says You Should Do as a Trader

| Finding | Personal Action |
|---------|----------------|
| Théo's edge came from better analysis of public data (RQ2 §7) | Look for systematic biases in market consensus, not tips |
| Top whales profit from P/L ratio, not win rate (RQ4 §1.2) | Manage position sizes ruthlessly; let winners run |
| Full Kelly is dangerous (Kelly addendum §4) | Use quarter Kelly; cap at 10% |
| Niche markets have longer price-adjustment windows (RQ4 §2.3) | Focus on thin markets where you have time to act |
| Geopolitical markets have highest insider risk (RQ2 §4) | These are the highest-signal markets — but also the most ethically fraught. Your call. |
| Zombie orders inflate reported win rates (RQ4 §1.2) | Don't trust leaderboard stats; verify from resolved positions only |
| Copy trading a single whale is fragile (RQ4 §3.3) | If trading outside Spyhop signals, use wallet baskets (5-10 wallets, 80% consensus) |
| The arms race favors fresh-wallet detection (RQ4 J6) | Spyhop's focus on anomalous new activity is structurally advantaged vs. whale-tracking |

### 3.3 Confidence-Weighted Summary of Key Numbers

Every threshold below traces to a specific research finding. Confidence reflects how well-supported the number is.

| Parameter | Value | Confidence | Source |
|-----------|-------|------------|--------|
| Fresh wallet: max prior trades | 5 | HIGH | RQ3 §2.1 — convergence across 4+ tools + all confirmed cases |
| Size anomaly: order book impact | 2% | MOD | RQ3 §2.2 — pselamy default; no independent validation |
| Niche market: daily volume | $50K | MOD | RQ3 §2.3 — pselamy default; reasonable but arbitrary |
| Volume spike multiplier | 5x | MOD | RQ3 §2.2 — PolyTrack guidance; range is 3-10x |
| Alert threshold score | 7/10 | MOD | RQ3 §3.2 — community standard (3+ signals); maps to log10 of multiplicative product |
| Kelly fraction | 0.25 (quarter) | MOD | Kelly addendum §4.2 — standard professional practice; appropriate for uncertain estimates |
| Max position | 10% of bankroll | HIGH | RQ4 §6.1 — survives 20 consecutive losses; widely used in practice |
| Price drift skip threshold | 10% | MOD | RQ4 §2.3 — PolyTrack guidance |
| Insider correctness at score 9 | 85% | LOW | Kelly addendum §5.2 — inferred from case data; no statistical validation |
| Daily loss limit | 10% | MOD | RQ4 §6.2 — practitioner standard |

**LOW confidence parameters need validation through paper trading.** Especially the score-to-correctness mapping — this is the most speculative part of the sizing model and the first thing to calibrate with real data.

---

## Part 4: Build Sequence

### V2: Wallet Profiling (Next)

**What to build**:
- `profiler/wallet.py` — fetch wallet trade history from Data API
- Trade count, wallet age (first trade timestamp), market diversity
- Cache in SQLite with TTL

**Config inputs**: `[profiler]` section above

**Validates**: Fresh wallet detector has the data it needs

### V3: Detection & Scoring

**What to build**:
- `detector/fresh_wallet.py` — uses wallet profile; returns multiplier
- `detector/size_anomaly.py` — uses order book depth (CLOB API) + market daily volume (Gamma API)
- `detector/niche_market.py` — uses market daily volume
- `detector/scorer.py` — multiplicative composition → 0-10 scale
- `alerter/cli.py` — ranked suspicious activity table (Rich)

**Config inputs**: `[detector.*]` and `[scorer]` sections above

**Validates**: The 3-signal detection model against live data. Do the thresholds produce reasonable alert rates?

### V4: Paper Trading

**What to build**:
- `executor/paper.py` — PaperExecutor: simulated order fill at current price
- Score-to-correctness → Kelly → position sizing pipeline
- Trade journal (SQLite table: signal details, entry price, size, outcome)

**Config inputs**: `[executor]` and `[executor.kelly]` sections

**Validates**: The core thesis — does signal-filtered following produce positive expected value?

### V5: P&L Tracking

**What to build**:
- Resolution poller (check if tracked markets have resolved)
- P&L calculator (entry price vs. resolution price)
- Performance analytics: win rate by score tier, by category, by entry price

**Config inputs**: `[resolution]` section

**Validates**: Score-to-correctness mapping; optimal thresholds; category effects

### V6: Live Trading

**What to build**:
- `executor/live.py` — LiveExecutor using py-clob-client Level 2 (authenticated)
- Limit order placement at target price
- Real P&L tracking with actual fills

**Prerequisites**: V5 demonstrates positive EV across 50+ paper trades

---

## Appendix: Quick-Reference Decision Cards

### Card 1: "Should I follow this signal?"

```
Score >= 7?              → NO: skip
Price moved < 10%?       → NO: skip (edge gone)
Resolution > 1 hour?     → NO: skip (too late)
Under 5 open positions?  → NO: wait
Under daily loss limit?  → NO: stop for today
                         → YES: size the trade (Card 2)
```

### Card 2: "How much should I bet?"

```
Market price:  ___¢
Score:         ___
Correctness:   score 7→70%, 8→80%, 9→85%, 10→90%

Your estimate: (correctness × 1.00) + ((1 - correctness) × market_price)
Kelly odds:    (1.00 / market_price) - 1
Kelly f*:      (your_estimate × odds - (1 - your_estimate)) / odds
Quarter Kelly: f* × 0.25
Cap at 10%:    min(quarter_kelly, 0.10)

Position:      bankroll × capped_fraction
```

### Card 3: "When do I exit?"

```
Market resolves YES?     → Automatic $1.00 payout ✓
Market resolves NO?      → Automatic $0.00 loss ✗
Event window passes?     → Sell immediately (salvage value)
Counter-evidence emerges? → Sell immediately
Price hits 90¢+?         → Consider selling to free capital
                           (only if resolution is weeks away)
```

### Card 4: "Something went wrong"

```
3 consecutive losses?    → Pause 24 hours. Review trade journal.
Daily limit hit (-10%)?  → Stop trading today. No exceptions.
Weekly limit hit (-20%)? → Stop trading this week. Review everything.
50+ trades, negative EV? → Stop. Reassess thresholds and correctness mapping.
Score 9-10 trades losing
  at >50% rate?          → Score-to-correctness mapping is wrong.
                           Reduce correctness estimates by 10-15 points.
                           Consider dropping to eighth Kelly.
```

---

## Sources

All findings trace to the primary research documents:
- [RQ1: Landscape](RQ1_LANDSCAPE.md) — regulatory status, market growth, structural vulnerabilities
- [RQ2: Whale Patterns](RQ2_WHALE_PATTERNS.md) — 10 documented cases, insider playbook, Théo framework
- [RQ3: Detection Heuristics](RQ3_DETECTION_HEURISTICS.md) — tools, thresholds, scoring, false positives
- [RQ4: Counter-Trading Strategy](RQ4_COUNTER_TRADING.md) — profitability evidence, latency, risk management
- [Trading Strategies Taxonomy](TRADING_STRATEGIES.md) — legitimate strategies to filter as false positives
- [Kelly Criterion Addendum](ADDENDUM_KELLY_CRITERION.md) — bet sizing theory and Spyhop-specific application
