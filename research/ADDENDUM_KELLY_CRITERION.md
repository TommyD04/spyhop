# Addendum: The Kelly Criterion — A Practical Guide for Prediction Markets

**Purpose**: Standalone reference on Kelly criterion bet sizing, written for someone new to the concept. Covers the theory, the math, prediction market adaptations, and how it applies to Spyhop's executor.

---

## 1. The Core Problem Kelly Solves

You've identified a bet you think is mispriced. The market says 30% probability; your analysis says 60%. You have edge. But how much of your bankroll should you risk?

- **Too little**: You leave money on the table. If you bet $10 on a $10,000 bankroll, even a great edge barely moves the needle.
- **Too much**: One bad outcome wipes you out. If you bet $8,000 on a $10,000 bankroll, a single loss is catastrophic — even if you were "right" 60% of the time.

The Kelly criterion finds the **mathematically optimal** fraction of your bankroll to bet, given your edge. It maximizes the **long-term geometric growth rate** of your wealth — meaning it grows your bankroll as fast as possible *without* going broke.

---

## 2. The Formula

### 2.1 Simple Binary Bet (Win or Lose Everything)

For a bet where you either win `b` dollars per dollar wagered, or lose your entire stake:

```
f* = (p * b - q) / b
```

Where:
- **f*** = optimal fraction of bankroll to bet (the "Kelly fraction")
- **p** = your estimated probability of winning
- **q** = probability of losing = 1 - p
- **b** = net odds received (what you win per dollar risked)

### 2.2 Worked Example: Coin Flip with Edge

Imagine a biased coin: 60% heads, 40% tails. You win $1 for every $1 bet on heads.

```
p = 0.60 (your win probability)
q = 0.40 (your loss probability)
b = 1.00 (even money — win $1 per $1 bet)

f* = (0.60 * 1.00 - 0.40) / 1.00
f* = (0.60 - 0.40) / 1.00
f* = 0.20
```

**Kelly says: bet 20% of your bankroll each flip.** On a $10,000 bankroll, that's $2,000 per bet.

Over many flips, this fraction maximizes your long-run growth. Bet less and you grow slower. Bet more and you risk ruin — even though you have a genuine edge.

### 2.3 Key Intuition

The Kelly fraction is directly proportional to your **edge** and inversely proportional to the **odds**:

- **More edge → bigger bet**: If p goes from 0.60 to 0.80, f* goes from 0.20 to 0.60
- **Better odds → smaller bet (as % of bankroll)**: At 3:1 odds, you need less bankroll at risk to capture the same edge
- **No edge → no bet**: If p * b = q (fair odds), f* = 0. Kelly never recommends betting without edge.
- **Negative edge → Kelly is negative**: This means "don't bet" (or bet the other side)

---

## 3. Applying Kelly to Prediction Markets

### 3.1 Prediction Market Prices ARE Probabilities

On Polymarket, a "Yes" share priced at $0.30 implies a 30% probability. If you buy at $0.30 and the event happens, you receive $1.00 (profit of $0.70). If it doesn't happen, you lose your $0.30.

This maps directly to Kelly:
- **Your cost**: price you pay per share (e.g., $0.30)
- **Your payout if right**: $1.00 per share
- **Net odds (b)**: (payout / cost) - 1 = (1.00 / 0.30) - 1 = **2.33**
- **Your estimated probability (p)**: your analysis of the true probability
- **Market's implied probability**: the current price

### 3.2 Full Prediction Market Kelly Formula

```
# Given:
market_price = 0.30          # Current price of "Yes" share
your_estimate = 0.60         # Your estimated true probability of "Yes"

# Derived:
b = (1.0 / market_price) - 1  # Net odds = (1.00 / 0.30) - 1 = 2.33
p = your_estimate              # 0.60
q = 1 - p                     # 0.40

# Kelly fraction:
f_star = (p * b - q) / b
f_star = (0.60 * 2.33 - 0.40) / 2.33
f_star = (1.40 - 0.40) / 2.33
f_star = 1.00 / 2.33
f_star = 0.43                 # Bet 43% of bankroll
```

**Kelly says: bet 43% of your bankroll.** On a $10,000 bankroll, buy $4,300 worth of "Yes" shares at $0.30.

### 3.3 Sensitivity to Edge Size

The bigger the gap between your estimate and the market price, the more Kelly tells you to bet:

| Market Price | Your Estimate | Edge (gap) | Net Odds (b) | Kelly f* |
|-------------|--------------|------------|---------------|----------|
| $0.30 | 0.35 | +5 pts | 2.33 | 0.07 (7%) |
| $0.30 | 0.45 | +15 pts | 2.33 | 0.21 (21%) |
| $0.30 | 0.60 | +30 pts | 2.33 | 0.43 (43%) |
| $0.30 | 0.80 | +50 pts | 2.33 | 0.63 (63%) |
| $0.50 | 0.60 | +10 pts | 1.00 | 0.20 (20%) |
| $0.50 | 0.70 | +20 pts | 1.00 | 0.40 (40%) |
| $0.80 | 0.90 | +10 pts | 0.25 | 0.50 (50%) |

Notice: the same 10-point edge produces different Kelly fractions depending on the odds. A 10-point edge at $0.30 (long odds) recommends 7%; a 10-point edge at $0.80 (short odds) recommends 50%. This is because at short odds, you're risking more per unit of potential gain, so Kelly adjusts accordingly.

---

## 4. Why Full Kelly Is Dangerous (And What to Use Instead)

### 4.1 The Problem with Full Kelly

Full Kelly **assumes you know the true probability exactly**. In reality, you don't. Your estimate of "60% true probability" might actually be 45% or 75%. If your estimate is even slightly wrong, full Kelly overbets.

Simulation results for a bettor with true 60% edge at even money (f* = 0.20):

| Strategy | Growth Rate | Probability of Halving Bankroll | Probability of 10x Bankroll |
|----------|------------|-------------------------------|----------------------------|
| Full Kelly (20%) | Optimal | ~33% at some point | Highest (eventually) |
| Half Kelly (10%) | ~75% of optimal | ~11% | Slightly lower |
| Quarter Kelly (5%) | ~50% of optimal | ~4% | Lower |
| Eighth Kelly (2.5%) | ~25% of optimal | ~1% | Much lower |

The tradeoff: fractional Kelly grows slower but **survives drawdowns**. Since a 50% drawdown requires a 100% gain to recover, avoiding large drawdowns is more important than maximizing growth rate.

### 4.2 Fractional Kelly: The Practical Standard

Professional bettors and quant funds almost universally use fractional Kelly:

- **Half Kelly**: Aggressive but survivable. Gives ~75% of optimal growth with dramatically lower ruin probability.
- **Quarter Kelly**: The standard "conservative" approach. Used when probability estimates are uncertain — which they always are in prediction markets.
- **Eighth Kelly**: Ultra-conservative. Appropriate for paper trading validation or when the signal is new and unproven.

**Rule of thumb**: Use the Kelly fraction that matches your confidence in your probability estimate:

| Confidence in Your Estimate | Recommended Kelly Fraction |
|----------------------------|---------------------------|
| Very high (proprietary data, Théo-style) | Half Kelly |
| Moderate (strong signal, some uncertainty) | Quarter Kelly |
| Low (new signal, unvalidated) | Eighth Kelly |
| Unvalidated (paper trading) | Track full Kelly but don't trade |

### 4.3 Why Not Just Use Fixed Fractions?

Some traders use simple rules like "always bet 2% of bankroll." This works but leaves money on the table:

- A 2% bet on a massive edge (market at 0.10, true probability 0.90) is far too conservative
- A 2% bet on a tiny edge (market at 0.48, true probability 0.52) is too aggressive relative to the edge
- Kelly adapts to the size of the edge, which fixed fractions don't

That said, **capping** the Kelly fraction at a maximum (e.g., never more than 10% regardless of calculated Kelly) is a sensible guardrail.

---

## 5. Kelly for Spyhop's Executor

### 5.1 The Challenge: What's "p"?

Kelly requires an estimate of the **true probability** of the outcome. For Spyhop, the situation is:

- The **market price** gives the consensus probability
- Spyhop's **suspicion score** tells us how likely the whale trade contains real information
- But the suspicion score is NOT a probability estimate of the market outcome

We need to bridge from "this trade looks like an insider" to "the insider is probably right, so the true probability is higher than the market price."

### 5.2 Proposed Bridge: Score-to-Edge Mapping

```
# Spyhop detects a trade:
#   Market: "Event X by March 15?" at $0.25 (25% implied)
#   Whale bought YES
#   Suspicion score: 8/10

# Step 1: Map suspicion score to "insider correctness" estimate
# Based on documented cases, insiders are right ~85-95% of the time
# (Every confirmed case in RQ2 resolved in the insider's favor)
# Scale by score confidence:

score_to_correctness = {
    7: 0.70,    # Alert threshold — moderate confidence insider is right
    8: 0.80,    # High suspicion — likely right
    9: 0.85,    # Very high — almost certainly right
    10: 0.90,   # Maximum — overwhelming evidence
}

insider_correctness = score_to_correctness[8]  # 0.80

# Step 2: Blend market probability with insider signal
# If we're 80% confident the insider is right, and the insider bought YES:
# Our estimate = (insider_correctness * 1.0) + ((1 - insider_correctness) * market_price)
# This means: 80% chance the outcome is YES (insider is right),
#             20% chance we fall back to market consensus

our_estimate = (0.80 * 1.0) + (0.20 * 0.25) = 0.85

# Step 3: Apply Kelly
b = (1.0 / 0.25) - 1 = 3.0
p = 0.85
q = 0.15

f_star = (0.85 * 3.0 - 0.15) / 3.0 = (2.55 - 0.15) / 3.0 = 0.80

# Step 4: Apply quarter Kelly
position_fraction = 0.80 * 0.25 = 0.20  # 20% of bankroll

# Step 5: Apply maximum cap
position_fraction = min(0.20, 0.10) = 0.10  # Capped at 10%
```

### 5.3 Complete Sizing Pipeline

```
detect_trade(whale_trade)
  → compute suspicion_score (0-10)
  → if score < 7: skip
  → map score → insider_correctness (0.70 - 0.90)
  → compute our_estimate = blend(insider_correctness, market_price)
  → compute kelly_fraction = kelly(our_estimate, market_price)
  → apply fractional_kelly (default: quarter)
  → apply max_position_cap (default: 10% of bankroll)
  → apply staleness_check (price moved > 10%? skip)
  → apply liquidity_check (order book deep enough? reduce if not)
  → execute
```

### 5.4 Worked Example: Iran Strike Scenario

```
Market: "US strikes Iran by Feb 28?" at $0.08 (8% implied)
Whale: Fresh wallet, $60K bet on YES, niche market, 2 hours before event
Suspicion score: 9/10
Bankroll: $50,000

insider_correctness = 0.85 (score 9)
our_estimate = (0.85 * 1.0) + (0.15 * 0.08) = 0.862

b = (1.0 / 0.08) - 1 = 11.5
p = 0.862, q = 0.138

f_star = (0.862 * 11.5 - 0.138) / 11.5 = (9.913 - 0.138) / 11.5 = 0.85

quarter_kelly = 0.85 * 0.25 = 0.213 (21.3%)
capped = min(0.213, 0.10) = 0.10 (10%)

position_size = $50,000 * 0.10 = $5,000
shares = $5,000 / $0.08 = 62,500 shares

If event happens: 62,500 * $1.00 = $62,500 (profit: $57,500, 11.5x)
If event doesn't: loss of $5,000 (10% of bankroll — survivable)
```

---

## 6. Common Mistakes

### 6.1 Estimating Edge from Outcome, Not from Process

**Wrong**: "The insider was right, so my edge was huge."
**Right**: "Before the outcome was known, my *estimated* edge was X based on the suspicion score."

Kelly must be calculated *before* you know the result. If you adjust your "edge" retroactively using outcomes, you'll overfit and overbet.

### 6.2 Ignoring the Denominator

Kelly fractions can be misleadingly large when odds are long. A market at $0.05 (5% implied) with your estimate at 50% produces:

```
b = 19.0, p = 0.50, q = 0.50
f* = (0.50 * 19.0 - 0.50) / 19.0 = 9.0 / 19.0 = 0.47
```

47% of your bankroll on a coin-flip! This is because Kelly only sees the expected value, not the variance. At long odds, even quarter Kelly (11.8%) is aggressive. **Always apply a maximum cap.**

### 6.3 Treating Kelly as a Single-Bet Formula

Kelly is designed for **repeated bets over time**. It optimizes the *sequence*, not any individual bet. A single Kelly-sized bet might lose — that's expected. The magic is in the long-run compounding across many bets.

This means:
- You need many signals over time, not one big trade
- Each bet should be a small fraction of your bankroll
- The growth happens through compounding, not any single win

### 6.4 Forgetting That "p" Is an Estimate

Your probability estimate is the weakest link. Kelly gives the optimal bet *for a given p*. If p is wrong, Kelly's recommendation is wrong. Fractional Kelly (quarter, eighth) is insurance against estimation error.

---

## 7. Summary

| Concept | Key Point |
|---------|-----------|
| What Kelly does | Finds the bet size that maximizes long-run bankroll growth |
| The formula | f* = (p * b - q) / b |
| For prediction markets | b = (1 / market_price) - 1; p = your true probability estimate |
| Why not full Kelly | Assumes perfect probability estimates; too aggressive in practice |
| Recommended fraction | Quarter Kelly for most situations; eighth for unvalidated signals |
| For Spyhop | Map suspicion score → insider correctness → blended probability → Kelly → fractional Kelly → cap |
| Maximum position | Never more than 10% of bankroll on a single trade, regardless of Kelly output |
| Critical caveat | Kelly optimizes a *sequence* of bets, not any single bet. You need many trades for it to work. |

---

## References

- Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*, 35(4), 917-926.
- Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting and the Stock Market." *Handbook of Asset and Liability Management*.
- Application of Kelly Criterion to Prediction Markets — [arXiv:2412.14144](https://arxiv.org/html/2412.14144v1)
- Risk-Constrained Kelly Criterion — [QuantInsti](https://blog.quantinsti.com/risk-constrained-kelly-criterion/)
- Kelly Criterion in Trading Systems — [QuantConnect](https://www.quantconnect.com/research/18312/kelly-criterion-applications-in-trading-systems/)
