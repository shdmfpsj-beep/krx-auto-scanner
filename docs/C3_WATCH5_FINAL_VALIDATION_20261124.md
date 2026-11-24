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
