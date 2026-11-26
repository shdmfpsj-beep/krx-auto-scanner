# C3 daily-operation schedule recovery, 2026-11-26

User authorization: immediately run November 25 through the existing live manual route, and replace the old 08:00 schedule with 07:17 primary / 07:47 missing-event check / 08:27 final missing-event check. The existing 08:45 read-only alarm remains unchanged.

## Evidence and immediate recovery

At 09:14 KST the daily workflow had no November 26 schedule/manual run and no November 25 TOP5/WATCH5/reference reservation. Main had advanced only through existing report-data updates; daily code and financial/technical policies matched the verified release. The last observed schedule was created November 25 at 14:18 KST, rather than 08:00. The missing event is upstream of selection code; scheduler backend/actor/account-limit cause cannot be established from available read access. Some administration/runner settings are unreadable (403), which is not evidence they are disabled.

PR #211 extends the existing bounded controller authorization through November 26 15:30 KST only, without changing live-delivery gates. Its verified main merge started actual daily run 45728023784 at 09:20:23 KST, explicit target 20261125, real collection/live approval. Schedule stabilization does not dispatch another operating run while this one is running or completed.

## Existing workflows, new timing

- Daily workflow: `17 22 * * 1-5` UTC = Tuesday–Saturday 07:17 KST.
- Existing incident/recovery workflow: `47 22 * * 1-5` and `27 23 * * 1-5` UTC = Tuesday–Saturday 07:47 / 08:27 KST.
- No new workflow or alarm is created. Existing daily non-cancelling concurrency and 35-minute processing timeout remain. Recovery checks are lightweight; they do not run regression tests or collect KRX/DART every morning.

## Admission and recovery

The existing reference calendar and 21:00 cutoff determine the target and original signal expiry. A small daily admission job runs before any market/financial collection. It checks current-main context, active workflow, prior running operations and all three existing send-reservation families (including confirmed-reference sidecars). All reads must be verifiable. Default branch/manual historical previews remain DRY_RUN and do not require a live reservation.

Known successful CASH+EMPTY completion prevents another full scan even though there is no Telegram reservation. For this case the guard verifies the earlier real artifact digest, original date, final execution outcome and three delivery channels. A previous preview with real candidates but no sends does not count as completed live delivery. Partial/uncertain sends, failed/HOLD/ERROR operations, invalid/missing message IDs, date/hash mismatch, unreadable receipts and incomplete history block automatic recovery. Unknown failures are never guessed to be transient.

A delayed primary that arrives after backup completion passes through the same admission gate and is skipped. Existing daily workflow concurrency serializes races; a newer queued run cannot cause the current admitted primary to skip itself. No automatic rerun of an unresolved failed operation is attempted.

Only an approved scheduled missing-event check may dispatch a missing day. Before POST it creates **only a new**, separate `receipts/c3_dispatch_daily/{asof}.json` marker without a `sha`. The marker is never edited/deleted. If creation or dispatch is uncertain, subsequent checks do not retry the POST. This control marker is not a TOP5 selection, trading-ledger entry, WATCH receipt or reference receipt.

Recovered manual delivery additionally verifies its `scheduled-recovery-{asof}-{parent_run_id}` correlation against an actual main schedule event from the existing recovery workflow and its matching dispatch marker. A typed correlation string alone cannot authorize a live send. Existing per-family Telegram create-only reservations, destination checks, exact image hashes, message IDs, no automatic resend and original signal validity remain mandatory.

## Validation and limits

Retain all 379 tests after urgent recovery and add 18 focused admission/recovery tests: missing primary, active/queued races, completed CASH/SENT, delayed-primary prevention, preview distinction, partial/unknown delivery, receipt integrity/permissions, archive hash failure, approved parent proof, create-only dispatch and uncertain-POST protection, expiry and default preview compatibility. All operating/CI workflows are checked by pinned actionlint 1.7.12. Algorithm, financial PASS criteria, 5% risk, rank, PNG design, ledger, existing receipts and 08:45 alarm remain unchanged.

GitHub documents that scheduled events can be delayed or dropped under load, especially at the start of an hour: https://docs.github.com/en/actions/how-tos/troubleshoot-workflows . Off-hour schedules and independent missing-event checks reduce exposure but cannot guarantee execution during a GitHub-wide scheduler outage. Manual recovery success is not schedule success. The first actual new primary/backup/final-check events remain operational observations.
