# C3 / K100 MASTER — Sector First (2026-10-22)

## One outcome
**Every completed Korean trading day, identify the three sectors with the strongest verifiable convergence of fresh positive catalysts, trading activity, and investor money flow; select quality stocks only from these sectors; propose a technically justified structural stop first and then realistic 1st/2nd entry prices. If evidence or entry quality is insufficient, recommend CASH.**

No new paid server, Kiwoom token requirement or trading order API in the baseline workflow. Keep free GitHub + freely accessible public data. Do not promise verified live market data when unavailable.

## Required execution order (never invert)
1. **Sector TOP3 FIRST** — compare all eligible KRX sectors using dated catalysts, verified turnover/volume and breadth, verified net buying / money flow when accessible. Keep the already established sector scoring rubric consistent across the 08:35, 13:00, 16:00 and night reports: verified money inflow / turnover / investor net buying 30, news / disclosures / concrete fresh catalysts 20, forward earnings / orders / industry growth 20, breadth across constituent stocks 20, US macro / global linkage 10. Do not silently redistribute missing-item scores. Record scores, as-of, URLs/sources and unavailable items. Missing net flows must not be fabricated from rising price or inferred turnover. If source coverage is weak, label TOP3 *provisional*, avoid recommending a buy.
2. **Inside those three sectors only** — expand to around 20 quality candidates overall based on ordinary-share eligibility, earnings/growth/financial soundness, verified catalyst, flow, and rising trend. Exclude pharma/biotech per user's current instruction. Unknown financials or instrument type must be marked unverified. Do not treat temporary price rankings as proof of business quality.
3. **Select TOP5 max, not forced** — prioritize 1–5 trading-day setups: leader continuation, first controlled pullback after transition, reclaim, pre-ignition / 2nd-line transmission. Independent score >=85/100 only when its underlying components (sector+flow, fundamental+catalyst, trend, setup) are verified; **the existing technical preliminary score is not this final 100-point score.** If fewer than five qualify, return fewer or none. Do not invent a numerical five-day return probability.
4. **Stop BEFORE buys** — establish actual completed DAILY-bar confirmed structural pivot/retest invalidation (not 10-minute low), ensure positive rational stop and feasible risk. Then show 1st and 2nd entry price ranges based on support/reclaim, no-chase cap, realistic resistance-based target and forward R:R. Never use fixed arbitrary 1% or automatic averaging. Absence of verified level => unpriced watch / CASH.
5. **Trade gate** — CASH at top if market weak, total verified stock score <85, price extended, R:R poor, cash/position unknown, or any critical evidence missing. No simultaneous C3 second position. Do not invent available cash or orderable shares. Existing K100 Core positions are managed separately from new entries.

## Daily in-chat report, priority order
- **One-line decision:** BUY candidate / WAIT / CASH, with grounded reason, market data as-of and completion time.
- **Sector TOP3 table:** rank, sector, verified catalyst (date), turnover/volume acceleration, breadth, foreign/institutional flows when verified, source confidence, score.
- **TOP5 execution table:** sector, stock, why it stands out, verified score, latest close/as-of, DAILY structural stop, first/second buy range, no-chase cap, target, reward/risk, action. No price if unverified.
- **C3/K100 state:** C3 one-position focus; K100 current four Core positions tracked separately; latest available holdings/cash must be reconfirmed when stale.
- **Required Next Data:** only the few missing inputs genuinely blocking today's verdict.

## Timing and trust
- 08:35 KST: US macro/overnight *preview*; no invented Korea close, no blind buy.
- After verified KRX close (~16:00 onward): collect sector evidence and publish final report **when collection and checks have actually completed**. Do not claim results exist at 16:00 if the GitHub job is still running.
- GitHub is not a trading terminal; all outputs research-only, user executes orders manually.
- Block approvals for stale, mismatched, thin-coverage, estimated-as-verified, survivorship-biased, or otherwise incomplete market/sector evidence.
- Backtests, ATR refinements, statistical studies and new indicators are supporting tasks, never replace the top-down sector-first deliverable.
- Free data source outages: record failure, publish CASH and diagnostics rather than recycle yesterday's TOP3 as if fresh.

## Implementation priority
P0. Validate and complete today's free sector evidence (membership + turnover + breadth + verified net flow + fresh catalysts).
P1. Join sector TOP3 to constituents and financial candidates; enforce ordinary stock / non-biotech filters.
P2. Apply completed daily-bar support/stop/retest geometry and 85-point verified final gate.
P3. Produce mobile-ready final report (and CSV/JSON with source timestamps), test against frozen historical as-of data.
P4. Add optional refinements only after the above end-to-end path works.

This document is the project-specific objective for subsequent C3/K100 development; it is not evidence that the above market-data integration is already complete.
