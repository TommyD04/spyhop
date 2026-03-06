# Spyhop Research Plan

## Purpose

Develop an evidence-based understanding of suspicious whale behavior in prediction markets — specifically Polymarket — to inform detection heuristics and trading strategy for the Spyhop tool. This research supports practical application: the findings will directly configure detection thresholds, scoring weights, and trade logic.

## Analytic Framework

### Confidence Ratings

Adapted from the IC's Analytic Standards (ICD 203). Each key judgment carries a confidence level reflecting source quality, corroboration, and analytic certainty.

| Level | Label | Definition |
|-------|-------|------------|
| **HIGH** | High Confidence | Well-corroborated by multiple independent, reliable sources. Analytic logic is strong. Changing this judgment would require significant new evidence. |
| **MOD** | Moderate Confidence | Based on credibly sourced information, but with gaps. Could be interpreted differently. Plausibly correct but not locked in. |
| **LOW** | Low Confidence | Based on fragmentary, single-source, or unverifiable information. May reflect a plausible pattern but lacks corroboration. Treat as hypothesis. |

### Source Tiers

| Tier | Description | Examples |
|------|-------------|---------|
| **T1** | Primary evidence: academic research, regulatory filings, court documents, on-chain forensic analysis with transparent methodology | CFTC orders, academic papers, Chainalysis/Nansen reports with methodology |
| **T2** | Credible secondary: investigative journalism from established outlets, well-sourced analysis from known researchers/analysts | WSJ, Bloomberg, The Block, CoinDesk investigations, named-author Substack with track record |
| **T3** | Community intelligence: social media threads, anonymous analyses, forum posts, Discord/Telegram leaks | Crypto Twitter, Reddit r/polymarket, anonymous on-chain sleuthing, trading community lore |

**Handling T3 sources**: Not dismissed, but flagged. Community intelligence often surfaces patterns before formal analysis catches up. A T3 claim corroborated by on-chain data or multiple independent T3 sources can elevate to effective T2.

### Assertion Format

Each research topic produces a set of key judgments in this format:

```
**[ASSERTION]**: [Statement of finding]
**Confidence**: [HIGH | MOD | LOW]
**Sources**: [T1/T2/T3 citations]
**Analytic basis**: [Why we assess this — what evidence supports/contradicts]
**Implication for Spyhop**: [How this informs detection or trading logic]
```

---

## Research Questions

Organized into four workstreams. Each produces a standalone document.

### RQ1: The Landscape — Prediction Markets & the Insider Problem

**File**: `RQ1_LANDSCAPE.md`

**Central question**: How prevalent is insider/informed trading in prediction markets, and what structural features make these markets vulnerable?

Sub-questions:
- What is the regulatory status of Polymarket, Kalshi, and comparable platforms? How does regulatory ambiguity create insider trading opportunity?
- What documented cases exist of insider or informed trading on prediction markets (any platform)?
- How does the political betting boom (2024 US election) compare to earlier prediction market activity in terms of volume, participant profile, and suspicious activity?
- What parallels exist with Congressional stock trading (STOCK Act), sports betting by officials, and other "new marketplace" insider patterns?
- What is the cultural thesis: is there evidence of a broader shift toward speculation/gambling orientation, and does it correlate with insider activity in new markets?

**Source strategy**: T1 (CFTC actions, academic literature on prediction market efficiency) + T2 (investigative journalism on Polymarket controversies, election betting coverage) + T3 (community narratives about "the house always wins")

**Priority**: Medium — contextual foundation. Skim first, deep-dive only where findings directly inform detection.

---

### RQ2: Known Whale & Insider Patterns on Polymarket

**File**: `RQ2_WHALE_PATTERNS.md`

**Central question**: What specific behavioral signatures distinguish insider/informed traders from legitimate whales on Polymarket?

Sub-questions:
- What are the documented cases of suspected insider trading on Polymarket? (The "French whale" / Théo controversy, election markets, other named cases)
- What on-chain forensic analyses have been published? What patterns did they identify?
- What distinguishes a "smart money" whale (legitimate edge) from a suspected insider (non-public information)?
- What wallet behaviors correlate with insider trading: wallet age, funding patterns, trade timing relative to resolution, position concentration, bet sizing?
- Are there known wallet clusters or Sybil patterns (multiple wallets, single actor)?
- What role do market makers vs. directional bettors play, and how do you distinguish them?
- What is the typical "insider playbook" as described by on-chain researchers?

**Source strategy**: T2 (investigative pieces on specific controversies) + T3 (Crypto Twitter forensic threads, Polymarket community analysis) + T1 (any academic work on prediction market microstructure)

**Priority**: HIGH — this is the core input to Spyhop's detection logic. Every finding here maps to a detector threshold or scoring weight.

---

### RQ3: Detection Heuristics — What Practitioners Actually Use

**File**: `RQ3_DETECTION_HEURISTICS.md`

**Central question**: What heuristics do on-chain analysts, competing tools, and trading communities use to flag suspicious Polymarket activity?

Sub-questions:
- What detection approaches do existing tools use? (Polywhaler, Polysights, Polymarket Whales Twitter bots, community dashboards)
- What thresholds do practitioners use for "whale" classification? ($ amount, % of book, % of daily volume)
- How do on-chain sleuths trace wallet funding sources? What patterns are red flags vs. benign?
- What is the false positive landscape — what looks suspicious but is actually legitimate? (Market makers rebalancing, arbitrage bots, large retail)
- What temporal patterns matter? (Time-to-resolution, time-of-day, burst patterns)
- What market characteristics make a trade more suspicious? (Low liquidity, niche topic, near resolution)
- What scoring or ranking approaches have been proposed or implemented?
- What are the known blind spots or evasion techniques? (Trade splitting, wallet rotation, OTC)

**Source strategy**: T3 (practitioner threads, tool documentation, trading community discussion) + T2 (analysis write-ups) + T1 (academic anomaly detection methods applicable to order flow)

**Priority**: HIGHEST — directly configures Spyhop's detectors, thresholds, and scoring formula. Practitioner heuristics are the primary output.

---

### RQ4: Counter-Trading Strategy — Betting Alongside (or Against) Whales

**File**: `RQ4_COUNTER_TRADING.md`

**Central question**: What is the evidence that following or fading whale trades is profitable on Polymarket, and what strategies have been proposed?

Sub-questions:
- Is there published evidence (backtests, P&L reports, academic studies) on the profitability of whale-following strategies on prediction markets?
- What is the latency problem — how quickly do prices move after a whale trade, and is there a window to act?
- Copy vs. contrarian: under what conditions does each work? Are there signal-specific recommendations?
- What bet sizing approaches are used for signal-based trading? (Kelly criterion, fixed fraction, score-scaled)
- What are the known failure modes? (Whales being wrong, price already moved, liquidity dried up)
- What risk management frameworks exist for this type of strategy?

**Source strategy**: T3 (trading community experience, backtesting claims) + T2 (strategy write-ups) + T1 (academic work on informed trading and price impact)

**Priority**: High — directly informs Spyhop's executor, risk engine, and bet sizing curve.

---

## Research Execution

### Approach

Each RQ will be researched via web search, with findings compiled into the assertion format above. Research is iterative — early findings in one RQ may surface leads for another.

### Sequencing

```
RQ3 (Detection Heuristics)     ← Start here: highest practical value
  |
RQ2 (Known Whale Patterns)     ← Grounds heuristics in specific cases
  |
RQ4 (Counter-Trading Strategy) ← Informs executor and risk config
  |
RQ1 (Landscape)                ← Cultural context, regulatory backdrop
```

RQ3 first because it most directly feeds Spyhop's V1-V3 build. RQ1 last because it's contextual — important for the thesis but not blocking implementation.

### Deliverables

| Deliverable | Description |
|-------------|-------------|
| `RQ1_LANDSCAPE.md` | Landscape assessment with key judgments |
| `RQ2_WHALE_PATTERNS.md` | Catalog of known insider patterns and cases |
| `RQ3_DETECTION_HEURISTICS.md` | Practitioner heuristics with thresholds and confidence |
| `RQ4_COUNTER_TRADING.md` | Counter-trading strategy evidence and recommendations |
| `SYNTHESIS.md` | Cross-cutting findings: recommended Spyhop defaults with confidence-weighted rationale |

`SYNTHESIS.md` is the capstone — it translates research findings into specific, actionable configuration recommendations for Spyhop's detectors, scoring, risk engine, and trading logic.
