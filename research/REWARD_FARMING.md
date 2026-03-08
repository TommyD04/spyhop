# Reward Farming & Wash Trading on Polymarket

## Summary

Reward farming is the dominant source of false positives in Spyhop's detection pipeline. An estimated 25% of all Polymarket volume ($4.5B) is wash trading, peaking at 45% on sports markets. Farmers execute scripted buy-sell round-trips on the same market from the same wallet (or wallet clusters), losing a small spread to inflate volume metrics. The primary motivation is qualifying for the anticipated $POLY token airdrop.

---

## 1. The $POLY Airdrop

### Confirmed Facts

- **October 2025**: CMO Matthew Modabber confirmed on Degenz Live podcast: "There will be a token, there will be an airdrop."
- **Token name**: $POLY (expected)
- **Airdrop allocation**: 5-10% of total token supply
- **Timeline**: 2026, after U.S. relaunch stabilizes
- **Prerequisite**: U.S. re-entry completed first (done as of late 2025)
- **Anti-Sybil**: Polymarket has stated Sybil/bot accounts will be filtered from airdrop eligibility

### Polymarket Valuation (Airdrop Value Context)

| Date | Event | Valuation |
|------|-------|-----------|
| Jan 2025 | Series C ($150M) | $1.2B |
| Oct 2025 | ICE/NYSE investment ($2B) | $9B |
| Oct 2025 | Seeking new round | $12-15B |
| Jan 2026 | Secondary market | $11.6B |

### Estimated Airdrop Pool

At $10B FDV with 7.5% allocation (midpoint): **~$750M airdrop pool**.

Rough per-trader estimates (highly speculative):
- Average allocation across ~200K traders: ~$3,750
- Top 10%: ~$20,000-50,000+
- Top 1%: ~$100,000+

### Likely Eligibility Criteria (Based on DeFi Airdrop Precedent)

| Factor | Expected Weight | What farmers optimize for |
|--------|----------------|--------------------------|
| Trading volume | High | Round-trip wash trades to inflate volume |
| Number of trades | Medium | High-frequency small trades |
| Markets traded | Medium | Spread activity across many markets |
| Consistency | Medium | Daily activity sustained over months |
| Liquidity provided | Medium | Resting limit orders near midpoint |
| Profitability | Low/Unknown | Probably not weighted heavily |

---

## 2. Polymarket's Reward Programs

### Liquidity Rewards (Market Makers)

Paid daily (midnight UTC) to wallets with resting limit orders near the midpoint.

**Quadratic scoring formula**: `Score = ((max_spread - order_spread) / max_spread)^2 * order_size`

Key mechanics:
- Being 2x tighter than competitors **quadruples** (not doubles) your rewards
- Two-sided quoting (bid + ask) earns up to 3x via the `Q_min` formula
- Scaling factor `c = 3.0` on all markets (as of early 2026)
- Market-specific params (`max_incentive_spread`, `min_incentive_size`) available via CLOB API
- Minimum payout: $1/day
- Extreme markets (<10% or >90% probability): two-sided liquidity required

**Important**: This rewards *resting limit orders*, not market takers. The round-trip farmers you see in the RTDS feed are likely taking liquidity, not providing it. They don't earn liquidity rewards directly — they're farming volume/trade count for the airdrop.

### Holding Rewards

- 4% APY on eligible positions (select political markets only)
- Position value sampled randomly once per hour, paid daily
- Eligible markets: 2028 presidential, 2026 midterms, select international politics
- Rate is variable, subject to change

---

## 3. Observed Farming Patterns in Spyhop Data

### The 61-Second Round-Trip Pattern

Observed in live Spyhop data (March 2026):
- Same wallet buys on a market, then sells (or vice versa) **exactly ~61 seconds later**
- Consistent cadence across multiple wallets suggests shared bot infrastructure
- Trades appear on niche/low-volume markets (sports props, municipal elections)

**Why 61 seconds?** Most likely explanations (ranked by probability):
1. **Wash-trade detection avoidance** — Polymarket likely flags same-wallet, same-market trades within 60s. The bot adds 1s safety margin.
2. **Settlement batching** — Polygon's off-chain matching may batch on ~60s cycles
3. **Rate limiting** — CLOB order submission throttle per wallet (less likely; API allows faster)

### Wallet Rotation

- Farmers use rotating proxy wallets to distribute volume
- Columbia study identified one cluster of **43,000 wallets** doing ~$1M in volume
- Each wallet does a limited number of round-trips before rotating to a new one
- This is why FreshWalletDetector fires — the wallets genuinely are fresh

### Market Selection

- Sports markets preferred for farming: **45% of sports volume is wash trading** (Columbia study)
- High market count = more spread across criteria
- Frequent resolution = faster position turnover
- Lower scrutiny than political markets (which Polymarket monitors more closely)

### Category Breakdown of Wash Trading (Columbia Study)

| Category | Wash Trading % of Volume |
|----------|--------------------------|
| Sports | 45% |
| Elections | 17% |
| Politics | 12% |
| Crypto | 3% |

---

## 4. The Farmer's Economics

### Cost Per Round-Trip

On a near-certainty market (e.g., 99.5c YES):
```
BUY  10,000 YES @ 99.5c  = $9,950
SELL 10,000 YES @ 99.4c  = $9,940
Loss per round-trip       = ~$10 (the spread)
```

On a 50/50 market the spread loss is similar but slippage risk is higher.

### Estimated Farming P&L

```
Cost per round-trip:     ~$5-15 (spread loss, varies by market)
Round-trips per day:     ~50 (across 5 markets)
Daily cost:              ~$250-750
Duration:                ~180 days (6 months of sustained farming)
Total farming cost:      $45K-135K

Output:
  Trades generated:      ~18,000
  Volume generated:      ~$1.8M
```

**The bet**: Spend $45K-135K farming to earn $50K-500K+ in airdrop allocation. Asymmetric upside if the airdrop is large; total loss if Polymarket successfully filters them out.

---

## 5. Columbia University Study (November 2025)

### Key Findings

- **~25% of all Polymarket volume (~$4.5B) is wash trading**
- 14% of 1.26M active wallets showed suspicious patterns
- Suspicious trades peaked at **~60% of weekly volume** in December 2024
- Dropped below 5% by May 2025, rose back to ~20% by October 2025
- Detection method: algorithmic clustering of wallets trading exclusively with each other

### Three Enabling Factors Identified

1. No KYC verification
2. Zero transaction fees
3. Anticipated token launch incentivizing volume farming

### Study Limitation

Researchers "cannot definitively prove motivation" — could be airdrop farming, volume inflation for market manipulation, or other purposes. But airdrop farming is the consensus explanation.

---

## 6. Implications for Spyhop

### False Positive Problem

Reward farmers trigger all three detectors:
- **FreshWalletDetector**: Rotating wallets are genuinely fresh (0-2 prior trades)
- **SizeAnomalyDetector**: $10K+ trades on low-volume markets hit the threshold
- **NicheMarketDetector**: Farmers target niche markets (sports props, municipal elections)

Result: Farmers dominate the high-score alerts, drowning genuine insider signals.

### Proposed Detection Heuristic

Tag trades as `FARM` when **all** of the following are true:
- Same wallet
- Same market (condition_id)
- Opposite side (BUY then SELL, or vice versa)
- Time delta <= 120 seconds (generous window around the observed 61s cadence)

This could be extended with:
- Wallet cluster detection (multiple wallets with identical trading cadence)
- Category weighting (Sports signals worth less than Politics/Crypto)
- Round-trip P&L analysis (net-zero or slightly negative = farming signature)

### Priority

**High** — This is the single largest source of noise in the current pipeline and must be addressed before the detection system produces actionable signals.

---

## Sources

- [Polymarket Will Launch Token and Airdrop — CoinDesk (Oct 2025)](https://www.coindesk.com/markets/2025/10/24/polymarket-will-launch-token-and-airdrop-after-u-s-relaunch-cmo-says/)
- [Polymarket Confirms POLY Token — 99Bitcoins](https://99bitcoins.com/news/bitcoin-btc/polymarket-confirms-poly-token-launch-and-airdrop-plans/)
- [Polymarket Raises $2B at $9B Valuation — insights4vc](https://insights4vc.substack.com/p/polymarket-raises-2b-at-9b-valuation)
- [Polymarket Seeking $12-15B — Bloomberg via CoinDesk](https://www.coindesk.com/business/2025/10/23/polymarket-seeks-investment-at-valuation-of-usd12b-usd15b-bloomberg/)
- [Columbia Study: 25% Wash Trading — Decrypt](https://decrypt.co/347842/columbia-study-25-polymarket-volume-wash-trading)
- [Airdrop Farmers Refine Tactics — CoinMarketCap](https://coinmarketcap.com/academy/article/polymarket-airdrop-farmers-refine-tactics-ahead-of-launch)
- [Polymarket Liquidity Rewards Docs](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
- [Polymarket Holding Rewards](https://help.polymarket.com/en/articles/13364459-holding-rewards)
- [Reverse Engineering Liquidity Rewards — PolyMaster (Jan 2026)](https://medium.com/@wanguolin/my-two-week-deep-dive-into-polymarket-liquidity-rewards-a-technical-postmortem-88d3a954a058)
- [Polymarket Airdrop Guide — Bitget](https://web3.bitget.com/en/academy/polymarket-airdrop-guide-how-to-participate-and-claim-poly-rewards)
