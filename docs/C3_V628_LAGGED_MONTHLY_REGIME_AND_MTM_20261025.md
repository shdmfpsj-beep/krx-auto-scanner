# C3 v6.28 — Lagged market filter vs actual marked monthly study (2026-10-25)

## Result, not an approved live BUY
Replayed v6.25's frozen **804** signals through v6.26 one-stock-at-a-time engine with same 0.65% assumed round trip, five preset model/exit pairs, **9** predeclared MONTHLY/DAILY KOSPI200 ETF (069500) regime contexts, 2 historical time blocks = **90 model-period regime comparisons**. Historical data only through Oct23, 2026; current day Oct25 Sunday. Previous month filter uses previous **COMPLETED calendar month end**, not the current month's eventual performance. Daily status uses **completed signal-day D** only and affects potential D+1 entries. Skipped signals never reallocated with future knowledge.

**Important result: lagged simple positive/trend filters do not improve the simulated returns**.

| Portfolio, Jan–Oct23 2026 | No filter | Previous month ETF return >0 | Previous month close >20MA | Signal day ETF close >20MA |
|---|---:|---:|---:|---:|
| HMA+Darvas, 10% full exit | +12.704% (16) | -7.685% (11) | -2.914% (13) | +7.382% (13) |
| HMA+Darvas, 7% trail | +2.447% (16) | -6.976% (11) | -5.883% (13) | -10.165% (13) |
| WaveTrend, 7% trail | +39.688% (10) | +18.928% (6) | +16.287% (7) | +33.118% (8) |
| Baseline RS, 7% trail | -24.849% (31) | -22.579% (22) | -34.497% (25) | -25.277% (22) |

**Do not promote a seemingly nice regime gate into actual BUY policy** based on same historical data. The filtered strategies have even smaller trade samples.

## Corrected actual-month marked-to-market reporting

Older v6.27 spreadsheet booked a trade's entire compound return on **exit month**, ignoring end-of-month *open* hypothetical portfolio values. This artificially understates interim mark-to-market drawdowns. v6.28 adds each session close of the held stock with a full-reinvested 1-position cash balance, 0.65% reserve for hypothetical liquidation, and original stop-first modeled exits. Simulated orders remain unverified.

| Strategy | Original v6.27 realized-exit-only peak drawdown | New v6.28 marked daily peak drawdown | Historical hypothetical compounded PnL |
|---|---:|---:|---:|
| HMA+Darvas 10% target | -12.34% | **-13.72%** | +12.70% |
| HMA+Darvas 7% trail | -8.73% | **-14.42%** | +2.45% |
| WaveTrend 7% trail | -3.61% | **-7.09%** | +39.69% |
| RS 7% trail | -42.77% | **-46.56%** | -24.85% |

For HMA+Darvas 10%: **February -8.35% marked**, compared with -5.64% realized-only exit-month; March -0.97% marked compared with -3.81% when booked by exit-month. WaveTrend: April marked +5.83% vs exit-only +11.64%; May marked +6.33% vs exit-only +0.80%. Difference is timing of paper unrealized values, not earned or broker-verified profit.

## Source and testing

- Fully executed in current ChatGPT container: `c3_v628_monthly_gate.py`, `c3_v628_mark_to_market.py`, `test_c3_v628.py`. Local **12 safety tests passed**, historical source v18 archive and v6.25 model-dated catalog. All observations and daily marked portfolio CSVs plus Korean mobile report available as `C3_v628_profit_regime_research.zip`.
- The research branch also has **`scripts/market_month_lag_guard_v628.py`**, **`scripts/test_market_month_lag_guard_v628.py`** and a small free GH Actions CI `.github/workflows/market_month_lag_guard_v628_free.yml`. This pure market-lag library provides market **research context only**, not orders. **Do not claim the full local 90-comparison pipeline ran in GH**; CI only checks 10 causal asof/monthend scenarios when workflow succeeds.
- History v18 **date-only** raw prices are NOT independently certified KRX regular-session-only, KOSDAQ market state not represented by ETF 069500, whole-population point-in-time common stock/non-bio exclusion and corporate action dividends not certified. Full capital reinvestment and 09:00 D+1 opening and stop-first OHLC are optimistic/uncertain; cash/current account is not confirmed. C3 position risk and K100 account must remain separate.
- **No strategy passed independent truly unseen test**, historical windows repeatedly inspected and small trade counts; no validated profit expectancy / probabilities and no actual money made.
- Forward next step after 2026-10-26 regular session: freeze 2 watch models HMA+Darvas versus WaveTrend, require audited regular-only price/valid issuer/source/known corporate actions and actually broker feasible entries, and track *monthly realized plus marked-to-market* alongside risk/cancel data, market benchmark, 2R verified overhead, 80 final score, single-slot/actual cash. No autoorders; no retroactive October signal promotion.

**Status: trade_approved=False, orders_enabled=False. Research draft only, no live merges.**
