# C3 v6.26 (2026-10-25) — exit profit capture vs risk, event causal audit

**Study executed locally; historical bar end 2026-10-23. No broker orders.** Run code, full per-trade records and 12 passing unit tests are shared as `C3_v626_exit_profit_research.zip` in the initiating ChatGPT conversation. This GitHub text file is the research ledger; **no GitHub Actions success is being claimed for v6.26**.

## Predeclared source and execution experiment

- Frozen v6.25 dated signal catalog **804 rows, 409 distinct tickers**, from the user's archived v18 dated OHLCV market ZIP. The price source is **not independently certified KRX regular-session-only** and historic common stock / excluded pharma-biotech/PIT issuer data are unverified. No prices after 2026-10-23.
- Eight candidate generators: VCP contraction breakout, squeeze expansion, NR7, RS acceleration, HMA pullback with risk+green, WaveTrend reclaim, HMA+Darvas combination, and baseline RS5.
- Next-session OPEN research vs resting limit at D close -0.2ATR. For NEXT_OPEN, select ticker using only completed D-date info, then inspect D+1 opening gap; an invalid gap cancels the trade without hindsight substitution. Resting daily low touch is **not certified broker fill**.
- Seven predefined exits: 7% trail baseline, 5% trail, 1.5R or 2R full takeprofit, +10% / +15% full takeprofit, and +10% 50%-partial then trailing 7%. D+1...D+5 at most, one nominal C3 position at a time, same daily candle stop-first, stop gap-through at open and 0.65% total cost.
- Eight selection x two entries x seven exits x two previously inspected periods **224 comparison rows**. No new unseen holdout, no completed BUY authorization and no guarantee of stop fill. Additional +0.3 percentage point costs stress and largest winner removed.

## SAME-ENTRY matched exit comparison (not one-slot portfolio performance)

Fixed the `NEXT_OPEN+STOP_TRAIL7` chosen signal ticker/day and recomputed alternative exits **on the same entry** to isolate profit taking, rather than allowing the early exit to create a new replacement trade.

| Base model, period | 7% trail mean | 10% full take-profit mean | 10% half take-profit then trail mean | n |
|---|---:|---:|---:|---:|
| HMA+Darvas, EARLIER | +0.140% | +2.110% | +0.950% | 10 |
| HMA+Darvas, RECENT | +0.420% | +0.420% | +0.420% | 6 |
| WaveTrend, EARLIER | +5.725% | +4.361% | +5.043% | 6 |
| WaveTrend, RECENT | +0.353% | **-3.211%** | +0.666% | 4 |

- HMA+Darvas total 16 matched tickets: +10% full exit versus 7% trail had mean improvement **+1.232 percentage points**, but median improvement = 0 and **only 5/16 changed**. Unclustered trade bootstrap 95% difference **[-0.438,+3.159]pp**, which includes zero. Bootstrap does not fully account for correlated sectors/dates.
- In the earlier period HMA+Darvas 10% target portfolio's worst hypothetical trade was **-12.336%**, whereas original 7% trailing portfolio's worst was **-7.481%**. Increased mean return need not mean safer worst loss (different subsequent positions once exits change).
- WaveTrend 10% full target was worse by mean **-2.245pp** on 10 matched entries; no universal takeprofit setting.
- Both periods n>=20, mean/median positive, largest-winner-removed positive, stress cost positive and worst >-12% acceptance gates: **0 of 112 paired strategies**. Never promote sample-tail strategies into BUY.

## Corporate-event causality

`417310` Koramco The One REIT has special-dividend ex-date **2026-08-28**. Earlier v6.25 source summary highlighted a later Aug26 filing/press release, but publicly mirrored filing [2026-08-19 16:11:48 KST, 20260819800342](https://awakeplus.co.kr/data/view/20260819800342) already stated this ex-date, dividend scale and risk. [2026-08-26 Yonhap](https://www.yna.co.kr/view/AKR20260826128200008) corroborates effective date. The code compares earliest available known notice to D+1 08:35, **not to future price**. Only this exemplar corporate notice is loaded; issuer action coverage remains incomplete and no BUY is allowed.

If an otherwise admitted research holding subsequently shows anomalous large price gaps with unknown cause, the case is **unscorable** without cash distribution/corporate actions, **not silently counted as actual trading loss and not ex-post exchanged for a different earlier stock choice**. Fully valid backtest requires point-in-time full event inventory and actual total-return cashflow (including investor entitlement, payment timing, taxes).

## Next falsifiable model

- Maintain the first-priority **HMA+Darvas first retest** stock selection and shadow-compare the 7% prior high trail versus 10% full/50%-partial targets **prospectively** from the next genuinely new Korean regular trading day.
- Add confirmed daily pivot stop, KRX regular-only 09:00–15:30 price source, corporate action PIT list, KOSPI/KOSDAQ market/industry leadership, one-slot actual broker cash and 80/100 final stock BUY score, dated real resistance net >=2R, share-type/bio exclusions.
- Price legality/limit contact, gap cancellations, same-day stop-target path ambiguity, transaction cost sensitivity, absolute cash returns vs broad index, drawdown and outliers must all be reported. At present trade_approved=False; orders_enabled=False; K100 changes none.
