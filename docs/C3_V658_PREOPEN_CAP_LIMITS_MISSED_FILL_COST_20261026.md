# C3 v6.58 — pre-open small upper-cap limits vs missed D+1 entries (2026-10-26)

**Research only. NO new BUY; K100 and Work v6.38 frozen A/B unchanged; PR #25 DRAFT; broker orders disabled.** User decides capital and share quantities. Chart-only D price and original structure stop and D-recorded first overhead used; direct issuer catalyst and verified regular-only KRX prices unavailable for current 2026-10-26 stock picks.

## What was ACTUALLY run
- Original Work **264 frozen D signals, 94 distinct D dates, 192 original stock price files**, latest signal D=2026-10-19 and price source through 2026-10-23. Original first overhead D recorded only **74/264**, **190 missing not no-resistance**. 2023 KRX unified cash-stock price tick floor research approximation, official 2026 ticker venue not certified.
- Three precommitted next-session pre-open **resting buy-limit caps**: D close +0.10ATR, +0.25ATR, +0.50ATR. If D-documented first overhead exists and price cap reaches it, reject that cap before D+1. Original D daily structural stop and target unchanged; no account-level risk input; no 1% stop or fixed -10% second buy. Opening prices below cap modeled at opening price, above cap but daily low touching cap modeled only as a **price contact proxy**; if entry bar stop or target might have happened first, status UNKNOWN. Buy fee 0.15%, sell 0.50%; stop-first five and twelve sessions; nonfilled opportunity=CASH0; paired common-D comparisons only.
- Added **264×3×2 = 1,584** price-proxy trials, in addition to previous **2,640** (five entry methods × 5/12 sessions), total 4,224. This is historical mined repeated sample, NOT new independent OOS, actual broker fill, regular-only exchange price, or 09:05 tradable intraday entry.

| New method | cap D-valid | D+1 price-contact proxy | Conditional 5d net median | 5d matched opportunity vs D+1 OPEN | 12d matched opportunity vs D+1 OPEN | 12d vs prior D-close resting limit |
|---|---:|---:|---:|---:|---:|---:|
| Dclose+0.10ATR | 260 | 231 | +0.424% | +0.103pp (251) | +0.369pp (249) | +0.094pp (245) |
| Dclose+0.25ATR | 252 | 236 | +0.739% | +0.172pp (254) | +0.508pp (252) | +0.149pp (244) |
| Dclose+0.50ATR | 243 | 236 | +0.565% | +0.071pp (261) | +0.280pp (259) | -0.048pp (245) |

Date-cluster bootstrap 2000 draws **CAP25 vs open** 5d 95% [-0.075,+0.404]pp includes zero; 12d [+0.219,+0.836]pp excludes zero but **multiple methods/horizons/comparators and extensively mined original history invalidate independent statistical superiority claims**. CAP25 vs D-close resting limit 12d 95% [-0.258,+0.638]pp includes zero. Do not promote CAP25 as proven optimized threshold.

**Predeclared robustness checks:** CAP25 5d mean opportunity in Jan-Jun +1.401% (215 matched), Jul-Oct **-1.712%** (39); 12d Jan-Jun +2.704% (215), Jul-Oct **-3.058%** (37). Timing improvements cannot rescue weak stock selection or markets. Among D-first-overhead-known 65 comparable, CAP25 5d mean opportunity difference vs open **-0.045pp**, 12d +0.585pp; missing-overhead 189/187 comparable 5d +0.247pp, 12d +0.481pp — missing overhead does not mean open sky or live BUY eligibility.

**D+1 gap retrospective diagnosis ONLY, not tradable at the observed same open:** D+1 gap <=-0.25ATR n49, 5d opening-price mean -0.874%; -0.25..0 n92 +0.801%; 0..+0.25 n58 +2.242%; >+0.25 n65 +0.017%. Can't observe opening gap and retroactively claim same opening execution. For future conditional intraday gap, require authentic KRX 09:05+ bars/quote timestamp and new stop/entry calculation.

## Source and tests
- Exact user full portable ZIP **`C3_v658_상단허용지정가_타점실증연구.zip`** SHA256 **`fb18a11d3be53cf3865cc8eaea51bed602dad1dea90ea0530ed6d471d9a206da`**; detailed Korean report `c3_v658/C3_v658_실제체결가능성_상단허용지정가_타점연구보고서.md`.
- Full code `entry_timing_v657.py` original replay, `entry_cushion_v658.py`, `run_v658.py`, `test_v658.py`. **34 local tests PASS**. Fresh extraction + SHA256 input verification, **34 tests PASS again**, full replay and **all 9 output files SHA256 byte-identical**. Includes 264 original D-only stock price/stop/overhead entry cards with second overhead / direct issuer catalyst / KRX venue explicitly NOT_VERIFIED and status CASH.
- GitHub small safe guard `research/c3_v658/preopen_cap_guard.py`, `research/c3_v658/test_preopen_cap_guard.py` (**12 authored mini fixtures**), `.github/workflows/c3_v658_preopen_cap_guard.yml` separate from full empirical ZIP; remote GitHub Actions success NOT established.
- **Research next:** current verified KRX 09:00–15:30 stock OHLC + official direct issuer catalyst posted by D + absolute peer-sector breadth + real documented support and first overhead + no chasing above dated resistance. If not verified, report CASH. No orders, no K100 change, no production merge.

Source constraints: volume-profile POC/VAH/VAL, investor net buying, current live quote and exact actual Kiwoom order fill are all UNVERIFIED.
