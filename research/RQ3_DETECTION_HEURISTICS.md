# RQ3: Detection Heuristics — What Practitioners Actually Use

**Central question**: What heuristics do on-chain analysts, competing tools, and trading communities use to flag suspicious Polymarket activity?

**Research date**: 2026-03-05

---

## Executive Summary

The Polymarket insider detection ecosystem has matured rapidly since 2024. At least seven distinct tools and multiple on-chain research teams now monitor whale and insider activity. Despite different approaches, the community has converged on a core set of heuristics organized around five signal categories: **wallet freshness**, **size anomaly**, **market niche**, **temporal proximity**, and **wallet clustering**. The most reliable detection comes from signal compounding — a single flag is noise; three or more flags together reliably identify suspicious activity.

This document catalogs practitioner heuristics with specific thresholds, assesses their reliability, and maps each to Spyhop's detection architecture.

---

## 1. Existing Tools & Their Approaches

### 1.1 Polywhaler

- **Type**: Commercial SaaS whale tracker
- **Signals**: Monitors $10K+ trades in real-time, market sentiment, AI-powered predictions
- **Thresholds**: $10K minimum trade size for alerts
- **Scoring**: Proprietary; not publicly documented
- **Sources**: [T3] [Polywhaler](https://www.polywhaler.com/)

### 1.2 pselamy/polymarket-insider-tracker (Open Source)

- **Type**: Open-source Python pipeline (PostgreSQL + Redis + Docker)
- **Architecture**: Polymarket CLOB API → Wallet Profiler → Anomaly Detector → Alert Dispatcher
- **Detection signals**:
  - **Fresh Wallet**: < 5 lifetime transactions on Polygon, min $1K trade
  - **Liquidity Impact**: > 2% of visible order book consumed
  - **Sniper Cluster**: DBSCAN clustering — wallets entering within minutes of creation
  - **Event Correlation**: Positions opened 1-4 hours before news breaks
- **Scoring**: Multi-factor heuristic — "HIGH (3/4 signals triggered)" model. No probabilistic formula in v1; composite count of triggered signals
- **Anomaly formula** (from docs): `sqrt(size_z² + timing_z² + wallet_age_z² + activity_z² + price_z²) / sqrt(5)`, normalized 0-1
- **Insider probability**: `anomaly_score * 0.4 + pattern_match_score * 0.4 + correct_outcome_boost * 0.2`
- **Config env vars**: `MIN_TRADE_SIZE_USDC=1000`, `FRESH_WALLET_MAX_NONCE=5`, `LIQUIDITY_IMPACT_THRESHOLD=0.02`
- **Track record**: Flagged a wallet that turned $35K → $442K (12.6x) with 5 alerts before event
- **Sources**: [T2] [GitHub](https://github.com/pselamy/polymarket-insider-tracker)

**[ASSERTION]**: The pselamy tracker's z-score composite formula is the most transparent scoring approach in the ecosystem and represents a reasonable starting point for Spyhop's scorer.
**Confidence**: MOD
**Sources**: T2 (GitHub documentation)
**Analytic basis**: Formula is published but no public backtest validates its discrimination power. The 0.4/0.4/0.2 weighting is not empirically justified in the docs.
**Implication for Spyhop**: Adopt the z-score composite as a baseline, but replace the `correct_outcome_boost` term (requires post-resolution data) with a timing-proximity signal for real-time use.

### 1.3 Polymarket Whale Tracker (Chrome Extension)

- **Type**: Browser extension with background polling
- **Thresholds**: Default $25K; user-configurable $10K–$100K
- **Method**: Polls Polymarket APIs every 5 min (background) / 30 sec (active)
- **Wallet ID**: Assigns consistent pseudonymous identifiers (e.g., "Institutional Whale #5678") for cross-market tracking
- **Sources**: [T3] [Chrome Web Store](https://chromewebstore.google.com/detail/polymarket-whale-tracker/onhhaghaecempnnodenjjlhkobgpkkfj)

### 1.4 PolyInsider

- **Type**: Real-time dashboard
- **Key feature**: "Insider Trades" — tracks new wallets making $5K+ first-time bets
- **Threshold**: $5K first bet from fresh account
- **Sources**: [T3] [Polymark.et listing](https://polymark.et/product/polyinsider)

### 1.5 PolyTrack

- **Type**: Analytics platform with cluster detection
- **Signals**: Wallet clustering (funding, timing, behavior), volume alerts, position timing vs news/events, historical performance
- **Whale classification**: $100K+ total historical volume
- **Cluster detection**: Automated identification of related wallets based on funding source, timing overlap, and behavioral fingerprints
- **Sources**: [T2] [PolyTrack](https://www.polytrackhq.app/blog/detect-insider-trading-polymarket)

### 1.6 Unusual Predictions (Unusual Whales)

- **Type**: Extension of established stock/options surveillance platform
- **Signals**: Trader profitability, historical records, bet timing
- **Approach**: Surfaces historical whale records so followers can assess track record before copying
- **Sources**: [T2] [Unusual Whales](https://unusualwhales.com/predictions), [Finance Magnates](https://www.financemagnates.com/cryptocurrency/unusual-whales-extends-insider-radar-to-prediction-markets-with-unusual-predictions/)

### 1.7 PolyGains

- **Type**: Whale trading terminal
- **Method**: Monitors the CTF Exchange contract on Polygon, analyzing every matched order
- **Sources**: [T3] [PolyGains](https://polygains.com/)

**[ASSERTION]**: The tool ecosystem has converged on a common signal set (fresh wallet, size, niche market, timing, clustering) despite being independently developed. This convergence suggests these are the genuine discriminating signals.
**Confidence**: HIGH
**Sources**: T2/T3 (7 independent tools reviewed)
**Analytic basis**: Independent convergence across commercial, open-source, and community tools. No tool adds radically different signal types — differences are in thresholds and scoring, not signal selection.
**Implication for Spyhop**: Spyhop's Phase 1 detector set (fresh wallet, size anomaly, niche market) covers 3 of the 5 consensus signals. Phase 2 should prioritize temporal clustering and wallet cluster detection.

---

## 2. Signal Catalog: Thresholds & Confidence

### 2.1 Fresh Wallet Detection

| Parameter | Practitioner Range | Recommended Default | Confidence |
|-----------|-------------------|---------------------|------------|
| Max prior trades | 0–5 | **5** | HIGH |
| Min trade size to flag | $1K–$5K | **$1,000** | MOD |
| Wallet age (days) | < 1 day – < 7 days | **< 7 days** | MOD |

**What practitioners look for**:
- Wallets with zero prior Polymarket activity making large first bets
- Proxy wallet age vs. trade count (a fresh proxy may belong to an experienced crypto user — check Polymarket trade count, not raw Polygon nonce)
- Wallets created specifically for a single bet, then abandoned after resolution

**Red flag multiplier**: Fresh wallet + large bet + niche market = exponentially more suspicious. PANews found that in the Iran strikes case, many insider wallets "completed all transactions within the same block in just a few minutes" — created, funded, bet, all in one session.

**False positive sources**:
- New legitimate users who happen to start with a large bet
- Users migrating from another platform
- Institutional traders deploying new proxy wallets

**[ASSERTION]**: The "< 5 prior trades" threshold is well-established across practitioners and supported by multiple confirmed insider cases where wallets had 0-2 prior trades.
**Confidence**: HIGH
**Sources**: T2 (pselamy tracker, PolyInsider, PANews analysis, Bubblemaps)
**Analytic basis**: Every documented insider case (Iran strikes, Axiom, geopolitical events) involved wallets with minimal prior activity. The < 5 threshold captures these while allowing legitimate but new users some buffer.
**Implication for Spyhop**: Use 5 as default `FRESH_WALLET_MAX_TRADES`. Consider a sliding scale: 0 trades = maximum suspicion, 1-2 = high, 3-5 = moderate.

### 2.2 Size Anomaly Detection

| Parameter | Practitioner Range | Recommended Default | Confidence |
|-----------|-------------------|---------------------|------------|
| Whale trade floor | $5K–$25K | **$10,000** | MOD |
| Order book impact | > 2% of depth | **2%** | MOD |
| Volume ratio | > 5-10x daily norm | **5x daily average** | MOD |
| Capital concentration | 40-60%+ on single position | **Not for V1** | LOW |

**What practitioners look for**:
- Trade size relative to market liquidity (not absolute dollars) — $10K on a $5M market is noise; $10K on a $50K market is a signal
- Volume spikes 5-10x normal levels in hours before announcements
- Heavily one-sided flow: 95%+ of volume in one direction without a public catalyst
- Position sizes 5-10x larger than the trader's typical amounts

**PolyTrack's guidance**: "Volume that's 5-10x normal levels in the hours before a major announcement" is the primary size-based red flag.

**[ASSERTION]**: Size anomaly is most meaningful when measured relative to market liquidity, not as an absolute dollar threshold. The 2% order-book-impact threshold from pselamy is a reasonable starting point.
**Confidence**: MOD
**Sources**: T2 (pselamy, PolyTrack), T3 (community consensus)
**Analytic basis**: Absolute dollar thresholds ($10K, $25K) are useful as noise filters but don't distinguish meaningful impact. A $10K bet on a thin niche market is far more suspicious than $10K on a presidential election market. Relative sizing captures this.
**Implication for Spyhop**: Implement both an absolute floor ($10K default) and a relative measure (% of order book depth or daily volume). The relative measure should drive scoring; the absolute floor is just a noise filter.

### 2.3 Niche Market Detection

| Parameter | Practitioner Range | Recommended Default | Confidence |
|-----------|-------------------|---------------------|------------|
| Low-volume threshold | < $50K daily volume | **$50,000** | MOD |
| Market age factor | New markets (< 48h) | **Flag but don't score** | LOW |

**What practitioners look for**:
- Low-volume markets where a single bet can move the price significantly
- Markets on obscure or specialized topics where information asymmetry is highest
- Markets where resolution depends on a decision by a small number of people (e.g., government officials, corporate boards)

**Key insight from HN discussion**: Markets where "a person can change the decision" are structurally vulnerable to insider trading — the information edge is inherent, not circumstantial.

**[ASSERTION]**: Niche market detection is a strong signal but only in combination with other factors. Many legitimate traders prefer niche markets for genuine edge.
**Confidence**: MOD
**Sources**: T2 (pselamy), T3 (HN discussion, community analysis)
**Analytic basis**: Niche markets have higher base rates of both informed trading AND legitimate contrarian analysis. The signal is ambiguous alone but powerfully discriminating when compounded with fresh wallet + timing.
**Implication for Spyhop**: Use < $50K daily volume as the niche threshold. Apply as a multiplier to other signals, not a standalone alert trigger.

### 2.4 Temporal Proximity (Timing Signals)

| Parameter | Practitioner Range | Recommended Default | Confidence |
|-----------|-------------------|---------------------|------------|
| Pre-event window | 30 min – 4 hours | **1-4 hours** | HIGH |
| Volume spike threshold | 3-5x baseline | **5x baseline** | MOD |
| Off-hours trading | Late night, weekends | **Flag as modifier** | LOW |
| Pre-event exit | Hours-days before negative news | **Phase 2** | LOW |

**What practitioners look for**:
- Large positions placed 30 minutes to 2 hours before breaking news
- Entry at 15-25% odds that eventually resolve at 90-100%
- Sustained accumulation over days before a public catalyst emerges
- Trading during off-hours when fewer participants are active
- Volume spikes without any corresponding public catalyst
- Multiple coordinated wallet exits simultaneously

**Iran strikes case study**: Bubblemaps found that most insider wallets were "funded within 24 hours before the attack and bought 'Yes' shares just hours before explosions were reported." PANews identified a "vacuum period" where 521 addresses frantically accumulated positions.

**[ASSERTION]**: Temporal proximity to resolution/event is the single most discriminating signal for insider detection, but requires event timestamps for retrospective analysis. For real-time detection, the absence of a public catalyst for a volume spike is the operational equivalent.
**Confidence**: HIGH
**Sources**: T1 (Bubblemaps forensic analysis, PANews on-chain tracking), T2 (PolyTrack, pselamy)
**Analytic basis**: Every confirmed or strongly suspected insider case shows concentrated activity in the 1-24 hour window before an event. This pattern is consistent across geopolitical (Iran), crypto (Axiom), and political markets.
**Implication for Spyhop**: Phase 1 can implement a lightweight version — flag when large trades on soon-to-resolve markets come from fresh wallets. Full temporal clustering (DBSCAN) is Phase 2.

### 2.5 Wallet Clustering / Sybil Detection

| Parameter | Practitioner Range | Recommended Default | Confidence |
|-----------|-------------------|---------------------|------------|
| Funding source overlap | Same exchange/master wallet | **Phase 2** | HIGH |
| Timing synchronization | Within minutes | **Phase 2** | HIGH |
| Behavioral fingerprints | Similar sizes, patterns | **Phase 2** | MOD |
| Common market overlap | 20-70+ shared markets | **Phase 2** | MOD |

**What practitioners look for**:
- Multiple wallets funded from the same exchange account or master wallet
- Synchronized trading within minutes across different wallets
- Similar position sizes and behavioral fingerprints
- Round-number funding amounts (e.g., exactly 10,000 USDC from the same source)
- Wallets created around the same timeframe with identical trading patterns

**Chainalysis methodology (French whale case)**: Identified 11 accounts belonging to Théo through wallet clustering analysis using "sophisticated heuristics that detect common ownership by examining transaction patterns, timing, funding sources, and behavioral signatures."

**PANews methodology (Iran 521 addresses)**: Cross-referenced "number of common markets, consistency of direction, and time overlap" to find coordinated clusters sharing "20-70 common markets" and "150 identical derivative orders."

**[ASSERTION]**: Wallet clustering is the highest-confidence signal for identifying coordinated insider activity, but is the most technically complex to implement. It requires funding-chain tracing (Polygon RPC) and behavioral fingerprinting.
**Confidence**: HIGH
**Sources**: T1 (Chainalysis, Bubblemaps), T2 (PANews)
**Analytic basis**: Both the French whale (11 accounts) and Iran strikes (521 addresses) cases were cracked primarily through cluster analysis. Single-wallet analysis would have missed the scale of coordinated activity.
**Implication for Spyhop**: Critical for Phase 2. Phase 1 can flag individual suspicious wallets; Phase 2 connects them. Funding-source overlap is the simplest cluster signal to implement first.

---

## 3. Composite Scoring Approaches

### 3.1 pselamy Anomaly Score

```
anomaly_score = sqrt(size_z² + timing_z² + wallet_age_z² + activity_z² + price_z²) / sqrt(5)
```
Normalized to 0-1 range. Each component is a z-score measuring standard deviations from "normal" behavior.

**Insider probability**:
```
insider_probability = anomaly_score * 0.4 + pattern_match_score * 0.4 + correct_outcome_boost * 0.2
```

### 3.2 Signal-Count Heuristic (Community Standard)

Most practitioners use a simpler approach:
- 1 signal: Monitor / log
- 2 signals: Elevated suspicion
- 3 signals: Alert / flag for review
- 4+ signals: High confidence insider indicator

This aligns with Spyhop's planned 0-10 composite where alert threshold is >= 7.

### 3.3 PANews 8-Criteria Rating

Applied to the Iran/Khamenei case:
1. Early buy-in at low prices before increases
2. Trading exclusively in winners' direction
3. Precise targeting of specific markets
4. Activity concentrated in narrow time windows
5. Holding through settlement (no early exit)
6. High ROI
7. Extremely short wallet active period
8. Large absolute profits

Addresses meeting 5+ of 8 criteria were flagged as suspicious.

**[ASSERTION]**: Signals should compound multiplicatively, not just add. A fresh wallet making a large bet on a niche market hours before resolution is exponentially more suspicious than each signal individually.
**Confidence**: HIGH
**Sources**: T2 (pselamy, PANews, PolyTrack), T3 (community consensus)
**Analytic basis**: Every confirmed insider case exhibits 3+ compounding signals. The z-score Euclidean norm approach from pselamy partially captures this (squared terms), but a multiplicative approach may better reflect the exponential increase in suspicion.
**Implication for Spyhop**: Spyhop's scorer should use multiplicative compounding. Proposed: `composite = base_score * Π(signal_multipliers)` where each triggered signal multiplies the score. This naturally produces the exponential scoring the research supports.

---

## 4. False Positive Landscape

### 4.1 Legitimate Whales That Look Suspicious

| Behavior | Looks Like | Actually Is |
|----------|-----------|-------------|
| Market maker rebalancing | Large opposing trades | Delta-neutral liquidity provision |
| Arbitrage bot | Rapid coordinated trades | Cross-market price correction |
| Institutional new account | Fresh wallet, large bet | Fund deploying through new proxy |
| Théo-style contrarian | Massive concentrated bet | High-conviction informed analysis (not insider) |
| Hedge leg | One-sided bet on niche market | Part of a multi-market hedge |

### 4.2 The Whale Win Rate Illusion

PANews analysis of 27,000 trades by the top 10 Polymarket whales revealed:

| Trader | Reported Win Rate | Actual Win Rate |
|--------|------------------|-----------------|
| SeriouslySirius | 73.7% | 53.3% |
| DrPufferfish | 83.5% | 50.9% |
| gmanas | — | 51.8% |
| simonbanza | — | 57.6% |
| RN1 | — | 42% (net loss) |

The gap is caused by "zombie orders" — unclosed positions that inflate reported win rates. SeriouslySirius held 2,369 open orders with 1,791 completely failed positions left unsettled.

**Key finding**: Top whale profitability comes from profit/loss ratio management (DrPufferfish: $37.2K avg win vs. $11K avg loss, 8.62 P/L ratio), NOT from high win rates. This is critical for distinguishing insiders (who have genuinely high win rates on specific event types) from skilled traders (who manage position sizing).

**[ASSERTION]**: Reported Polymarket win rates are unreliable due to zombie orders. Any detection system using win rate as a signal must calculate it from closed/resolved positions only.
**Confidence**: HIGH
**Sources**: T2 (PANews analysis of 27,000 trades)
**Analytic basis**: Systematic analysis with specific trader-level data showing 20-30 percentage point discrepancies between reported and actual win rates.
**Implication for Spyhop**: Phase 2 win-rate anomaly detector must filter out unclosed positions. Use only resolved markets for win-rate calculation. True insider signal: high win rate on *specific event categories* (geopolitical, crypto announcements), not overall.

### 4.3 Market Maker vs. Directional Bettor

Market makers on Polymarket:
- Trade both sides of a market
- Appear as "whales" by volume but are liquidity providers
- Often use multiple wallets for different strategies
- Position sizes are proportional to available liquidity, not conviction

**Detection approach**: If a wallet has roughly balanced YES/NO exposure across a market (or across related markets), it's likely a market maker. Directional insiders take one-sided bets.

---

## 5. Known Blind Spots & Evasion Techniques

### 5.1 Documented Evasion Methods

| Technique | How It Works | Detection Difficulty |
|-----------|-------------|---------------------|
| **Trade splitting** | Break large bet into many small trades across time | Medium — aggregate analysis catches it |
| **Wallet rotation** | New wallet for each bet; never reuse | High — no history to analyze |
| **VPN + fresh crypto** | Anonymize identity and funding source | High — no KYC on Polymarket |
| **Delayed accumulation** | Build position slowly over days/weeks | High — blends with normal activity |
| **Multi-wallet Sybil** | Distribute across 10-100+ wallets below detection thresholds | Medium — cluster analysis catches it |
| **OTC settlement** | Trade off-platform; settle privately | Very High — invisible to on-chain monitoring |
| **Opposite-side noise** | Place small opposing bets to appear balanced | Medium — net exposure analysis catches it |

### 5.2 Structural Blind Spots

- **No KYC**: Polymarket doesn't verify identity, so attribution requires blockchain forensics only
- **Proxy wallet indirection**: The proxy wallet architecture adds a layer between the user's EOA and their trades
- **Kalshi opacity**: Kalshi (the regulated competitor) doesn't expose on-chain data, so insider activity there is invisible to public analysis
- **Sophisticated insiders**: The most dangerous insiders (e.g., government officials with classified information) are unlikely to use obviously fresh wallets — they may have established accounts with normal-looking history
- **Information gradients**: Some traders have partial information (e.g., a journalist about to publish) that is technically non-public but not "classified" — this sits in a gray zone

**[ASSERTION]**: Current detection methods are biased toward catching unsophisticated insiders who use fresh wallets and large bets. Sophisticated insiders with established accounts, distributed positions, and slow accumulation are largely invisible to existing tools.
**Confidence**: HIGH
**Sources**: T2 (Gizmodo investigation), T3 (HN discussion, community analysis)
**Analytic basis**: Every documented "caught" case involves obvious signals (fresh wallet, concentrated bet, tight timing). Selection bias — we only know about the ones who were caught. The absence of evidence for sophisticated insider activity is not evidence of absence.
**Implication for Spyhop**: V1 should focus on catching the unsophisticated majority (which is still valuable). V2+ should add behavioral baseline comparison (is this wallet acting differently than its own history?) to catch sophisticated actors.

---

## 6. Recommended Spyhop Defaults

Based on practitioner convergence and documented cases, the following defaults are recommended for Spyhop's Phase 1 configuration:

### 6.1 Noise Filter (Pre-Scoring Gate)

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `min_trade_size_usd` | $1,000 | pselamy default; catches small insider bets while filtering micro-trades |
| `alert_threshold_usd` | $10,000 | Community consensus whale floor; below this, only flag if other signals compound |

### 6.2 Detector Thresholds

| Detector | Parameter | Default | Source Convergence |
|----------|-----------|---------|-------------------|
| FreshWallet | `max_prior_trades` | 5 | HIGH — pselamy, PolyInsider, case evidence |
| FreshWallet | `wallet_age_days` | 7 | MOD — varies across tools |
| SizeAnomaly | `orderbook_impact_pct` | 0.02 (2%) | MOD — pselamy default |
| SizeAnomaly | `volume_spike_multiplier` | 5.0 (5x daily avg) | MOD — PolyTrack guidance |
| NicheMarket | `max_daily_volume_usd` | 50,000 | MOD — pselamy default |

### 6.3 Scoring Formula (Proposed)

```
# Phase 1: Multiplicative compounding
base_score = 1.0

if fresh_wallet:    base_score *= fresh_multiplier    # 2.0-3.0 based on how fresh
if size_anomaly:    base_score *= size_multiplier     # 1.5-3.0 based on magnitude
if niche_market:    base_score *= niche_multiplier    # 1.5-2.5 based on how niche

composite = min(10, log_scale(base_score))  # Map to 0-10 scale
alert if composite >= 7
```

This differs from pselamy's additive z-score approach by using multiplicative compounding, which better reflects the practitioner consensus that signal co-occurrence is exponentially more suspicious than any single signal.

### 6.4 Alert Tiers

| Score | Tier | Action |
|-------|------|--------|
| 0-3 | Normal | Log only |
| 4-6 | Elevated | Display in monitoring table |
| 7-8 | Suspicious | Alert + flag for review |
| 9-10 | Critical | Immediate alert + full wallet audit |

---

## 7. Key Cases Referenced

| Case | Date | Signals Present | Detection Method | Outcome |
|------|------|----------------|-----------------|---------|
| French Whale (Théo) | Oct-Nov 2024 | Size (massive), multi-wallet | Chainalysis cluster analysis | $85M profit; no insider finding |
| Iran strikes cluster | Feb 2026 | Fresh wallet, timing, clustering, niche | Bubblemaps, PANews | $1.2M+ across 6+ wallets; Israeli indictments |
| Khamenei death (Magamyman) | Mar 2026 | Timing, win streak, geopolitical niche | On-chain analysis | $553K; Israeli police investigation |
| Axiom/ZachXBT | Feb 2026 | Fresh wallet, single-market concentration, timing | Defioasis on-chain analysis | $1.2M across 8 insider wallets |
| 521 Khamenei addresses | Feb-Mar 2026 | 8-criteria PANews rating; 62 exclusively Iran-focused | PANews forensic analysis | Coordinated cluster identified |

---

## 8. Open Questions for Further Research

1. **Calibration data**: No public dataset exists of confirmed-insider vs. confirmed-legitimate trades. Without ground truth, threshold tuning is heuristic, not empirical.
2. **Market maker identification**: How to reliably distinguish market makers from directional whales in real-time without historical context?
3. **Cross-platform leakage**: Do insiders who trade on Polymarket also trade on Kalshi? Is there a detectable funding-flow correlation?
4. **Optimal scoring weights**: The 0.4/0.4/0.2 weighting in pselamy's formula and our proposed multiplicative approach are both unvalidated. Backtesting against known cases would improve confidence.
5. **Evasion adaptation**: As detection tools become more visible, are insiders adapting their behavior? Is there evidence of threshold-aware trade splitting?

---

## Sources

### T1 (Primary Evidence)
- Bubblemaps forensic analysis of Iran strike wallets — [The Block](https://www.theblock.co/post/391650/fresh-accounts-netted-1-million-on-polymarket-hours-before-us-airstrikes-on-iran-bubblemaps)
- Chainalysis wallet clustering analysis (French whale) — via [Fortune](https://fortune.com/2024/11/02/french-whale-polymarket-30-million-donald-trump-election-bet-kamala-harris/), [Yahoo Finance](https://finance.yahoo.com/news/polymarket-whale-actually-made-85-050139914.html)
- Israeli indictments for insider trading on Polymarket — [Al Jazeera](https://www.aljazeera.com/economy/2026/3/4/traders-mint-money-on-betting-platforms-on-us-israel-strike-on-iran)
- Columbia University study on wash trading (~25% fake volume) — [CoinDesk](https://www.coindesk.com/markets/2025/11/07/polymarket-s-trading-volume-may-be-25-fake-columbia-study-finds)
- Academic ML approaches to insider detection — [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-024-00500-2)

### T2 (Credible Secondary)
- pselamy/polymarket-insider-tracker — [GitHub](https://github.com/pselamy/polymarket-insider-tracker)
- NickNaskida/polymarket-insider-bot — [GitHub](https://github.com/NickNaskida/polymarket-insider-bot)
- PANews: 521 addresses Iran/Khamenei analysis — [PANews](https://www.panewslab.com/en/articles/019caef8-7f10-7114-b20e-35dd654a54be)
- PANews: 27,000 trades whale analysis — [PANews](https://www.panewslab.com/en/articles/516262de-6012-4302-bb20-b8805f03f35f)
- PolyTrack insider detection guide — [PolyTrack](https://www.polytrackhq.app/blog/detect-insider-trading-polymarket)
- Gizmodo: Tracking insider trading as a business — [Gizmodo](https://gizmodo.com/tracking-insider-trading-on-polymarket-is-turning-into-a-business-of-its-own-2000709286)
- CoinDesk: Axiom insider trading — [CoinDesk](https://www.coindesk.com/markets/2026/02/27/polymarket-bettors-appear-to-have-insider-traded-on-a-market-designed-to-catch-insider-traders)
- NPR: Magamyman Khamenei bet — [NPR](https://www.npr.org/2026/03/01/nx-s1-5731568/polymarket-trade-iran-supreme-leader-killing)
- Unusual Whales Predictions — [Finance Magnates](https://www.financemagnates.com/cryptocurrency/unusual-whales-extends-insider-radar-to-prediction-markets-with-unusual-predictions/)

### T3 (Community Intelligence)
- Polywhaler — [polywhaler.com](https://www.polywhaler.com/)
- PolyInsider — [polymark.et](https://polymark.et/product/polyinsider)
- PolyGains — [polygains.com](https://polygains.com/)
- Hacker News discussion: Uncovering insiders with AI — [HN](https://news.ycombinator.com/item?id=47091557)
- DeFi Prime ecosystem guide — [DeFi Prime](https://defiprime.com/definitive-guide-to-the-polymarket-ecosystem)
- Defioasis on-chain analysis (Axiom wallets) — via [CoinDesk](https://www.coindesk.com/markets/2026/02/27/polymarket-bettors-appear-to-have-insider-traded-on-a-market-designed-to-catch-insider-traders)
