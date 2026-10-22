# C3 / K100: sector-first, risk-first, profit-proof checkpoint (2026-10-22)

## Objective
Find **three genuinely liquid and positive-flow domestic sectors** informed by global industrial developments, select the best fundamentally verified eligible stocks within those sectors, and offer **only technically defensible stop-first 1st/2nd entries**. Avoid large drawdowns; seek positive **net** expectancy in repeatable 1–5 trading-day swings. User places orders manually on Android. No paid server or Kiwoom REST API is required for the baseline.

## What is now implemented in the repo (code, not certified results)
- WORLD-FIRST free GDELT discovery and dated Naver/OpenDART evidence, with no headline automatically upgraded to verified catalyst.
- v18 sector ETF-member flow/turnover/breadth **provisional** sector TOP3, then research constituent TOP5.
- As-of validated completed daily-bar structural pivot stop and entry references for dynamic sector members, cache-first + free-data backup.
- Prospective shadow journal: only same-day logged signals; simulated next-session OPEN, gap/no-chase filter, structural stop, 2R target, 5 completed sessions, 0.40% modeled round-trip friction, adverse same-bar ordering.
- NEW: Fixed alternative "D+1 or D+2 pullback limit" at **signal close - 0.35 × ATR14**, order expires after the second session. Only historical OHLC-based *possible* touches, not live queue executions.
- NEW: Side-by-side entry comparison for the **same locked sector signal cohort**, with completed/pending/missing/skip split. Compare not just win rate among hypothetical fills but average **net profit per resolved signal including nonfills as zero**.
- NEW: Block retroactive signals from old rerun reports; freeze previous completed shadow results and reject silent gaps in dated stock OHLC candles.
- Mobile main report integrates a short A/B research section; longer experiment artifacts available separately.
- Retain latest generated daily artifact up to 90 days, subject to repository Actions availability/storage settings. Signal continuity is not guaranteed if runs or artifacts stop.

## Essential caveats
- **Not** verified profitability or a brokerage-executable strategy. Today's scores, source availability, and final 85/100 investment eligibility must still pass independent checks.
- The intrabar order of high/low and actual limit-order queue priority are unknown. A touched limit is a *possible*, not confirmed, fill. Same-bar ambiguity is penalized.
- A high conditional win rate with a tiny filled sample may be inferior to a lower conditional win rate with adequate participation; compare per-signal metrics, too.
- Prices may have split/rights/corporate-action adjustment issues; live tradability and broker-specific ticks must be checked.
- The shadow experiment simulates **per signal**, sometimes concurrently. It is **not** the realised return of C3's one-position, one-stock, no-overlapping-trades account. Account-level allocation, capital and portfolio drawdown must be separately modeled before making return claims.
- 0.4% round-trip cost is a fixed research assumption and not an assertion about current Korean fee or tax rates. Examine sensitivity before use.
- An experiment with 30 completed trades is still insufficient to prove a durable edge; evaluate more observations, changed regimes, out-of-sample dates and cost/fill uncertainty.
- All actual decisions remain CASH when catalysts, fundamentals, sector evidence, latest price, structural stop, final 85-point score, and entry trigger are incomplete.

## Prioritized future development — not implemented yet
1. Correct and verify GitHub Actions run logs for the full no-cost workflow, especially today's as-of evidence, new experiment test logs, and output retention.
2. Capture sufficient prospectively recorded samples; report market regime, overlapping signal clustering and per-sector success/failure without data-snooping.
3. Model a true C3 **one-position** equity curve with available-cash gate, fees, opportunity cost and peak-to-trough drawdown.
4. Compare next-open, first pullback and objectively definable reclaim entries on non-overlapping *out-of-sample* blocks; prohibit changing the "winner" based on an insufficient sample.
5. Quantify 85-point final stock ranking only when auditably dated catalyst, cash flow/financials and sector/price evidence are all available, rather than equating it with a research proxy.

## Repo artifacts
- `scripts/shadow_trade_audit.py` + `scripts/test_shadow_trade_audit.py`
- `scripts/shadow_entry_comparison.py` + `scripts/test_shadow_entry_comparison.py`
- `.github/workflows/sector_first_daily.yml` (daily report and experiment)
- `.github/workflows/sector_first_daily_checks.yml` (offline safety tests)
- `output/shadow_scorecard_mobile.md` and `output/entry_ab_mobile.md` in the nightly Actions artifact, if jobs actually succeed.
