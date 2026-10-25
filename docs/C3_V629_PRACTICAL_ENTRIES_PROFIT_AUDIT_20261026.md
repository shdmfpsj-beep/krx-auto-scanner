# C3 v6.29 — 2026-10-26 premarket entry-feasibility profit study (RESEARCH ONLY)

## Dataset, methods, audit

- Completed historical source only through **2026-10-23** (Oct26 Korean market has not opened at time of research). Frozen source `v18-market-source.zip` & v6.25 signal catalog SHA256 `a45dd507ca964cc93b07e828438862b6ad089dc22c38a4138ed8a1d2f2a39a84`.
- 804 initial signal rows; **692** signal rows restricted to HMA+Darvas(122), WaveTrend(33), baseline RS5(537). Only **213 independent model/date opportunities** after D-only candidate prescreen (HMA+Darvas=59, WaveTrend=24, baseline=130); these 213 days are NOT independent observations in portfolio sense.
- Four entry modes: (1) D+1 opening, (2) single D+1 close minus 0.20 ATR resting limit, (3) D+1 / D+2 close minus 0.65 ATR deeper retest resting limit, (4) D+1 completed bar confirmed support/reclaim THEN D+2 open, bounded gap. KRX normal common-share tick-round. D+1 gap -2% to +2.5%; invalid gap cancels and **never retro-select the second-ranked D ticker**.
- Two exit modes, 7% previous-completed-bar trailing stop and +10% takeprofit with structure stop. Five trading bars from model entry, same-candle stop-first and hypothetical 0.65% total friction. **Price touch is NOT execution**. One-slot sequential simulated strategy is distinct from same-D fixed opportunity matched comparisons.
- 213 ×4 ×2 = **1,704 historical price/exit observations**, 639 fixed-opportunity paired alternatives, 48 period/model/entry/exit score cells, 314 total repeated one-slot simulated trade records across modes. 15 local tests passed including exact -2% gap floating boundary, future mutation selection, stop-first, no after-open ticker hindsight replacement.
- Full reproducible Python study code, 6 main CSV/JSON reports, code tests, execution logs in current ChatGPT conversation `C3_v629_entry_and_profit_frontier.zip`; Korean mobile `C3_v629_practical_entry_research.md`. **Research code was executed locally; not claimed to be passing remote GitHub Actions CI.**

## 7% trailing-stop one-slot simulated per-trade average, with small counts

| Model & entry | 2026 Jan–June | 2026 Jul–Oct23 |
|---|---:|---:|
| HMA+Darvas D+1 OPEN | +0.140% (n10) | +0.420% (n6) |
| HMA+Darvas D+1 -0.2ATR limit | +0.170% (n9) | -1.182% (n4) |
| HMA+Darvas D+1/D+2 -0.65ATR limit | -0.122% (n10) | +1.338% (n5) |
| HMA+Darvas confirm D+1 then D+2 OPEN | +8.520% (n3) | -0.025% (n2) |
| WaveTrend D+1 OPEN | +4.763% (n5) | +0.353% (n4) |
| WaveTrend D+1 -0.2ATR limit | +2.901% (n5) | -2.335% (n3) |
| WaveTrend D+1/D+2 -0.65ATR limit | +6.742% (n3) | +2.478% (n2) |
| WaveTrend confirmed D+2 OPEN | no trades | -3.920% (n1) |

No consistently high-sample profitable research model found; both time periods have been inspected many times.

## Selection bias: matched fills vs missed opportunity

On same D-date single selected ticker and the 7% trailing exit, consider **all** research signal opportunities, counting canceled/unfilled signals as 0 instead of selecting only observed price-touch wins:

| Model & alternate vs OPEN | Pre-fixed opportunities | Alternate price contacts | Both price contacts | Delta conditional on both touches | Delta per ALL opportunities |
|---|---:|---:|---:|---:|---:|
| HMA+Darvas deep retest | 59 | 31 | 28 | +2.301 percentage points | **+1.108pp** |
| HMA+Darvas near limit | 59 | 34 | 30 | +0.925pp | +0.697pp |
| HMA+Darvas confirmed D+2 | 59 | 6 | 6 | +3.326pp | +1.657pp (very infrequent entry) |
| WaveTrend deep retest | 24 | 8 | 8 | +2.977pp | **-0.428pp** |
| WaveTrend near limit | 24 | 10 | 9 | +1.081pp | -0.627pp |

**Interpretation:** WaveTrend's deeper orders appear better only after cherry-picking filled orders; many missed rising stocks reverse the result on all fixed opportunities. HMA+Darvas D+1/D+2 deeper retest is worth **prospective WATCH research** but its one-slot H1 result was negative, and the 59 dates are reused/historically inspected so do not infer a tradeable positive expectancy from +1.108pp. Date bootstrap cannot correct for repeated tickers, sector dependence or 49+ previous experimental model comparisons.

## Next pinned prospective test, not a live order

- Freeze HMA+Darvas -0.65 ATR D+1/D+2 deep retest vs original D+1 allowed-gap OPEN, and WaveTrend OPEN/near-limit alternatives.
- Collect genuinely **new** 2026-10-26 onward 09:00–15:30 certified regular-only completed D bar and previous 65+ session data; stop structure first; final independently verified stock 80/100, dated overhead net reward:risk >=2R, issuer common stock & non pharma-bio PIT, dated announcements and complete corporate actions, actual broker orderable KRW and C3 one slot. If unavailable **CASH**.
- Count attempted/canceled/unfilled, intraday execution realism, stop gaps, full portfolio cash-equity daily marked path, actual monthly return/drawdown and cash benchmark. Do not substitute NXT/after-hours date-only prices.
- **Safety `trade_approved=False`, `orders_enabled=False`. No K100 change, no actual orders.** Do not merge this draft research branch as a production scanner.
