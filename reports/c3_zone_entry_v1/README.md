# C3 Zone Entry V1 — preregistered independent paired research

One support zone [lower, upper], two pre-queued limits: 50% at upper and 50% at lower. These are not independent support strategies. No production, original signal/stop, ledger, Telegram, schedule or order change is authorized by this branch. PR104 provides only source loading, actual-price charting and structural helper code; its performance is not assumed successful.

## Scope and reuse

Main remains 32b2caae3d508cea5b1ca1b5cc505b82636bb8e1. Source engine is exactly 54e7120b01966930e176d431e85b679347210c41, registered source state da44b0225e228353a77a57998fc31c482ce8e11a. This branch is stacked on PR104 research commit c7860e1b4cba9b93f8e142a7bc84c1c4d377b856 and is not a main deployment.

Reuse original stock preselector, B positive/improving board-relative strength, turnover rank, original A_SUPPORT_LIMIT plan, ATR, KRX ticks and confirmed pivots. Existing `staged_entry_research.py` was reviewed: it buys first at next open, uses a distinct second support, rescales capital and creates hypothetical 2R targets. Those semantics do not match upper/lower orders in one original zone, so they are not presented as an implementation of this experiment. No new indicator is added.

## Fixed before the first real run

See `config/c3_zone_entry_v1_protocol.json`. Same original selected ticker/date cohort in all models, with a 23-session lockout before plan filtering (common maximum 3-entry + 20-holding clock, not a change to original operational de-duplication). No model-specific historical ticker backfill. All planned capital is KRW5m; A uses 100% at original upper, B uses 50:50 original upper/lower, C uses 50:50 new zone if independently eligible. H, a diagnostic control, uses 50% at original upper and leaves the rest cash to isolate the incremental lower order.

C uses the most recent two-right-bar-confirmed, unbroken pivot over the existing 35-bar lookback. A single support-zone lower is support +0.25 current ATR; upper is support +1.0 current ATR, capped at current close. Its stop is the support invalidation low minus 0.5 ATR at confirmation, frozen for that new research plan. These coefficients reuse the original zone's construction, not fit to SamsungE&A/Wonik. Resistance is actual confirmed overhead pivots, never a fabricated 2R target. Separate full-fill and first-only quantities/risks/RRs are reported. C's reused provisional 8%/8%/1ATR/1.5R filters are research assumptions, not proven profitability rules; no first-leg 1.5R gate substitutes for integrated position risk.

Quantities are integer shares fixed using limit prices and costs before the next open. Unspent capital stays cash. Nominal limit fill prices never exceed the limit; fixed slippage is an extra research friction, not an assertion that an exchange buy limit trades above its limit.

Primary comparison replays canonical O-H-L-C and O-L-H-C orders EACH day, branches exact-touch fill uncertainty, and merges equivalent economic states. This is not all possible intraday oscillation or broker queue proof. Report adverse/optimistic simulated outcomes and ambiguity rather than exclude ambiguous losing trades. Both buy limits are queued before open; a gap below a zone is NOT retrospectively cancelled. A gap below stop can fill queued limits; immediate-open and same-day-low manual-exit stress are separately flagged uncertain. Costs match the original engine: buy0.15%, sell0.5%, each-side slippage0.1%.

All A/B/C arms share primary R1 exit / intraday structural stop / time exit assumptions. This is a controlled comparison of entry allocations, NOT an assertion of the original C3 close-stop execution's historic returns. A separate success-case diagnostic holds past R1 and uses the frozen close-stop-next-open policy to distinguish a user's ongoing holding from the primary hypothetical R1-exit experiment. Daily data cannot verify actual fills/times.

Split chronology exactly as prior work: last40 sessions as a reused comparison interval, purge23 signal sessions before it, end development outcomes before that interval. History has already been researched, universe/sector membership is conditioned on Nov11 and financial original/PIT is unverified. Do not call this independent unseen validation. Report same-plan-valid subsets, descriptive width/distance bins and regime breakdowns. Per-opportunity planned-money expectation and per-plan drawdown are not a capital-constrained portfolio simulation. A predeclared +0.5 percentage-point paired effect, 80% power /5% alpha calculation is only an IID lower-bound sample-planning illustration; correlated and reused observations do not certify adoption.

## Case evidence

Original dated preview artifact13878507537 (archive SHA256 fac8e85c6de8ec76f2610723b75638694a48c37d3962e629cdddc058d7e335ba) records Nov05 SamsungE&A [60,700,63,500], stop57,700 and Wonik [22,100,23,500], stop20,600. Its source receipt clocks do not authenticate availability before the hypothetical next open. Registered Nov06 decisions, if present, are read separately, never retroactively created.

User-reported orders: SamsungE&A63,500/KRW2.5m and60,700/KRW2.5m, both reported filled; Wonik23,500/KRW2.5m reported filled. No user-confirmed Wonik lower fill, actual quantities, broker receipts or execution times were found. A prior assistant's106 shares/23,450 average is not treated as independently verified user execution. The new two-order Wonik simulation is hypothetical, not fabricated actual history.

## Execution evidence

Only this branch's push runs actual archived-data research; PR events run unit tests only. GITHUB_TOKEN contents/actions are read-only, the original KRX secret only decrypts existing archives. Private bulk panel/encryption material is excluded from artifacts. Original signal/stop/receipt blob inventories and main are compared before and after. Source-control results, case risk/replay JSONs, all current candidate diagnoses, paired event paths, metrics and real60-candle/MA60-warmed charts are preserved in Actions. Actual result and verdict will be recorded after inspecting the execution.

Primary exchange references: https://regulation.krx.co.kr/contents/RGL/03/03020204/RGL03020204.jsp (buy-limit pricing and non-guaranteed execution), https://regulation.krx.co.kr/contents/RGL/03/03010201/RGL03010201.jsp (opening auction priority). Neither replaces broker fill evidence. The official daily volume/value scope remains uncertified for regular-only use.
