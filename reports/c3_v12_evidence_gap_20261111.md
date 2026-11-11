# C3 v1.2 — independent primary-proof gap register
Research only. Parent: PR #90. No operational weights, entries, ledgers, 120d collector, Telegram, approvals or CASH changed.

## Frozen input provenance
- KRX: 150 market sessions, 395575 rows, 129 total selections, 51 new; original Actions run 42950252617, artifact 13824887176, sha256 60acbfc1ccaa65b9485fb05856eb89d531d37eb3a8ba8a7f31ed1037654f516f.
- Prior v1.1: 410 price discontinuities (73 adjacent market sessions, 337 ticker gaps); 7 DART title candidates for corporate action, 1 halt/delist title, 65 unmatched.
- DART title match is NOT ex-rights effective date/reference-price proof. Issuer par/share unchanged in retrospective query is NOT absence of action.
- Existing 51 new signals: first entry 51, second entry 1; D+1/2/3 overlap 2/3/6, not executions; actual certified fills 0.
- Frozen independent 5/10/20 session holdout: 17/40, 14/35, 6/20 positive. No new independent sample in this PR.

## Explicit missing primary evidence
1. Eight linked events require official KIND effective date, ex-rights reference price, raw/unadjusted versus adjusted quote basis, original notice and source hashes. Current status: BLOCKED, not 8 confirmed.
2. Remaining 65 adjacent events and 337 ticker-gap events have no certified event taxonomy. Current status: UNRESOLVED.
3. 15:30 regular-session OHLCV versus extended-session scope not certified from an independently timestamped source. Current status: BLOCKED.
4. 14 provisional financial date matches are not original numeric DART filing vintages. Strict numeric PIT: 0. Official dated KOSPI/KOSDAQ 21-close index: 0. Original flow vintage: not verified. Do not score.
5. New independent post-cutoff cohort and intraday/broker fill evidence: unavailable. No second-entry benefit, net PnL or price-band uplift certified.

## New safety property
scripts/c3_v12_primary_proof_gate.py rejects unsupported corporate-action, financial and execution claims. Even complete metadata only permits **manual source audit**, not automatic promotion. No trading decision authorized.
