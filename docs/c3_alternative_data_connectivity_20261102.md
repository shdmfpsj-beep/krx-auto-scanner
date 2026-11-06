# C3 no-cost intraday provider decision (2026-11-02)

## Verified official sources
- KIS developer introduction: https://apiportal.koreainvestment.com/about-open-api — personal account, OAuth 2.0 client credentials, REST/WebSocket, personal use of quote data.
- KIS API catalog: https://apiportal.koreainvestment.com/apiservice — domestic equity quote REST and real-time WebSocket. No statement here confirming that GitHub runner IP is allowed; live test required.
- GitHub hosted runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners — dynamic outbound IP; not a reliable Kiwoom registered IP.
- Tailscale GitHub Action: https://tailscale.com/docs/integrations/github/github-action — network connectivity, not a source of static egress by itself; requires exit node.

## Ranked paths for smartphone-only, no always-on PC, no paid cloud
1. KIS REST domestic stock quote adapter: **preferred conditional path**. User needs eligible KIS account, API registration, and GitHub Actions secrets. Test auth + 1 ticker read-only first. Confirm no fixed-IP rule with official support if unclear. No brokerage orders.
2. Another broker API: evaluate provider IP policy and quote terms; do not claim compatible without an authenticated test.
3. Public intraday data: validate source, licensing, timestamp, regular KRX session and staleness; not assumed real-time.
4. Kiwoom + fixed egress proxy: requires legitimate authorized fixed IP, which may cost money; not free by assumption.
5. Kiwoom self-hosted runner at registered network: requires an always-on device; conflicts with user's constraint.

## Implementation gates
- Keep daily close research running separately.
- For KIS: secrets only in GitHub repository secrets; never paste to chat. Read-only quote endpoints only, never order endpoints.
- Quote must include exchange/market session, source timestamp and fetch timestamp. Reject NXT/after-market, stale, or ambiguous timestamps.
- No auto-fill without a verified forward observation.
- Do not enable recurring 30-minute workflow before first authenticated successful KRX regular-session quote and API quota checks.
