# C3 v6.33 — GST first-breakout D-day ranking / market-relative strength / cash ROI audit (2026-10-26, premarket)

**Research only. No BUY/ no order execution.** Source only completed to Friday **2026-10-23**; Oct26 session not used. Reproducible current-conversation local report: `C3_v633_GST_leader_ranking_report.md`, code/846 candidate rows/5544 ranked entry-exit research cases/200 random placebo runs: `C3_v633_GST_leader_ranking_research.zip`. Parent frozen v18 archive SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30`, frozen v6.32 D-only candidates SHA256 `5caea0c2256c0bc82cdc78e86d056e7d35c8d701eb603081bbe061bafd8eb2ce`. **13 local safety tests pass.** No remote GitHub full 5544-backtest/CI success is claimed.

## D-only selection (NO future-ranked stocks)

Frozen v6.32 selection universe of **846** date-model-ticker signals, **372** distinct stock codes, **308** model-D groups, **170** groups with >1 competing ticker. Each group gets just one ticker frozen by D-close features; D+1 opening gap can CANCEL but cannot swap to alternate using hindsight. Alternative six D-only ranks (predefined for this iteration, but still *exploratory in previously seen data*):

1. V632_BASE original.
2. LOW_STRUCT_RISK: smallest D structure stop risk.
3. CONFIRMED_RS: completed D ret5 less ETF 069500 ret5 plus 20-day relative return, breakout strength and risk penalty.
4. MONEY_FLOW: completed D turnover / prior 20-day mean, rv20 and traded-value notional.
5. BALANCED_LEADER: RS + money-flow acceleration + breakout strength minus risk.
6. MINIMIZED_OVERHEAT: penalized ret5 >8% with structural risk controls.

**Important**: Actual sector map, PIT issuer common-stock and pharma/bio exclusions, accurate company catalysts, 09:00–15:30 certified regular-only bars, corporate-action complete economic returns, realized broker fills, contemporaneous actual C3 cash, final 80/100 final stock score and dated overhead reward>=2R remain unverified. ETF 069500 is market proxy, NOT actual GST sector index.

## Frozen NEAR60_RISK8 GST-inspired cohort: 12-day previous-high 7% trail, 269230 KRW research cash / 1% equity risk / 0.65% costs

| D-rank | Shadow 1-slot trades | Virtual compounded account ROI |
|---|---:|---:|
| Original v6.32 | 14 | **+3.835%** |
| Low structure risk | 12 | **-0.674%** |
| Relative strength | 12 | **+2.655%** |
| Money-flow acceleration | 14 | **+0.665%** |
| Balanced relative strength, volume, risk | 13 | **+4.329%** |
| Penalize hot shares | 12 | **-0.674%** |

Balanced higher than original by **only +0.494pp**, from a different set of entries allowed by cash freed from exits. **Paired 75 identical D opportunities** instead show BALANCED changes chosen ticker just **10 of 75** and hurts mean opportunity PnL **-0.592pp**, including earlier -0.835pp, recent -0.133pp, canceled opportunity treated as CASH zero. This is NOT repeatable stock-picking edge. Recent H2 BALANCED 20 filled hypothetical cases mean +0.903%, median **-1.364%**, largest winner removed mean **-0.168%** vs V632 baseline mean +1.076%, median -1.364%, largest winner removed +0.014%.

### Randomized as-of placebo

Uniformly select one ticker from exactly that same D-day candidate list (no subsequent returns consulted) using deterministic seeds 246600..246799, 200 1-slot hypothetical portfolios per cohort, with same gap cancellations, integer-share 1% risk and 0.65% costs. NEAR60 200-run compound ROI median **+2.330%**, 5th..95th **[-0.188%, +5.710%]**, original ranks at ~**77.0th percentile**, BALANCED at ~**82.5th percentile**. **Neither convincingly distinguishes selection skill from randomness**; tuning against already-inspected 2026 Jan–Oct samples makes apparent edge less credible, and placebo is retrospective not a new untouched test.

### Actual GST 2026-09-21 prior-day competition

GST 083450: as-of 9/21 ret5 +10.526%, rv20 1.051, turnover accel 1.121, D structure risk 6.064%; alternative 074600 ret5 +12.305%, rv20 1.203, turnover accel 1.304, risk 6.541%. V632/RS/MONEY_FLOW/BALANCED all rank **074600 first, GST second**. In a 2026-09-22 hypothetical open trade with frozen D stop, 12-day 7% previous-high trail and 0.65% costs: GST **+8.3113%**, 074600 **+6.5716%**. Both winners. Ranking GST first merely because we now know user's successful GST trade is hindsight overfit and prohibited.

## Decision
0 new validated high-confidence rankers; **CASH**, `orders_enabled=False`, `trade_approved=False`. Treat BALANCED as RESEARCH CHALLENGER **not** as published new candidate score, original as baseline. Freeze both on genuinely fresh 2026-10-26 onward verified regular 09:00–15:30 data, record all D options, actual cash/order/fill/missed costs, completed 5d and 12d outcomes, marked monthly cash equity and unrealized peak drawdown, PIT real sector breadth and company catalysts. Do not infer other 2026 historical days untouched. No K100 modification; keep PR draft unmerged.
