# C3 v6.54 — 개별주 상승지속 vs 실제 매수 가능가격 5일·12일 감사 (2026-10-26)

**연구 전용. 최신 연구원본 2026-10-23, 2026-10-26 신규 정규장 시세 및 실제 키움 체결 인증 없음. BUY=0 / CASH.** Work v6.38 A/B와 K100 유지, 실전 자동주문 비활성, 사용자가 직접 자금/비중/수량 관리. 종목선정과 주가 기준 지지·저항·구조손절에는 계좌자금 및 1% 계획위험 미사용.

## 실제 실행된 연구
- **이미 여러 번 재검토한** Work v6.51 과거 D 시점 **264개** 원신호에 v6.48 2670개 매수/청산 가격 프록시와 v6.46 D 당시 저항/구조손절 원장을 티커·D날짜·패턴으로 정확 결합. 5일 후속 결과 264건, 12일 후속 262건. 94개 신호일, 동시종목 및 보유기간 중복 -> 264개의 독립 매매가 아니며 계좌 복리수익도 아님.
- 미래사후 수집 ETF 멤버 분류(v6.53의 7228행 10/23 수집)는 **연구 종목선정 입력에서 완전히 제외**. 시점 인증 안 된 공식 정규장 전용 OHLC/PIT 보통주·비제약바이오·기업공시/체결 정보는 실전 BUY 승인 근거가 아님.
- 사전 상태로 계산 가능한 시장폭20(아카이브 종목의 MA20 위 비율)과 개별주 과거5일 수익, 과거20일 수익, 시장대비 RS5만 사용; 미래 청산결과를 선정 함수에 투입하지 않음. 그러나 50%·5일·20% 조건 자체는 이전 2026 역사 탐색을 보면서 선택되었으므로 진정한 새로운 동결 미래검증은 아님.
- 진입: v6.48 D+1 OPEN 모의 가격, 5/12일 stop-first 가격접촉·종가청산 프록시와 왕복 총비용 0.65% 가정. 브로커 매수 주문/저가 터치/목표 체결의 현실성을 인증하지 않음.

| 연구 D-gate | 5일 pass | 5일 조건부 평균 | 미선택=현금0 동일 기회 5일평균 | 12일 조건부 평균 |
|---|---:|---:|---:|---:|
| ALL |264|+0.6135%|+0.6135%|+1.230% (262관측)|
| market breadth20 >=50% |168|+1.6884%|+1.0744%|+1.919%|
| stock historical ret5>0 |223|+0.975%|+0.824%|+1.831%|
| **breadth>=50% AND stock ret5>0** |**145**|**+2.256%**|**+1.239%**|**+3.135%**|
| joint + past ret20<=20% |120|+1.853%|+0.842%|+2.899%|
| market relative stock rs5>0 |147|+1.406%|+0.783%|+2.148%|
| prior5 +5..+10% (historically overfit exploratory bin)|114|+2.314%|+0.999%|+3.302%|

**Risk to claims:** joint 5d all-opportunity improvement over ungated only **+0.6255pp**, **95% trading-date-cluster bootstrap [-0.100, +1.277]pp** from 2000 deterministic date resamples across correlated same-day signals; 12d improvement **+0.505pp**, interval **[-0.641,+1.542]pp**. Both include zero. Recent H2 Jul-Oct23 for joint only **n10**: 5day avg +0.208% but top2 removed -0.953%; 12day avg -0.718% and top2 removed -2.776%. A model cannot claim robust continuation edge on these old retrospective signals. Adding an intuitive past20d overheat penalty **reduces** all-opportunity 5day from +1.239 to +0.842; not every indicator adds alpha.

### Signal quality vs entry quality is CRUCIAL
Among all 264 completed D signals, **74** have a recorded prior-to-D overhead resistance and only **1** has net >=2R from original D close. Among the **145 joint-gate** apparent stronger continuation signals, **36** have recorded D overhead; **ZERO** demonstrate >2R at original D closing price after fees. The other 109 do NOT have a certified overhead target in this archive; absence is not proof there is no upside. Never recommend all 145 as BUY, never manufacture an invisible resistance or lower unfilled bid to force RR2. New entry must come from actual price support/retest, original structural stop and dated overhead, independently of money/lot size. Certified KRX-only current price and news/sector are missing.

### Local delivered runnable full audit
- Current conversation archive `C3_v654_종목상승지속_가격검증_전체연구자료.zip`, SHA256 **`2e6078861b23ff253e583be79636f830e5684523ed33fc5efd4a4a9cadb707c1`**. Full Python (`stock_continuation_audit_v654.py`, `run_v654.py`, `test_v654.py`), unmodified input snapshots with SHA256, 264-signal priced D with 5/12 outcome, 14-row statistical summary, 2 full gate and cash0 opportunity ledgers, optional historical non-BUY one-stock manual template, Korean report `C3_v654_개별주_상승지속_타점검증_연구보고서.md`.
- **32/32 local regression tests PASS**; clean separate ZIP extraction full rerun produced **6/6 result output files byte-for-byte SHA256 identical**. New GitHub docs written here, not equivalent to full GitHub CI/complete historical replay on GitHub. No new certified source data or live performance claim.

### Research prioritization
1. Keep v6.38 A/B historical baseline; optional market breadth + stock positive prior5 as **research challenger/caution**, never current hard BUY/0-1 score approval. Price quality mandatory independent check.
2. Latest date- and venue-certified KRX 09:00–15:30 daily bars, authentic as-of ETF PDF/company issuer membership and fresh dated catalyst; verify support→entry/structure stop→date-recorded overhead and scenario actions. Actual broker evidence for fill/nonfill; omit invented historical POC/VAH/VAL.
3. User-facing report must include observable market asof/close, A support, B realistic pullback, C conditional breakout, invalidating original structural stop, known 1st/2nd resistances, future upside thesis/rejection and separate existing-holder/new-buyer actions. Unknown target/stop remains UNKNOWN/WAIT.
4. New independent 2026-10-26+ completed official regular-only data **not yet used**. New genuine P&L verification 0. CASH/WAIT, no K100 or broker modification.

Momentum crash research for economic context: Daniel & Moskowitz (2016), https://doi.org/10.1016/j.jfineco.2015.12.002. Official source menu for further KRX verification https://data.krx.co.kr/ .
