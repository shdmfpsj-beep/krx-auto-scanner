# C3 TOP5 final production release — 2026-11-24

The user explicitly approved merging PR #202, activating Balanced, replacing only
the existing morning-check prompt, and one clearly labelled Telegram connection
test. No trading orders, paid infrastructure, backtests or additional schedules
are included.

## Verified before merge

- Main base: `ab1ca30bfe24f0e7cbc197e1db9468d6807f1f6a`; PR documentation head:
  `4fcfbfea2ef3e42ac009f46aed74d0eec77b56da`.
- Existing actual full-market code: `85ec123033c2249e81fc3a98a09677355e03d686`.
  [Successful actual run](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45351271747),
  [artifact 14900018369](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45351271747/artifacts/14900018369).
  These are **2026-11-23** observations, not November 24 results.
- The existing 258 tests plus six connection-test safety regressions passed locally:
  **264 passed, zero failures**. The new release CI repeats this exact regression
  set before permitting a connection test.
- The production daily workflow already defaults to `balanced`, including schedule
  events, and uses `EXECUTABLE_FINANCIAL_APPROVAL_V1`. Legacy remains available.
- The paper ledger, existing November 19 stock receipt, session policy and validated
  entry-geometry module have fixed SHA-256 preflight checks. No such file is edited
  by this release change. Main has no active branch-protection requirement or
  repository ruleset at preflight; merge still uses GitHub's normal merge API and
  an expected PR-head SHA.

## Minimal final operational addition

`c3_balanced_final_release.yml` has **no schedule**. Its main push job only runs for
the explicitly approved PR #202 release merge title. It runs all regressions and
the existing synthetic positive PNG/JSON/CSV/Telegram DRY_RUN proof before the
single real text-only connection test. PR executions never receive Telegram
credentials or send messages.

The connection helper creates
`release_checks/c3_telegram_connection_20261124.json` using create-only GitHub
Contents API semantics, before contacting Telegram. Existing stock receipts and
the daily signal reservation namespace are not used. Reruns, existing markers,
permission failures and uncertain network responses do not trigger another send.
The fixed text explicitly says **TEST — 실제 매수 신호 아님**. Its API evidence
contains only HTTP status, `ok`, message ID, timestamps and a destination-match
boolean; bot token and chat identifier are never logged.

Actual post-merge results are recorded by the workflow in
`telegram_connection_result.json`, `release_status.json`, the regression log and
the `c3-balanced-final-release` artifact. A green PR regression job is not proof
that the post-merge connection test has sent. The final PR description records the
observed merge/run/artifact and morning-prompt update after those actions finish.

## November 24 and recurring operations

At release preparation it is before 21:00 KST. The existing cutoff forbids selecting
November 24 as a completed operating day yet. No November 24 counts or stocks are
inferred from November 23. The existing next schedule is **2026-11-25 08:00 KST**,
expected target **2026-11-24**, subject to actual KRX response completeness and
normal OpenDART checks. This one-time connection test does not run that collection.

The existing daily cron `0 23 * * 1-5`, 35-minute timeout, concurrency, duplicate
reservations and scheduled-main-only stock send approval remain unchanged.
The existing 08:45 task keeps its enabled state and Monday–Friday schedule; only
the prompt from `C3_TOP5_MORNING_CHECK_PROMPT_20261124.md` is authorized for replacement.
Its read-only rules remain. Saturday's GitHub run has no Saturday 08:45 check under
the unchanged Monday–Friday task; altering days needs separate user approval.

First actual schedule, November 24 outcome and first eligible production stock
image delivery remain operational observations until their actual artifacts and
Telegram message IDs exist. A successful text connection test is not evidence
of a real stock image send or market eligibility.

## Final observed deployment outcome — 2026-11-24 KST

**PRODUCTION_READY_WITH_LIMITATIONS. Development is complete and the existing daily
workflow now uses Balanced as its scheduled default.** The first new
schedule and the November 24 market result have not happened at this checkpoint.

- [PR #202](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/202) merged normally
  with exact approved head `d478326f5ae2f7d484740a6bd6454dd81328cc5d`.
  Production merge commit: `680a0cb363099669bfaae62d5aef578d7017d703`.
  Its tree `298d718e05e17c6a8d7df6dbabebaed9c5bb9224` exactly matches the validated
  PR tree. No protection bypass or force update was used.
- [Post-merge main run 45368591531](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45368591531)
  completed **SUCCESS**, push event, 18:47:54–18:48:44 KST. All **264** tests passed.
  The independent existing Sector First safe CI also succeeded.
- [Final artifact 14907623471](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45368591531/artifacts/14907623471)
  was downloaded and verified, SHA-256
  `13ae7a8271064795d7e7399705a6dc00286f5a500ee886ea4190135974f3baab`.
  The separately labelled synthetic positive path has five final PNGs, five CSV
  rows, matching JSON/PNG metadata and hashes, and delivery **DRY_RUN**, not SENT.
- Telegram **one real TEST text**, HTTP **200**, `ok=true`, `message_id=48`,
  destination matches configured chat, sent **18:48:38.434 KST**. Actual stock
  signals sent: **zero**. `telegram_connection_result.json` preserves this response
  evidence without token/chat identifier. No normal stock receipt was created.
- The create-only test reservation produced main commit
  `c73d37a070efa8f2f1d3ecfc1159edbaeb550502`; comparison with the merge commit shows
  **only** `release_checks/c3_telegram_connection_20261124.json` added. No code,
  daily reservation, prior receipt or paper ledger changed. This state means a
  test attempt was reserved; the actual SENT result remains in the artifact.
- Existing morning task `6ae53e1be3848191b8bdc818036ed09c` was updated at **18:44:55
  KST** with the exact replacement prompt. API response confirmed enabled=true,
  identical title and identical Monday–Friday 08:45 schedule. No task was created.
- [Latest actual KRX/OpenDART PR run 45367684039](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45367684039)
  also completed SUCCESS: **November 23**, direct 128 responses / 165,932 rows,
  KOSPI 935 + KOSDAQ 1,836, valid60=2,488, interest9, finance9/9,
  PASS3 / rejected2 / review4 / error0, ENTRY_READY0 / NEAR_ENTRY0 / WATCH2 /
  TOP5 0 / **CASH_NO_ELIGIBLE**. Empty entry intersections3, risk>5%4, WATCH2;
  approval-required0, approval finance complete=true, nonblocking reviews4.
  Final buy PNG0, diagnostic PNG9, TOP5 CSV0 rows, delivery CASH, stock sends0.
- [Actual market artifact 14907717041](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45367684039/artifacts/14907717041)
  was downloaded and verified, SHA-256
  `3109d27fc85b4dfec9d828394946eba3f0c32ed3b1d020114f7d5acdcc358d3c`.

**November 24: pending, no market counts or selection inferred.** It is before
21:00 KST. Existing next schedule is **November 25 08:00 KST**, expected as-of
November 24, followed by the unchanged **08:45 read-only check**. Manual/PR/push
success is not actual schedule success. Older schedule records exist, including
November 20 success and November 21 failure, but they do not prove the new 08:00
schedule. GitHub creation delays remain possible; the morning check reports
waiting/in-progress from actual records and never resends automatically.

Remaining observations: first post-release schedule, actual November 24 outcome,
and the first genuinely eligible stock-image delivery/normal receipt. Saturday
has a GitHub scan but no Saturday morning-check task under the preserved weekday
schedule; adding Saturday requires separate approval. Formal historical PIT and
corporate-action/adjusted-price certification remain explicitly unverified;
existing price discontinuity exclusion and disclosure-time guards remain active.
No extra algorithm research or API development is required for this release.
