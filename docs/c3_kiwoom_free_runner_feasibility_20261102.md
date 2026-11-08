# C3 free-runner Kiwoom feasibility (2026-11-02)

## Verified external constraints
- Kiwoom REST API requires pre-registered IP addresses; registered IPs are limited (official Kiwoom documentation: https://openapi.kiwoom.com/intro/serviceInfo).
- Standard GitHub-hosted Actions runners use dynamic outbound IPs; GitHub explicitly advises against using their ranges as an allowlist (https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
- Existing Kiwoom credentials tied to the user's laptop IP are **not** KIS credentials. Never substitute one for the other.

## Decision and safety gate
- **DO NOT** enable Kiwoom API calls from standard GitHub-hosted Actions runners or auto-register ephemeral runner IPs.
- **DO NOT** attempt to bypass provider IP controls or request API keys in issue comments/chat.
- Keep existing KRX close-based paper-forward collection and TOP2 research checks separate from intraday claims.
- Intraday quote status remains `PENDING_PROVIDER_CREDENTIALS` / `NO_VERIFIED_QUOTE` until authenticated timestamped quotes are collected from an authorized endpoint.
- No broker orders; no fabricated prices; no paper fills without a forward timestamped observation.

## No-cost paths to evaluate
1. Continue the existing daily regular-market research source and end-of-day forward ledger (no broker credentials required). Validate source scope and dates before trading signals.
2. Investigate publicly permitted, timestamped, regular-session intraday quotes for only the two watched stocks, with explicit provenance, rate limits, and data licensing; never present unverified quotes as real-time.
3. If the user later authorizes a fixed-egress endpoint or supported broker API, add a separate read-only adapter and credential checks. Paid cloud or an always-on personal PC is not assumed.

## Current limitation
GitHub push-triggered probe can confirm pipeline health but does not provide real prices without an authorized data provider. Do not describe successful unit tests as successful live market monitoring.
