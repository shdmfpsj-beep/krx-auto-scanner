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
