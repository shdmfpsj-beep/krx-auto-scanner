# Dynamic Entry Geometry V2 — independent research

**FINAL: see [RESULTS_KO.md](RESULTS_KO.md). Initial dynamic outcomes below were invalidated by the omitted-failed-retest defect. Corrected run 43164556284 / code 7f7916328a9434dc7bc9751d0d34518f0d17163b: 75 tests pass, 13 new Nov11 plans, zero geometry-passing candidates, no operational promotion.**

This branch calculates new support-based entry ranges from completed prices. It does not replace, register, edit or send any operational C3 signal. The production engine remains 54e7120b01966930e176d431e85b679347210c41. The frozen November 11 original is source run 43086941571. Production main, original ledgers/stops, Telegram receipts and morning schedules are protected by before/after blob inventories.

## Reuse and changes

- Reuse HMA60 and confirmed turns/first-pullback phase from `first_pullback_v55.py`; reject an already completed earlier reclaim before calling a new reclaim the first pullback.
- Reuse simple-mean ATR14 from `free_structural_v52.py`, KRX tick rounding, confirmed two-right-bar pivots and completed breakout/retest detector from `entry_strategy_v58.py`.
- Reuse contraction/higher-low/volume-dryup inputs from `krx_preignition_v87.py` on the preceding bar, ignore its arbitrary score, and require the current completed breakout and repeated support.
- Generate entry ranges from the identified support and stop from its actual invalidation low minus a fixed 0.25 ATR buffer. R1/R2 are actual confirmed overhead pivot highs. Do not invent a target at an all-time high or move the stop to manufacture reward/risk.
- A distinct second confirmed support is optional and is an alternative entry, not an automatic averaging-down instruction. Three strategies are distinct from two entries.
- Only two added indicators: population-standard-deviation Bollinger BandWidth20 (20 SMA, two deviations) and Wilder ADX14. Compare their frozen filters through ablations, without changing thresholds after stock-level results.

## Frozen pre-run protocol and comparison

`config/c3_dynamic_entry_v2_protocol.json` records unvalidated research assumptions before the first real replay: at most one ATR/8% entry distance, at most 8% structural stop risk, net R1/R >=1.5, 20-day mean turnover >= KRW1bn, original positive/improving board-relative momentum. None is a validated profitability threshold or a production approval.

First reproduce the frozen 2769-market / 2416-continuous / 1988-eligible / 149-technical / 50-B / 4-old-geometry / 0-combined control. New strategies examine all reproduced technical candidates with an explicit 80-bar warm-up requirement. The historical comparison uses the November 11 eligible universe retrospectively, the original price preselector/rank, and reports that current-universe/sector conditioning and survivorship have not been eliminated. It is not an exact replay of historically registered signals.

The retained raw history is extended without altering any approved 90-bar suffix. Reset at missing board sessions, name changes, audited rebase events, >35% discontinuities, invalid/halted prices; no performance path crosses these boundaries. A 60-candle chart requires 119 contiguous actual observations to display MA60 on the entire visible window.

The last 40 observed sessions are a chronological comparison segment; purge 23 signal sessions before it and stop development outcomes before the segment begins. This reused history is not an independently unseen validation set. Choose among dynamic ablations using development data only if at least 20 complete development opportunities exist; otherwise retain the preregistered DYNAMIC fallback. Report the original model, dynamic, +BandWidth, +ADX and both. Independent strategy arms are separate; combined results count a ticker once with a 20-session lockout. Rank by original turnover/RS; within a ticker choose the closest ATR-distance valid plan before looking at outcomes.

Compare 1/2/3-session range expiry and 5/10/20-session after-entry outcomes using the same conservative common maturity clock. A gap below the entry range cancels, a limit fill occurs only after a future daily low touches the range, a stop wins an ambiguous same-bar target, and intraday entry-bar highs cannot prove post-fill targets. R1 exits and an independent R2-before-stop opportunity path are separate. Costs reuse the existing engine (buy0.15%, sell0.5%, each-side slippage0.1%). Cash-inclusive half-slot opportunity metrics are not a capital-constrained portfolio simulation.

## Company quality and authorization limits

The existing financial snapshot was collected after November 11 and lacks authenticated original filing/PIT evidence. It is labeled context only, excluded from historical ranks and cannot certify financial stability. Strict integrated TOP2 therefore remains unconfirmed (candidate count null), distinct from a valid zero-candidate CASH result. Regular-only OHLCV/turnover scope remains uncertified, and buy approval stays false.

No Telegram API call, credential for delivery, registration/publish function, live order, paid API, schedule change or main merge is part of this research workflow. The workflow runs only on this research branch; pull requests run tests only. Artifacts exclude the private restored market panel and encryption material.

## Evidence

The Actions workflow `c3_dynamic_entry_research_v2.yml` preserves the exact protocol, original replay, all current candidate diagnostics, historical event/outcome rows, real PNGs and their source hashes, tests, and protected before/after inventories. Actual execution results will be appended after inspecting the run and artifacts.

## Initial executions — INVALIDATED BY STRUCTURAL-STOP DEFECT

Commit `5dc4ee51b7474df3536894c89daba7c5908e911b`, push run **43163227570**, PR-test run **43163260439** both succeeded. The push artifact **13918294316** has ZIP SHA256 `939be0d53bc611e8b87ca9de56ca22d569df45b2d90e9e7dcc38af7c939ce23c`. Regression: **72 passed, 0 failed**. The full retained source has **1,012,593 rows / 372 sessions, 2025-05-02 through 2026-11-11** (panel SHA256 `b5ab966f36eae3635d7d2e5b3e9a8bb4f1c3fdd828f1b91c273a763d13968932`). All original last-90 suffixes and 2769/2416/1988/149/50/4/0 counts reproduced.

November 11 produced 13 new plans, 3 geometry-passing tickers, and 1 geometry+momentum+liquidity ticker (425420). The development-chosen BandWidth variant has **zero** final technical candidates on that date; the base-only ticker is an ablation watch, not a selected TOP2. Its future chart is explicitly labeled as such. No financial-quality original/PIT is authenticated, so integrated selection remains held with candidate count null and CASH.

Development signals: 2025-08-28 through 2026-08-07; outcomes stop 2026-09-10; comparison segment 2026-09-11 through 2026-11-11, with a 23-session purge. For 1-day expiry / 20-day outcome, development chose DYNAMIC_BB (33 complete opportunities, 17 fills, opportunity mean +1.3297%, filled mean +2.5812%). Its comparison segment contains only 4 complete opportunities, **zero fills**. Zero return is uninvested cash, not demonstrated profitable trading. DYNAMIC comparison: 16 complete / 2 fills / opportunity mean -0.7988%; C3_ORIGINAL: 11 complete / 2 fills / -1.3190%; ADX: 12 complete / 3 fills / -1.3612%; both filters: 1 complete / 0 fills / 0%. These different opportunity cohorts are not paired evidence of causal improvement.

Verdict: **RESEARCH MAINTAIN**, no operational promotion. Subsequent reporting changes add method funnels, direct company-evidence gate statuses, source-linked MA audit values and a clearly labeled base-model watch chart. They do not change the protocol, historical selections or outcomes; verify equality against the first artifact after execution.

## Mandatory correctness fix discovered in actual chart inspection

The actual TFE chart exposed an omitted failed retest: legacy `breakout_retest` accepted any earlier contact, and the initial dynamic wrapper calculated the stop only from contacts closing near the breakout level. Later much lower bars were omitted. This could falsely retain invalidated support and inflate net reward/risk. **The initial performance and TFE watch plan above are invalidated implementation results, not usable evidence for adoption.**

The correction inspects EVERY post-breakout completed bar through confirmation, sets the invalidation low to the full observed minimum, and rejects a breakout if any subsequent close violates the already-existing v58 support tolerance (level minus 0.25 ATR). The confirmation-day low is also included for compression. No numerical research threshold was relaxed. Three explicit regression cases protect later breakdowns, intraday undercuts and the confirmation-day low. A recorded correctness amendment changes the protocol hash transparently; all original numerical parameters are unchanged. Recompute all selections and performance after this fix. No production or registered stop is edited.
