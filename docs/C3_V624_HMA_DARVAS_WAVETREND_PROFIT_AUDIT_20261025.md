# C3 v6.24 (2026-10-25) — HMA / Darvas / WaveTrend predeclared profitability audit

## Scope and status
- Dates: archived source observed through **2026-10-23**. Eight stock signals x two entry types x four exits x two already-examined periods = **128 comparative rows**.
- Underlying input: frozen v18 price ZIP joined to v6.22 liquidity-filtered **21,036 observations, 1,369 ticker codes**. Signals from asof D close **only**; D+1 open may CANCEL, never retrospectively reselect ticker after seeing gap. One C3 position at once, stop-first, total 0.65% round-trip assumed costs. Actual order fills/cash/regular-only historical OHLC/PIT issuer excluded-pharma status **not independently attested**.
- Entry A next trading day's observed OPEN (idealized auction execution, not confirmed fill). Entry B resting limit **D close minus 0.2 ATR**; if D+1 opens below limit -> CANCEL, low/high contact **only a contact**.
- Study structure stop = prior 16 daily lows, through D, minus 0.15 ATR; stop evaluated before hypothetical 2R target if both touched in one candle; prior-day high only for 7% trailing stop. Not a verified daily pivot or current executable order.
- Independent market context: old v6.22 ETF 069500 regime proxy as-of D; 2026-10-26 onward is the only genuinely new period after repeated scrutiny of previous time windows.
- Formula references [TradingView HMA](https://kr.tradingview.com/support/solutions/43000589149/), [public Darvas example](https://www.tradingview.com/script/W2a3PSO7-Darvas-Box-Theory/), [WaveTrend example](https://www.tradingview.com/script/PETdqtCF-WaveTrend/). This is our **public-indicator-inspired proxy**, NOT the exact settings/proprietary source code from named YouTube channels.

## v6.24 no-lookahead single-slot study comparison: NEXT_OPEN, stop+7% prior-day trailing

| Predeclared signal | Earlier number | Earlier avg net | Recent number | Recent avg net |
|---|---:|---:|---:|---:|
| HMA16 rising turn | 21 | -1.837% | 13 | -0.487% |
| HMA16 first pullback | 15 | +0.340% | 11 | -0.984% |
| Darvas locked box breakout | 10 | -2.585% | 6 | -0.983% |
| Darvas retest after breakout | 10 | -0.520% | 4 | +0.157% |
| WaveTrend WT1 crosses WT2 up with MA20 trend | 6 | +5.725% | 4 | +0.353% |
| HMA + prior-locked Darvas | 10 | +0.140% | 6 | +0.420% |
| Baseline short RS5 >+5% | 20 | -0.519% | 11 | -1.214% |
| Baseline 20MA recapture | 20 | -1.400% | 9 | -3.477% |

- **WaveTrend** all 10 (hypothetical) mean +3.577%, but recent four median **-1.608%** and largest one trade +19.405% dominates; earlier six mean falls from +5.725% to **+2.990%** after largest winner excluded. Do NOT call profitable edge.
- **HMA+Darvas** all 16 mean +0.245%, median +0.343%, single largest winner excluded mean **-0.436%**; 5000 sample simple per-trade bootstrap 95% mean range approx [-1.873%, +2.383%] (not independent sector/date corrected); cost increase to 0.95% => **-0.055% average**. Prior +0.140% and recent +0.420% small samples.
- Of 128 period-specific comparisons, both periods were positive for **four combinations** (3 HMA/Darvas same entry with different correlated exit modes + 1 WaveTrend). **ZERO** combinations had at least eight open-priced contacts in *each* period and positive mean in both. Do not choose multiple-tested winners for live BUY.
- Historical broker fills / actual C3 capital / company fundamentals unknown. A superficially positive study is **never BUY authorization**.

## Computation and tests
The current ChatGPT conversation includes **`C3_v624_indicators_profit_research.zip`** with:
- `c3_v624/v624_indicator_research.py` — complete implemented reproducible pipeline and predefined definitions,
- `c3_v624/test_v624_indicator_research.py` — **9 passing local unit tests** (HMA hand arithmetic, no future-data mutation of D indicator, stop-first if stop & target touch, gap-through stop, limit gap-through cancel, D+1 reselection prevention, limited-sample reporting, fixed modes),
- `c3_v624/v624_predeclared_comparison.csv` 128 rows, `v624_shadow_cases.csv`, `v624_cancelled_entries.csv`, `v624_status.json`, source log.
**This is local research**. No new v6.24 GitHub Actions green CI run or official TradingView Pine side-by-side reproduction is claimed. Research remains draft and unmerged.

## Proposed next fixed-hypothesis forward check
1. A **WaveTrend reclaim** on the completed regular-only D candle, verified actual common stock outside pharmaceutical/bio, with confirmed pivot structure & verified overhead net >=2R, no huge open gap and adequate cash.
2. B **HMA turn + locked Darvas breakout/retest** with same regular 09:00-15:30 source, confirmed sector leadership, cash, score >=80, stop/target.
3. C **HMA first pullback + WT reclaim** only when both already available as-of D.
4. Audit per-session canceled/unfilled proposals; **CASH whenever no verified trade meets live gates**. Never force positive signals. Evaluate on genuine post-Oct23 sessions with one real single-slot shadow ledger before any code is promoted to live.
5. Analyze results by *median, sample, confidence interval, adverse day gaps, cost sensitivity, 1-position portfolio, worst/drawdown, simple cash benchmark, and stop-first targets*. Avoid reusing already-inspected July–October as unseen validation.

**Safety:** `trade_approved=False`, `orders_enabled=False`, no broker integration, K100 position management unchanged.
