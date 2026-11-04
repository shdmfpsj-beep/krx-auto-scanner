# C3 / K100 cross-chat integration checkpoint — 2026-11-04

This is a **research inventory**, not an approval to trade, a verified scanner run, or a replacement for immutable historical plans.

## Source-of-truth boundaries
- GitHub main: operational workflows and durable paper ledger; do not overwrite existing positions or change production schedules as part of this research PR.
- Research branch / PR #30: read-only ledger audit, synthetic regression tests, independent OHLCV comparison prototype.
- The 2026-10-30 research TOP2 (Orion 271560 / Dong Suh 026960) were registered on 2026-10-31; subsequent hypothetical fills are **not broker fills**.
- Paper ledger observed through 2026-11-03 when last inspected. No confirmed 5/10/20-session outcome, no regular-only source certification, no real orders.
- Comparing adjusted pykrx prices with another adjusted pykrx file is not independent verification. Matching numbers alone does not prove the provider captured exclusively 09:00–15:30 KST.
- PR #30 tests have not yet been verified as passing on GitHub Actions. Do not merge until tested.

## Reconciled workstreams from previous conversations
1. **C3 full-universe data coverage**: an older v5.7.2 collection recorded 2,568 valid of 2,679 symbols (95.9%); 111 missing. A later inspection found 40 suspended/zero-volume-like rows not safely mergeable. These are *historical snapshots*, not the present-day coverage claim. Always publish actual session, expected count, successful count, exclusions and reasons.
2. **C3 ranking**: TOP2 only, no pharmaceutical/biotech; do not use the account cash balance or share price as a ranking feature. Report sector leadership, relative strength, price/volume, liquidity, independently confirmed investor flows if available, earnings/news, and structural entry geometry. No score/price should be fabricated from missing data.
3. **Entry/exit research**: daily-chart structural invalidation stop FIRST; then a realistic watch band, no-chase cap, first resistance and T1/T2. Compare pullback, post-breakout retest, and continuation entries without requiring the watch band to be within 3% of stop. A same-day high after assumed entry cannot prove target order. Close-below-stop exits at the next genuinely observed open, never a favorable later open.
4. **Forward tests**: immutable prospective TOP2 registration, no backdated fills; 5/10/20 observed sessions, open and early-closed positions in denominator, costs, missing-session gaps, no-fill missed rallies, and ambiguous OHLC ordering. Keep small samples descriptive, not predictive.
5. **Historical research**: older v6.37/v6.38 and v62/v66 research investigated confirmation swing lows, breakout/rebreak, pullback and ignition strategies. Some backtests were negative or had severe drawdowns; **none should be promoted** to production based on those studies. Corporate actions, point-in-time universes, delistings and adjusted-vs-unadjusted prices remain critical.
6. **K100**: keep Core existing holdings management separate from Tactical new candidates. Reconcile holdings against current user-supplied positions before any action table; old snapshots must not be treated as current holdings. Do not modify K100 production as a side effect of C3 research.
7. **Mobile reports**: two large portrait charts with actual 20–30 daily candles only after valid sourced bars, MA20/MA60 where history exists, volume, stop/buy zone/resistance/targets, session, source and approval state. Never generate fictional charts or claim verified TOP2 without verified data.
8. **News**: distinguish domestic items, global requests attempted, queries succeeded and observed articles. Zero articles is incomplete rather than positive confirmation.
9. **Automation**: do not silently modify existing ChatGPT scheduled tasks, GitHub production schedules, account orders or broker secrets. Cash/no new approved buys remains default when gates fail.

## Research PR #30 changes
- `scripts/c3_paper_integrity_audit_v1.py`: read-only plan/ledger safety and chronology checks.
- `scripts/test_c3_paper_integrity_audit_v1.py`: synthetic regression cases.
- `scripts/c3_price_concordance_v1.py`: fail-closed separate-provider OHLCV comparison; `regular_only_concordance_passed` is NOT `regular_only_certified`.
- `scripts/test_c3_price_concordance_v1.py`: synthetic comparison regressions.
- `.github/workflows/c3_paper_integrity_research.yml`: research-only CI test configuration.

## Next verification sequence
1. Confirm CI runs and inspect logs. If none, diagnose GitHub Actions branch workflow trigger / manual dispatch before reporting success.
2. Verify ledger audit against actual main snapshot; repair schema mismatches in research branch only.
3. Acquire independently sourced **actual regular-session-only** OHLCV and trustworthy provenance, compare per ticker/date, investigate adjusted-price and volume semantics.
4. Produce source-verified TOP2 entries and mobile charts. Keep `trade_approved=false` until all independent gates pass.
5. Evaluate 5/10/20-session prospective cohorts and missed-rally rates without hindsight, then compare alternative entry strategies.

This checkpoint does not claim current-day scan completion, confirmed CI success, or improved returns.
