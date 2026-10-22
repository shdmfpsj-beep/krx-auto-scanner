# C3 / K100 MASTER — Sector First (2026-10-22)

## 2026-10-23 ACTIVE OVERRIDE — REGULAR ONLY (supersedes full-day instructions below)

- Production C3/K100 strategy uses **KRX regular 09:00–15:30 only**. KRX after-market 16:00–20:00, and off-hours closing-price trades 15:40–16:00, must stay in a separate diagnostic layer; never merge later OHLC, turnover, prices or money-flow with the regular strategy.
- User alerts KST are 08:35 premarket, 13:00 intraday, 16:00 regular-close preview, and **18:30 REGULAR-ONLY final** (replaces 22:15). Github regular-only 18:00 report precedes it. Old automatic 22:00 Sector First and 22:05 research bridge are now **manual-only** all-session historical diagnostics.
- Strict early capture is scheduled at **15:35 KST**, before off-hours trading starts 15:40. Actual API execution start AND completion must fall in 15:33–15:39. Scheduler/API late => CAPTURE_WINDOW_NOT_VERIFIED / CASH. No retroactive dating.
- PyKRX get_market_ohlcv(date, market) is a date-only source without explicit regular-session attestation; capture time alone does not prove regular-only OHLC, turnover or investor flows. Never invent such attestation. Require verified session-scoped minute candles or independently documented, session-certified source before BUY can be considered.
- Separate archives: krx-regular-observation at 15:35, krx-aftermarket-observation at 20:25 (diagnosis only), krx-regular-only-18h-final at 18:00. The final report must never download the after-market archive.
- A BUY setup requires >=65 correctly scoped historical regular-session bars, verified regular-session foreign/institution investor flow and constituent turnover, daily structure stop before entries, cost-adjusted R:R>=2, verified final score >=80/100, cash and one-slot C3 checks. Data unavailable -> PENDING_DATA_VALIDATION and CASH, not confirmed 0 candidate universe.
- Legacy v18 20:15 source is an **all-session diagnostic**, not regular-only production evidence. Workflow CI success is not proof of valid quotes, actual returns, or BUY approval. Orders disabled.

## One outcome
**Every completed Korean trading day, identify the three sectors with the strongest verifiable convergence of fresh positive catalysts, trading activity, and investor money flow; select quality stocks only from these sectors; propose a technically justified structural stop first and then realistic 1st/2nd entry prices. If evidence or entry quality is insufficient, recommend CASH.**

No new paid server, Kiwoom token requirement or trading order API in the baseline workflow. Keep free GitHub + freely accessible public data. Do not promise verified live market data when unavailable.

## Required execution order (never invert)
1. **Sector TOP3 FIRST** — compare all eligible KRX sectors using dated catalysts, verified turnover/volume and breadth, verified net buying / money flow when accessible. Keep the already established sector scoring rubric consistent across the 08:35, 13:00, 16:00 and night reports: verified money inflow / turnover / investor net buying 30, news / disclosures / concrete fresh catalysts 20, forward earnings / orders / industry growth 20, breadth across constituent stocks 20, US macro / global linkage 10. Do not silently redistribute missing-item scores. Record scores, as-of, URLs/sources and unavailable items. Missing net flows must not be fabricated from rising price or inferred turnover. If source coverage is weak, label TOP3 *provisional*, avoid recommending a buy.
2. **Inside those three sectors only** — expand to around 20 quality candidates overall based on ordinary-share eligibility, earnings/growth/financial soundness, verified catalyst, flow, and rising trend. Exclude pharma/biotech per user's current instruction. Unknown financials or instrument type must be marked unverified. Do not treat temporary price rankings as proof of business quality.
3. **Select TOP5 max, not forced** — prioritize 1–5 trading-day setups: leader continuation, first controlled pullback after transition, reclaim, pre-ignition / 2nd-line transmission. Independent score >=80/100 only when its underlying components (sector+flow, fundamental+catalyst, trend, setup) are verified; **the existing technical preliminary score is not this final 100-point score.** If fewer than five qualify, return fewer or none. Do not invent a numerical five-day return probability.
4. **Stop BEFORE buys** — establish actual completed DAILY-bar confirmed structural pivot/retest invalidation (not 10-minute low), ensure positive rational stop and feasible risk. Then show 1st and 2nd entry price ranges based on support/reclaim, no-chase cap, realistic resistance-based target and forward R:R. Never use fixed arbitrary 1% or automatic averaging. Absence of verified level => unpriced watch / CASH.
5. **Trade gate** — CASH at top if market weak, total verified stock score <80, price extended, R:R poor, cash/position unknown, or any critical evidence missing. No simultaneous C3 second position. Do not invent available cash or orderable shares. Existing K100 Core positions are managed separately from new entries.

## World-first leading-news intake (free GitHub Actions)
- **08:05 KST weekdays**: `.github/workflows/global_sector_morning.yml` collects GDELT foreign industry/macro *search samples* and writes `global_preopen_brief_mobile.md`. Label independent-headline early-watch sectors as foreign **research only**. Count different source domains AND distinct headline signatures, discounting exact syndicated duplicates.
- **08:35 KST alarm**: read that morning artifact; explain overseas event → likely industry exposure → possible Korean beneficiaries/losers → **KRX verification still required**. Use dated original articles and company disclosures where independently verifiable; do not conflate GDELT seen timestamp with original publication.
- **20:15 KST weekdays**: Sector Evidence v18 starts its scheduled post-20:00 KRX after-market read-only collection. Same-day full-session evidence is not eligible as completed until **20:10 KST**, and it must then pass independent source-date, constituent-flow and OHLC integrity checks. Collection is not guaranteed to finish before 22:00.
- **22:00 KST weekdays**: sector-first mobile job makes a first verified-source attempt. If v18 collection is still running or the price source fails, produce CASH with PENDING_DATA_VALIDATION, never a false 0 qualifying sectors. Once the v18 standalone collection succeeds **after** 22:00, a GitHub workflow_run triggers a new Sector First attempt; this is not automatic brokerage execution or a guarantee of fresh data. The 22:15 alarm reports only evidence actually available at its runtime.
- Global `early_watch` is NOT the confirmed sector TOP3 and must not automatically raise sector points or authorize an order. No evidence of Korean net buying, real fundamental uplift, dated catalyst substance and completed-daily support => CASH.
- GitHub cron scheduling can be delayed, and public news/market APIs may fail or rate-limit; reports must state the actual capture timestamp and missing/partial status.

## Daily in-chat report, priority order
- **One-line decision:** BUY candidate / WAIT / CASH, with grounded reason, market data as-of and completion time.
- **Sector TOP3 table:** rank, sector, verified catalyst (date), turnover/volume acceleration, breadth, foreign/institutional flows when verified, source confidence, score.
- **TOP5 execution table:** sector, stock, why it stands out, verified score, latest close/as-of, DAILY structural stop, first/second buy range, no-chase cap, target, reward/risk, action. No price if unverified.
- **C3/K100 state:** C3 one-position focus; K100 current four Core positions tracked separately; latest available holdings/cash must be reconfirmed when stale.
- **Required Next Data:** only the few missing inputs genuinely blocking today's verdict.

## Timing and trust
- 08:35 KST: US macro/overnight *preview*; no invented Korea close, no blind buy.
- **16:00 KST**: the 15:30 *regular-session* close may be analyzed separately and labeled REGULAR_SESSION_CLOSE_PRELIMINARY; this is **not** the completed full KRX extended-session price/flow tape. The KRX after-market is open until 20:00. Keep OHLC data's session basis explicit; regular close and last after-market trade are not interchangeable.
- **20:10 KST onwards**: a same-day *full-session* source is eligible for validation. Full-session as-of defaults in `scripts/krx_session_clock.py`, `scripts/daily_asof_gate.py`, `scripts/sector_first_daily.py` and both v18 source collectors must agree; the weekday heuristic does not certify exchange holidays or actual provider completion.
- GitHub is not a trading terminal; all outputs research-only, user executes orders manually.
- Block approvals for stale, mismatched, thin-coverage, estimated-as-verified, survivorship-biased, or otherwise incomplete market/sector evidence.
- Backtests, ATR refinements, statistical studies and new indicators are supporting tasks, never replace the top-down sector-first deliverable.
- Free data source outages: record failure, publish CASH and diagnostics rather than recycle yesterday's TOP3 as if fresh.

## World-first news intelligence: active development contract (2026-10-22)
- Discover global news before relying on delayed Korean coverage: US, EU, China, Taiwan, Japan and other countries. Use source-country and language metadata, not a location inferred from English headlines. Important subjects include semiconductors, AI/data centers, transformer grids, shipbuilding/LNG, defense, battery supply, commodity prices, Fed policy and export controls.
- Free GDELT DOC 2.0 collector is configured for 16 non-biotech KRX-aligned sector queries plus four global macro queries. The global_sector_morning.yml gathers discovery before 08:35 KST on weekdays; sector_first_daily.yml gathers again after market close. Existing Korean Naver news and OpenDART remain complementary.
- Separate GLOBAL_EARLY_WATCH from domestic-verified TOP3. Show foreign press links, country and GDELT first-seen time. Independent foreign source mentions are research signals only; they are neither proven facts nor positive catalysts. GDELT seen time is not original publication time; no claim that an article preceded the Korean press without corroborated timestamps.
- Trace the causal chain: global event -> affected supply chain -> which listed Korean firms have demonstrable exposure -> dated catalysts/earnings revisions -> domestic capital flow and favorable entry. Include negative implications, regulation, sanctions, customer capex cuts and adverse FX/rate effects, not merely optimistic stories.
- Require article text and original company/government/filing corroboration before upgrading from headline discovery to a verified positive catalyst, and validate that news did not already get priced in before assigning final sector score. Headlines/volume alone never approve buy or fill any missing points of the sector 100-point rubric.
- If overseas collection is stale/rate-limited/missing, report source failure and keep CASH instead of inventing or recycling a global signal. Early watch can influence research priority but never override missing domestic price/flow or verified trade score.

## What the free v18 pipeline actually implements now
The daily *provisional research* TOP3 has been changed to a flow-first relative priority: constituent 5-day foreign+institution net buying 40%, as-of constituent reported turnover 30%, constituent advancing breadth 20%, and 5-day relative strength 10%. This research priority index is NOT the final 100-point sector score above, cannot establish turnover acceleration by itself, and does not include independently verified positive catalysts or forward earnings. The data covers dated ETF constituent proxies, not all stocks in the economic sector. Unknown constituent turnover or coverage blocks the provisional rank. The separate news/OpenDART index lists source links but never upgrades headlines to positive catalysts without validating substance. Every unverified trade gate remains CASH.

## 2026-10-22 reporting and account-state amendment (authoritative)
- C3: user explicitly reported **all shares of 세방전지(004490) sold**. Status is *CASH / no C3 position reported*; prior Sebang investment thesis is **retired**. Do not recycle the historical 4 shares @64,700 as active or anchor recommendations on the old view. Exit price, realized P&L, and broker-confirmed orderable cash remain unknown. See `config/c3_position_state.json`. New unrelated user fills supersede this snapshot.
- Sector discovery now includes verified **positive one-day money-flow sectors before 60% breadth** as research watch, with narrow breadth and 0% advancing labeled risky. This does not approve trades.
- **Data pending ≠ verified zero:** when KRX source dates, OHLC integrity, or constituent flow validation are missing/conflicting, `sector_selection_outcome=PENDING_DATA_VALIDATION` and `stock_selection_outcome=PENDING_DATA_VALIDATION`. Do not publish numbered "unselected" pseudo-ranks, "TOP3=0 confirmed", or "TOP5=0 good stocks" for an incomplete run.
- **Verified zero:** only a validated, sufficiently covered session with no qualifying positive sector net flow may use `VERIFIED_NO_QUALIFYING_SECTOR` and sector count 0. Missing final 80-point company/entry validation still implies **BUY approvals = 0**, not that research candidates do not exist.
- Keep workflow execution SUCCESS/FAILURE, market-data integrity, research selections, and trade authorization in distinct fields. Failed workflows never imply the exchange had no investable companies.
- All active mobile reports and reminders must apply this 80/100 *final verified score* minimum in addition to market, structural daily stop, 2R cost-adjusted and actual-account gates. Do not present relative research index as final score.

## 2026-10-23 KRX after-market source integrity amendment
- KRX's 16:00–20:00 after-market began 2026-09-14; an **18:20 market source snapshot was mid-session**, contrary to the earlier completion assumption. Previous OHLC violations cannot be conclusively attributed to session mixing without paired real-source verification.
- v18 standalone weekday cron is now **20:15 KST**, post-close cutoff **20:10 KST**; the explicit v18 backfill has the same full-session timestamp guard. Never silently normalize closes to fit highs/lows.
- A nominal 20:10 cutoff means only *eligible for validation*. OHLC inequality anomalies, request-vs-data quality, stale ETF-member files, non-matching as-of dates, unknown trading holiday or unverified investor flows all keep TOP3/TOP5 as PENDING_DATA_VALIDATION and BUY count 0.
- KRX regular-vs-after-market comparison is read-only and stores exact capture timestamps; samples outside the requested capture windows are not evidence of what happened at 15:30 or 20:00.
- Report workflow success, price/flow source validation, number of research candidates and actual BUY approvals separately. Do not imply a 22:15 alarm has the completed archive if GitHub's delayed 20:15 v18 job remains in progress.

## Implementation priority
P0. Validate and complete today's free sector evidence (membership + turnover + breadth + verified net flow + fresh catalysts).
P1. Join sector TOP3 to constituents and financial candidates; enforce ordinary stock / non-biotech filters.
P2. Apply completed daily-bar support/stop/retest geometry and 80-point verified final gate.
P3. Produce mobile-ready final report (and CSV/JSON with source timestamps), test against frozen historical as-of data.
P4. Add optional refinements only after the above end-to-end path works.

This document is the project-specific objective for subsequent C3/K100 development; it is not evidence that the above market-data integration is already complete.
