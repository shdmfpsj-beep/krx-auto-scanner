# C3 11/13 first morning preflight

At 12:05 KST on 11/12, main remained PR100 commit d051d5d1eb75f466d3fa06a3ebfffef6658e1f92, research state remained 99a5e872f4f07a279b46ece9589fdb3771e18e8d and the latest registered source was 11/11 run43086941571. No completed 11/12 daily source or new morning execution existed. No intraday price was used as a completed session.

## Minimal repairs

The approved reusable engine now seals the registered source date/run/decision hash/market hash after its normal registration, then returns the exact research commit only after publication succeeds. The caller checks out that commit and verifies the parent execution and source date before any candidate evaluation. The review verifies the same sealed decision and market hashes again. Previous-day state, failed registration, altered state commit, cross-run signal and source mismatch fail closed. Repeated same-session registration reuses the original source id. The approved engine SHA, A/B models, plans, stops, 120-session inputs and 8%/8%/1.5 experimental status remain unchanged. Official source preflight is explicitly limited to an eight-minute job.

The obsolete queued Telegram schedule run43097349217 uses pre-migration commit f25b10c5cd6052236a0c3bacba0c00396487af5c. A separate deployment job may cancel only that exact still-queued scheduled run, after tests pass; it never calls Telegram or changes a receipt. It does not cancel an active execution. Completion must be confirmed from GitHub, not inferred from a cancel request.

## Validation boundary

New-session tests use synthetic data explicitly labelled as fixtures. The actual source replay only decrypts and checks the already registered 11/11 original, matching source43086941571, decision SHA1990a9f2629d62b1c6c1ae35f78635305c577572b6d58652bd2cad4d5d9641fc and market SHA076d80581421a7f24e08da1bd607d4ecfec6b26d1d170daec0e0360d73c25b22. No new market or signal is registered and no Telegram credential is supplied. Already verified 2769/1988/149/50 evidence is reused after its ZIP digests match current GitHub artifacts; the full-market scan is not redundantly rerun.

A main deployment test probes existing KIS minute credentials and the existing Kiwoom daily adapter for one historical 11/11 sample. Missing credentials, rejection or incomplete minute coverage remain uncertified. Kiwoom adjusted daily bars cannot certify regular-only unadjusted whole-market OHLCV/amount. No new broker, paid API or order is used.

## Timing and remaining evidence

08:10/20/30 KST and ChatGPT08:45 remain unchanged. Previous approved engine run43086941571 used about74 seconds in its engine job and10 seconds for publication; the new company review has a540-second financial budget plus corporation-map time. These observations are not next-session service guarantees. Job queues, dependency installation, data retries and provider latency can exceed08:45. The report must show pending/failure/selection held, never replace the date with old candidates. The actual 11/12 source and 11/13 automatic registration/delivery can only be checked once they exist.

Official KRX evidence: https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC and https://data.krx.co.kr/contents/MDC/EASY/main/MDCEASY002.jsp. Official daily turnover/volume aggregate trading; the displayed regular-market subtotal also includes off-hours closing/block/basket trades. The official daily API and a matching cache are one origin, not independent regular-only certification. BUY remains blocked.

## Actual deployment follow-up

PR101 merged as main022eb5a7a42224799e8cfa97ec692ba6e9f9f041. Main run43148053564 passed its registered-source/31-test verification. KIS had no configured credential pair (ready_count0); the existing Kiwoom token endpoint rejected the read-only attempt with HTTP400 and an HTML response. Neither is certified. The queued legacy sender's ordinary cancel request returned HTTP409; that job failed and did not create a cancellation result file. Follow-up code preserves the failure evidence and allows only one documented force-cancel attempt on the same still-queued exact legacy run, then confirms actual status. It cannot claim cancellation from an HTTP request or keep retrying indefinitely. Repeated deployment checks do not repeat the provider authentication probes already recorded in artifact13912931566.
