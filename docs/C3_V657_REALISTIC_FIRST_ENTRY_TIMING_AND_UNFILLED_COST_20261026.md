# C3 v6.57 — REALISTIC entry timing / price-grid / missed-opportunity audit (2026-10-26)

**User's scope: C3 picks stocks with rising potential and gives chart-evidenced first entry, original D structural stop, recorded first and conditional second overhead target, and future-upside scenario. Account capital/shares/1%-loss budget are USER decisions.** Work v6.38 original A/B untouched, PR #25 DRAFT, no broker orders, no K100 changes.

## Actually executed locally and cleanly reproduced
Input: **264 frozen** Work original research D-pattern signals across **94 different D dates and 192 exact original daily-stock price files**, with **550 D technical level lines**, last source D 2026-10-23. Source immutable v18 archive SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30`. Five **D-time precommitted** entry methods × 5/12 sessions = **2,640 historical model-price situations**. Synthetic rates BUY 0.15%, SELL 0.50%; stop first. No account cash/quantity/risk% in ticker/level formula. Original recorded D hurdle missing for most stock picks => no invented upper target. Each computed limit rounded DOWN to 2023 KRX standardized tick grid (1/5/10/50/100/500/1000 won by quoted band); actual 2026 issuer/venue/time certification still required, not an executable order. Synthetic OHLC low touch or next-session open is not broker fill; unknown intrabar entry/stop/target order **UNSCORABLE**. 2026 data reused many times before this study -> neither independent OOS nor profit proof.

| D-frozen entry plan | Observable open or limit price contact (264 D cases) | Completed 5-day shadow price exits | Conditional median 5d net price PnL | Matched same D 5day mean opportunity difference vs D+1 open with no-fill CASH 0 |
|---|---:|---:|---:|---:|
| NEXT OPEN | 264 | 264 | +0.4076% | baseline |
| **D closing price limit next D+1** | 222 | 222 | +0.4642% | **-0.0614pp** (matched 248) |
| **D close - 0.10 ATR14 limit next D+1** | 211 | 211 | +0.4239% | **-0.0672pp** (matched 249) |
| D close - 0.25 ATR14 limit next D+1 | 183 | 183 | +0.2614% | **-0.4317pp** (matched 251) |
| D-documented nearest MA/pivot/support ≤0.75 ATR below D close, order valid for next 2 days | 123 contacts from 192 signals with eligible support | 123 | **-0.4986%** | **-0.7499pp** (matched 251) |

From matched 12d opportunity comparisons: next D closing-price limit **+0.3938pp** (246 matched); -0.10ATR **+0.1564pp** (247); -0.25ATR **-0.6459pp** (249); near D technical support 2-day **-1.1471pp** (249). Trading-D-cluster 2,500 resample 95% uncertainty intervals for **next-close limit:** 5day **[-0.5098,+0.3266]pp**, 12day **[-0.2054,+0.9315]pp** — **BOTH INCLUDE ZERO**. No trade-rule profit superiority demonstrated and strong repeated-model overfitting risk. An older v6.48 0.25 ATR threshold on a 267 D cohort differs numerically because new tick rounding, 264 fixed D cohort, nearest-technical-support alternative, additional same-day uncertain fill handling.

### Other research observations, not approved filters

- D candle close in its upper quarter n205 => mean net 5d +0.184%, other candles n59 => +2.105%; repeated after-event diagnostic and winners dominate.
- D-verified MA/pivot/old-resistance technical price line within 0.75ATR n192 => historical net 5d mean +0.200%, no such line n72 => +1.717%; **the mere presence of technical support DOES NOT establish probability of continuation**.
- July–Oct23 subsequent model conditional means were negative: D+1 OPEN n40 5d -1.690%, D close limit completed n37 -1.648%. Date cutoff now used only for historical diagnostic, never a calendar-based live BUY blocker.
- Rejected limit orders => 0 in **matched D opportunity analysis**; ambiguous paths and later missing data are dropped as a pair, never quietly counted as wins. Multiple stocks same date and overlapping periods => this is NOT one-slot cash/EOD equity compounding or broker-verified execution, and date resampling is not an OOS statistical guarantee.

## Research artifacts, testing, independent re-run

Exact finished working container artifacts:
- `C3_v657_타점정밀화_연구코드_실증검증.zip` SHA256 **`71087d2692de2b59586a0a315ed39ae8e6dece30010522e3078c1f3b3ecf025a`**.
- `c3_v657/C3_v657_타점정밀화_수익성검증_연구보고서.md` detailed mobile Korean report.
- Full portable source `entry_timing_v657.py`, `run_v657.py`, **37 local Python regression tests PASS** including **pandas Series.asof collision** regression, book-price grids, D support level no-future assertion, same-day ambiguous entry/order and no-real-fill; 192 original stock OHLC members, 264 D signals and 550 D technical level source rows all embedded in the ZIP.
- **Clean-room extraction** to a DIFFERENT directory with `sha256sum -c INPUT_SHA256SUMS.txt` PASS, all **37 tests PASS**, full 2,640-case replay and **8 output CSV/JSON files byte-for-byte SHA256 identical**. No new remote full empirical GitHub Actions run claimed.
- GitHub actual SMALL pure-logic core `research/c3_v657/entry_price_grid_guard.py`, `research/c3_v657/test_entry_price_grid_guard.py` (**16 authored fixtures**), and `.github/workflows/c3_v657_entry_price_guard.yml`. This mini GitHub code is NOT the 37-case historical price replay. Any remote workflow success must be explicitly fetched and verified before saying CI passed.

## Development decision: what to really do next

**Priority A:** verify company catalyst dated public BEFORE end D + absolute-rising peer breadth + healthy whole daily structure, and evaluate a **reachably priced first entry near the last completed session closing price** only where a dated actual price support and original structural stop provide a plausible thesis. **Do NOT program automatic next-open BUY or indiscriminate Dclose resting limit**. B: 0.10ATR is exploratory but price alone insufficient. C: old MA/pivot support alone and 0.25ATR deeper discount lowered opportunity returns historically, so deprioritize. No automatic -10% second buy, and no cash/risk cap determined price. Require current regular-only KRX 09:00–15:30 issuer OHLC, authentic PIT ordinary-share/no-pharma-bio, timestamped new company filings, actual first resistance/volume profile or clearly label unknown. If missing any element, reported actions WAIT/CASH without fake entries/stops/targets. If verified, report user-preferred one-stock A support/B real first pullback/C condition breakout, original structural stop and 1st/2nd realistic resistance, fresh next5/12d upside with clear invalidation and scenarios.

**The v6.57 entry price levels are research price formulas only**. New 2026-10-26+ genuinely fresh prospective completed and certified broker PnL cases = **0**. Work A/B and K100 unchanged, orders disabled, PR remains DRAFT.

Sources: [2023 KRX cash-stock ticks](https://news.kbs.co.kr/news/view.do?ncd=7581122), [TradingView Broker Emulator](https://www.tradingview.com/support/solutions/43000786181-broker-emulator/), [TradingView Bar Magnifier](https://www.tradingview.com/support/solutions/43000669285-what-is-bar-magnifier-backtesting-mode/), [TradingView Volume Profile](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/).
