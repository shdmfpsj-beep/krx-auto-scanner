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

- Local focused tests: 73 passed before CI (59 preserved + 14 boundary tests).
- AST comparison: `ReceiptStore`, `Telegram`, `deliver`, `delivery_key`, `report_error`, `expected_session`, `validate_photos` unchanged.
- PR CI must exercise current live dry-run, actual saved receipt diagnostics, two read-only prior-session control requests, historical real-image regressions and a **zero-send** persisted duplicate check.
- CI must then publish the same-source derived packet to the research branch without Telegram credentials.
- After CI, merge only this report/operations patch; do not merge research PR #30 or change example-request configuration.
- Read `reports/c3_forward_v8/presentation/latest.json` only when its source hash/run/date matches `latest.json`. `NOT_READY` has no current TOP2/images. The immutable evidence for old successful cards is not a new live report.
- Tonight's actual schedule events and ChatGPT delivery remain unobserved until they occur. If prices remain unavailable, CASH/no new signal/no Telegram album is the correct safe outcome.
