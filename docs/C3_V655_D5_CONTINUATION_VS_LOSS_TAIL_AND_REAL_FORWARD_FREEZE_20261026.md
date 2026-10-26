# C3 v6.55: 5D vs 12D upward continuation decision — NO PROFIT EDGE CERTIFIED

2026-10-26 KST. **Research only / CASH / 0 independently verified new filled profitable trades**. User requested only stock picks, evidenced A/B/C buy levels, chart structure stop, dated overhead and continued-upside judgement; all capital/position size decisions are the user's. No account budget, 1% risk preset, or position size enters v6.55 selection.

## The new test actually run locally (no retrospective metric tuning)

- Parent immutable Work v6.38 and v6.54 **264** old historical D-candidate signals and v6.48 D+1 OPEN price-contact paper exit models, as-of last 2026-10-23.
- Recovered all **192 exact source stock CSV members** from frozen 55MB v18 price archive SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30` into a portable 1.15MB nested ZIP; match D-candidate stock/date/model exact one-to-one. 264 with D5 price proxy; 262 have both completed 5- and 12-session outcome. Two future-12 incomplete events **excluded** from 5-vs-12 common-denominator table, not assigned winners.
- Compare on the exact same entry/stop/exit base: fixed 5 sessions, fixed 12 sessions, contingent 12 sessions **ONLY IF at completed fifth trading-day close the original 5day stop/target has NOT already closed the trade and 5day price-proxy return after estimated costs is positive**; also compare adding confirmed day5 Close>MA20. A decided extension substitutes original archived D+1-open-to-12-session paper result; unextended substitutes original 5-session result. No new broker fill/fee assertions. This is a path-combination *historical research challenger*, not independently calibrated 2026-10-26 signal or actual valid order. The 5day outcome is known only on D5 (not available to D origination).
- D-asof historical "strong" cohort `breadth20>=50% and stock prior ret5>0` n**145** (40 distinct prior D dates). That gate was already repeatedly explored in old Jan–Oct23 prices and is NOT independent holdout.

| Same 145 strong D historical cases | Original 5day | Original 12day | D5 positive-return conditional extension |
|---|---:|---:|---:|
| Mean 5/12 price-only net return | **+2.256%** | +3.135% | +3.100% |
| Median | **+1.702%** | +2.365% | +0.269% |
| Share net profitable | **62.07%** | 60.0% | 50.34% |
| Share loss <= -5% | **15.86%** | 31.03% | 23.45% |
| Share loss <= -10% | **4.83%** | 17.93% | 8.28% |

The conditional extension candidates are **72 of 145**, and day5 MA20 adds **zero differentiated candidates**: every positive-surviving original D5 trade in this sample was also above MA20. Thus **do not sell the extra moving average as predictive value**. Average return of conditional extension vs original 5 sessions +**0.8443 percentage points**, but month-block bootstrap with just **6 months** for the strong cohort (4,000 deterministic resamples) **95% interval [-1.214,+4.442]pp** overlaps zero. Original fixed-12 vs fixed-5 +0.879pp with interval [-0.815,+5.367]pp also overlaps zero. 12day and conditional extension share losses in several names; no demonstrated edge after accounting for repeated discovery and fill assumptions.

All 262 paired historic D signals: fixed5 mean +0.606%, fixed12 +1.230%, conditionally extended +1.057%, but **5day-positive extension profit rate only 41.98% vs fixed5 51.91%** and -5% loss-share 31.68% vs 24.81%. This is another caution that "profit at day5" does not automatically predict continued upside.

Recent H2 Jul–Oct23 strong signals **only 10**, original 5day mean +0.208%, 12day -0.718%, day5 conditional extension -0.460%, not a winner in the recent historical period. No date-segment cherry-picking into live default.

## Current date first actual immutable market observation

GitHub committed `research/c3_v655/frozen_market_snapshot_20261026.json` after today's 15:30 close, quoting **KBS closing-index story** 2026-10-26 16:53:26 KST update https://world.kbs.co.kr/service/news_view.htm?Seq_Code=205125&lang=e: KOSPI **5,469.47 (-1.46%)**, KOSDAQ **727.21 (-3.26%)**. **This is a third-party reported index close, NOT a directly authenticated full KRX regular-only all-stock price tape or complete industry/foreign/institutional flow feed.** This system has no verified Oct26 individual-stock price/sector PIT/company catalyst/resistance ranking input ready; 2026-10-26 qualified D stock candidate array thus **[] EMPTY, CASH** rather than fabricate a portfolio or use tomorrow's backfill. The GitHub commit timestamp (not JSON timestamp alone) records publication timing. Preserve this frozen observation and log a future 2026-10-27+ company-qualified selection only after authentic source available.

## Reproducibility and provenance

- Full user archive **`C3_v655_상승연장_수익개선_완전재현.zip`**, SHA256 `2e14d5b12986213d6fe5093dfca57708d31ecddb4b07a144b471d589c4759d27`, `/mnt/data/c3_v655/C3_v655_보유연장_수익성_가격연구보고서.md`, 192 exact v18 stock-price source members, frozen input D+5 outcome 264 rows and original v648 5day archive, full v655 research source plus 28 local tests, 264-row signal ledger, 16 scenario summary rows and 9 month-bootstrap analyses, index observation JSON and SHA256 input manifest.
- A **completely separate clean ZIP extraction** ran all **28/28 local tests**, then full runner; the four key output CSV/JSON files matched byte-for-byte. This is historical model reproducibility, not financial efficacy.
- GitHub actual **SMALL read-only validator** `research/c3_v655/extension_guard.py`, fixture `research/c3_v655/test_extension_guard.py` (13 authored test cases), and `.github/workflows/c3_v655_d5_extension_tests.yml`. The GitHub 13-case CI is NOT the user-local full 28-test market-archive replay; **remote test completion not claimed**. No secrets/trading actions and Work v6.38 frozen.

## DEVELOPMENT DECISION

**Keep frozen 5-day first-pullback exit and 12-day target-chasing modes as prior research controls; defer deployment of D5-profit+MA20 extension**. Next true upside model research should prioritize a newly recorded break/retest **past dated overhead**, verified direct issuer catalyst, sector absolute advance and actual market conditions on D5; **not** adding more moving averages or after-the-fact choosing best horizon on the same already inspected 2026 data. For actual target entry, issue a screenshot-style fresh-time stock trading report only with authentically observed day/price support, original structural stop and recorded nearest resistance/1st/2nd confirmed goal; unknown current stock prices/sector PIT => CASH/data-needed.

No automatic orders, 0 independently completed new broker trades, no K100 changes, PR #25 DRAFT.
