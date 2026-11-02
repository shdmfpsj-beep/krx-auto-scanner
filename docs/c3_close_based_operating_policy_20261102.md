# C3 close-based TOP2 swing research — operating policy

Effective: 2026-11-02. No live brokerage orders. No intraday quote dependency.

## Daily sequence
1. Wait for a completed, dated KRX daily OHLCV dataset; report its actual trading date, not the workflow execution date.
2. Rank the market and publish TOP2 only from available evidence. Prefer CASH when the market is weak, the candidate score is below the active threshold, or entry geometry is poor.
3. Freeze each TOP2 plan **before** the next trading session: source run ID, source close, entry range, daily-chart structural stop, first/second resistance, expiry, and source quality.
4. Forward-evaluate only subsequent sessions. Do not retrospectively claim fills on signal day.
5. Record whether daily low/high touched the entry range, but label it `TOUCHED_NOT_EXECUTION_VERIFIED`. Daily OHLCV alone does not prove fill order, queue priority, or intraday sequence.
6. If the same daily bar could have reached entry, stop, and target in different orders, mark `AMBIGUOUS_PATH` and exclude from confirmed win-rate; additionally compute a conservative downside scenario.
7. Apply the user's close-based stop rule consistently: a confirmed close below structural stop triggers a *next-session* modeled exit, not an intraday stop fill.
8. Evaluate outcomes at 5, 10 and 20 subsequent sessions: entry-touch rate, missed-entry rate, stop incidence, target touches, MFE/MAE, conservative P&L, and ambiguous-path rate. Report cohort counts and avoid interpreting small samples as validated profitability.
9. Show a mobile TOP2 execution table with ticker, dated close, buy zone, structural stop, R1/R2, entry status, and confidence/source scope.

## Data safety
- Distinguish `PYKRX_RESEARCH_REGULAR_ONLY_UNCERTIFIED` from certified regular-session data.
- No verified daily source => `DATA_PENDING`, never invented fills or returns.
- Any same-day high/low path ambiguity remains unresolved without intraday bars.
- Do not auto-enable the retired 30-minute heartbeat or intraday cron audit.
- Retain existing daily paper-forward workflow; verify its source freshness and completed scan before trusting outputs.

## Priority
1. Reliable daily close capture and source-date checks.
2. TOP2 quality and entry geometry.
3. Prospective paper ledger and conservative outcome measurement.
4. Only then consider optional intraday feeds if daily-bar ambiguity materially impairs results.
