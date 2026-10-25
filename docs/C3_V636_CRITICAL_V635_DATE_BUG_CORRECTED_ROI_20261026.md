# C3 v6.36 100만원 수익모델 연구 — CRITICAL v6.35 backtest chronology correction (2026-10-26)

**Status: CASH. No actual broker trading, independent 2026-10-26+ samples = 0, not a proven profit model. Main MASTER v6.36 corrective override must take priority over ALL previous v6.35 1m performance claims.**

## Bug & correction that change research conclusion

In v6.35 historical loader, pandas row `r.asof` accessed the **Series.asof method**, instead of the *asof-date field* `r['asof']`. As a result, date-column strings were full `<bound method NDFrame.asof ...>` representations. Historical selection then sorted by non-dates and its `D <= previous_exit_date` one-slot check did not actually enforce chronological one-stock trading. **The previous v6.35 +7.5296% GST base, +3.3319% GST balanced, -1.4208% HMA deep, -4.3988% HMA open, -0.1182% WaveTrend scenario results and their 52/50/28/35/14 paper trade counts are INVALID.**

Fixed only `asof=r['asof']` in both loader branches; preserved dated v629 and v633 source snapshots (latest Oct23), ticker/exit/stop/risk, costs 0.65% and stress 0.95%, 1m simulated account, 1% planned equity loss exposure, whole shares, same-ticker no reselect. Re-ran **30 configurations** (5 fixed models × .5/1/2% risk × .65/.95% friction), with actual model-date prior exit chronology and separate complete CSVs.

| Fixed model, risk budget 1%/KRW 10k | Corrected paper fills | Corrected historical 0.65%-cost ROI | Corrected 0.95%-cost ROI | Contribution excluding best 2 |
|---|---:|---:|---:|---:|
| GST V632 original rank + 12day trailing | 13 | **+2.1661%** | +1.3921% | -4,118 KRW |
| GST V633 BALANCED rank + 12day trailing | 12 | **+4.6443%** | +3.6640% | +2,461 KRW |
| HMA+Darvas two-session deep retest + 7pct trail | 13 | +1.2422% | +0.8675% | -11,722 KRW |
| HMA+Darvas next open + 7pct trail | 15 | +0.2203% | -0.1470% | -20,796 KRW |
| WaveTrend next open + 7pct trail | 7 | -0.0881% | -0.3205% | -13,222 KRW |

These are hypothetical **price contacts/open-price trades and gross equity sizing**; no verified Kiwoom actual fills. Some source daily bars cannot be independently certified KRX regular 09:00–15:30 only, full corporate distributions and historical common-stock/pharma exclusions unverified, and daily marked max drawdown not recomputed.

## What constrains actual profitability?

The corrected GST BALANCED 1m portfolio has **8 wins of 12 model paper trades**, paper winrate 66.67%; historical average P&L win/loss break-even winrate ~39.30%, but **Wilson 95% lower winrate ~39.06%**, just BELOW the historical break-even estimate. The estimated required winrate is itself uncertain and in-sample. Of hypothetical +46,443 KRW total, TOP TWO paper winners contribute ~43,982 KRW (**94.7%**), leaving only ~+2,461 KRW from other 10, and with assumed extra +.30pp transaction costs that residual turns **-2,141 KRW**. No independent evidence of repeatable expectancy. GST BASE 13 paper fills 61.5% win, 46.1% estimated break-even, 95% Wilson lower 35.5%; top2 removal negative.

Even more academic literature, e.g. momentum in broad portfolios, does not establish a 5–12 day GST-pattern gain in KRX: [Moskowitz et al. (2012)](https://www.sciencedirect.com/science/article/pii/S0304405X11002613.), [Daniel & Moskowitz (2016) momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002), [Bailey & López de Prado (2014) DSR](https://doi.org/10.3905/jpm.2014.40.5.094).

## Immediate development path, no wishful tuning

- STOP generating new HMA lengths, takeprofit thresholds or rank weights on the repeatedly mined Jan–Oct23 history. Retain GST base/BALANCED as frozen champion/challenger, HMA deep as execution challenger and WaveTrend as no-approval watch.
- Require dated 2026-10-26 onward verified **09:00–15:30 KRX regular-only** D-close input; data quality and PIT issuer/corporate actions, actual sector peers/catalysts, independent stock score >=80, nearby dated overhead net >=2R, completed daily structural stop. Do not use post-D opening gaps to rerank D-stock winner. A low-priced limit touch is NOT broker execution.
- Simulated starting capital 1,000,000 KRW != user's current actual Kiwoom cash. Risk cap 1% per paper position is account loss-budget incl .65% cost, not 1% stop-loss at stock quote. Orders remain disabled. K100 unchanged.
- Trial performance only after strictly new independent periods; publish signal cancels, min1 share affordable, actual fills when verified, 5/12-session closed PnL, realized and open-position daily equity/maximum drawdown, additional cost stress, benchmark and same-day random stock. At least 30 new truly independent closed validated trades in >=3 months needed for initial decision review (NOT formal significance).
- Sources considered in Korean mobile research artifact from this conversation: public official TradingView HMA, Supertrend, VWAP, bar magnifier, publicly indexed Korean YouTube 대박차트연구소 and 대박주식연구소, and academic overfitting/momentum literature. No channel-specific video parameters or success rates fabricated.

### Proof of work

Local corrected reports and reproducible Python + both the old contaminated loader and corrected new chronology + **15 passed tests** delivered as:
- `C3_v636_수익개선_연구보고서.md`
- `C3_v636_수익개선_오류정정_연구자료.zip`

Research branch includes separate unit-fixture chronology checker; these **GitHub CI smoke tests are distinct from the executed local 30-scenario historical replay**. Do not claim remote full-market replay or new trading-fills proof. **trade_approved=False, orders_enabled=False.**
