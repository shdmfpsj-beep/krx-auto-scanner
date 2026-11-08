# C3 TOP2 intraday feed: verified integration decision (2026-11-02)

## Hard constraints
- Existing Kiwoom account only; no new brokerage account.
- Free GitHub-hosted Actions; no always-on PC or paid cloud.
- KRX regular session only; exclude NXT and after-hours.
- No live orders. No paper fill without an authorized, fresh, timestamped quote.

## Official evidence
- Kiwoom REST API requires registered IP(s), up to 10: https://openapi.kiwoom.com/intro/serviceInfo
- Kiwoom official sample client: https://github.com/Kiwoom-Securities/Kiwoom-REST-API
- KRX Open API terms and API key: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp

## Engineering decision
1. Keep 30-minute GitHub Actions heartbeat and scheduled-run audit. These **do not** collect quotes.
2. Do **not** place Kiwoom app secrets in code or artifacts. Do **not** send authenticated calls from random GitHub-hosted runner IPs.
3. A fixed-egress, user-controlled host (or provider-confirmed stable allowlisted egress) is necessary for reliable Kiwoom integration. A free, unattended, static-IP solution has **not** been verified.
4. KRX official Open API is not established as an intraday stock-price feed. Do not mislabel daily OHLCV as intraday.
5. No scraping of unofficial price endpoints until automated-use permission and market/timestamp semantics are confirmed.
6. Research quote observation and paper-entry eligibility remain separate gates. A quote record's self-asserted permission flags are not independent evidence of a provider license; deployment must enforce a trusted provider allowlist.
7. Until a legitimate quote feed is connected, run close-based screening only and report `NO_VERIFIED_QUOTE` for TOP2 intraday watch.

## Next evidence needed
- Provider-confirmed quote feed entitlement and permitted automation use.
- Fixed outbound IP acceptable to Kiwoom without paid infrastructure, or a separate explicitly authorized provider.
- Verified quote timestamp, KRX-vs-NXT venue, freshness and holiday handling.
- End-to-end read-only test, then paper-forward validation. Never live order.
