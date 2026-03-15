# V4b — FARM Detection: Empirical Analysis of Both-Side Trading in Spyhop Data

## Status

**Phase**: Research complete, implementation pending
**Data window**: 2026-03-06 to 2026-03-15 (9 days, ~10K trades)
**Limitation**: Single-week sample. Patterns should be validated over 2–3 additional weeks before calibrating final thresholds.

---

## 1. Problem Statement

Spyhop's composite scorer (fresh wallet × size anomaly × niche market) identifies large, unusual trades as potential insider signals. The paper trader then follows these signals. However, some high-scoring trades come from wallets that are **trading both sides of the same market** — effectively hedging or market-making, not expressing directional conviction. Following one leg of a hedged pair earns zero edge minus spread, wasting position slots and capital.

This analysis examines the empirical prevalence, structure, and behavioral signatures of both-side trading in the live Spyhop dataset to design a detection and exclusion mechanism ("FARM filter") for the paper trading pipeline.

---

## 2. Scale of the Problem

### Raw numbers

| Metric | Value |
|--------|-------|
| Total trades in DB | 10,308 |
| Wallet-market pairs with both-side trading | 39 |
| Unique wallets involved | 20 |
| Total hedged gross volume | ~$7M |
| Hedged trades as % of all trades | ~2% by count |
| Signal contamination (score ≥ 6.0 from hedgers) | 13 of 520 (2.5%) |

### Why 2.5% contamination matters

The 13 contaminated signals are disproportionately **large-dollar trades** — exactly the ones the paper trader sizes up on. All 13 come from a single wallet (`0x2a2C53bD...`) hitting `size_anomaly=3.0 × niche_market=2.5 = score 6.5` repeatedly on sports O/U and match-winner markets. With `min_score=6.0` and score-weighted sizing, these would become the paper trader's largest positions — and they're directionally meaningless.

### Repeat offenders

Two wallets dominate:

| Wallet | Markets Hedged | Gross Volume | Trades in RTDS | Trades (Deep Profile) | Unique Markets (Deep) |
|--------|:-:|:-:|:-:|:-:|:-:|
| `0x2a2C53bD...` | 13 | $2.35M | 239 | **806** | **442** |
| `0x7AF9Bac9...` | 4 | $1.87M | 54 | **478** | **175** |

Both are profiled as `trade_count=6` in the shallow wallet cache (the `limit=6` ceiling), masking their true scale. Deep API profiling reveals they are systematic operators: 66 and 18 trades/day respectively, across hundreds of markets.

---

## 3. Three Behavioral Clusters

Analysis of combined pricing (`sum_p` = avg price side A + avg price side B), net exposure ratio, market type, and timing reveals three distinct clusters.

### Cluster A — Pure Market-Makers (tight spread, balanced)

| Attribute | Value |
|-----------|-------|
| sum_p | 0.95–1.02 |
| Net ratio (|USD_A - USD_B| / gross) | < 0.25 |
| Market types | Spread bets, head-to-head (NBA, tennis) |
| Pairs in dataset | 6 |
| Hedge gap | Seconds to low minutes |

**Signature**: Near-equal USD on both sides, prices barely moved between legs. Classic two-sided liquidity provision. Zero directional signal.

**Detection confidence**: Very high. Low false-positive risk.

### Cluster B — In-Play Soccer Operators (tight spread, directional)

| Attribute | Value |
|-----------|-------|
| sum_p | 0.95–1.02 |
| Net ratio | 0.40–0.80 |
| Market types | Soccer "Will X FC win on..." match-winner markets |
| Pairs in dataset | 17 |
| Hedge gap | 5–60 minutes |

**Signature**: Tight combined pricing (prices didn't shift much) but heavily skewed to one side. These wallets are building directional positions during live UCL/EPL matches while partially hedging. The tight sum_p means both legs traded at similar odds; the skewed net_ratio means they have a view but manage risk.

**Detection confidence**: Moderate. The larger leg may contain signal, but the hedge contaminates it. Repeat-offender tracking (hedging on N+ distinct markets) is the safest filter.

### Cluster C — Dynamic In-Play Hedgers (shifted spread)

| Attribute | Value |
|-----------|-------|
| sum_p | 1.20–1.94 |
| Net ratio | 0.20–0.80 |
| Market types | NBA head-to-head, tennis, live sports with fast price movement |
| Pairs in dataset | 12 |
| Hedge gap | 15 minutes to hours |

**Signature**: Prices moved dramatically between the two legs — a goal was scored, a set was won, or momentum shifted. The high sum_p means they bought one side at one price regime and the other side at a completely different price. They're reacting to live events, not pre-positioning.

**Detection confidence**: Lower. The first leg may have been a legitimate signal at the time of entry. The hedge arrives later in a different price context. Risk: filtering these suppresses some genuine in-play reaction signals.

---

## 4. Category Patterns

### Hedged market types (keyword-classified)

| Category | Markets | Wallets | Trades | % of Hedged Activity |
|----------|:-:|:-:|:-:|:-:|
| Soccer match-winner | 8 | 10 | 113 | ~55% of trades |
| Head-to-head (NBA, tennis) | 8 | 6 | 34 | ~17% |
| Over/Under (NHL, NBA, soccer) | 7 | 2 | 20 | ~10% |
| Spread bets (NBA, UCL) | 3 | 3 | 11 | ~5% |
| Tennis | 2 | 2 | 16 | ~8% |
| Social (Elon tweets) | 1 | 1 | 7 | ~3% |
| Politics (Iran regime) | 1 | 1 | 4 | ~2% |

**27 of 28 hedged markets are live sports.** Only 2 non-sports markets show both-side trading (Elon Musk tweets, Iranian regime). The Columbia study's finding that 45% of sports volume is wash trading is consistent with what we see here.

### Event slug coverage gap

19 of 28 hedged markets have `NO_TAG` in the events table because the Gamma API event slug doesn't always match between the `markets` and `events` tables. Sports markets with structured slugs (e.g., `ucl-psg1-cfc1-2026-03-11-psg1`) don't resolve to their parent event. This means category-based filtering must use keyword heuristics on `market_question`, not the events table `primary_tag`.

### Timing confirms in-play activity

| Hour (UTC) | Hedged Trades | Corresponds to |
|:-:|:-:|:--|
| 19:00 | **66** | UEFA Champions League kickoff |
| 16:00–17:00 | 44 | EPL afternoon matches |
| 23:00–01:00 | 48 | US evening sports (NBA, NHL) |

---

## 5. Spread (sum_p) Patterns

### Distribution

| sum_p Range | Pairs | Interpretation |
|:-:|:-:|:--|
| < 0.98 | 4 | Market-maker capturing spread |
| 0.98–1.02 | 26 | Both legs traded at essentially the same odds |
| 1.02–1.20 | 2 | Slight price shift between legs |
| > 1.20 | 10 | Major in-play price movement between legs |

### Category × Spread interaction

**Tight spread (sum_p ≤ 1.05):**

| Market Type | Pairs | Avg net_ratio | Behavior |
|:--|:-:|:-:|:--|
| Spread bets | 3 | 0.203 | Pure MM — most balanced |
| Head-to-head | 3 | 0.148 | Pure MM — most balanced |
| Over/Under | 6 | 0.377 | MM with slight lean |
| Match-winner | 17 | 0.531 | Directional + partial hedge |

**Shifted spread (sum_p > 1.05):**

| Market Type | Pairs | Avg net_ratio | Behavior |
|:--|:-:|:-:|:--|
| Head-to-head | 9 | 0.359 | In-play reaction (NBA, tennis) |
| Other | 3 | varies | Elon tweets, soccer, O/U |

**Key finding**: Tight-spread + low net_ratio (SPREAD and H2H types) = highest-confidence FARM signal. Tight-spread + high net_ratio (MATCH_WINNER) = mixed signal. Shifted-spread = lowest-confidence FARM signal (may be legitimate in-play trading).

---

## 6. Detection Time Window (R2)

### How fast does the hedge arrive?

| Gap Bucket | Pairs | Cumulative % |
|:-:|:-:|:-:|
| < 10s | 1 | 2% |
| 10s–1m | 2 | 7% |
| 1–5m | 4 | 17% |
| 5–15m | 11 | 44% |
| 15–60m | 13 | 76% |
| 1–6h | 8 | 95% |
| 6h+ | 2 | 100% |

**Median hedge gap: ~15 minutes.** Only 3 of 41 pairs complete within 60 seconds (the heuristic proposed in the original REWARD_FARMING.md).

### First-leg signal status

Of 41 hedge pairs analyzed (first-leg-to-first-hedge-leg):
- 32 first legs have signals in the signals table
- **5 scored ≥ 6.0** (all from `0x2a2C53bD`, all sports)
- **0 triggered alerts** (none reached score ≥ 7)
- No paper positions exist yet (table empty), so this is a pre-emptive fix

### Implication for lookback window

A **30-minute lookback** catches ~60% of hedge pairs at the time the second leg arrives. A **60-minute lookback** catches ~76%. The lookback approach works well for detecting the *hedge leg* (blocking the second trade), but cannot prevent entry on the *first leg* — that requires wallet reputation (Layer 2).

---

## 7. Deep Wallet Profiles (R1)

### Shallow profile blindspot

All 20 both-side wallets show `trade_count=6` in the wallet cache — the shallow fetch ceiling (`limit=6`). The system cannot distinguish a 6-trade newcomer from an 800-trade market-maker.

### Deep API results (top 3 wallets)

| Wallet | Shallow Count | Actual Trades | Actual Markets | Volume | Trades/Day |
|--------|:-:|:-:|:-:|:-:|:-:|
| `0x2a2C53bD...` | 6 | 806 | 442 | $15.8M | 66 |
| `0x7AF9Bac9...` | 6 | 478 | 175 | $5.7M | 18 |
| `0x7312a01D...` | 6 | 187 | 82 | $851K | 13 |

These are professional-scale operators. The fresh wallet detector correctly returns 1.0x for them (they exceed the 5-trade threshold), but a deep profile revealing 400+ markets would be a much stronger disqualifier.

---

## 8. Bonus Finding: Multi-Outcome Event Spreaders

Three high-frequency wallets (`0xd04d93BE`, `0x241f846866C2`, `0xA8B202e6`) trade 60–278 times concentrated on 3–5 markets — but never trigger both-side detection because they trade **related but separate condition_ids** within the same event:

- "Will the Fed decrease rates by 50+ bps?" (condition A)
- "Will the Fed increase rates by 25+ bps?" (condition B)
- "Will there be no change in Fed rates?" (condition C)

These are effectively spreading across the probability space of a single event. Current detection (same wallet + same condition_id + opposite outcome) misses them entirely. Detection at the **event level** (grouping related condition_ids) would catch this, but requires a different data model.

**Scope**: Deferred to a future iteration. Condition_id-level detection covers the primary risk (sports market-makers).

---

## 9. Proposed Two-Layer Defense

### Layer 1 — Real-Time Lookback (catches hedge leg)

When a new trade scores ≥ `min_score` and the paper trader considers entry:

1. Query: "Has this wallet traded the **opposite outcome** on the same `condition_id` within the last T minutes?"
2. If yes → reject paper trade, log as `FARM_HEDGE`
3. Recommended T: **30 minutes** (catches ~60% of hedge pairs)

This blocks the second leg of a hedge pair but cannot prevent entry on the first leg.

### Layer 2 — Wallet Reputation (catches first leg proactively)

Maintain a `farm_wallets` set (table or in-memory). A wallet gets flagged when:

1. Layer 1 has caught it on **N+ distinct markets** (recommended N=2)
2. Once flagged, ALL future trades from that wallet are suppressed from paper trading

This is the "fool me twice" defense. After observing a wallet hedge on 2+ markets, we have high confidence it's a systematic hedger, not a one-time position reversal.

### False positive mitigation

- A legitimate trader selling a position they no longer believe in would appear as opposite-side on **1 market**, not 2+. The N≥2 threshold on Layer 2 avoids punishing one-time reversals.
- Layer 1 only blocks the paper trade — it doesn't suppress the signal from the database or dashboard. The trade is still visible and scored; it's just not followed.

---

## 10. Data Limitations & Next Steps

### What we know

- Both-side trading is overwhelmingly sports-focused (27/28 markets)
- Two wallets account for ~60% of hedged volume
- Median hedge gap is ~15 minutes — lookback detection is feasible
- Deep profiles confirm these are high-volume systematic operators, not insiders

### What we don't know (9-day sample limitation)

- Whether the same wallets persist week-over-week or rotate
- Whether the sports-heavy skew holds across different sporting calendars
- Whether the Fed rate spreaders are persistent or event-specific
- Whether the 15-minute median gap is stable across market types over time
- The false-positive rate of the proposed heuristics on a larger dataset

### Recommended plan

1. **Continue data collection** for 1–2 weeks while implementing
2. **Implement Layer 1** (lookback, T=30min) — conservative, low risk of false positives
3. **Implement Layer 2** (reputation, N=2) — builds on Layer 1 observations
4. **Re-validate** heuristic parameters after 3 weeks of data
5. **Defer** multi-outcome event-level detection (Fed spreaders) to a later phase

---

## 11. Adjacent Open Questions

These issues surfaced during the FARM investigation and are closely related. Gathering them here for scoping before implementation.

### Q1: Shallow wallet profile ceiling (limit=6)

**Problem**: `WalletCache._fetch_shallow()` requests `limit=6` from the Data API. Any wallet with 6+ trades appears identical — a 7-trade newcomer looks the same as an 800-trade market-maker. The fresh wallet detector correctly returns 1.0x for all of them, but FARM detection needs to distinguish these.

**Proposed fix**: Bump `limit` from 6 to 25–50. Still a single API call, no pagination needed, negligible payload increase. A wallet returning 50 trades across 30+ markets is a structurally different actor than one returning 7 trades on 2 markets. This enables a richer wallet classification (see Layer 2 reputation) without adding system complexity.

**Trade-off**: Slightly larger API response on the hot path. At `limit=25`, the incremental data is ~4KB per wallet — well within the profiling budget.

**Status**: Implemented. Limit bumped to 25, 1,619 stale cache entries invalidated.

### Q2: Event category tagging — slug mismatch (UNKNOWN tags)

**Problem**: 70% of markets show as UNKNOWN/NO_TAG in the dashboard because the `events` join uses exact slug matching (`e.event_slug = m.slug`), but market slugs have outcome-specific suffixes:

```
Event slug:  bun-hof-wol-2026-03-14
Market slug: bun-hof-wol-2026-03-14-hof       (outcome suffix)
Market slug: nba-was-bos-2026-03-14-total-229pt5  (market type suffix)
```

**Fix (two-step lookup)**:
1. **Exact match first** (indexed, O(1)) — preserves the 332 markets that already resolve correctly
2. **Prefix fallback on miss** — `SELECT ... FROM events WHERE ? LIKE event_slug || '%' ORDER BY LENGTH(event_slug) DESC LIMIT 1`

The `ORDER BY LENGTH DESC` picks the longest (most specific) matching event slug, which correctly handles the `-more-markets` ambiguity (some events exist in both base and `-more-markets` variants). The direction of the `LIKE` is important: the market slug (longer) is tested against the event slug (prefix), not the other way around.

**Impact on V4b**: Proper category tagging enables category-weighted FARM detection (sports hedging is structurally different from political hedging) and feeds into the dashboard experience.

**Status**: Implemented.

### Q3: Resolution proximity screening — long-dated market filter

**Problem**: The paper trader has no awareness of when a market resolves. Observed: a GOP house control bet that doesn't resolve for ~8 months got paper-traded — no insider edge exists that far out.

**Existing research** (from `SYNTHESIS.md` §2.1 and `RQ3_DETECTION_HEURISTICS.md` §2.4):

| Time Band | Label | Proposed Modifier | Rationale |
|:-:|:-:|:-:|:--|
| > 30 days | SPECULATIVE | 0.5x dampen | Too far for insider knowledge to exist |
| 7–30 days | EARLY | 1.0x neutral | Informed trader sweet spot |
| 1–7 days | HOT | 1.5x boost | Insider sweet spot — info exists, not yet public |
| < 24 hours | IMMINENT | 2.0x boost | Peak insider risk |

Also proposed: a kill switch for < 1 hour to resolution (insufficient time to capture edge).

**What's needed for implementation**: Market end-date data. The Gamma API provides `end_date_iso` on events/markets, but we don't store it yet. Requires:
1. Schema addition: `end_date` column on `markets` or `events` table
2. Capture `end_date_iso` during Gamma API fetch
3. A new detector or score modifier that computes time-to-resolution at signal time

### Q4: Niche market low-odds outsized bets (undeveloped thesis)

**Observation**: In some categories, outsized bets at very low odds (e.g., $50K at 5¢) on niche markets may represent high-conviction signals worth tailing with small positions. The intuition: a 20:1 payout on a low-volume market from a non-farming wallet could indicate genuine information advantage.

**Status**: Thesis not yet developed. Needs:
- Definition of "low odds" threshold (< 10¢? < 20¢?)
- Category constraints (which markets does this apply to?)
- Interaction with existing detectors (NicheMarketDetector already flags low-volume markets; how does price regime modify the signal?)
- Risk model: Kelly-criterion sizing for low-probability high-payout bets

This is conceptually the inverse of FARM filtering — instead of *excluding* noise, it's about *boosting* a specific signal shape. May warrant its own detector or a score modifier layer.

---

## Appendix: Key Queries

All analysis performed on `C:/Users/thoma/AppData/Local/spyhop/spyhop.db`.

### Identify both-side wallet-market pairs
```sql
SELECT t.wallet, t.condition_id, GROUP_CONCAT(DISTINCT t.outcome) as outcomes,
       COUNT(*) as trades, SUM(t.usdc_size) as total_usd
FROM trades t
GROUP BY t.wallet, t.condition_id
HAVING COUNT(DISTINCT t.outcome) > 1
ORDER BY total_usd DESC
```

### Time gap between opposite-side legs
```sql
SELECT t1.wallet, t1.condition_id,
       t1.outcome as out1, t2.outcome as out2,
       ROUND((julianday(t2.timestamp) - julianday(t1.timestamp)) * 86400) as gap_seconds
FROM trades t1
JOIN trades t2 ON t1.wallet = t2.wallet
              AND t1.condition_id = t2.condition_id
              AND t1.outcome != t2.outcome
              AND t1.timestamp < t2.timestamp
```

### Net exposure per hedge pair
```sql
WITH per_outcome AS (
    SELECT wallet, condition_id, outcome,
           SUM(usdc_size) as side_usd, AVG(price) as avg_price
    FROM trades
    GROUP BY wallet, condition_id, outcome
)
SELECT a.wallet, a.condition_id,
       (a.avg_price + b.avg_price) as sum_p,
       ABS(a.side_usd - b.side_usd) / (a.side_usd + b.side_usd) as net_ratio
FROM per_outcome a
JOIN per_outcome b ON a.wallet = b.wallet
                  AND a.condition_id = b.condition_id
                  AND a.outcome < b.outcome
```
