# C3 TOP5 + WATCH5 final execution validation — 2026-11-24

WATCH5 is a separate observation channel. It never changes the formal TOP5
selection, financial score, entry calculation, 5% cap, existing signal history,
paper ledger, TOP5 reservation or normal operating result.

## Actual defect reproduced and fixed

PR #203's initial code `320d248c33b9cbb1a12463f20a138edbdccff34c` was executed against
actual artifact14913270782. It failed with `KeyError: 'asof'`: the verified isolated
integration outcome has no `asof`, although every dated original has it. The fix
requires all dated originals to agree and validates an outcome date whenever
present. It does not invent a date or allow mismatched periods.

Additional necessary delivery fixes:

- Preserve partial-success message IDs and a sanitized failure stage/reason;
  never log credential-bearing HTTP exception text or automatically retry.
- Validate actual financial PASS across report, selection and the existing
  classifier on original financial evidence. `financial_eligibility=WATCH_ONLY`
  does not mean financial failure.
- Recheck the unchanged `valid_entry(..., allow_watch=True)` against original
  technical evidence, OHLCV dates/prices, moving averages and existing duplicate
  history. WATCH distance is `(close-entry_high)/close*100`, strictly >2 and <=5.
- Verify source PNG SHA-256 and identity, preserve the classic chart and add the
  clear observation banner, distance and finance PASS. Generated PNG identity
  and hash are verified again before any reservation or multipart request.
- Use the existing configurable Korean font directory. R2 remains null/미확정
  when the original contains no second resistance; no target is fabricated.
- Separate create-only `receipts/c3_watch5_daily/{asof}.json` reservations, no
  writes to normal TOP5 receipts. Existing reservations and uncertain sends
  block retry. Current schedule/main/date/expiry checks precede actual sends.
- Report HOLD/ERROR/upstream failures as blocked; a WATCH failure does not alter
  formal TOP5's `execution_outcome.json` or `delivery_result.json`. The WATCH step
  records its own result even after an upstream failure and cannot send then.
- Replace only stale generated WATCH previews on reuse, never official images
  or receipts. The daily checkout includes the module; existing cron,
  concurrency and 35-minute timeout are unchanged.

## Actual November 23 replay — no KRX/DART recollection

Source: [run45376364821 / artifact14913270782](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45376364821/artifacts/14913270782).
ZIP downloaded and SHA-256 verified:
`270d3685a7e59345e2bed2b745e81a395b0dca872474627837d8b087c2a4192e`.

The new module was actually executed. Original dated JSON hashes remained
unchanged; no network request, operating reservation or Telegram send occurred.

| Field | 화천기계010660 | 아모레퍼시픽홀딩스002790 |
|---|---:|---:|
| Close | 3,605 | 27,350 |
| Entry low–high | 3,475–3,500 | 25,850–26,450 |
| Structural stop | 3,365 | 25,250 |
| Structural risk | 3.86% | 4.54% |
| Distance | 2.9126213592% | 3.2906764168% |
| R1 | 3,845 | 28,300 |
| R2 | 미확정 | 미확정 |
| Financial verdict / entry state | PASS / WATCH | PASS / WATCH |

Official TOP5=0; official state=`CASH_NO_ELIGIBLE`; WATCH5=2; generated WATCH
PNGs=2; WATCH state=`DRY_RUN`; actual Telegram=0. 윈스테크넷 is not selected:
its existing structural-risk rejection remains authoritative.

## Tests and CI evidence

The original264 regressions are retained. Thirty-one WATCH5 tests cover the required
selection matrix, score/distance/code sorting, maximum5+5, real classic rendering,
metadata/date/hash/source mismatches, legacy isolation, HOLD/ERROR, upstream
failure, stale production data, mocked create-only duplicate reservation,
Telegram multipart/HTTP/ok/message-ID/destination checks, partial failure and
secret-safe errors. Tests do not send Telegram messages.

The separate `c3_watch5_validation.yml` executes the module on the actual source
artifact and a clearly labelled synthetic TOP5five+WATCH5five input. Full
regressions and these execution proofs must pass before merge. The existing
Balanced CI only skips API recollection when source comparisons prove financial,
technical and existing workflow steps are unchanged; delivery-only changes have
their own full regression/execution job. Other engine/config changes still
require its previous validation. Existing integration success alone is not
counted as WATCH5 verification.

The first WATCH5-specific CI succeeded, but the delivery-only comparison in the
separate Balanced CI initially raised FileNotFoundError for its own sparse-
excluded YAML. It now reads both versions with git show. A regression executes
the real detector inside a sparse Git checkout and proves both delivery-only
skipping and required validation after a real configuration change.

After merge, the same new CI runs against main and attempts fixed November24
actual KRX/OpenDART collection with the unchanged21:00 policy and manual DRY_RUN
boundary. It does not receive Telegram secrets. A missing/incomplete day is
recorded as HOLD/error, never substituted with November23. Actual post-merge
run/Artifact/SHA and result are recorded in the final PR description and artifacts.

## Existing morning check and remaining observations

Only the existing task `6ae53e1be3848191b8bdc818036ed09c` prompt may be updated to
read `watch_delivery_result.json`, `watch5/manifest.json` and separate WATCH
reservations/message IDs, alongside formal TOP5. Its weekday08:45 schedule and
active state must remain unchanged. CASH permits separate WATCH reporting;
HOLD/ERROR does not. DRY_RUN is not SENT; partial sends remain partial.

Existing cron `0 23 * * 1-5` means KST Tuesday–Saturday08:00. The existing morning
check is Monday–Friday08:45, so Saturday has no08:45 check. No extra schedules or
alerts are added. Next scheduled run is November25 08:00 KST, expected target
November24; actual GitHub scheduling can be delayed. First actual scheduled WATCH
photo/message ID remains an operational observation. The earlier connection TEST
is not repeated. No new selection algorithm, API, backtest or order logic is added.


## Post-merge operating definition repair

PR #203 merged as `8487de1f93ce01403a6fc266bb9cce5fb1057ee1`. Its isolated WATCH
execution and295 regressions succeeded, but the actual operating workflow parser
rejected the newly added status function in a step environment. The observed
[run45398139084](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45398139084)
annotation was:

`(Line: 1013, Col: 38): Unrecognized function: 'success'. Located at position 1 within expression: success()`

No operating job started and no Telegram send or reservation occurred. The
minimal repair changes only the environment expression to
`job.status == 'success'`. The existing regression now also rejects status-check
functions in env mappings, where GitHub disallows them, while preserving the
normal `always()` step condition. This repair is submitted through a separate
normal PR, with no forced push/merge. The final closeout uses its successful
checks and repaired-main validation; the earlier invalid-definition run is not
reported as a successful operating execution.


The fixed-date November24 live check is restricted to the explicitly titled
initial #203 release merge, so future delivery edits do not repeatedly collect
that historical date. The first main check reached HOLD_DATA_INCOMPLETE at KRX
collection; it did not manufacture a November24 result or send Telegram. The
repair validates the unchanged engine with the verified artifact and does not
retry unavailable data automatically. On a new delivery-only PR, the existing
change detector falls back to the actual PR base SHA when event.before is absent;
financial/technical/config changes still require its normal validation.

## Final observed closeout result

**PRODUCTION_READY_WITH_LIMITATIONS — WATCH5 development complete.**

- PR203 merged as `8487de1f93ce01403a6fc266bb9cce5fb1057ee1`; the operating
  expression repair [PR204](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/204)
  merged as **`eec025c854a1b5e73351e441f93b4c444d11f7b5`** after all checks succeeded.
  Both were normal expected-head merges with no force/protection bypass.
- Validated repair head `efe3ecf006f8331a49a0d9d44f2ca9bd031fd8d6` and repaired
  main have identical tree `bd0520781e7f34d472c0212aac8c821b26248cea`.
- Repaired-main [run45399906769](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45399906769)
  is **push/SUCCESS**, 22:05:47–22:06:57 KST. **295 tests passed, zero failed**:
  original264 plus WATCH31. Repeated executions are not added to this count.
  Real November23 WATCH2 and separate synthetic TOP5five+WATCH5five both passed;
  transport was forbidden in actual-market replay and mocked in sender tests.
- [Final artifact14923570329](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45399906769/artifacts/14923570329)
  was downloaded/extracted and SHA-256 verified:
  `3322cdc9228133874ae5f1f1677de2da772536267ad6b16e780a194cec0b3417`.
  Its two actual November23 PNG hashes also match the files delivered to the user:
  010660=`426b223a48ddd068392b365aefd2699e493c1faa2b17c231571e1a9f7ad54c8a`,
  002790=`ce2d068c48bfa107be90e6f3d9cfce761de1b2514ecf9ad864fe1d61533b36c3`.
- Original main [run45398141438](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45398141438)
  actually queried November24 under the fixed-date/manual DRY_RUN boundary.
  The reference calendar chose24, next entry session25, expiry25 15:30 KST.
  **Both November24 KOSPI and KOSDAQ responses had OutBlock_1=[] (zero response
  rows); newest available day was23.** The raw response SHA-256 for each was
  `82c0031bc13af348ac1e1304aca28f309632975110f2508534e93216791dfa90`.
  Actual collection log: `TODAY_60_SESSION_SOURCE_INCOMPLETE`.
- Therefore November24 is **HOLD_DATA_INCOMPLETE**, not CASH and not a completed
  November24 financial/technical scan. November24 universe, PASS and TOP5 counts
  are **not calculated**, rather than zero eligible stocks. WATCH is BLOCKED,
  PNG0 and actual send0. No November23 price was substituted for24. OpenDART
  processing for24 was not reached. The program completed the safe HOLD with
  exit0; a successful verification job is not proof of complete market data.
- [November24 attempt artifact14922416874](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45398141438/artifacts/14922416874)
  was downloaded/extracted and SHA-256 verified:
  `59cdc7076ffdd67b790f509ca7f0a8e55a5aba432d30c6a2708589188be151a4`.
  This contains the actual request/response evidence, krx_collection.log,
  validation_result.json and blocked watch5_validation_proof.json. The repaired
  main does not automatically repeat this unavailable historical request.
- Actual Telegram messages in this closeout: **zero**. No new TOP5/WATCH
  reservations or normal stock receipts were created. The existing real
  connection TEST was not repeated. Partial/API/message-ID/chat matching tests
  use mocks; first scheduled real WATCH photo is still unobserved.
- Existing morning task was updated at **21:55:44 KST**. API confirmed exact
  prompt match and unchanged enabled=true, title and Monday–Friday08:45 schedule.
  It now reads independent WATCH results/reservations/message IDs and reports
  partial failures even if the GitHub job is green. No new alarm was created.
- Git comparison against pre-WATCH main14930b8 confirms **no changes** to any
  existing receipt, paper ledger, financial selector, financial engine, entry
  geometry or session policy. Cron/timeout/concurrency remain unchanged.

Changed files across the release/repair are c3_watch5_delivery.py,
c3_watch5_validation.py, test_c3_watch5_delivery.py, the daily/isolated/WATCH
validation workflow files, this report, and the synchronized morning prompt
source document. Final documentation-only commits do not alter validated code.

Next existing schedule: **2026-11-25 08:00 KST**, expected target24 if actual KRX
responses then contain it. Next existing read-only check: **08:45 KST**. GitHub
schedule creation can be delayed; neither event is marked successful in advance.
Saturday has a GitHub run but no Saturday08:45 check under the preserved task
schedule. Remaining limitations are actual data publication/availability and
first schedule/first genuine WATCH delivery observation, not additional algorithm
research. No paid API, new scheduled alarm, orders or performance study is added.
