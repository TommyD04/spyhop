# Scoring analysis and config changes — March 24, 2026

## Purpose

This memo documents the P&L review, detector analysis, and config changes made on 2026-03-24 across both the insider and sporty_investor theses. It covers what we found, what we changed, and what remains open.

---

## Portfolio snapshot

As of this session:

| | Insider | Sporty investor | Total |
|---|---|---|---|
| Resolved positions | 3 | 45 | 48 |
| Win/loss | 2W / 1L | 19W / 26L | 21W / 27L |
| Win rate | 67% | 42% | 44% |
| Realized P&L | +$5,680 | -$32,396 | **-$26,716** |
| ROI | +34.7% | -18.2% | -13.7% |
| Open positions | 0 | 11 | 11 |
| Open exposure | — | $46,860 | $46,860 |

The insider thesis is profitable but tiny — three positions, two of which were near-certainty bets that barely moved the needle. The sporty investor thesis is responsible for the entire portfolio loss.

---

## Insider thesis

### What we found

All three insider positions used distinct wallets (0–4 prior trades each), but only one was a genuine insider signal:

**Position #74 — NYA Up/Down (+$5,680)**: Fresh wallet (4 prior trades) bet 106.9% of daily market volume at exactly $0.50 on a specific-day index direction call. Entry at even money, won at $0.997. This is the pattern the thesis is built for.

**Positions #71 and #116 (near-certainty traps)**: Both entered at $0.999. Fresh wallet + large size detectors fired, but the entry price reveals no informational content — someone parking capital on a near-certain outcome. #71 (Gold won't hit $7K) ended -$2.79; #116 (Iran won't attack Israel) ended +$2.54. Economic washes.

The near-certainty problem won't be solved by tuning fresh_wallet or niche thresholds. It requires the planned B1 entry price modifier — a dampener on insider scores when entry is ≥$0.85.

### Changes made

**fresh_wallet thresholds collapsed.** The 1–2 and 3–5 trade buckets had nearly identical average scores (4.86 vs 4.62 across 1,258 signals). Collapsed into a single 1–5 tier at 2.0x. The zero-trades tier (3.0x) and the no-signal tier (>5 trades, 1.0x) are unchanged.

| Tier | Before | After |
|---|---|---|
| 0 prior trades | 3.0x | 3.0x |
| 1–2 prior trades | 2.5x | **2.0x** |
| 3–5 prior trades | 2.0x | 2.0x |
| 6+ prior trades | 1.0x | 1.0x |

**niche_market ramp increased.** The top two tiers get modest upward adjustments. This raises the normalizer from 7.40 → 7.14 (slight compression on liquid-market scores) with a net positive effect: liquid-market positions like #116 drop closer to the 7.0 threshold, while genuine ultra-niche positions score higher.

| Tier | Before | After |
|---|---|---|
| < $10K daily | 2.5x | **2.8x** |
| $10K–$25K daily | 2.0x | **2.2x** |
| $25K–$50K daily | 1.5x | 1.5x |
| > $50K daily | 1.0x | 1.0x |

### What remains open

The B1 entry price modifier is still the most impactful unbuilt fix. Under current config, a brand-new wallet betting $5K on a 99.9% certain outcome still scores 7.1 and opens a paper position. That's wrong. The fix is a dampener (e.g. 0.5x) on the insider composite when entry price exceeds $0.85.

---

## Sporty investor thesis

### What we found

**The entry price thesis is backwards.** The 0.35–0.50 "sweet spot" — the range we built the thesis around — posted a 36% win rate and -$20,310 total P&L across 22 positions. The EV gap was -8pp (needed 40%+ wins, got 36%). The 0.65–0.85 range had 67% wins but the payout math still doesn't work at those prices (needed ~72%). No entry price range showed reliable edge.

**The niche adjacent band ($25K–$50K) has no edge.** It scored 1.5x (boosted) and generated 11 positions with a -$14,432 total — the worst loss of any niche bucket. The $10K–$25K sweet spot was the only bucket with any residual validity, though even that was nearly flat (-$1,600 across 11 positions).

**WalletExperience doesn't filter.** 47 of 48 resolved positions landed in the 6–25 trade "sweet" tier. It's providing a near-constant 1.8x boost to everything, not differentiating signals.

**The combined effect of entry price and niche boosting was over-scoring weak signals.** A sporty_investor trade on a $200K liquid NBA market at $0.50 entry would score 6.5s under the old config. That's a bad bet on an efficient market — the model was treating it as a reasonable signal.

### Changes made

**entry_price flattened.** Sweet spot (2.0x) and adjacent (1.5x) boosts removed. Only the near-certainty dampen (0.5x at ≥$0.85) remains. With 48 total positions and the 0.35–0.50 range being the *worst* performer, there's no empirical basis for any price-based boost yet.

| Range | Before | After |
|---|---|---|
| 0.35–0.50 (sweet spot) | 2.0x | **1.0x** |
| 0.25–0.65 (adjacent) | 1.5x | **1.0x** |
| ≥0.85 (near-certainty) | 0.5x | 0.5x |

**niche_nonlinear sweet spot expanded, adjacent removed.** Lower bound drops from $10K to $5K — consistent with the thesis that thin-but-tradeable markets carry more edge. The adjacent band ($25K–$50K) drops from 1.5x to 1.0x based on its -$14,432 empirical performance.

| Tier | Before | After |
|---|---|---|
| $5K–$25K daily | (lower bound was $10K) | **2.0x** |
| $10K–$25K daily | 2.0x | 2.0x (lower bound expanded) |
| $25K–$50K daily | 1.5x | **1.0x** |
| > $50K daily | 1.0x | 1.0x |

**Normalizer impact of flattening entry_price.** Setting `multiplier_sweet = 1.0` changes entry_price's `max_multiplier` from 2.0 to 1.0. The scorer recomputes the normalizer at startup: max_product drops from 7.2 → 3.6, normalizer shifts from 11.66 → 17.93. This has a material gating effect: any position with niche=1.0 (outside the sweet spot) now scores ≤4.6s and doesn't cross the 5.0 alert threshold. In practice, this blocks all trades on markets over $25K daily volume without touching the threshold config.

**Size/vol detector: decided against.** The insider thesis uses SizeAnomalyDetector because it spans all market sizes — a whale moving 10%+ of a liquid market is a genuine signal. For sporty, the $10K trade floor combined with the $5K–$25K niche filter already means every qualifying position represents 40–200% of daily volume. A separate metric would be redundant and add an unvalidated parameter.

### What remains open

WalletExperience still isn't doing much. 98% of positions hit the "sweet" tier. Options include tightening the sweet spot boundaries, adding a hard exclusion for very high trade counts (potential bots), or dropping it entirely and relying on niche alone. Waiting for more resolved positions before changing it.

The sporty_investor thesis needs 50+ sweet-spot-only positions before any further recalibration is worth doing. The changes today should significantly cut position volume by blocking the liquid-market and adjacent-band trades.

---

## Resolver bug fix

The `_resolve_position` method in `resolver.py` was using raw `outcome_prices` for P&L calculation rather than snapping to canonical settlement values. When a market resolves, prices approach 1.0/0.0 but may not have fully settled at poll time. The resolver's boundary trigger fires at ≥0.99 or ≤0.01, but then used the raw price (e.g. 0.9985) to compute P&L, producing small but incorrect results.

**Example:** Position #71 (Gold won't hit $7K, BUY No). Resolved as No. Exit price recorded as 0.9985 instead of 1.0. P&L: -$2.79 instead of +$5.58.

Fix: after reading `exit_price = float(outcome_prices[outcome_index])`, snap to 1.0 if ≥0.99 and 0.0 if ≤0.01. Already-closed positions in the DB retain their original (slightly incorrect) P&L. Applies to all future resolutions.

---

## Display change

Score column now suffixes `s` for sporty_investor scores across all views (live table, `spyhop history`, `spyhop positions`). A score of `8.5s` and `8.5` are on different scales with different alert thresholds — the suffix makes that visible at a glance without adding a column.
