# 2026-11-06 operating integration checkpoint

Scope: report/data plumbing only. No strategy, risk, order, scanner, or receipt-policy changes.

## Observed before deployment

- Main `fc3caeaab7ae31738fc346a2254eafde7fafa560` includes merged PR #37.
- User-approved final-image QA run `42209694215` delivered exactly two caption-free photos; the later QA run `42209894727` recorded `POSTFIX_QA_DUPLICATE_BLOCKED`. Neither was repeated here.
- Full real research rehearsal `42212094443` passed 758 tests and saved the research branch (`5d72dc6ab32ed54f9337cbe09b5d9db42b3ec005`). Pipeline success did **not** mean price success: source session 2026-11-06 was `UNAVAILABLE`, source as-of null, new signals zero.
- Cache dated-file commit `16e3805db740e6cbe7c079998462b87121ca53b4` was 14:01:26 KST, before close; it cannot certify the day's EOD.
- Existing ChatGPT task `6ae53e1be3848191b8bdc818036ed09c` prompt was updated and read back at 20:39:06 KST. Enabled state, weekday 22:30 Asia/Seoul schedule, and task identity were preserved. Future delivery is unverified.

## Changes under test

1. `--mode live --dry-run` takes the real validation/decryption/rendering path and never creates a Telegram client. Missing prices produce a silent skip and empty presentation packet.
2. Derived handoff files use the exact current public report hash, research revision, engine version, original data date, image hashes, and separately dated post-selection company context. Historical previews cannot enter this live packet.
3. Handoff publication exclusively writes `reports/c3_forward_v8/presentation/`; the source latest hash is rechecked, the Git update is non-forced, and a competing/newer report aborts publication. Decisions and delivery receipts are untouched.
4. Existing 22:45/09:00 Telegram schedules are unchanged. When current prices are absent and no research run is active, one existing pinned research workflow call retries the entire official/validated-cache collection. Valid data with fewer than two candidates does not trigger recollection or invented candidates. Completion events do not invoke recursive recovery.
5. Existing 22:15/08:20 main caller, Telegram album policy, private archive validation, and immutable ledger are reused.

## Verification and continuation

- Focused tests: 59 preserved + 18 boundary tests after Git-transient handling.
- AST comparison: `ReceiptStore`, `Telegram`, `deliver`, `delivery_key`, `report_error`, `expected_session`, `validate_photos` unchanged.
- PR CI must exercise current live dry-run, actual saved receipt diagnostics, two read-only prior-session control requests, historical real-image regressions and a **zero-send** persisted duplicate check.
- CI must then publish the same-source derived packet to the research branch without Telegram credentials.
- After CI, merge only this report/operations patch; do not merge research PR #30 or change example-request configuration.
- Read `reports/c3_forward_v8/presentation/latest.json` only when its source hash/run/date matches `latest.json`. `NOT_READY` has no current TOP2/images. The immutable evidence for old successful cards is not a new live report.
- Tonight's actual schedule events and ChatGPT delivery remain unobserved until they occur. If prices remain unavailable, CASH/no new signal/no Telegram album is the correct safe outcome.

## Actual CI evidence / corrected failures

- First PR rehearsal `42214409864`: tests/live silent skip passed; diagnostic adapter import failed because its transitive standard-library-only modules were missing from sparse checkout. Added the six real dependencies.
- Second rehearsal `42214668670`: all 73 tests, live no-send gate, actual source diagnostics, two real historical PNGs, DART 2 companies x 4 quarters, and persisted duplicate check passed. Publication hit a GitHub `502` during a read, before any Git write.
- At 21:03:09 KST the same official key/request returned 2026-11-05 KOSPI 938 and KOSDAQ 1,831 rows. The saved actual 20:42:14-16 KST 2026-11-06 attempts both returned HTTP 200 / 17-byte JSON / empty `OutBlock_1`, twice. Cache failure was `DATED_CACHE_NOT_PUBLISHED_AFTER_CLOSE`.
- Evidence supports date-dependent source availability, rather than a general authentication/parser failure. Exact official publication SLA was not confirmed from accessible primary documentation; do not assert a particular next-day publication time as proven.
- Added bounded retries to idempotent handoff Git reads only. An uncertain Git-ref update is reconciled by reading the real saved packet; Telegram POST is never retried by this code.
- Chart readiness and delivery status are separate. Verified images/company analysis can remain available to ChatGPT if Telegram delivery is uncertain, with the original no-resend claim preserved.

## Deployment and final concurrency guard

- PR #38 merged to main `ead942f2b00dcedd2f1dea606786be31874a1d40` at 21:09:32 KST. Main cron/pin read-back confirmed unchanged 22:15/08:20 caller and 22:45/09:00 Telegram schedules, engine `0f6ebc67bd755b00945388d431e32d94183ba7fe`.
- Rehearsal `42215155177` passed 77 focused tests and actual research-only handoff publication. The saved packet is `NOT_READY`, source null, expected 2026-11-06, zero TOP2/images, at research commit `e47b6e841a6112cd24836b3303511a748df4a669`.
- A final integration review identified that a derived presentation commit could move the research HEAD during a still-running engine's publication lease. Handoff publication now checks for active caller/research runs before building the transaction and immediately before moving the ref; it defers instead of touching the engine's in-progress state. Artifact evidence remains readable.
- The additional guard has a focused fault test. Tiny start-time races remain fail-closed via the engine's original HEAD lease and non-forced publisher update; no ledger is overwritten and failed engine evidence stays in its artifact.
- No additional album was sent in this Work. Existing delivery receipt branch was preserved at `7501cafd66e7ce7ca38b79c36deb4da6a5762892` during the final read-back.
