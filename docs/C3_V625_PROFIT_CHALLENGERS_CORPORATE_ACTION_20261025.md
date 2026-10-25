# C3 v6.25 (2026-10-25) — volatility-contraction challengers & dividend total-return audit

**Status: research only, no live BUY/order or independently profitable model.**

Archived price through Oct 23. Old v18 date-only bars are not independently regular-only 09:00–15:30/PIT-adjusted, original 2026-07–10 period has been viewed by research many times. Inputs are 21,036 liquidity-screened observations from 1,369 codes. Four workers generated 667 indicator signal rows. Models: **VCP prior-10-bar range <=70% of earlier 20**, **prior 10d volatility squeeze <=65% of prior30 then break**, **previous-day NR7 + RV breakout**, **RS5-acceleration breakout**, **HMA first pullback + structure risk <=6% + market favorable**. Existing WaveTrend reclaim, HMA/Darvas combined, simple RS5 are fixed controls.

Eight selection modes x 2 entries (D+1 gap-limited open or price-contact-only limit) x 2 exits (STOP_TRAIL7 or STOP_TARGET2R) x 2 previously examined periods = **64 study rows**. 0.65% friction plus 0.30pp stress. Selected ticker at D without knowing D+1 opening; no hindsight replacement; 1-slot shadow portfolio with D-only 16-bar stop proxy and 5 sessions. Actual fills or real K100/C3 orders **not verified**.

| NEXT_OPEN + STOP_TRAIL7 | Earlier n / mean | Recent n / mean |
| --- | --- | --- |
| VCP contraction break | 2 / -6.120% | 2 / **-43.549%** (unadjusted special dividend) |
| Squeeze expansion | 9 / -1.716% | 6 / **-13.540%** (same event) |
| NR7 breakout | 7 / -2.025% | 5 / -1.920% |
| RS acceleration | 6 / -3.382% | 3 / -2.802% |
| HMA pullback + risk <=6 + broad proxy green | 6 / -0.632% | 1 / -2.567% |
| WaveTrend reclaim control | 6 / +5.725% | 4 / +0.353% |
| HMA+Darvas control | 10 / +0.140% | 6 / +0.420% |
| RS5 control | 20 / -0.519% | 11 / -1.214% |

**Crucial discovery**: 2026-08-26 signal in **코람코더원리츠 (417310)** uses 2026-08-27 opening KRW 10,970; on 2026-08-28 ex-dividend opens KRW 2,290. Price-only stop-first backtest recorded -79.7749%, but **2026-08-28 was special-dividend ex-date** with approximately KRW 8,900 per share expected dividend and T+2 entitlement by owning stock Aug27. Securities/REIT corporate distribution and taxes are not in raw OHLC. A **price-only -79.8% is not shareholder total return**; it is unscorable without PIT filing/actual distribution entitlement/cash. Press sourced 2026-08-26: https://web3.newspim.com/news/view/20260826000967 and DART link https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260826800685 . Online public alert noted 17:07 KST, after D completed 15:30 and before D+1 08:35, making a **new pre-open corporate-action cancellation gate** falsifiable. Do not assert all official filing timestamps independently certified.

Post-hoc REMOVE single anomalous 417310 case only to quantify data sensitivity, NOT as ex-ante trading rule: recent squeeze other 5 cases mean -0.292% vs polluted -13.540%; VCP other 1 = -7.322% vs -43.549%. No new profitable edge.

**Acceptance rules preregistered in script:** n >=20 completed single-slot trades in BOTH periods; mean/median/mean without top winner positive in both; +0.30pp higher cost still positive; worst loss >=-12%. **0 models pass**. Future genuine out-of-sample and official regular-only/PIT data required. 18 local unit tests (9 new indicators and 9 corporate action guard) passed. All results from local ChatGPT runtime, no GitHub Actions success claimed for v6.25.

Research artifacts in chat: `C3_v625_mobile_profit_report.md` and `C3_v625_profitability_research.zip`, including full code/data/price-contact/cancel/mean etc. Financial model is not an order and must not modify K100 core holdings. No user C3 cash certification. `trade_approved=false`, `orders_enabled=false`.
