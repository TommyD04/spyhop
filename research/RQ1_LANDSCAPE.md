# RQ1: The Landscape — Prediction Markets & the Insider Problem

**Central question**: How prevalent is insider/informed trading in prediction markets, and what structural features make these markets vulnerable?

**Research date**: 2026-03-07

---

## Executive Summary

Prediction markets have grown from a niche curiosity to a **$50B+ annual volume industry** in under three years, driven by the 2024 US election, geopolitical volatility, and a cultural shift toward speculation among younger demographics. This explosive growth has outpaced regulatory frameworks — creating a structural gap where insider trading is **technically possible, practically unpoliced, and only now beginning to face legislative response**. Polymarket and Kalshi control ~97.5% of the market, with fundamentally different regulatory postures (Polymarket: recently re-regulated offshore platform; Kalshi: CFTC-designated contract market). The insider trading problem is not hypothetical — at least 10 documented cases exist on Polymarket alone, one criminal prosecution has been filed (Israel), and Kalshi has disclosed its own enforcement actions. The regulatory landscape is evolving rapidly, with multiple bills introduced in Congress and the CFTC signaling new rulemaking.

---

## 1. Regulatory Status of Major Platforms

### 1.1 Polymarket — From Outlaw to Re-Regulated

**Timeline**:

| Date | Event |
|------|-------|
| Jun 2020 | Polymarket launches; operates as unregistered DeFi binary options platform |
| Jan 2022 | CFTC orders $1.4M penalty; Polymarket charged with operating unregistered exchange for event-based binary options. Required to wind down non-compliant markets |
| 2022-2025 | Operates offshore, accessible to non-US users. US users technically blocked but enforcement limited |
| Nov 2024 | 2024 US election drives massive volume ($3.7B on election alone); mainstream media attention |
| Nov 2025 | Polymarket receives Amended Order of Designation from CFTC, acquiring QCEX to gain regulated status |
| Dec 2025 | Begins phased US rollout via invite-only waitlist; must implement enhanced surveillance, clearing procedures, Part 16 reporting |
| Jan 2026 | US users gain access; Nevada Gaming Control Board files complaint seeking to block Polymarket in Nevada without a state gaming license |
| Feb 2026 | CFTC Chairman Selig withdraws proposed ban on political/sports event contracts; signals new rulemaking for "clear standards" |

**Current status**: Federally regulated in the US via CFTC designation. However:
- US access still limited (phased rollout)
- State-level challenges ongoing (Nevada, Massachusetts)
- Offshore operations continue in parallel
- No KYC for offshore users; on-chain settlement via Polygon

**Insider trading enforcement**: Zero enforcement actions by Polymarket itself (no KYC = limited ability to identify traders). Platform relies on blockchain transparency and third-party forensics.

### 1.2 Kalshi — The Regulated Incumbent

**Status**: Full Designated Contract Market (DCM) designation from CFTC since 2020 — the same classification as CME Group. Every market requires CFTC review and clearance before listing.

**Insider trading enforcement**: Kalshi has opened **200 investigations** in the past year, with over a dozen becoming active cases. Two public enforcement actions disclosed:

| Case | Date | Violation | Penalty |
|------|------|-----------|---------|
| California political candidate | May 2025 | Traded on own candidacy (direct influence over outcome) | $2,246 disgorgement + penalty; 5-year suspension |
| YouTube channel editor | Aug-Sep 2025 | Used non-public knowledge of upcoming video content | $20,398 disgorgement + penalty; 2-year suspension |

Both cases were detected by Kalshi's internal surveillance systems, accounts frozen before profits withdrawn, and referred to the CFTC.

**Key difference from Polymarket**: Kalshi has KYC, centralized accounts, and internal surveillance. Trades are NOT on-chain, making them invisible to public forensics but visible to the exchange. Polymarket has the opposite transparency model — public on-chain data but no identity verification.

### 1.3 Regulatory Comparison

| Dimension | Polymarket | Kalshi |
|-----------|-----------|-------|
| Federal status | CFTC-designated (Nov 2025) | CFTC DCM (2020) |
| KYC required | No (offshore); Yes (US regulated) | Yes |
| Trades on-chain | Yes (Polygon) | No |
| Public transparency | Full (all trades visible) | None (account-level data private) |
| Insider detection | Third-party / community forensics | Internal surveillance team |
| Enforcement actions | 0 (platform-level) | 2 disclosed; 200+ investigations |
| State-level challenges | Nevada, Massachusetts | Massachusetts |

**[ASSERTION]**: The Polymarket/Kalshi regulatory asymmetry creates a paradox: Polymarket's blockchain transparency makes insider activity *detectable* by anyone, but its lack of KYC makes it *unpunishable* by the platform. Kalshi's KYC makes insider activity *punishable* but *invisible* to outside observers. This means Polymarket is structurally better suited for third-party monitoring tools like Spyhop.
**Confidence**: HIGH
**Sources**: T1 (CFTC orders, Kalshi enforcement disclosures), T2 (CoinDesk, PYMNTS, CoinMarketCap)
**Analytic basis**: Direct comparison of platform architectures and enforcement records.
**Implication for Spyhop**: Spyhop's existence is enabled by Polymarket's transparency model. An equivalent tool for Kalshi is structurally impossible without exchange cooperation.

---

## 2. Documented Cases of Insider Trading on Prediction Markets

### 2.1 Case Summary (Detailed analysis in RQ2)

| # | Case | Platform | Date | Category | Profit | Status |
|---|------|----------|------|----------|--------|--------|
| 1 | Israeli military/civilian | Polymarket | Jun 2025 | Geopolitical | $150K+ | **Criminal indictment** (Tel Aviv) |
| 2 | Venezuela/Maduro capture | Polymarket | Jan 2026 | Geopolitical | $436K | Under scrutiny; sparked legislation |
| 3 | Iran strikes cluster (6 wallets) | Polymarket | Feb 2026 | Geopolitical | $1.2M | Bubblemaps forensic analysis |
| 4 | 521 Iran/Khamenei addresses | Polymarket | Feb-Mar 2026 | Geopolitical | Unknown | PANews forensic analysis |
| 5 | Magamyman (Khamenei death) | Polymarket | Mar 2026 | Geopolitical | $553K | Israeli police investigation |
| 6 | OpenAI employee | Polymarket | Feb 2026 | Corporate/Tech | $16.9K (individual) | **Employee fired** |
| 7 | OpenAI 77-position cluster | Polymarket | 2023-2026 | Corporate/Tech | Unknown | Unusual Whales analysis |
| 8 | AlphaRaccoon (Google) | Polymarket | Dec 2025 | Corporate/Tech | $1M+ | No investigation |
| 9 | Axiom/ZachXBT | Polymarket | Feb 2026 | Meta-market | $1.2M | On-chain analysis |
| 10 | KPMG earnings cluster | Polymarket | Feb 2026 | Corporate/Earnings | Unknown | Community analysis |
| 11 | Taylor Swift/romanticpaul | Polymarket | Aug 2025 | Entertainment | $3K | No investigation |
| 12 | California candidate | Kalshi | May 2025 | Political | $246 | **Platform enforcement** |
| 13 | YouTube editor (MrBeast) | Kalshi | Aug 2025 | Entertainment | $5.4K | **Platform enforcement** |

### 2.2 Prevalence Assessment

**[ASSERTION]**: Insider trading on prediction markets is endemic, not exceptional. With 13 documented cases across two platforms in under 18 months — including criminal prosecution, corporate terminations, and platform enforcement — the base rate of insider activity is significantly higher than zero. Given detection limitations and selection bias (we only see the obvious cases), the true prevalence is likely substantially higher.
**Confidence**: HIGH
**Sources**: T1 (Israeli indictment, CFTC advisory, Kalshi enforcement), T2 (NPR, CoinDesk, Bloomberg, Gizmodo)
**Analytic basis**: 13 cases is a floor, not a ceiling. Detection methods are biased toward unsophisticated actors. The KPMG cluster, Magamyman, and OpenAI 77-position cluster suggest more sophisticated, ongoing insider activity.
**Implication for Spyhop**: The market for insider detection tools is validated by the prevalence data. Spyhop addresses a real, documented problem.

---

## 3. Market Growth and the Scale of Opportunity

### 3.1 Volume Explosion

| Period | Monthly Volume | Annual Run Rate | Key Driver |
|--------|---------------|-----------------|------------|
| Early 2024 | < $100M/mo | < $1.2B | Pre-election baseline |
| Nov 2024 | ~$3.7B (election month) | N/A | 2024 US Presidential Election |
| Late 2025 | ~$13B/mo | ~$44B | Post-election diversification |
| Feb 2026 | ~$17.9B/mo (Kalshi + Polymarket combined) | ~$50B+ | Iran war, geopolitical markets |

**Growth**: ~100x in monthly volume from early 2024 to early 2026.

### 3.2 User Growth

- Prediction market users grew from ~4,000 to 600,000+ in 2025
- Polymarket: dominant in crypto-native user base
- Kalshi: growing in US retail via fiat onramps
- Robinhood: prediction markets are "fastest-growing product line," generating $100M+ annualized revenue within first year

### 3.3 Market Duopoly

Kalshi and Polymarket control **97.5%** of prediction market volume. This concentration means:
- Insider activity is concentrated on two platforms
- Detection tools need only target two ecosystems
- Regulatory frameworks need only cover two major players

**[ASSERTION]**: The prediction market industry is in a hyper-growth phase, with volume doubling approximately every 6 months. This growth attracts more capital, more participants, and more information asymmetry — creating both more insider trading opportunity and more demand for detection tools.
**Confidence**: HIGH
**Sources**: T2 (Gambling Insider, DeFi Rate, The Block, PANews, International Banker)
**Analytic basis**: Volume data from multiple independent sources converges on ~$50B 2026 projection. User growth from 4K to 600K+ is a 150x increase.
**Implication for Spyhop**: The addressable market for Spyhop-type tools is growing rapidly. Early mover advantage in detection tooling is significant.

---

## 4. Structural Vulnerabilities

### 4.1 Why Prediction Markets Are Vulnerable to Insider Trading

Traditional securities markets have evolved extensive insider trading defenses over ~90 years of regulation. Prediction markets have almost none:

| Defense | Stock Market | Polymarket | Kalshi |
|---------|-------------|-----------|-------|
| Statutory prohibition | Securities Exchange Act §10(b) | None | CEA fraud provisions (untested) |
| Regulatory enforcement | SEC + DOJ | None (offshore) | CFTC (limited) |
| Platform surveillance | FINRA + exchange monitoring | None | Internal team (200 investigations/yr) |
| Identity verification | Full KYC + beneficial ownership | None (offshore) | Yes |
| Insider reporting obligations | Form 4 filings | None | None |
| Trading blackout periods | Pre-earnings, M&A | None | None |
| Whistleblower programs | SEC bounty program | None | None |
| Penalties | Criminal (up to 20 years) + civil | None (no jurisdiction) | Platform suspension + disgorgement |

### 4.2 The Information Asymmetry Problem

Prediction markets are uniquely vulnerable because:

1. **Resolution depends on real-world events** — unlike stock prices (which reflect discounted cash flows), prediction markets resolve based on binary outcomes controlled by identifiable actors (presidents, generals, executives, investigators)

2. **Information sources are concentrated** — a military operation is known to a small number of officials; an earnings report is known to auditors and executives; a product launch date is known to company employees. The information gradient is steep and binary.

3. **Anonymity is structural** — Polymarket doesn't verify identity. A government official can create a wallet and bet on their own decisions with minimal technical sophistication.

4. **No separation of roles** — Traditional markets separate "insiders" (officers, directors) from "outsiders" and impose trading restrictions on the former. Prediction markets have no concept of "insider status."

5. **Resolution is often abrupt** — A military strike, a product announcement, or an investigation publication resolves a market in minutes. The information advantage is time-limited but absolute.

**[ASSERTION]**: Prediction markets have a structural insider trading vulnerability that is inherent to their design, not a bug to be fixed. Markets that resolve based on discrete human decisions will always be vulnerable to information asymmetry. The question is whether the information aggregation benefits outweigh the insider trading costs.
**Confidence**: HIGH
**Sources**: T1 (academic literature on prediction market efficiency), T2 (Corporate Compliance Insights, Hodder Law, DL News)
**Analytic basis**: Structural analysis of information flow in prediction vs. traditional markets. The vulnerability is architectural, not operational.
**Implication for Spyhop**: Spyhop addresses a permanent market feature, not a temporary bug. Insider detection will be valuable as long as prediction markets exist in their current form.

---

## 5. Parallels with Other "New Marketplace" Insider Patterns

### 5.1 Congressional Stock Trading (STOCK Act)

The STOCK Act (2012) prohibits members of Congress from using non-public information for personal financial gain. Parallels:

- **Passed after public outrage** over documented insider trading by legislators
- **Enforcement is near-zero** — no member of Congress has ever been prosecuted under the STOCK Act
- **Disclosure requirements** exist but are poorly enforced (late filings, minimal penalties)
- **Ongoing concern**: Campaign Legal Center notes "congressional stock trading continues to raise conflicts of interest concerns"

**Parallel to prediction markets**: The Torres bill (Public Integrity in Financial Prediction Markets Act of 2026) follows the STOCK Act pattern — legislation triggered by public outrage, focused on government officials, likely to have weak enforcement.

### 5.2 Sports Betting by Officials

Since the Supreme Court struck down PASPA in 2018, sports betting has expanded to 38+ states. Insider patterns:
- Professional athletes, coaches, and officials betting on games they influence
- Family members and associates placing bets on behalf of insiders
- Information asymmetry: injury reports, lineup decisions, referee assignments

**Parallel**: The prediction market / sports betting boundary is blurring. Kalshi and Polymarket both list sports-adjacent markets. State gaming regulators (Nevada, Massachusetts) are claiming jurisdiction over prediction markets using gambling law frameworks.

### 5.3 Crypto Market Manipulation (Pre-2022)

Before the 2022 crypto crash, insider trading in token launches and exchange listings was rampant:
- Exchange employees front-running token listings
- Project insiders dumping tokens at launch
- Coordinated pump-and-dump schemes

**Parallel**: The same blockchain transparency that enables crypto insider detection enables Polymarket insider detection. Tools like Bubblemaps and Chainalysis have pivoted from crypto market forensics to prediction market forensics.

**[ASSERTION]**: Prediction market insider trading follows a well-documented pattern seen in every "new marketplace" — initial regulatory vacuum, documented abuse, public outrage, legislative response, and eventually some enforcement equilibrium. We are currently in the "public outrage → legislative response" phase.
**Confidence**: HIGH
**Sources**: T1 (STOCK Act text, CFTC enforcement advisory), T2 (Campaign Legal Center, Corporate Compliance Insights, Stinson LLP)
**Analytic basis**: Historical pattern matching across Congressional trading (1990s-2012), sports betting (2018-present), crypto markets (2017-2022), and prediction markets (2024-present). Each follows the same regulatory lifecycle.
**Implication for Spyhop**: The regulatory window is currently open — insider detection tools are most valuable during the "enforcement vacuum" phase. As regulation matures, platform-level surveillance may reduce (but not eliminate) the need for third-party tools.

---

## 6. The Cultural Thesis: Speculation, Gambling, and Prediction Markets

### 6.1 The Demographic Shift

Prediction markets are riding a broader cultural wave:

- **37%** of Gen Z self-identify as sports betting addicts (early 2025 survey)
- **31%** of Americans believe prediction markets will reshape culture
- **30%** of consumers engaged in betting activity in Q2 2025 (up from 25% in Q2 2024)
- Prediction market users grew **150x** (4K → 600K+) in 2025
- Teens (18-20) blocked from gambling are pivoting to prediction platforms like Kalshi
- A majority of Gen Z investors also gamble regularly, "often without a clear distinction between the two activities"

### 6.2 The Investing/Gambling Convergence

The boundaries between investing, trading, and gambling are dissolving:

```
Traditional investing → Day trading → Meme stocks → Crypto → Sports betting → Prediction markets
     (401k)            (Robinhood)    (GME/AMC)     (Doge)    (DraftKings)    (Polymarket)
```

Each step moves toward:
- Shorter time horizons
- More binary outcomes
- Less fundamental analysis, more narrative/momentum
- More gamification (instant feedback, social sharing)
- Lower barriers to entry

Robinhood's prediction markets are its "fastest-growing product line" ($100M+ annualized revenue in first year), suggesting mainstream retail integration is imminent.

### 6.3 Does the Speculation Culture Correlate with Insider Activity?

**Hypothesis**: More participants + more volume + more market types + less regulation = more insider trading opportunity.

**Evidence supporting**:
- Volume growth (100x in 2 years) creates more markets, including niche ones where information asymmetry is highest
- Younger, crypto-native participants are less likely to view insider trading as problematic (cultural norm of "degen" trading)
- Low barriers to entry mean insiders face minimal technical friction (create wallet → fund → bet → withdraw)
- Market proliferation means prediction markets now cover topics where insiders are easy to identify (corporate earnings, military operations, product launches)

**Evidence against**:
- More participants also means more monitoring (Bubblemaps, PANews, Unusual Whales all emerged from the community)
- Blockchain transparency enables forensics that traditional markets lack
- Academic research suggests market manipulation attempts can actually *increase* accuracy by creating profit incentives to bet against manipulators

**[ASSERTION]**: The speculation culture shift is a tailwind for both prediction market growth AND insider trading prevalence. The same demographic and cultural forces driving adoption (gamification, crypto-native users, shorter time horizons) also reduce the perceived stigma of insider trading and lower the friction for executing it.
**Confidence**: MOD
**Sources**: T2 (Futurism, Decrypt, TransUnion, RFI Global, Qz), T3 (community discussion)
**Analytic basis**: Demographic data on gambling/speculation growth is strong. The causal link between cultural attitudes and insider trading prevalence is inferred, not directly measured.
**Implication for Spyhop**: The user base for prediction market tools (including Spyhop) is growing rapidly. The "degen" culture may also create demand for tools that *help* users trade alongside insiders, not just detect them — which aligns with Spyhop's counter-trading features.

---

## 7. The Academic Perspective: Are Insider Traders Good for Markets?

### 7.1 The Information Aggregation Argument

Academic literature identifies a tension:

**For insider participation**:
- Insiders bring private information into public prices, improving prediction accuracy
- Prediction markets' value proposition IS information aggregation — insiders are the most informed participants
- Market manipulation attempts can increase accuracy by creating profit incentives to bet against manipulators
- Corporate prediction markets (Google, Ford) improve forecast accuracy by 25% vs. expert panels, partly because insiders participate

**Against insider participation**:
- Insider trading creates **adverse selection** — informed traders profit at the expense of uninformed participants
- Calibrated forecasters may rationally avoid markets where they expect adverse selection, creating thin, fragile markets
- Insider profits are a wealth transfer from uninformed to informed, not value creation
- Uninformed participants eventually leave, reducing liquidity and the information aggregation that makes prediction markets valuable

### 7.2 The Regulatory Paradox

The CFTC's Division of Enforcement advisory (Feb 2026) states that "misuse of nonpublic information" in prediction markets is subject to CFTC fraud provisions. But:
- SEC insider trading law (§10b-5) does NOT apply — prediction market contracts are not securities
- CFTC's authority over non-securities prediction market manipulation is untested in court
- Polymarket's offshore operations were historically outside CFTC jurisdiction
- The Torres bill would create the first explicit statutory prohibition, but only for government officials

**[ASSERTION]**: The legal framework for prediction market insider trading is nascent and largely untested. The CFTC has signaled intent to regulate but has not yet brought an enforcement action. The Torres/Merkley/Klobuchar bills, if passed, would create the first clear prohibitions but apply only to government officials. For non-government insiders (corporate employees, auditors, journalists), the legal status of prediction market insider trading remains ambiguous.
**Confidence**: HIGH
**Sources**: T1 (CFTC enforcement advisory, Torres bill text, CFTC press releases), T2 (CNBC, Axios, DL News, Hodder Law)
**Analytic basis**: Direct review of regulatory actions and proposed legislation. No court has ruled on CFTC's authority over prediction market insider trading.
**Implication for Spyhop**: The absence of clear legal prohibition means insider trading on prediction markets exists in a gray zone. Spyhop serves a market-integrity function that regulators have not yet filled. This also means Spyhop's outputs are more likely to be used for trading advantage than for enforcement referrals, at least until the legal framework matures.

---

## 8. Key Judgments

### J1: Prediction markets are in the "regulatory vacuum → legislative response" phase
**Confidence**: HIGH — Multiple bills introduced (Torres, Merkley, Klobuchar). CFTC signaling new rulemaking. Parallels STOCK Act (2012), post-PASPA sports betting regulation (2018+). Enforcement equilibrium likely 2-5 years away.

### J2: Insider trading on prediction markets is prevalent and growing
**Confidence**: HIGH — 13 documented cases across 2 platforms in 18 months. Volume growth (100x in 2 years) creates more markets and more opportunity. Detection is improving but enforcement lags dramatically.

### J3: Polymarket's transparency model uniquely enables third-party monitoring
**Confidence**: HIGH — On-chain settlement means every trade is public. Kalshi's opacity makes equivalent monitoring impossible. Spyhop's entire value proposition depends on this transparency.

### J4: The cultural shift toward speculation is a tailwind for both market growth and insider prevalence
**Confidence**: MOD — Demographic data on gambling growth is strong (37% Gen Z self-report as betting addicts; 150x user growth). Causal link to insider trading is inferred, not measured.

### J5: The academic debate on whether insider participation helps or harms prediction markets is unresolved
**Confidence**: MOD — Both sides have theoretical support. Empirically, prediction markets are accurate despite (or because of?) insider participation. The welfare question (who bears the cost) is separate from the accuracy question.

### J6: The prediction market industry is a Polymarket/Kalshi duopoly (97.5% market share)
**Confidence**: HIGH — Multiple independent volume analyses converge. This concentration simplifies the detection problem — Spyhop need only target Polymarket initially.

---

## Sources

### T1 (Primary Evidence)
- CFTC 2022 enforcement order against Polymarket — [CFTC](https://www.cftc.gov/PressRoom/PressReleases/8478-22)
- CFTC Enforcement Division prediction markets advisory (Feb 2026) — [CFTC](https://www.cftc.gov/PressRoom/PressReleases/9158-26)
- Kalshi enforcement case disclosures — [Kalshi Blog](https://news.kalshi.com/p/kalshi-trading-violation-enforcement-cases)
- Torres bill: Public Integrity in Financial Prediction Markets Act — [ritchietorres.house.gov](https://ritchietorres.house.gov/posts/in-response-to-suspicious-polymarket-trade-preceding-maduro-operation-rep-ritchie-torres-introduces-legislation-to-crack-down-on-insider-trading-on-prediction-markets)
- Merkley/Klobuchar: End Prediction Market Corruption Act — [CNBC](https://www.cnbc.com/2026/03/05/prediction-markets-merkley-ban-iran.html)
- STOCK Act text and analysis — [Congress.gov](https://www.congress.gov/bill/112th-congress/senate-bill/2038)
- Academic: Information aggregation in prediction markets — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1386418123000794), [Oxford Academic](https://academic.oup.com/restud/article/91/6/3423/7588779)
- Academic: Manipulation and prediction market accuracy — [Management Science](https://pubsonline.informs.org/doi/10.1287/mnsc.1110.1404)

### T2 (Credible Secondary)
- Polymarket CFTC re-approval — [CoinDesk](https://www.coindesk.com/business/2025/11/25/polymarket-secures-cftc-approval-for-regulated-u-s-return), [The Bulldog Law](https://www.thebulldog.law/polymarket-receives-cftc-approval-to-resume-us-operations-after-years-offshore), [CoinMarketCap](https://coinmarketcap.com/academy/article/polymarket-wins-cftc-approval-for-us-trading-platform)
- CFTC Chairman Selig withdraws proposed ban — [Corporate Compliance Insights](https://www.corporatecomplianceinsights.com/cftc-withdraws-proposed-rule-prediction-markets/), [Sidley Austin](https://www.sidley.com/en/insights/newsupdates/2026/02/us-cftc-signals-imminent-rulemaking-on-prediction-markets)
- Polymarket re-entry to US — [Reason](https://reason.com/2026/01/04/the-return-of-polymarket/), [CryptoNews (legality guide)](https://cryptonews.com/cryptocurrency/is-polymarket-legal/)
- Kalshi vs Polymarket comparison — [DeFi Rate](https://defirate.com/prediction-markets/kalshi-vs-polymarket/), [Laika Labs](https://laikalabs.ai/prediction-markets/kalshi-vs-polymarket)
- Market volume data — [Gambling Insider](https://www.gamblinginsider.com/in-depth/110180/prediction-market-statistics), [DeFi Rate](https://defirate.com/prediction-markets/), [The Block](https://www.theblock.co/post/383733/prediction-markets-kalshi-polymarket-duopoly-2025), [International Banker](https://internationalbanker.com/finance/accounting-for-the-explosive-growth-in-prediction-markets/)
- Kalshi/Polymarket duopoly — [Phemex](https://phemex.com/news/article/kalshi-and-polymarket-dominate-975-of-prediction-market-in-2025-64652)
- Torres/legislation coverage — [Axios](https://www.axios.com/2026/01/05/venezuela-polymarket-prediction-insider-trading), [Yahoo Finance](https://finance.yahoo.com/news/rep-torres-moves-ban-officials-130710169.html), [Front Office Sports](https://frontofficesports.com/prediction-market-scrutiny-intensifies-with-introduction-of-insider-trading-bill/), [SBC Americas](https://sbcamericas.com/2026/01/05/congressman-torres-prediction-markets/)
- Kalshi enforcement — [NPR](https://www.npr.org/2026/02/25/nx-s1-5726050/kalshi-insider-trading-enforcement-actions), [PYMNTS](https://www.pymnts.com/news/regulation/2026/cftc-vows-clean-prediction-markets-as-kalshi-flags-insider-trading/), [Finance Magnates](https://www.financemagnates.com/forex/cftc-flags-insider-risks-in-prediction-markets-as-kalshi-sanctions-two-traders/), [Blockhead](https://www.blockhead.co/2026/02/26/kalshi-cracks-down-on-insider-trading-discloses-first-enforcement-cases/)
- STOCK Act failures — [Campaign Legal Center](https://campaignlegal.org/update/stock-act-failed-effort-stop-insider-trading-congress)
- Legal analysis — [Hodder Law](https://hodder.law/insider-trading-prediction-markets/), [DL News](https://www.dlnews.com/articles/regulation/prediction-markets-bend-insider-trading-rules-will-they-break/), [Corporate Compliance Insights](https://www.corporatecomplianceinsights.com/prediction-markets-sports-betting-insider-trading/)
- Sports betting / prediction market tension — [Stinson LLP](https://www.stinson.com/newsroom-publications-sportsbooks-or-commodity-exchanges-the-rising-legal-tensions-between-sports-betting-and-prediction-markets)

### T3 (Community Intelligence)
- Cultural shift / gambling — [Futurism](https://futurism.com/future-society/prediction-markets-gambling), [Decrypt](https://decrypt.co/355886/gen-z-betting-big-prediction-markets), [RFI Global](https://rfi.global/prediction-markets-as-a-window-into-gen-z-and-millennial-financial-thinking/), [TransUnion](https://newsroom.transunion.com/gen-z-millennial-speculators-drove-year-over-year-gambling-growth-in-q2-2025/), [Qz (teen gambling)](https://qz.com/prediction-markets-teenage-gambling)
- Market outlook — [insights4vc](https://insights4vc.substack.com/p/prediction-markets-at-scale-2026), [Monolith VC](https://medium.com/@monolith.vc/prediction-markets-2025-polymarket-kalshi-and-the-next-big-rotation-c00f1ba35d13)
- Nevada complaint — [DataWallet (restricted countries)](https://www.datawallet.com/crypto/polymarket-restricted-countries)
