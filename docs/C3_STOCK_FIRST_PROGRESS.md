# C3 stock-first research progress (2026-10-31 KST)

**User priority:** Find likely early leaders and practical entries, with a chart
showing **structural stop -> entry band -> target 1 -> target 2**. Do not make
finance disclosures or press coverage hard prerequisites. Avoid repetitive
historical P/L optimization and automatic portfolio sizing.

## Done in research branch (draft PR #28, not merged)

- [x] Full-market frozen source from GitHub Actions 41051723762:
  2,625 -> 457 early candidate observations -> 96 technically researched.
- [x] Stock strength evaluated separately from price entry geometry.
- [x] Oversold/reflex bounce separated from established early leadership.
- [x] Daily confirmed support -> rounded structural stop; practical entry band
  without mandatory stop+3% cap.
- [x] Future completed-candle breakout watch separated from pullback orders.
- [x] 45-session candlestick/volume/MA5/MA20 chart with stop/entry/T1/T2.
- [x] Objective T1/T2 from dated, confirmed swing-high history; NEVER fill in
  unobserved targets with arbitrary percentage profits.
- [x] Downstream TOP2 chart and action sheet choose symbols from ranked models
  rather than hardcoding Orion/Dongseo.
- [x] Missing fundamental reports or public bullish news = neutral; provisional
  DART data is not treated as independently verified evidence.
- [x] v7 full-history radar: 18 old resistance levels recovered in 96 symbols;
  NICE Evaluation Information is one additional *watch-only* challenger.
- [x] Local v7 deterministic/source-integrity checks: 7 passed.
- [x] v6 compressed input manifest now includes its required provisional DART
  and event title audit CSVs.

## Unresolved; do NOT treat as completed

- [ ] GitHub Actions successful run for the new PR branch not confirmed
  (no workflow run associated with last inspected head).
- [ ] Independent KRX regular-session-only source and actual exchange turnover.
- [ ] Authenticated foreign/institution order flow by ticker and sector.
- [ ] Updated daily source and new-date re-ranking after 2026-10-30.
- [ ] Evaluate lightweight current corporate catalysts **only when verified**.
- [ ] Full downstream trading approval: deliberately **disabled**.
- [ ] Telegram: postponed until user explicitly requests it.

## Frozen 2026-10-30 research view

| Priority | Stock | Stop | Entry watch | T1 historical | T2 historical | State |
|---|---|---:|---|---:|---:|---|
| 1 | Orion 271560 | 109,600 | 110,900–113,700 | 131,500 | 141,700 | Primary price watch |
| 2 | Dongseo 026960 | 26,900 | 27,600–27,950 | 29,550 | 30,550 | Historical heavy-supply / secondary |
| Challenger | NICE 030190 | 16,470 | 16,780–17,070 | 18,000 | 18,140 | Older pivot: 157 sessions ago |

Both C3 research opportunities and price chart outputs are **NOT** BUY orders,
profit guarantees, independently verified regular-session scope, or proof of
foreign/institution accumulation. Stop slippage/gaps can cause greater losses.

The next development gate is **new dated observations plus verified sector-flow
data**, not repeating tests of old portfolio returns or pretending media silence
means a stock lacks a driver.


## 2026-10-31: Daily large portrait charts and close-integrity guards

- Existing ChatGPT C3 22:30 KST daily report task updated: display two large inline portrait charts (not side-by-side), source run ID, original trading date, TOP2 reasoning and final strategy table.
- Each visual has real-price full-range map and a separately labeled zoomed 35-session OHLC chart, MA5/MA20, volume, structural stop, entry band, historical target 1 and 2.
- Added scripts/c3_top2_large_portrait_v2.py plus test_c3_top2_large_portrait_v2.py; generic TOP2 selection from newly dated ranked input (no fixed Orion/Dongseo tickers). Output targets 1751x2618 pixel image per stock.
- Added scripts/c3_regular_price_reconciliation_v1.py and test_c3_regular_price_reconciliation_v1.py: use declared regular close only as untrusted comparison. Missing, mismatched and future-date prices are visibly blocked; do not automatically move the structural stop and targets.
- Research-only GitHub workflow extended to test/generate poster images and close-integrity audit as artifacts. The branch remains draft/unmerged.
- Locally generated and visually inspected October 30 portrait previews: 271560 and 026960, 1751x2618; source close 114200 / 28400. The earlier externally checked regular-only close values 114800 / 28450 were labeled as a discrepancy, not substituted into study OHLCV.
- Still pending: one successful GitHub remote workflow run for these new changes, authenticated regular KRX close + flow reconciliation, and a NEW dated v5-ranked TOP2 source from the production scan. The daily report prompt alone cannot guarantee an image when the source, renderer or run is missing.
- Zero BUY approvals and zero brokerage orders. Historical user stops unchanged. Empty news/finance evidence remains neutral. No Telegram integration.

