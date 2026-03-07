# RQ2: Known Whale & Insider Patterns on Polymarket

**Central question**: What specific behavioral signatures distinguish insider/informed traders from legitimate whales on Polymarket?

**Research date**: 2026-03-05

---

## Executive Summary

Since 2024, at least **10 distinct insider trading cases** have been documented on Polymarket, spanning geopolitical events, tech product launches, celebrity news, and corporate earnings. One case (Israel/IDF) has produced criminal indictments — the first globally for prediction market insider trading. Analysis of these cases reveals a remarkably consistent **insider playbook**: create fresh wallet → fund rapidly → place large directional bet on niche/binary market → collect on resolution → abandon wallet. The most sophisticated actors (French whale Théo, KPMG cluster) deviate from this playbook, using multiple accounts, slow accumulation, or domain-specific targeting to evade detection.

This document catalogs known cases, extracts behavioral signatures, and identifies the spectrum from unsophisticated insiders (easily caught) to sophisticated informed traders (largely invisible to current methods).

---

## 1. Case Catalog

### Case 1: The French Whale — Théo (Oct-Nov 2024)

**Category**: Legitimate smart money (NOT insider)
**Market**: 2024 US Presidential Election
**Profit**: ~$85 million (most profitable prediction market trade in history)

**What happened**: A French trader named Théo deployed ~$80M across 11 Polymarket accounts betting on Trump's victory. He commissioned custom YouGov "neighbor polls" in PA, MI, and WI — asking respondents who their *social circle* was voting for rather than who they personally supported. The results showed significantly more Trump support than traditional polls, which he attributed to the "shy Trump voter" effect.

**Wallet behavior**:
- Used 11 separate accounts to distribute position and minimize price impact
- Built position through many small transactions ("to prevent the price of his bets from rising")
- Liquidated virtually all personal liquid assets to fund the wager
- Professional banking background; sophisticated financial modeling

**Detection signals triggered**: Size anomaly (massive), multi-wallet clustering
**Detection signals NOT triggered**: Not a fresh wallet user; had trading history; built position gradually

**Investigation outcome**: Polymarket + third-party intelligence firms found no evidence of insider trading. Classified as "high-conviction trader exploiting mispricing." France's ANJ investigated the platform (not the trader) for gambling regulation compliance.

**[ASSERTION]**: Théo represents the archetype of a legitimate "smart money" whale — someone with a genuine analytical edge, not non-public information. His behavioral signature (gradual accumulation, multiple accounts for execution, commissioned research) is categorically different from insider patterns.
**Confidence**: HIGH
**Sources**: T1 (Chainalysis), T2 (WSJ, Bloomberg, CBS News, Fortune, The Block)
**Analytic basis**: Multiple independent investigations; trader self-identified and explained methodology; custom polling data was independently verifiable.
**Implication for Spyhop**: Théo-style traders will trigger size anomaly and clustering alerts. Spyhop should NOT classify gradual accumulation across established accounts as "insider" — it's a false positive signature that needs to be scored down.

---

### Case 2: Venezuela/Maduro Capture (Jan 2026)

**Category**: Strongly suspected insider
**Market**: "Maduro ousted by January 31?" / "US invades Venezuela?"
**Profit**: ~$436,000 (12x return on $32K)

**What happened**: Hours before Trump announced the capture of Venezuelan leader Maduro, a Polymarket account wagered $32K on Maduro's ouster. The market had been in low single digits for weeks before climbing shortly before 10pm ET on Friday, ahead of Trump's early Saturday morning announcement.

**Wallet behavior**:
- Account created December 27 (days before the event)
- Bet on exactly two things: US invading Venezuela and Maduro being forced out
- Used US crypto exchanges to cash out (not attempting to hide identity)
- Single-purpose wallet abandoned after resolution

**Detection signals triggered**: Fresh wallet, size anomaly, niche market, temporal proximity, single-market concentration
**Signals score**: 5/5 — textbook insider signature

**Investigation outcome**: Chainalysis unable to unmask identity. Rep. Ritchie Torres introduced legislation to ban government officials from prediction market insider trading. 30 House Democrats co-sponsored.

**[ASSERTION]**: The Maduro case is the purest documented example of the "insider playbook" — fresh account, narrow focus, large bet, precise timing, immediate exit. It triggered every known detection signal.
**Confidence**: HIGH
**Sources**: T2 (NPR, PBS, Axios, Fortune, The Hill, Yahoo Finance)
**Analytic basis**: Account age (5 days), single-topic focus, 12x return, timing alignment with classified military operation.
**Implication for Spyhop**: This case validates the compound scoring model. A Spyhop V1 with fresh wallet + size + niche detectors would have flagged this before resolution.

---

### Case 3: Iran Strikes Cluster (Feb 28, 2026)

**Category**: Confirmed insider cluster (criminal indictments in related case)
**Market**: "U.S. strikes Iran by February 28, 2026?"
**Profit**: $1.2M+ across 6+ wallets (Bubblemaps); broader analysis found 521 suspicious addresses (PANews)

**What happened**: Hours before US/Israeli strikes on Tehran, 150+ accounts placed four-figure bets correctly predicting the attack timing. Six accounts identified by Bubblemaps made $1.2M combined. PANews identified 521 suspicious profitable addresses across Iran-related markets.

**Wallet behavior**:
- Most wallets funded within 24 hours of the strike
- Bought "Yes" shares hours before explosions reported
- No prior activity beyond Iran-related predictions
- 62 addresses traded *exclusively* on Iranian markets
- 95 addresses had >50% of activity on Iran markets
- Some wallets completed all transactions "within the same block in just a few minutes" — created, funded, and bet in a single session
- Bubblemaps identified connected funding paths between the 6 core wallets

**Detection signals triggered**: Fresh wallet, timing proximity, niche market, wallet clustering, single-market concentration
**Related criminal case**: Two Israelis (IDF reservist + civilian) indicted in Tel Aviv District Court for using classified military intelligence to bet on Polymarket. Charges include "serious security offenses," bribery, and obstruction of justice. First known criminal prosecution globally for prediction market insider trading.

**PANews 8-criteria analysis of 521 addresses**:
1. Early buy-in at low prices ($0.03-$0.05/share)
2. Trading exclusively in winner's direction
3. Precise targeting of specific markets
4. Activity concentrated in narrow time windows
5. Holding through settlement
6. High ROI
7. Extremely short wallet active period
8. Large absolute profits

Cross-referencing revealed coordinated clusters sharing 20-70 common markets and 150 identical derivative orders.

**[ASSERTION]**: The Iran strikes case represents the most extensively documented insider trading operation on Polymarket, with both on-chain forensic evidence (Bubblemaps, PANews) and real-world criminal prosecution (Israeli indictments). It demonstrates that geopolitical/military markets are the highest-risk category for insider trading.
**Confidence**: HIGH
**Sources**: T1 (Israeli indictments, Bubblemaps forensics), T2 (The Block, CoinDesk, Al Jazeera, Bloomberg, NPR, CBC, PANews)
**Analytic basis**: Criminal charges filed; on-chain cluster analysis by two independent teams; 521 suspicious addresses identified with 8-criteria rating.
**Implication for Spyhop**: Geopolitical/military markets should receive a category-level risk multiplier. The PANews 8-criteria framework is a useful post-hoc validation checklist.

---

### Case 4: Magamyman — Khamenei Death (Mar 2026)

**Category**: Strongly suspected insider (under investigation)
**Market**: "Khamenei removed as Supreme Leader?"
**Profit**: $553,000

**What happened**: The account "Magamyman" made $553K betting on the death of Iran's Supreme Leader Ayatollah Khamenei, killed in an Israeli strike. The same account had a history of accurately predicting Israeli attacks on Iran, with most profits from geopolitical markets.

**Wallet behavior**:
- Repeat trader with established history of geopolitical bets
- Concentrated on Iran-related markets specifically
- Made $430K on the start of the war, $553K on Khamenei's death
- Pattern of accuracy on Israeli military operations specifically

**Detection signals triggered**: Win-rate anomaly (geopolitical category), niche market concentration, temporal proximity
**Detection signals NOT triggered**: Not a fresh wallet — established account with history

**Investigation outcome**: Israeli police opened investigation into whether the account owner has insider information or is extremely lucky.

**[ASSERTION]**: Magamyman represents a more sophisticated insider archetype — an established account with repeat accuracy in a specific domain. Standard "fresh wallet" detection would miss this entirely. Win-rate anomaly detection by category is required.
**Confidence**: MOD
**Sources**: T2 (NPR, Bloomberg, Middle East Eye)
**Analytic basis**: Repeat accuracy on specific event type (Israeli military operations) is statistically improbable through luck alone, but could reflect deep domain expertise or a SIGINT-adjacent information network.
**Implication for Spyhop**: Phase 2 win-rate anomaly detector should segment by market category. A wallet with 90%+ accuracy on geopolitical events but average performance elsewhere is a strong signal.

---

### Case 5: AlphaRaccoon — Google Insider (Dec 2025)

**Category**: Strongly suspected corporate insider
**Market**: Google 2025 Year in Search rankings; Gemini 3.0 Flash launch date
**Profit**: ~$1M+ total ($1M on Year in Search + $150K on Gemini)

**What happened**: Wallet "0xafEe" (alias AlphaRaccoon) correctly predicted 22 of 23 Google Year in Search outcomes in under 24 hours, including a $10.6K bet on d4vd (0.2% implied probability) that paid ~$200K. Previously won $150K correctly predicting the exact Gemini 3.0 Flash release date.

**Wallet behavior**:
- Concentrated exclusively on Google-related prediction markets
- Extremely high win rate on Google-specific events
- Large position sizes on low-probability outcomes
- Repeat success pattern on same company's events

**Detection signals triggered**: Win-rate anomaly (category: Google), niche market, size anomaly (betting on 0.2% outcomes)
**Detection signals NOT triggered**: Not a fresh wallet; established trading history across 290 markets

**Investigation outcome**: No identification of any Google connection. Circumstantial evidence only. No known investigation.

**[ASSERTION]**: Company-specific prediction markets create structural insider trading opportunities for employees and close associates. AlphaRaccoon's 22/23 accuracy on Google events is astronomically improbable through analysis alone.
**Confidence**: MOD
**Sources**: T2 (Gizmodo, Yahoo Finance, BeInCrypto, Benzinga)
**Analytic basis**: 22/23 = 95.6% accuracy on multi-outcome predictions with some outcomes at <1% implied probability. The probability of this occurring by chance is effectively zero. However, no direct evidence links the wallet to a Google employee.
**Implication for Spyhop**: Consider a "company concentration" signal — wallets that exclusively or disproportionately trade on markets related to a single company warrant elevated suspicion.

---

### Case 6: OpenAI Employee (Feb 2026)

**Category**: Confirmed corporate insider (fired)
**Market**: Various OpenAI product launch dates (Sora, GPT-5, ChatGPT Browser)
**Profit**: $16,872 (the fired employee); broader cluster unquantified

**What happened**: OpenAI fired an employee on Feb 27, 2026 for using confidential product launch information to profit on Polymarket. Unusual Whales subsequently identified 77 suspicious positions across 60 wallet addresses tied to OpenAI events dating back to March 2023.

**Wallet behavior (ChatGPT Browser cluster)**:
- 13 wallets with zero prior activity
- All created within 40 hours of the ChatGPT Browser public unveiling
- Collectively bet $309,486 on the product's launch date
- Coordinated creation timing suggests shared information source

**Detection signals triggered**: Fresh wallet (13 zero-activity wallets), timing proximity, wallet clustering (same creation window), niche market

**Investigation outcome**: Employee fired. No CFTC/SEC action (Polymarket offshore, not securities). Kalshi separately referred insider trading cases to CFTC around the same time.

**[ASSERTION]**: The OpenAI case is the most clearly documented corporate insider case — confirmed by the company itself through an internal investigation. The 13-wallet ChatGPT Browser cluster is a textbook Sybil pattern.
**Confidence**: HIGH
**Sources**: T2 (Gizmodo, TechTimes, WinBuzzer, Slashdot, UCStrategies)
**Analytic basis**: Company-confirmed termination for cause; 77 suspicious positions identified by independent analyst (Unusual Whales); 13-wallet creation cluster within 40-hour window.
**Implication for Spyhop**: Product launch markets for major tech companies should be flagged as high-risk categories. The 13-wallet cluster pattern (zero-activity wallets created in tight window, all betting same market) is a detectable Sybil signature even without funding-chain analysis.

---

### Case 7: Axiom/ZachXBT Investigation (Feb 2026)

**Category**: Confirmed insider trading on a meta-market
**Market**: "Which company will ZachXBT accuse of insider trading?"
**Profit**: $1.2M across top 8 wallets; $266K across another 5 wallets

**What happened**: ZachXBT published an exposé accusing Axiom employees of insider trading. Before publication, wallets bet heavily on "Axiom" in a Polymarket market predicting which company would be named. 8 of the top 10 winning wallets were likely insiders. One trader bought $50.7K of "Axiom" shares at 15.1% odds and made $39K in a day.

**Wallet behavior**:
- Minimal prior market activity
- Single concentrated position on one market
- Timing aligned with fast odds shifts (entry at 13.8-15.1% odds)
- 3 addresses achieved >$100K profits trading only this single market

**Detection signals triggered**: Fresh/minimal-history wallet, single-market concentration, size anomaly, timing proximity

**Irony**: Insiders traded on a market *designed to catch insider traders*, creating a recursive insider trading problem.

**[ASSERTION]**: Meta-markets (markets about investigations, regulatory actions, or enforcement) are inherently vulnerable to insider trading because the information source (the investigator/regulator) is a small, identifiable group.
**Confidence**: HIGH
**Sources**: T2 (CoinDesk, crypto.news, CoinFomania, TradingView)
**Analytic basis**: 8/10 top wallets flagged as insider addresses by Defioasis; single-market trading pattern; entry at low implied probability with rapid resolution.
**Implication for Spyhop**: Markets whose resolution depends on a single actor's decision (investigations, product announcements, regulatory rulings) should receive elevated risk scoring.

---

### Case 8: Taylor Swift/Kelce Engagement — "romanticpaul" (Aug 2025)

**Category**: Suspected insider (unconfirmed)
**Market**: "Taylor Swift and Travis Kelce engaged in 2025?"
**Profit**: ~$3,000 (small by insider standards)

**What happened**: 15 minutes before the couple's public announcement, user "romanticpaul" purchased ~1,200 "Yes" shares at <$0.50. The trade moved a $385K market by ~12%.

**Wallet behavior**:
- Established account with $1.61M total volume across 290 markets
- Overall negative P&L (-$4,885), suggesting NOT a sophisticated trader
- Single profitable event amid broader losses
- Timing: 15 minutes pre-announcement

**Detection signals triggered**: Timing proximity (15 min), market impact (12% move)
**Detection signals NOT triggered**: Not a fresh wallet; not unusual size for this trader

**Speculation**: Crypto community speculated Paul Sidoti (Taylor Swift's guitarist for 18 years) could be the trader, based on the username. Unverified.

**[ASSERTION]**: This case illustrates the detection challenge of small-scale insider trades by established accounts. The $3K profit on a $385K market is within the noise floor of most detection systems.
**Confidence**: LOW
**Sources**: T3 (Benzinga, PokerScout, TheStreet, Mitrade)
**Analytic basis**: Timing is suspicious (15 min pre-announcement) but the trader has a long history and overall loses money, making the insider hypothesis less compelling. Could be luck, a tip, or actual insider knowledge — insufficient evidence to distinguish.
**Implication for Spyhop**: Small-scale insider trades on entertainment/celebrity markets may be below Spyhop's detection threshold — and that's acceptable. Focus resources on high-impact cases.

---

### Case 9: KPMG Earnings Cluster (Feb 2026)

**Category**: Suspected auditor/professional insider ring
**Market**: Corporate earnings predictions ($HD, $DASH, $KMX, $THO, $SNEX)
**Profit**: Unknown (pattern identified, not fully quantified)

**What happened**: A cluster of wallets made "max conviction" bets on corporate earnings outcomes, with every targeted company sharing the same auditor: KPMG. Traders showed late entries, high win rates, and wallet rotation to avoid detection.

**Wallet behavior**:
- Traded only on KPMG-audited company earnings markets
- High-conviction, correctly-timed positions
- Switched wallets frequently to avoid pattern detection
- Markets ranged from $200 to $200K in volume
- Bets placed "right before the official reports drop"

**Detection signals triggered**: Win-rate anomaly (earnings category), temporal proximity, wallet rotation (evasion behavior), company/auditor concentration

**Investigation outcome**: No formal investigation. Pattern identified by on-chain researcher Lirratø.

**[ASSERTION]**: The KPMG case demonstrates a novel insider pattern: targeting markets that share a common information source (auditor) rather than a common topic. This is difficult to detect without cross-referencing market metadata (e.g., which auditor handles each company).
**Confidence**: MOD
**Sources**: T3 (Lirratø on X), T2 (Gaming America, Cryptopolitan, EventWaves Substack)
**Analytic basis**: Pattern is suggestive but not proven. All targeted companies sharing one auditor is suspicious but could be coincidental (KPMG audits many companies). Wallet rotation suggests awareness of detection methods.
**Implication for Spyhop**: Phase 2 could add a "common metadata" signal — if a wallet trades exclusively on markets sharing a non-obvious common factor (same auditor, same regulator, same geography), flag for review.

---

### Case 10: Israeli Military Indictees (Jun 2025 strikes, indicted Feb 2026)

**Category**: Confirmed criminal insider trading
**Market**: Timing of Israeli strikes on Iran (June 2025)
**Profit**: $150,000+

**What happened**: An IDF reservist accessed classified operational intelligence and shared it with a civilian, who placed bets on Polymarket tied to the exact timing of Israeli military strikes on Iran. First criminal prosecution globally for prediction market insider trading.

**Charges**: "Serious security offenses," bribery, obstruction of justice. Joint investigation by Director of Security of the Defense Establishment, Shin Bet, and Israel Police.

**Wallet behavior**: Not publicly detailed in available sources.

**[ASSERTION]**: This is the only case where the full chain has been proven: classified information → shared with accomplice → bet placed → profit realized → criminal prosecution. It confirms that prediction market insider trading is a real criminal justice issue, not just a community concern.
**Confidence**: HIGH
**Sources**: T1 (Israeli indictment, JPost, NPR, Times of Israel, NBC News, The Block)
**Analytic basis**: Criminal prosecution with formal charges. Investigation by three security/law enforcement agencies.
**Implication for Spyhop**: Validates the entire project thesis — insider trading on prediction markets is real, prosecutable, and detectable through on-chain analysis.

---

## 2. The Insider Playbook — Behavioral Signatures

### 2.1 The Unsophisticated Insider (Cases 2, 3, 6, 7)

The most common pattern, seen in 60%+ of documented cases:

```
Step 1: CREATE    → New wallet, zero history
Step 2: FUND      → Rapid USDC deposit (often within 24h of event)
Step 3: BET       → Large directional bet on binary outcome
                     Often at very low implied probability (5-25%)
Step 4: WAIT      → Hold through resolution (no hedging, no exit)
Step 5: COLLECT   → Full payout on resolution
Step 6: ABANDON   → Wallet goes dormant; funds withdrawn
```

**Detectable by**: Fresh wallet + size anomaly + niche market + timing proximity. Spyhop V1 catches this.

### 2.2 The Sybil Insider (Cases 1*, 3, 6, 9)

Distributes activity across multiple wallets to stay below detection thresholds:

```
Step 1: CREATE    → Multiple wallets (6-100+)
Step 2: FUND      → Each wallet funded from shared or similar source
Step 3: DISTRIBUTE → Each wallet bets independently, different amounts
Step 4: COORDINATE → All wallets take same directional position
Step 5: COLLECT   → Aggregate profits across cluster
Step 6: ROTATE    → Abandon wallets; create new ones for next trade
```

**Detectable by**: Wallet clustering (funding source, timing overlap, behavioral fingerprint). Requires Phase 2.

*Note: Théo used multi-wallet for execution efficiency, not evasion — categorically different motivation.

### 2.3 The Repeat Domain Expert (Cases 4, 5, 9)

Maintains an established account but exhibits improbable accuracy in a specific domain:

```
Step 1: ESTABLISH  → Normal trading history across many markets
Step 2: SPECIALIZE → Consistently profitable in one specific domain
Step 3: ACCUMULATE → Patient position-building, not rushed
Step 4: WIN        → High accuracy on domain-specific events (80%+)
Step 5: CONTINUE   → Does not abandon wallet; continues trading
```

**Detectable by**: Win-rate anomaly segmented by market category. Requires Phase 2 historical analysis.

### 2.4 The Meta-Market Exploiter (Case 7)

Trades on markets whose resolution is controlled by a small, identifiable group:

```
Step 1: ACCESS     → Learns about upcoming announcement/investigation/decision
Step 2: IDENTIFY   → Finds corresponding prediction market
Step 3: BET        → Takes position at low implied probability
Step 4: WAIT       → Announcement/decision resolves market
Step 5: PROFIT     → Often 5-10x returns due to low entry odds
```

**Detectable by**: Market-type classification (meta-markets, announcement markets, single-decision-maker markets) + fresh wallet + size anomaly.

---

## 3. Smart Money vs. Insider: Distinguishing Characteristics

| Characteristic | Legitimate Whale | Suspected Insider |
|---------------|-----------------|-------------------|
| **Wallet age** | Months-years of history | Hours-days old |
| **Market diversity** | Trades across many markets | 1-3 markets, often related |
| **Position building** | Gradual accumulation | Single large entry |
| **Direction** | May take both sides (hedging) | One-sided directional |
| **Timing** | Enters when odds are "wrong" by analysis | Enters hours before resolution event |
| **Win rate** | 50-60% with strong P/L ratio | 80%+ on specific category |
| **Post-resolution** | Continues trading | Abandons wallet or goes dormant |
| **Funding source** | Established exchange accounts | Fresh deposits, sometimes via bridges |
| **Risk management** | Position sizing, diversification | All-in on single conviction |
| **Public identity** | Often pseudonymous but consistent | Anonymous, disposable |

**[ASSERTION]**: The strongest single discriminator between smart money and insiders is the combination of wallet age + market diversity + post-resolution behavior. Legitimate whales have long histories, trade diverse markets, and continue trading after wins. Insiders have short histories, concentrate on narrow topics, and abandon wallets.
**Confidence**: HIGH
**Sources**: T1/T2 (synthesized across all 10 cases)
**Analytic basis**: Pattern holds across every documented case in the catalog. No confirmed insider case involved an established, diverse trading account that continued normal activity post-event.
**Implication for Spyhop**: The trifecta of (fresh wallet OR narrow focus) + (large directional bet) + (dormancy post-resolution) is the most reliable composite signal.

---

## 4. Market Type Risk Taxonomy

Based on case analysis, markets can be categorized by structural insider trading risk:

| Risk Level | Market Type | Information Source | Examples | Cases |
|------------|------------|-------------------|----------|-------|
| **CRITICAL** | Military/geopolitical operations | Government/military officials | Iran strikes, Venezuela raid | 2, 3, 4, 10 |
| **HIGH** | Corporate product launches | Company employees | OpenAI releases, Google Gemini | 5, 6 |
| **HIGH** | Investigation/enforcement outcomes | Investigators, regulators | ZachXBT exposés, CFTC actions | 7 |
| **HIGH** | Corporate earnings | Auditors, executives, IR staff | KPMG-audited companies | 9 |
| **MODERATE** | Celebrity/entertainment events | Inner circle, staff, family | Swift/Kelce engagement | 8 |
| **MODERATE** | Political elections | Pollsters, campaign insiders | US presidential election | 1 (but was NOT insider) |
| **LOW** | Crypto prices/markets | Wide information distribution | BTC/ETH price predictions | — |
| **LOW** | Weather/natural events | Generally unpredictable | Hurricane landfall, earthquake | — |

**[ASSERTION]**: Markets where resolution depends on decisions by a small, identifiable group of people (military commanders, corporate executives, investigators) carry the highest structural insider trading risk. Markets resolved by distributed or natural processes carry the lowest.
**Confidence**: HIGH
**Sources**: T2/T3 (synthesized across case catalog), T3 (HN discussion)
**Analytic basis**: 8 of 10 documented cases involve markets where a small group controlled the outcome. Zero confirmed insider cases on distributed-resolution markets (crypto prices, weather).
**Implication for Spyhop**: Market category should be a scoring input. Geopolitical and corporate-announcement markets receive elevated base risk. Implementation: tag markets by category (via Gamma API metadata or keyword classification of market questions).

---

## 5. The Role of Market Makers and Arbitrage Bots

### 5.1 Market Maker Behavior

Market makers on Polymarket:
- Trade both sides of markets to provide liquidity
- Appear as high-volume "whales" but are liquidity providers, not directional bettors
- Often use multiple wallets for different strategies
- May appear to bet on both YES and NO (delta-neutral)
- SeriouslySirius (top whale): simultaneously bet on 11 different outcomes for single NBA games

**How to distinguish**: Net directional exposure is near zero across a market. Trade frequency is high and consistent. P&L comes from spread capture, not directional accuracy.

### 5.2 Arbitrage Bots

Arbitrage bots exploit price discrepancies:
- **Rebalancing arb**: When YES + NO prices sum to ≠ $1.00, buy both for guaranteed profit
- **Cross-market arb**: Exploit price differences between correlated markets
- **Latency arb**: Trade on Polymarket faster than prices update (sub-100ms execution)

Scale: ~$40M in arbitrage profits identified across 86M bets (Apr 2024 - Apr 2025). Top 3 bot wallets: 10,200+ bets combined, $4.2M profit.

**Detection challenge**: Arbitrage bots can look like coordinated insider activity (many rapid trades, multiple wallets, high win rates). Key differentiator: arb bots trade *both sides* and have tiny margins per trade, while insiders take large one-sided positions.

### 5.3 Wash Trading

Columbia University study found ~25% of Polymarket transactions may be wash trades. Characteristics:
- Frequent trades between the same accounts
- Extremely short intervals between trades
- Almost no position settlement
- Volume peaked at ~60% of weekly volume in Dec 2024

**[ASSERTION]**: Market makers, arbitrage bots, and wash traders represent the three major false positive categories for insider detection. Each has distinct signatures that can be filtered with appropriate heuristics.
**Confidence**: MOD
**Sources**: T1 (Columbia study), T2 (DL News, Yahoo Finance, Finance Magnates, PANews whale analysis)
**Analytic basis**: Well-documented bot behavior with specific metrics. However, distinguishing sophisticated insiders from sophisticated bots remains an open problem.
**Implication for Spyhop**: Phase 1 should include a "balanced exposure" check — if a wallet has roughly equal YES/NO volume on a market, reduce insider suspicion score. This filters market makers and arb bots without complex modeling.

---

## 6. Key Judgments

### J1: Insider trading on Polymarket is real, documented, and prosecutable
**Confidence**: HIGH — Supported by criminal indictments (Israel), corporate terminations (OpenAI), multiple independent forensic analyses, and 10+ documented cases.

### J2: The "unsophisticated insider" playbook is consistent and detectable
**Confidence**: HIGH — Fresh wallet → fund → bet → resolve → abandon. Seen in 6+ cases. Spyhop V1's three detectors would catch this pattern.

### J3: Geopolitical/military markets have the highest insider risk
**Confidence**: HIGH — 4 of 10 cases; only category with criminal prosecution; information source (classified intelligence) is maximally asymmetric.

### J4: Sophisticated insiders are largely invisible to current methods
**Confidence**: MOD — By definition, we only know about the ones who were caught. Magamyman and KPMG cluster suggest more sophisticated patterns exist. Win-rate anomaly detection (Phase 2) partially addresses this.

### J5: The French whale case demonstrates the false positive problem
**Confidence**: HIGH — Théo triggered massive size alerts and used multiple accounts, yet was definitively not an insider. Any detection system will generate Théo-type false positives on large legitimate trades.

### J6: Market category is a strong prior for insider risk
**Confidence**: HIGH — Resolution mechanism (small-group decision vs. distributed process) is the structural determinant of insider trading opportunity.

---

## 7. Lessons from Théo: The Legitimate Whale Playbook

While the bulk of this document focuses on insider patterns, the French whale case offers an equally valuable counter-study — a framework for how *legitimate* informed trading works on prediction markets. Théo's methodology is well-documented and provides transferable principles for any participant seeking edge without non-public information.

### 7.1 Identify Systematic Bias in the Consensus Price

Théo's edge was not a better prediction — it was a **theory of error in the market**. He believed traditional polls systematically undercounted Trump support due to social desirability bias (the "shy voter" effect). Since Polymarket prices were effectively a poll-of-polls proxy, biased polls meant a biased market price.

**Principle**: The profitable question is not "what will happen?" but "why is the current price specifically wrong, and what structural factor is causing the mispricing?" Every prediction market trade should start with a theory of consensus error, not just a directional view.

### 7.2 Generate or Obtain Proprietary Data

Rather than arguing from intuition, Théo commissioned a custom YouGov poll in Pennsylvania, Michigan, and Wisconsin using "neighbor polling" — asking respondents who their *social circle* was voting for, not who they personally supported. This methodology is documented in academic literature as reducing social desirability bias. The results showed significantly more Trump support than traditional polls, providing independent confirmation of his thesis.

**Principle**: If you think a market is mispriced, can you generate or find data that the market isn't using? This does not mean insider information — it means *better public information* than the consensus is incorporating. Examples include:
- Local or domain-specific knowledge
- Alternative data sources (satellite imagery, social media sentiment, shipping data)
- Better analytical models applied to the same public data
- Primary research (polls, surveys, FOIA requests)

### 7.3 Size for Conviction, Not Comfort

Théo liquidated "virtually all his liquid assets" to fund the ~$80M wager. He identified *one* massive mispricing and concentrated capital rather than diversifying across many markets with small bets.

**Principle (with caveats)**: Prediction market edge is rare and temporary. When genuine mispricing is identified with strong evidence, position size should reflect the magnitude of the edge. This maps to Kelly criterion thinking — bet proportional to your edge, not your enthusiasm:
- **High conviction + strong proprietary evidence** → larger position
- **Moderate conviction** → moderate position
- **Speculative / entertainment** → small position

**Survivorship bias warning**: Théo's concentration worked spectacularly, but we do not hear about equally convicted traders who were equally wrong. His wealthy banking background meant he could absorb a total loss. Fractional Kelly (betting a fraction of the Kelly-optimal amount) protects against the cases where the thesis is correct but the specific outcome or timing is wrong.

### 7.4 Execute to Minimize Market Impact

Théo used 11 separate accounts and built his position through "a series of small transactions" specifically "to prevent the price of his bets from rising so he could get a better deal." He was buying at 30-40 cent odds; placing $80M at once would have pushed the price to 60+ cents and destroyed his own edge.

**Principle**: On Polymarket, a sufficiently large trader IS the market. Even at $10-50K levels on thinner markets, a single order can move the price materially. Practical execution steps:
- Check order book depth before placing (CLOB API `GET /book`)
- Split large orders into smaller tranches over time
- Use limit orders at target price, not market orders
- Be patient — accumulate over hours or days, not minutes

### 7.5 Remove Emotion and Identity from the Trade

Théo explicitly stated "I have absolutely no political agenda" and "I'm only doing it for the money." As a French citizen, he had no personal stake in US politics, allowing him to evaluate evidence without motivated reasoning or tribal bias.

**Principle**: The best prediction market edges come from topics where the trader can be purely analytical. Strong emotional attachment to an outcome (favorite team, political party, company) leads to overweighting confirming evidence, underweighting disconfirming evidence, holding losing positions too long, and sizing based on hope rather than evidence.

### 7.6 The Théo Decision Framework

Before any prediction market trade, four questions:

1. **What is the market's error?** — Not "what do I think will happen" but "why is the consensus price specifically wrong?"
2. **What evidence do I have that the market doesn't?** — Proprietary data, better models, domain expertise, or information the market is ignoring.
3. **How much edge does this give me?** — If the market says 35% and the analysis says 65%, that's a 30-point edge. Size accordingly.
4. **Can I execute without destroying my edge?** — Check liquidity. Split orders. Be patient.

**[ASSERTION]**: Théo's methodology — thesis-driven trading with proprietary data validation and disciplined execution — is the archetype of legitimate smart money on prediction markets. His approach is reproducible in structure even at smaller scale. The key differentiator from insider trading is that his information advantage came from *better analysis of public data*, not access to non-public information.
**Confidence**: HIGH
**Sources**: T2 (WSJ, CBS News 60 Minutes, Bloomberg, Fortune, Entrepreneur, The Free Press)
**Analytic basis**: Théo self-identified, explained his methodology publicly, and the custom polling data was independently verifiable. Multiple investigations confirmed no insider trading.
**Implication for Spyhop**: Understanding the legitimate whale playbook is as important as understanding the insider playbook — it defines the false positive boundary. Spyhop's scoring should reward indicators of Théo-style behavior (gradual accumulation, established accounts, diversified history) with lower suspicion scores.

---

## Sources

### T1 (Primary Evidence)
- Israeli indictments (IDF reservist + civilian) — [JPost](https://www.jpost.com/israel-news/crime-in-israel/article-886456), [NPR](https://www.npr.org/2026/02/12/nx-s1-5712801/polymarket-bets-traders-israel-military), [Times of Israel](https://www.timesofisrael.com/two-indicted-for-using-classified-info-to-place-online-bets-on-military-operations/), [NBC News](https://www.nbcnews.com/world/israel/israel-charges-reservist-classified-information-bet-polymarket-rcna258709), [The Block](https://www.theblock.co/post/389575/israeli-defense-reservist-civilian-indicted-over-alleged-insider-betting-on-polymarket-reports)
- Chainalysis wallet clustering (French whale) — via [Fortune](https://fortune.com/2024/11/02/french-whale-polymarket-30-million-donald-trump-election-bet-kamala-harris/), [Yahoo Finance](https://finance.yahoo.com/news/polymarket-whale-actually-made-85-050139914.html)
- Bubblemaps Iran strike forensics — [The Block](https://www.theblock.co/post/391650/fresh-accounts-netted-1-million-on-polymarket-hours-before-us-airstrikes-on-iran-bubblemaps)
- Columbia University wash trading study — [CoinDesk](https://www.coindesk.com/markets/2025/11/07/polymarket-s-trading-volume-may-be-25-fake-columbia-study-finds)
- OpenAI internal investigation (employee termination) — [Gizmodo](https://gizmodo.com/the-great-insider-trading-reckoning-reportedly-hits-openai-2000727838), [TechTimes](https://www.techtimes.com/articles/314884/20260227/openai-fires-employee-over-alleged-polymarket-insider-trading.htm)

### T2 (Credible Secondary)
- French whale (Théo) — [CBS News](https://www.cbsnews.com/news/french-whale-made-over-80-million-on-polymarket-betting-on-trump-election-win-60-minutes/), [WSJ via The Free Press](https://www.thefp.com/p/french-whale-makes-85-million-on-polymarket-trump-win), [Sherwood News](https://sherwood.news/markets/french-polymarket-theo-record-breaking-million-bet-pay-out/), [Entrepreneur](https://www.entrepreneur.com/business-news/how-trump-whale-theo-made-48-million-neighbor-effect/482539)
- Venezuela/Maduro — [NPR](https://www.npr.org/2026/01/05/nx-s1-5667232/polymarket-maduro-bet-insider-trading), [PBS](https://www.pbs.org/newshour/nation/a-400000-payout-after-maduros-capture-put-prediction-markets-in-the-spotlight-heres-how-they-work), [Axios](https://www.axios.com/2026/01/03/maduro-capture-bets-trade-prediction-markets), [Fortune](https://fortune.com/2026/01/12/polymarket-kalshi-insider-trading-prediction-markets-cftc-torres-titus-venezuela/), [The Hill](https://thehill.com/policy/technology/5687162-insider-trading-prediction-markets-venezuela/)
- Iran strikes cluster — [CoinDesk](https://www.coindesk.com/markets/2026/02/28/suspected-insiders-make-over-usd1-2-million-on-polymarket-ahead-of-u-s-strike-on-iran), [Al Jazeera](https://www.aljazeera.com/economy/2026/3/4/traders-mint-money-on-betting-platforms-on-us-israel-strike-on-iran), [Bloomberg](https://www.bloomberg.com/news/articles/2026-02-28/polymarket-iran-bets-hit-529-million-as-new-wallets-draw-notice), [CBC](https://www.cbc.ca/news/business/prediction-market-bets-iran-strikes-insider-trading-allegations-9.7112463), [Snopes](https://www.snopes.com/news/2026/03/03/polymarket-bets-iran-strikes/)
- Magamyman — [NPR](https://www.npr.org/2026/03/01/nx-s1-5731568/polymarket-trade-iran-supreme-leader-killing)
- AlphaRaccoon — [Gizmodo](https://gizmodo.com/polymarket-user-accused-of-1-million-insider-trade-on-google-search-markets-2000696258), [Yahoo Finance](https://finance.yahoo.com/news/polymarket-trader-makes-1-million-090001027.html), [Benzinga](https://www.benzinga.com/crypto/cryptocurrency/25/12/49208309/polymarket-returns-to-the-us-as-rumored-insider-pockets-1-million-on-google-trends-market)
- Axiom/ZachXBT — [CoinDesk](https://www.coindesk.com/markets/2026/02/27/polymarket-bettors-appear-to-have-insider-traded-on-a-market-designed-to-catch-insider-traders), [crypto.news](https://crypto.news/zachxbt-axiom-employees-insider-trading-report-2026/), [TradingView](https://www.tradingview.com/news/cointelegraph:a2a3b75ae094b:0-suspected-insider-wallets-rack-up-1-2m-betting-on-zachxbt-s-axiom-expos/)
- PANews 521 addresses — [PANews](https://www.panewslab.com/en/articles/019caef8-7f10-7114-b20e-35dd654a54be)
- PANews whale analysis — [PANews](https://www.panewslab.com/en/articles/516262de-6012-4302-bb20-b8805f03f35f)
- KPMG earnings — [Gaming America](https://gamingamerica.com/news/polymarket-earnings-bets-trigger-insider-trading-rumors-linked-to-kpmg), [Cryptopolitan](https://www.cryptopolitan.com/insiders-from-kpmg-may-be-active-on-polymarket-earnings-prediction-pairs/)
- Arbitrage bots — [DL News](https://www.dlnews.com/articles/markets/polymarket-users-lost-millions-of-dollars-to-bot-like-bettors-over-the-past-year/), [Yahoo Finance](https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html)

### T3 (Community Intelligence)
- romanticpaul/Swift — [Benzinga](https://www.benzinga.com/crypto/cryptocurrency/25/08/47367927/taylor-swift-and-travis-kelce-are-engaged-and-polymarket-trader-romanticpaul-predicted-it), [PokerScout](https://www.pokerscout.com/insider-trading-on-polymarket-foretold-taylor-swifts-engagement/)
- KPMG wallet analysis — [Lirratø on X](https://x.com/itslirrato/status/2027291968158539914), [EventWaves Substack](https://eventwaves.substack.com/p/kpmg-audited-companies-are-trading)
- Polymarket insider debate — [Medium (Josh W)](https://medium.com/@josh.insidertrading.tech/polymarket-how-crypto-prediction-markets-legalized-insider-trading-1665fe9e8598)
- Regulatory analysis — [philippdubach.com](https://philippdubach.com/posts/the-absolute-insider-mess-of-prediction-markets/), [Corporate Compliance Insights](https://www.corporatecomplianceinsights.com/prediction-markets-sports-betting-insider-trading/)
