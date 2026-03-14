# Spyhop Configuration Reference

Every parameter in `config.toml`, how it works, practical tuning guidance, and research citations.

## How the Controls Layer

The risk controls form a layered funnel. Each layer catches what the previous one doesn't:

```
usd_threshold  (noise floor — drop small trades)
     ↓
  min_score    (conviction gate — only trade high-confidence signals)
     ↓
max_concurrent (slot limit — cap simultaneous positions)
     ↓
max_position_pct (per-bet cap — no single outsized bet)
     ↓
max_exposure_pct (portfolio cap — total capital at risk)
```

The most impactful knobs for live tuning are `min_score` and `max_exposure_pct`. The concurrent limit matters less until V5 (resolution poller) starts closing positions.

**Missing layer:** Per-category exposure (research recommends 20% per category). Without it, all 20 slots could fill with correlated bets (e.g., UFC fights resolving the same night).

---

## [ingestor]

### `usd_threshold = 10_000`

The noise floor — trades below this USD value are dropped before any detection runs.

| Direction | Effect |
|-----------|--------|
| **Raise** (e.g., $25K) | Fewer trades, higher-quality signal, but misses smaller insider bets on niche markets where $10K is enormous |
| **Lower** (e.g., $5K) | Catches more activity on thin markets, but increases noise and API load from wallet profiling |

> **Citation:** SYNTHESIS.md §1.1 — "pselamy default $1K; we use ingestor threshold $10K." RQ3 §2.2 — community consensus settled on $10K–$25K as the effective whale floor.
> **Confidence:** HIGH

### `ws_url = "wss://ws-live-data.polymarket.com"`

RTDS WebSocket endpoint. No reason to change unless Polymarket migrates.

### `reconnect_delay_sec = 5`

Seconds to wait before attempting WebSocket reconnect after disconnect. Based on empirically observed ~20-minute silence freezes.

---

## [market_cache]

### `gamma_url = "https://gamma-api.polymarket.com"`

Gamma API base URL for market metadata lookups.

### `ttl_minutes = 60`

How long market metadata (volume, prices, question text) stays cached. Markets change slowly; 1 hour is reasonable.

---

## [profiler]

### `max_trades_to_fetch = 200`

How many historical trades to pull from the Data API when profiling a wallet. Determines how deep we look to decide if a wallet is "fresh."

| Direction | Effect |
|-----------|--------|
| **Raise** | Better accuracy on wallets with moderate history, but slower API calls and more rate-limit pressure |
| **Lower** | Faster profiling, but might misclassify a 50-trade wallet as fresh if you only check 20 |

> **Citation:** SYNTHESIS.md §1.1 (V2 specs). Practical trade-off, not empirically optimized.
> **Confidence:** MOD

### `wallet_cache_ttl_minutes = 30`

How long a wallet's profile stays cached before re-fetching.

| Direction | Effect |
|-----------|--------|
| **Raise** | Fewer API calls, but might miss a wallet that was fresh at 9:00 and active by 9:15 |
| **Lower** | More current profiles, but more API calls — matters at hundreds of whale trades per hour |

> **Citation:** SYNTHESIS.md §1.1. Operational parameter, not research-derived.
> **Confidence:** MOD-LOW

---

## [event_cache]

### `ttl_minutes = 120`

Events (category tags, metadata) change less often than markets. 2-hour cache is conservative.

---

## [detector.fresh_wallet]

### `max_prior_trades = 5`

Wallets with <= this many prior Polymarket trades are flagged as "fresh." The single most validated signal in the research.

| Direction | Effect |
|-----------|--------|
| **Raise** (e.g., 10) | Catches more wallets but dilutes the signal — a 10-trade wallet is much less suspicious than a 0-trade wallet |
| **Lower** (e.g., 2) | Very tight filter, only catches truly virgin wallets. Misses cases like the Axiom insider who had 3-4 prior trades |

> **Citation:** SYNTHESIS.md §1.2, RQ3 §2.1 — "The '<5 prior trades' threshold is well-established across practitioners and supported by multiple confirmed insider cases where wallets had 0-2 prior trades." Convergence across pselamy, PolyInsider, and community tools. Every documented case (Iran strikes, Axiom, OpenAI, Venezuela) involved wallets with 0-5 prior trades.
> **Confidence:** HIGH

### `multiplier_zero = 3.0` / `multiplier_low = 2.5` / `multiplier_mid = 2.0`

Graduated multipliers within the "fresh" band:
- **0 trades** → 3.0x (maximum suspicion)
- **1-2 trades** → 2.5x
- **3-5 trades** → 2.0x
- **>5 trades** → 1.0x (no signal)

| Direction | Effect |
|-----------|--------|
| **Raise** | Fresh wallet signal dominates the composite — a 0-trade wallet on a normal market could reach alert threshold alone |
| **Lower** | Fresh wallet matters less relative to size and niche — requires multiple signals compounding to trigger |

> **Citation:** SYNTHESIS.md §1.1 — "Graduated scoring within the 'fresh' range... 0 trades → multiplier 3.0 (maximum suspicion)." Multiplicative model from §1.2: "practitioner consensus that co-occurring signals are exponentially (not linearly) more suspicious."
> **Confidence:** MOD (graduated framework is sound; specific multiplier values are heuristic)

---

## [detector.size_anomaly]

### `min_trade_usd = 10_000`

Minimum trade size to evaluate for size anomaly. Currently redundant with `ingestor.usd_threshold` — would matter if you lowered the ingestor threshold to catch smaller niche-market trades while keeping size anomaly focused on larger ones.

> **Citation:** SYNTHESIS.md §1.1, RQ3 §2.2 — same sourcing as `usd_threshold`.
> **Confidence:** MOD

### `orderbook_impact_pct = 0.02`

**Reserved for V6 (CLOB integration).** Will flag trades consuming >2% of visible order book depth. Not currently active — requires Level 2 order book data.

> **Citation:** RQ3 §2.2 — "pselamy LIQUIDITY_IMPACT_THRESHOLD=0.02." Practitioners converged on 2% as the threshold for material market impact.
> **Confidence:** MOD

### `volume_spike_multiplier = 5.0`

**Reserved.** Will flag when a trade's volume is 5x the market's daily average. Not currently active.

> **Citation:** RQ3 §2.2 — "PolyTrack guidance: 5-10x normal volume in the hours before a major announcement." 5.0 is the lower (more inclusive) boundary of the recommended range.
> **Confidence:** MOD

### `multiplier_low = 1.5` / `multiplier_mid = 2.0` / `multiplier_high = 3.0`

Graduated multipliers based on trade size relative to 24h market volume:
- **2-5% of volume** → 1.5x
- **5-10% of volume** → 2.0x
- **10%+ of volume** → 3.0x

| Direction | Effect |
|-----------|--------|
| **Raise** | Size anomaly dominates the composite — a single large trade on a liquid market could approach alert threshold |
| **Lower** | Size matters less; need fresh wallet or niche market to compound before alerting |

> **Citation:** SYNTHESIS.md §1.1 — graduated scoring bands. The bands themselves (2%, 5%, 10%) reflect market impact thresholds from pselamy's implementation.
> **Confidence:** MOD

---

## [detector.niche_market]

### `max_daily_volume_usd = 50_000`

Markets with daily volume below this are considered "niche" — where insider information has the most impact because a single bet moves the price.

| Direction | Effect |
|-----------|--------|
| **Raise** (e.g., $100K) | More markets qualify as niche, including mid-tier sports and politics. Wider net but diluted signal |
| **Lower** (e.g., $25K) | Only the thinnest markets qualify — obscure geopolitical bets, small crypto. Very targeted |

> **Citation:** SYNTHESIS.md §1.1, RQ3 §2.3 — "Markets with daily volume below this are 'niche'... confirmed by case analysis." Every confirmed insider case involved niche/thin markets where information asymmetry was highest.
> **Confidence:** MOD (pselamy default, case-confirmed but somewhat arbitrary boundary)

### `multiplier_low = 1.5` / `multiplier_mid = 2.0` / `multiplier_high = 2.5`

Graduated multipliers by market thinness:
- **$25K-$50K daily** → 1.5x
- **$10K-$25K daily** → 2.0x
- **<$10K daily** → 2.5x

Note: Niche tops out at 2.5x vs size anomaly's 3.0x — niche alone is a slightly weaker signal. This reflects the research finding that niche + fresh is the real insider pattern; niche alone could just be a gambler.

> **Citation:** SYNTHESIS.md §1.1 — aligned with RQ2 §4 finding that markets controlled by small groups have highest insider risk.
> **Confidence:** MOD

---

## [scorer]

### `alert_threshold = 7`

Composite score >= 7 triggers an alert (yellow highlight). Also used as the denominator in position sizing: `size = base_position_usd * (score / 7)`.

**How scoring works:** `composite = log₁₀(fresh_mult × size_mult × niche_mult)` normalized to 0-10.
- 1 signal firing → score ~2-4
- 2 signals compounding → score ~5-7
- All 3 signals compounding → score ~7-10

| Direction | Effect |
|-----------|--------|
| **Raise** | Fewer alerts, higher conviction required. Position sizing shrinks (a score-7 trade gets less than base size) |
| **Lower** | More alerts, but the 0-10 scale loses discrimination at the top end |

> **Citation:** SYNTHESIS.md §1.1, RQ3 §3.2 — "Alert threshold score 7/10... community standard (3+ signals)." Maps to log₁₀ of multiplicative product where 3 compounding signals reach ~7.
> **Confidence:** HIGH

### `critical_threshold = 9`

Score >= 9 triggers a critical alert (red highlight). All three detectors firing at high multipliers. Currently UI-only — no different trading behavior.

> **Citation:** SYNTHESIS.md §1.1 — "Score >= 9 triggers immediate full audit." Aligns with PANews 8-criteria rating where 5+ criteria = suspicious.
> **Confidence:** MOD

---

## [display]

### `max_rows = 50`

Maximum trades shown in the live `watch` table. Older trades scroll off. Pure UI parameter, no research basis.

---

## [paper]

### `enabled = true`

Toggle paper trading on/off. Should default to `false` in production to prevent accidental live trading.

> **Citation:** RQ4 §7.2-7.3 — "Paper trading mode is unvalidated. Spyhop must implement paper trading before any real capital deployment."

### `starting_capital = 100_000`

Simulated bankroll. All position sizing is relative to this. Doesn't change strategy — just scales absolute dollar amounts.

> **Citation:** ADDENDUM_KELLY_CRITERION.md §5.4 uses $50K in worked examples. $100K chosen for simulation convenience.
> **Confidence:** MOD-LOW (arbitrary for paper)

### `base_position_usd = 5_000`

Starting point for position sizing before score scaling. A score-7 trade gets exactly $5K. A score-10 trade gets $5K × (10/7) = $7,143.

| Direction | Effect |
|-----------|--------|
| **Raise** | Larger positions, faster capital deployment, higher P&L variance |
| **Lower** | Smaller positions, more conservative, takes longer to see meaningful P&L signal in testing |

> **Citation:** SYNTHESIS.md §2.3, ADDENDUM_KELLY_CRITERION.md §5.2 — aligns with quarter-Kelly on a $100K bankroll (5% = $5K base). RQ4 §6.1 — "Max position per trade: 5% of bankroll... Survive 20 consecutive losses."
> **Confidence:** HIGH (Kelly-grounded)

### `max_position_pct = 0.10`

Hard cap — no single position can exceed 10% of capital ($10K on $100K), regardless of score.

| Direction | Effect |
|-----------|--------|
| **Raise** | Allows larger individual bets on very high-confidence signals. More concentrated risk |
| **Lower** (e.g., 0.05) | Research-recommended value. Survive 20 consecutive total losses. More conservative |

> **Citation:** ADDENDUM_KELLY_CRITERION.md §4.2 — "Maximum position: Never more than 10% of bankroll on a single trade, regardless of Kelly output." RQ4 §6.1 — "5% of bankroll... Survive 20 consecutive losses." Multiple sources converge on the 5-10% range.
> **Confidence:** HIGH

### `max_exposure_pct = 0.50`

Portfolio-level cap — total deployed capital across all open positions can't exceed 50% of bankroll ($50K). This is the **binding constraint** that actually limits risk, especially with `max_concurrent = 20`.

| Direction | Effect |
|-----------|--------|
| **Raise** | More capital at work, but correlated losses (e.g., a market category blowup) hit harder |
| **Lower** (e.g., 0.30) | More cash reserved, survives larger drawdowns, but fewer positions |

> **Citation:** RQ4 §6.2 — portfolio-level controls. The research also recommends a per-category exposure limit of 20% (not yet implemented).
> **Confidence:** MOD

### `max_concurrent = 20`

Maximum simultaneous open positions. Without the resolution poller (V5), this is effectively "total positions ever" since nothing closes.

**Interaction with exposure cap:** At 20 slots with a 50% cap ($50K) and ~$3-5K per position, the exposure cap bites around 10-15 positions. The concurrent limit is the outer guardrail; the exposure cap is the inner one.

| Direction | Effect |
|-----------|--------|
| **Raise** | Exposure cap is the real limit anyway — just allows more small positions to spread across |
| **Lower** (to 5) | Research-recommended. Forces concentration on highest-conviction trades |

> **Citation:** RQ4 §6.2 — "Max open positions: 5... Concentration limits." Current value of 20 is a deliberate test deviation to observe signal flow without the concurrent limit masking it.
> **Confidence:** MOD

### `min_score = 6.0`

Minimum composite score to open a paper position. The gatekeeper for the entire paper trading pipeline.

| Value | Behavior |
|-------|----------|
| **3.0** | Lets in single-signal trades (e.g., "large bet on the Lakers"). ~50% of all signals qualify |
| **6.0** (current) | Requires 2+ detector multipliers compounding (e.g., size 3.0 × niche 2.0 = 5.8) |
| **7.0** (research) | Only alert-level signals enter. Highest conviction, fewest positions |

> **Citation:** RQ4 §6.3 — "Min suspicion score to trade: 7/10... Alert threshold from RQ3." SYNTHESIS.md §2.2 playbook — "Skip if < 7." Current 6.0 is a deliberate test deviation.
> **Confidence:** MOD-HIGH

---

## Research-Recommended Controls Not Yet Implemented

These controls appear in SYNTHESIS.md §1.1 and RQ4 §6.2 but are not in `config.toml`:

| Control | Recommended Value | Source | Purpose |
|---------|-------------------|--------|---------|
| Per-category exposure | 20% of bankroll | RQ4 §6.2 | Prevent correlated bets (e.g., all UFC fights resolving same night) |
| Daily loss limit | 10% of bankroll | RQ4 §6.2 | Circuit breaker after bad day |
| Weekly loss limit | 20% of bankroll | RQ4 §6.2 | Circuit breaker after bad week |
| Consecutive-loss pause | 3 losses → pause | RQ4 §6.2 | Stop trading during cold streaks |

These require V5 (resolution poller) to function, since they depend on knowing realized P&L.
