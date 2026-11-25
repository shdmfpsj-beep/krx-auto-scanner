# C3 TOP5 + WATCH5: approved independent issuer operation

User approval: 2026-11-25. PR #209 connects the previously read-only comparison to the existing daily workflow. Financial PASS criteria, 100-point weights, technical prices, 5% maximum structural risk, industry exclusions, twenty-session history and existing ledger/receipts remain unchanged.

## Approval contract

Production balanced runs use `INDEPENDENT_ISSUER_FINANCIAL_APPROVAL_V2`. `EXECUTABLE_FINANCIAL_APPROVAL_V1` remains available unchanged for compatibility. The production selector first observes the entire existing interest pool using `select_approval_scoped()`, then runs the unchanged ranking/entry selector only on canonical financial PASS issuers.

- `approval_financial_complete`, `all_interest_financial_complete` and `coverage_complete` retain their existing meanings and values. In particular, the first two remain false for the November 24 source.
- `selected_financial_complete` and `selection_approval_complete` separately describe the approved selection. Delivery reproduces the result from the original geometry, pool and financial inputs rather than trusting new flags alone.
- `financial_unverified_excluded_codes` records issuer exclusions; no REVIEW_REQUIRED or ERROR record becomes PASS.
- Auth/rate-limit failures, original/identity integrity errors, future filings, unknown exceptions, missing requested observations and unverified technical disqualifications still block globally. A transport error is issuer-local only with explicit observations and a successful other issuer at the same endpoint. Unknown errors remain global.
- Financial comparability, ranking, entry-state gates and structural stops use the original engine.

## Three delivery channels

TOP5 requires PASS plus ENTRY_READY/NEAR_ENTRY. WATCH5 retains PASS, WATCH, exact risk <=5%, and distance >2% and <=5%. Reference images require REVIEW_REQUIRED, a valid ENTRY_READY/NEAR_ENTRY geometry, no proven financial hard failure, explicit missing-evidence reasons and no error. Each channel is capped at five; code/date/hash/source checks and existing history exclusions prevent overlap.

References carry `재무 미확인 참고용 — 정식 선정 및 매수 승인 아님`, the actual verdict and unresolved reasons. They do not enter TOP5 history or the trading ledger. Paths:

- `output/c3_top5/review_unverified/manifest.json`
- `output/c3_top5/review_delivery_result.json`
- create-only `receipts/c3_review_daily/{asof}.json`
- create-only confirmed-send `receipts/c3_review_daily/{asof}.sent.json`

Existing TOP5 and WATCH5 receipts are untouched. Reference receipt reads must be known absent before reservation. Partial/uncertain sends preserve successful message IDs and prohibit automatic retry. Final `execution_outcome.json` reconciles all three channels; a failed WATCH/reference channel cannot remain a green operational result merely because the earlier TOP5 step succeeded.

## Verified actual November 24 replay

Source: main run [45554051333](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45554051333), artifact [14994912183](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45554051333/artifacts/14994912183). ZIP SHA-256: `1720ea8890e8cce336ece09c7be8c44501e4a3bcb5379e3f9ab888ca8ea34c89`.

The actual archive contains 2,772 market symbols, 2,493 valid 60-session series, 12 technical interest candidates and 11 financial observations (one candidate is blocked by existing history). Finance remains PASS 3 / REJECTED 1 / REVIEW_REQUIRED 7 / ERROR 0. No API or correction recollection is performed. KRX payload hashes, original archive, original statements and original expiry are preserved.

| Channel | Code/name | Close | Entry | Stop | Exact risk | R1 | R2 |
|---|---|---:|---|---:|---:|---:|---:|
| TOP5 / NEAR_ENTRY / PASS | 053300 한국정보인증 | 5,400 | 5,230–5,300 | 5,100 | 3.7736% | 5,650 | 6,090 |
| WATCH5 / WATCH / PASS | 010660 화천기계 | 3,655 | 3,475–3,530 | 3,365 | 4.6742% | 3,845 | unconfirmed |
| Reference / NEAR_ENTRY / REVIEW_REQUIRED | 215200 메가스터디교육 | 40,750 | 40,050–40,100 | 39,300 | 1.9950% | 42,000 | unconfirmed |

WATCH distance is 3.41997%. Result: TOP5_READY, TOP5=1 / WATCH5=1 / reference=1, with three DRY_RUN channels, zero actual Telegram photos and no operating reservations. Whole approval remains false while selected approval is true. The source and independent outputs are compared byte-for-byte/hashes and JSON/CSV/PNG metadata.

Expiry remains **2026-11-25 15:30 KST**. Export copies conspicuously say historical/expired/no live send. These are past analysis, not fresh buy signals. Official adjusted prices, complete corporate-action certification and full historical PIT certification remain unavailable and are not claimed.

## Validation and deployment evidence

The final PR CI runs all 357 pre-existing tests plus 20 connection/reference tests (377 total). It also executes the actual production embedded manifest/TOP5 boundary, WATCH5 and reference scripts on the pinned actual archive with all network transport forbidden. GitHub actionlint 1.7.12 is verified against SHA-256 `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8` and validates the operating/recovery/review workflows.

The existing main-push verification workflow repeats full regressions and the same actual-source production replay after merge. Its artifacts, not a planned count, are the authoritative final test/run evidence. No new workflow, cron or alarm is added. Connection-only CI reuses the actual archive; changes to the actual collector still require live source validation.

## Latest-day and scheduling boundary

The existing 21:00 KST source cutoff is unchanged. On this explicitly authorized release push, November 25 is dispatched at most once only if that cutoff has been reached, main still matches the verified release, the workflow is active, no existing receipt/reservation or concurrent operating run is found, and all original live gates pass. Before 21:00 the controller records `DEFERRED_TO_EXISTING_SCHEDULE` without collecting or sending. Ordinary manual/PR runs remain DRY_RUN; the new manual approval token applies only to the approved November 25 release target. Expired November 24 signals cannot be live resent.

Existing cron: `0 23 * * 1-5` UTC = Tuesday–Saturday 08:00 KST; timeout 35 minutes and non-cancelling concurrency are unchanged. Next scheduled target: November 26 08:00 KST, using November 25 data. Existing 08:45 weekday read-only alarm is unchanged; the Saturday/weekday mismatch is disclosed. GitHub schedule delays remain possible (the observed November 25 schedule was created at 14:18 KST). A manual/main archive verification is not schedule execution or actual photo-send proof.

Deployment may be production-ready with limitations once merged CI is green: first fresh-day schedule and real photo message IDs remain observations, not verified sends. No further financial research or algorithm development is required for this release.
