# C3 / K100 MASTER — Sector First (2026-10-22)

## 2026-10-25 ENTRY PRICE IMPLEMENTATION — v6.19 research-only override

- **목표는 '매수가 제시'와 '실매수 승인'을 분리**하는 것. 실전 매매 승인 수를 목표로 조건을 조작하거나 과거 일봉 저가 접촉을 증권사 체결로 주장하지 않는다. CASH도 유효한 결정이지만 항상 구조 조건부 연구 Top5 및 거절 사유를 별도 표시한다.
- **주문 가능한 호가 단위:** KOSPI·KOSDAQ 일반 보통주 기준 2천원 미만 1원, 2천~5천 미만 5원, 5천~2만 미만 10원, 2만~5만 미만 50원, 5만~20만 미만 100원, 20만~50만 미만 500원, 50만원 이상 1,000원. KRX [호가단위 공식 안내](https://regulation.krx.co.kr/contents/RGL/03/03020100/RGL03020100.jsp). ETF 등 다른 증권 종류와 과거 제도 차이는 일반 보통주 호가테이블로 처리하지 말 것.
- **타점 계산 순서:** (1) 정규장 09:00–15:30 마감일과 동일 세션의 >=65봉 가격 출처를 재검증 (2) 일봉 최근 확정 피벗을 통한 상승 가설 무효화 **구조손절 먼저** (3) 당일 종가에서 0.20 ATR 아래 1차 연구 지정가 (4) 미체결 때만 20일선 +0.35 ATR 또는 확인된 20일 신고가 재시험 고점 +0.15 ATR로 대체 연구 지정가(동시 물타기 금지) (5) 갭하락으로 지정가 아래 시초가 시작, 갭상승 추격, 일봉 손절선 충돌 시 주문 조건 자동 무효화 (6) 실제 1주 주문가능 현금과 보유 0/1종목, 매수가-손절가 위험폭, 원본 저항까지 **왕복비용 차감 2R**, 최종 개별 주식 >=80점 등 확인 전 모두 WATCH/CASH.
- **특수 확인 진입:** 종가 재시험을 보고 즉시 **같은 봉에서** 체결했다고 가정하면 미래정보 누수다. D+1 재시험·종가 회복이 전부 확인된 뒤 **D+2 시가**를 확인할 수 있는 구조만 실험하고, 그 사이 시초가 갭은 정해진 허용범위를 벗어나면 미매수. 장중 10분봉 저점으로 5거래일 스윙 일봉 구조손절을 교체하지 말 것.
- **사후 연구 v6.19:** 2026-10-23까지 15거래일의 v18(date-only, 정규장-only 여부 미인증) 자료와 360개 종목·일자 신호에서 4유형 **244개 매수가 연구시나리오**, 102번 일봉 가격접촉 상한, 왕복비용/슬리피지 가정 0.65%. 모든 유형의 5일 모의 평균수익률은 음수. 4개 유형별 연구결과는 채팅 세션 첨부 산출물 참조. 수익확률을 검증하거나 2R 라이브 게이트를 제거하는 근거 아님.
- **현재 별도 GitHub 유틸리티:** `scripts/practical_entry_quotes_v619.py`, `scripts/test_practical_entry_quotes_v619.py` 및 무료 CI `.github/workflows/practical_entry_v619_free.yml`는 22개 안전·회귀 테스트 통과 후 **main에 읽기 전용 라이브러리 및 CI로 배포**. 기존 실거래 주문·알람 실행코드 자동연결은 하지 않음. 10/23 완료일 후보 6개에서 선익시스템만 1차 **83,600원, 구조손절 74,900원**, 미체결 대체 **80,300원**을 가상 산출. 기존 확인 저항 87,800원 대비 비용차감 0.40R/1.18R로 **둘 다 WATCH/CASH**. 이는 10/26 실전 호가가 아님.
- **최종 알람 표시:** 상단 미국·세계 위험/국내 위험, 관찰 Top5, 각 후보별 1차 호가·대체 호가(물타기 아님)·일봉 구조손절·저항·비용후 R:R·원본 검증/현금/최종점수 상태, 명확한 BUY 또는 CASH. 신규 BUY가 없으면 정확한 병목과 5개 관찰후보를 별도 제시. 기존 08:35/13:00/16:00/18:30 알림의 일간 판단에 모두 이 표시방식을 참조하게 한다. 스캔·예약주문을 직접 실행하는 지시는 아니다.
- **기준 소급자료 제한:** 10/23 이후 새로운 국내 정규장 마감일/키움 계좌/PIT 기업공시/당시 최초 공개 미국 자료가 확보되기 전 과거 참고가격을 실제 실행 매수가로 승격하지 않는다. `trade_approved=False`, `orders_enabled=False`를 준수한다.


## 2026-10-25 ACTIVE RESEARCH CONTEXT — US & GLOBAL MACRO (v6.18, no order authority)

- **순서:** 08:35 장전 → 13:00 장중 → 16:00 정규장 종료 잠정 → 18:30 최종 투자 보고마다 세계 매크로·미국증시를 선행 확인하되, C3/K100 기존 정규장-only·계좌·일봉 구조손절·최종 종목 >=80/100·비용 반영 2R 게이트를 대체하지 않는다. 08:35에서는 뉴욕시간 16:00 마감 이후 한국시간 08:35까지 실제 끝난 미국 시장일만 사용(DST 반영). 13시/16시/18:30에는 새 미국 마감이 없으면 동일한 전일 미국 장을 재사용하고 갱신 시각을 표시.
- **실측 미국 시장:** SPY(미국 광역), SMH·SOXX(반도체), XLK(기술), XLE(에너지), XLI(산업), XLU(유틸리티), EWT·EWJ·FXI(미국상장 해외시장 대용) ETF. 가격은 Yahoo Finance/yfinance 2차 제공처로 수집. SPY나 해외 ETF와 해당 한국 상장회사 매출이 바로 연결된다고 가정 금지. 미국 지수 및 업종 ETF의 1일/5일 변화와 20일선·강약은 **연구용 배경**.
- **무료 세계 매크로:** FRED SP500/NASDAQCOM(지수), VIXCLS(위험), DGS10/DGS2(미국 금리), DEXKOUS·DTWEXBGS(환율/달러), DCOILWTICO(유가), BAMLH0A0HYM2(신용 스프레드). 반드시 각각 **관측일/수집상태/출처/발표지연**을 붙인다. FRED 과거 수정자료는 발표 당시 PIT 가격 증명이 아니며, 마지막 관측일이 미국 최종 마감보다 오래된 시계열을 동일 날짜라고 꾸미지 않는다. 관측 누락은 `MISSING_OR_STALE`, **0% 변화 또는 긍정 점수 추정 금지**.
- **연구 위험등급:** `GLOBAL_RISK_OFF_RESEARCH_ONLY`(미국 광역 급락 또는 다중 위험), `GLOBAL_CAUTION_RESEARCH_ONLY`(광역·반도체 약세/매크로 변동성), `GLOBAL_MIXED_RESEARCH_ONLY`, `GLOBAL_SUPPORTIVE_RESEARCH_ONLY`, `GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY`. 국내 RED라면 우선 CASH. 해외 위험이 낮더라도 **미국 지표만으로 종목 BUY 불가**; 기업 직접 관련성·KRX 해당 날짜 정규장 가격/수급·타점·현금 재확인. 에너지 강세는 에너지 기업만의 가능성이므로 시장 전체 상승으로 일반화 금지.
- **결과 화면:** `시장 조합(미국/세계→국내)` 첫 줄, 대표 5개 지표의 최근 실제 날짜·등락, 국내 섹터 Top3/종목 Top5/구조손절·1차/2차 대체 매수가, BUY/CASH, Required Next Data. 시장 RED에서도 Top5 관찰은 계속하되 실거래 승인을 억지로 생성하지 않는다. 외국인/기관 수급은 현재 MASTER의 OPTIONAL override 유지.
- **실제 배포 상태:** 무료 읽기 전용 `.github/workflows/global_macro_risk_v618_free.yml`는 main에서 08:25 및 15:45 KST에 원본 관측 시도. GitHub cron 시작은 정확한 08:35 도착을 보장하지 않는다. 해당 날의 `v618_global_macro_status.json` 또는 `v618_global_macro_mobile.md` 가 있으면 원본 날짜/신뢰성 확인 후 참조하며, 없으면 뉴스·지수 출처를 별도로 검증해 표시한다. `trade_approved=False`, `orders_enabled=False`; 실전 매수 자동 실행 기능 아님. v6.15~v6.17 실험 브랜치 코드는 별도 검증 중이며 본 문구로 실전 BUY에 적용한 것이 아님.
- **검증 실행:** [v6.18 24개 안전성 테스트/글로벌 데이터 수집 성공](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40177651213), [해외 주의+국내 RED 연구 조합 증명](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40178102665). 구체적인 미실현 실전 수익률·종목 상승확률을 주장하지 않는다.


## 2026-10-25 v6.24 PUBLIC CHART HYPOTHESES — NO BUY AUTHORIZATION

- 지난 2025-12~2026-10-23의 기존 KRX date-only OHLCV 제한 소급 연구에서 **HMA16 첫 눌림, 다바스 확정 박스 돌파/재시험, WaveTrend 공개형 재상승 교차**를 TradingView 공개 지표 설명에 따라 독립 연구. 원본 유튜브 채널별 비공개 설정을 재현했다고 주장하지 않는다.
- `research/v615-usable-entry-frontier-20261025`의 `docs/C3_V624_HMA_DARVAS_WAVETREND_PROFIT_AUDIT_20261025.md`에 8개 조건 ×2 진입 ×4 청산 ×2 기간 = 128개 사후 비교 기록. 로컬 9개 테스트 성공, 신규 GitHub Actions CI v6.24는 별도로 인증하지 않음.
- HMA+Darvas 연구 NEXT_OPEN/구조손절/7% 추적: 앞선 10건 평균 +0.140%, 최근 6건 +0.420%, 합계 +0.245%지만 최고 1건 제외 -0.436%, 총비용 +0.30%p 스트레스 평균 -0.055%. WaveTrend: 앞선 6건 +5.725%, 최근 4건 +0.353%, 최근 중앙값 -1.608%. **포트폴리오 수익 검증 아님**.
- **두 기간 각각 n>=8, 두 기간 모두 평균 >0인 진입·청산 조합 0개**. 이미 재사용한 7~10월 구간은 진짜 이후 홀드아웃이 아님. 표본수가 적고 128개 비교 선택편향 우려; 실전 매수 지시와 신규 자동매수 금지.
- 향후 08:35/13:00/16:00/18:30 보고 시 위 세 기법은 검증 점수에 임의 가점 없이 **WATCH 연구 태그**만 부여 가능. 최종 국내 regular-only 09:00–15:30 인증된 당일·과거 시세, 시장·업종, 회사 실적·공시 발표시각, 보통주/비제약바이오 제외, C3 현금·1주 가능·단일 포지션, 독립 최종주식점수 >=80, **일봉 확인된 구조손절 먼저**와 검증 저항까지 비용차감 >=2R 모두 확인되기 전에는 CASH.
- 10/26 이후 아직 한 번도 연구에 사용하지 않은 일봉을 **순차적 전진 실험**하고 주문 취소/가격 접촉/이익/손절/거래비용/현금 대비 성과를 기록. 매수 성과 향상을 이유로 미래 시가에 따라 종목을 소급 교체하지 않음. 누적표본이 너무 적으면 확률 수치나 안정 수익성을 주장하지 않는다.
 

## 2026-10-25 v6.25 SPECIAL-DIVIDEND FIREWALL & NEW CHALLENGERS

- **기업행사 가격자료 감사를 수익모델 평가 전에 추가.** `417310 코람코더원리츠` 2026-08-26 신호 이후 08-27 연구상 시가 10,970원→08-28 배당락 시가 2,290원은 특별배당 약 8,900원 및 예정 청산분배 관련. 과거 OHLC 전용 모의손절 -79.775%는 실제 권리취득자의 투자 총수익률로 보고할 수 없음. 공시·시장 보고서: [DART 2026-08-26](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260826800685), [뉴스핌 2026-08-26](https://web3.newspim.com/news/view/20260826000967). 확정 배당 현금·세금·지급시점·권리 및 종목 분류 미검증이면 손익 `UNSCORABLE_CORPORATE_ACTION`으로 표기할 것. 당일 사전 공시 시각 미확인인 이벤트를 당시 알고 있던 것으로 소급하지 말 것.
- 읽기 전용 `scripts/corporate_action_guard_v625.py`와 `scripts/test_corporate_action_guard_v625.py`, `.github/workflows/corporate_action_guard_v625_free.yml`을 main에 추가. D 15:30과 D+1 08:35 PIT 시각 별도 체크; 불완전 공시목록은 GREEN 아니며, 기업행사 확인되면 신호 당일 후보선정 뒤 다음날 진입만 취소. 차순위 후보를 D+1 갭·발표를 보고 **사후로 선택하는 것은 금지**. **실제 스캐너/브로커 주문과 연결된 것 아님.**
- 새로운 공개 지표 영감 연구 v6.25: VCP 수축 돌파, 가격변동 스퀴즈 확장, NR7 돌파, 상대강도 가속, 작은 구조위험 HMA 눌림+시장 양호의 5개 challenger vs WaveTrend/HMA+Darvas/단기상대강도 기준선 3개. 과거 21,036관찰/1,369코드에서 667 기술패턴 신호, 8x2x2x2=64개 모의 비교. n>=20/각 기간, 평균·중앙값·최고1건 제외·비용+0.3%p에 모두 플러스이며 최대손실 >=-12%라는 최소 연구 조건을 통과한 **신규 모델 0개**. 세부 문서: 연구 Draft PR#25의 `docs/C3_V625_PROFIT_CHALLENGERS_CORPORATE_ACTION_20261025.md`. 이 결과는 새로운 독립 검증구간이 아닌 **반복 열람한 기간의 소급 실험**으로 실전 승인 근거 아님.
- **C3 지속적인 모델연구 알림 별도 활성화**: 평일 저녁 글로벌 매크로, 국내 정규장, 기업행사, 정규장 동질 65일+ 자료, 강한 섹터·실적, 실전호가/매수후 5일, 중앙값·수익률·절대손실·수수료 스트레스 및 CASH/RESEARCH/BUY 단계구분을 정기 평가. 새 모델을 추가하더라도 검증 손절+실제 저항 2R+최종 종목점수 >=80+증권사 잔고+1종목 원칙과 독립 새 기간 검증 유지.
- 현재 v6.25 실전 승인 **0건**. K100 보유/운영과 주식주문은 미변경.


## 2026-10-25 v6.26 PROFIT CAPTURE RESEARCH — NO BUY SIGNAL

- v6.25까지의 종목선정 조건은 고정하고 7%/5% 추적손절, 1.5R/2R, 10%/15% 전량익절, 10% 절반익절 후 7% 추적을 같은 시점/같은 종목으로 비교하는 **v6.26 읽기전용 후속연구**. `research/v615-usable-entry-frontier-20261025/docs/C3_V626_EXIT_CAPTURE_EVENT_CAUSALITY_20261025.md`에 재현 한계 및 결과 기록.
- 804개 v6.25 종목-패턴 신호, 409개 고유 코드에서 8선정 ×2진입 ×7청산 ×2기간 = 224 소급 비교. 이전 검토 자료 재사용이므로 독립 재현 우위 아님. HMA+다바스 동일진입 16건 10% 전량익절은 기존 7% 추적 대비 +1.232%p 평균 개선이지만 16건 중 5건만 다른 결과, 단순 부트스트랩 95% [-0.438,+3.159]%p로 영점 포함. 최고손실 및 수익 지속성 개선 근거 부족. 두 기간 각각 충분한 표본/중앙값/거래비용/최대손실 적격 **0개**.
- 원본 v6.25 기업행사 메모는 2026-08-26 공시만 최초 경고로 보아서는 안 됨. **코람코더원리츠 417310 배당락 2026-08-28은 2026-08-19 16:11:48의 DART 공시 미러(20260819800342)에서도 사전 확인 가능**: [공시 미러](https://awakeplus.co.kr/data/view/20260819800342). 판단은 단일 D 종가 뒤 **D+1 08:35**에 공시가 이미 있었는지로 한다. 실제 공시목록 전체가 확보됐다는 뜻은 아니므로 `UNKNOWN_EVENT_COVERAGE` 임의 해제 불가.
- 진입 결정 뒤의 급락을 보고 동일일 더 좋은 종목으로 소급 바꾸지 않는다. 비정상 가격 점프 후 총수익/배당권 등이 미검증이면 그 관찰을 **수익 산정 불가**로 표시하고 원본 손익·미체결 건수도 함께 남긴다.
- 10/26 이후만 이후 검증 신호이며 KRX regular 09:00–15:30 가격과 당시 종목종류/비제약바이오, 확정 피벗 구조손절, 유효 저항 비용차감 >=2R, C3 실제 키움 현금/단일 포지션, 최종 >=80 주식점수와 차트 이외 기업촉매의 모든 BUY 게이트는 그대로. 08:35/13:00/16:00/18:30 리포트에 v6.26은 '청산 연구 태그'로만 표시 가능, BUY 권한이나 자동주문 생성 금지.
- v6.26 전체 CSV/코드 12개 로컬 검증 통과는 첨부 연구 ZIP에 별도 보관; GitHub CI에서 전체 백테스트가 성공했다고 주장하지 않음.


## 2026-10-23 ACTIVE OVERRIDE — foreign/institution net buying is OPTIONAL

- **Do not require investor-category foreign or institutional net buying to screen sectors, rank stocks or consider a conditional BUY.** No net-flow data is a neutral `NOT_PROVIDED` source field, not a quality failure, a zero net buy, proof of retail inflow, or an automatic CASH reason.
- The **non-flow sector research rubric (100 points)** uses verified *regular-session* trading-activity/turnover acceleration (30), corroborated fresh catalysts/news/disclosures (20), earnings/order outlook supported by actual disclosures (20), constituent breadth and relative strength (20), and macro/global supply-chain context (10). A foreign/institutional flow value, if independently verified, can be displayed as a supplemental confirmation/warning **without automatically adding points**. This alternative weighting is a proposed research framework, not a validated profit predictor.
- For a final stock BUY continue to require a separate verified >=80/100 assessment (not the sector research score), true homogeneous regular-only daily bars >=65, stop determined before entry, fees/slippage-adjusted reward:risk >=2, valid market/position/cash and strong dated catalyst/earnings evidence. No artificial score inflation from missing flow. Do not equate turnover with foreign/institution purchases.
- Regular-only source price quality and sector coverage remain mandatory. The current PyKRX daily source is unscoped and the optional KIS sample is not market-wide; these independently still imply `PENDING_DATA_VALIDATION` and **CASH** until resolved. The missing-flow field alone no longer contributes to a hard-block reason.
- The 08:35, 13:00, 16:00 and 18:30 mobile reports must mark foreign/institution `OPTIONAL / NOT_PROVIDED`, not a `PRICE_SOURCE_UNVERIFIED` cause. The legacy statements below that investor-category net buying is universally required are superseded.

## 2026-10-23 ACTIVE OVERRIDE — REGULAR ONLY (supersedes full-day instructions below)

- Production C3/K100 strategy uses **KRX regular 09:00–15:30 only**. KRX after-market 16:00–20:00, and off-hours closing-price trades 15:40–16:00, must stay in a separate diagnostic layer; never merge later OHLC, turnover, prices or money-flow with the regular strategy.
- User alerts KST are 08:35 premarket, 13:00 intraday, 16:00 regular-close preview, and **18:30 REGULAR-ONLY final** (replaces 22:15). Github regular-only 18:00 report precedes it. Old automatic 22:00 Sector First and 22:05 research bridge are now **manual-only** all-session historical diagnostics.
- Strict early capture is scheduled at **15:35 KST**, before off-hours trading starts 15:40. Actual API execution start AND completion must fall in 15:33–15:39. Scheduler/API late => CAPTURE_WINDOW_NOT_VERIFIED / CASH. No retroactive dating.
- PyKRX get_market_ohlcv(date, market) is a date-only source without explicit regular-session attestation; capture time alone does not prove regular-only OHLC, turnover or investor flows. Never invent such attestation. Require verified session-scoped minute candles or independently documented, session-certified source before BUY can be considered.
- Separate archives: krx-regular-observation at 15:35, krx-aftermarket-observation at 20:25 (diagnosis only), krx-regular-only-18h-final at 18:00. The final report must never download the after-market archive.
- A BUY setup requires >=65 correctly scoped historical regular-session bars, verified regular-session foreign/institution investor flow and constituent turnover, daily structure stop before entries, cost-adjusted R:R>=2, verified final score >=80/100, cash and one-slot C3 checks. Data unavailable -> PENDING_DATA_VALIDATION and CASH, not confirmed 0 candidate universe.
- Legacy v18 20:15 source is an **all-session diagnostic**, not regular-only production evidence. Workflow CI success is not proof of valid quotes, actual returns, or BUY approval. Orders disabled.

### New read-only official minute data bridge (2026-10-23)

- **Official KIS [domestic-stock-213] KRX J (not NX/NXT or UN) minute source** is now optionally auditable using `scripts/kis_regular_minute_cli.py`, scheduled on weekdays 17:15 KST. It is NOT the default price source unless credentials are already configured as GitHub Secrets `KIS_APP_KEY`, `KIS_APP_SECRET`. No credentials means an explicit PENDING_PROVIDER_CONNECTION status and zero fabricated prices.
- KIS time-stamped rows are filtered to 09:00–15:30 and rebuilt into OHLC+volume only when opening and 15:30 auction, minimum minute coverage, date/market and original fields all pass. After-market minute records are discarded. Audits are currently restricted to three named sample tickers (at most five per run) to avoid pretending that 2,600 stocks have been processed.
- The 18:00 KRX regular-only final report optionally reads `kis-krx-regular-minute-audit` as a **separate observed price-subset diagnostic**, never as investor institutional/foreign net flow proof and never as 80-point trade clearance. It rejects mismatching dates and cannot use NXT/UN quotes.
- Once minute-price provider access and independent official regular investor net-flow proof are available, expand cohort and 65-day history before making sector TOP3 and stock TOP5. The presence of a token, successful CI, or a reconstructed price subset is not a BUY signal.

## One outcome
**Every completed Korean trading day, identify the three sectors with the strongest verifiable convergence of fresh positive catalysts, trading activity, and investor money flow; select quality stocks only from these sectors; propose a technically justified structural stop first and then realistic 1st/2nd entry prices. If evidence or entry quality is insufficient, recommend CASH.**

No new paid server, Kiwoom token requirement or trading order API in the baseline workflow. Keep free GitHub + freely accessible public data. Do not promise verified live market data when unavailable.

## Required execution order (never invert)
1. **Sector TOP3 FIRST** — compare all eligible KRX sectors using dated catalysts, verified turnover/volume and breadth, verified net buying / money flow when accessible. Keep the already established sector scoring rubric consistent across the 08:35, 13:00, 16:00 and night reports: verified money inflow / turnover / investor net buying 30, news / disclosures / concrete fresh catalysts 20, forward earnings / orders / industry growth 20, breadth across constituent stocks 20, US macro / global linkage 10. Do not silently redistribute missing-item scores. Record scores, as-of, URLs/sources and unavailable items. Missing net flows must not be fabricated from rising price or inferred turnover. If source coverage is weak, label TOP3 *provisional*, avoid recommending a buy.
2. **Inside those three sectors only** — expand to around 20 quality candidates overall based on ordinary-share eligibility, earnings/growth/financial soundness, verified catalyst, flow, and rising trend. Exclude pharma/biotech per user's current instruction. Unknown financials or instrument type must be marked unverified. Do not treat temporary price rankings as proof of business quality.
3. **Select TOP5 max, not forced** — prioritize 1–5 trading-day setups: leader continuation, first controlled pullback after transition, reclaim, pre-ignition / 2nd-line transmission. Independent score >=80/100 only when its underlying components (sector+flow, fundamental+catalyst, trend, setup) are verified; **the existing technical preliminary score is not this final 100-point score.** If fewer than five qualify, return fewer or none. Do not invent a numerical five-day return probability.
4. **Stop BEFORE buys** — establish actual completed DAILY-bar confirmed structural pivot/retest invalidation (not 10-minute low), ensure positive rational stop and feasible risk. Then show 1st and 2nd entry price ranges based on support/reclaim, no-chase cap, realistic resistance-based target and forward R:R. Never use fixed arbitrary 1% or automatic averaging. Absence of verified level => unpriced watch / CASH.
5. **Trade gate** — CASH at top if market weak, total verified stock score <80, price extended, R:R poor, cash/position unknown, or any critical evidence missing. No simultaneous C3 second position. Do not invent available cash or orderable shares. Existing K100 Core positions are managed separately from new entries.

## World-first leading-news intake (free GitHub Actions)
- **08:05 KST weekdays**: `.github/workflows/global_sector_morning.yml` collects GDELT foreign industry/macro *search samples* and writes `global_preopen_brief_mobile.md`. Label independent-headline early-watch sectors as foreign **research only**. Count different source domains AND distinct headline signatures, discounting exact syndicated duplicates.
- **08:35 KST alarm**: read that morning artifact; explain overseas event → likely industry exposure → possible Korean beneficiaries/losers → **KRX verification still required**. Use dated original articles and company disclosures where independently verifiable; do not conflate GDELT seen timestamp with original publication.
- **20:15 KST weekdays**: Sector Evidence v18 starts its scheduled post-20:00 KRX after-market read-only collection. Same-day full-session evidence is not eligible as completed until **20:10 KST**, and it must then pass independent source-date, constituent-flow and OHLC integrity checks. Collection is not guaranteed to finish before 22:00.
- **22:00 KST weekdays**: sector-first mobile job makes a first verified-source attempt. If v18 collection is still running or the price source fails, produce CASH with PENDING_DATA_VALIDATION, never a false 0 qualifying sectors. Once the v18 standalone collection succeeds **after** 22:00, a GitHub workflow_run triggers a new Sector First attempt; this is not automatic brokerage execution or a guarantee of fresh data. The 22:15 alarm reports only evidence actually available at its runtime.
- Global `early_watch` is NOT the confirmed sector TOP3 and must not automatically raise sector points or authorize an order. No evidence of Korean net buying, real fundamental uplift, dated catalyst substance and completed-daily support => CASH.
- GitHub cron scheduling can be delayed, and public news/market APIs may fail or rate-limit; reports must state the actual capture timestamp and missing/partial status.

## Daily in-chat report, priority order
- **One-line decision:** BUY candidate / WAIT / CASH, with grounded reason, market data as-of and completion time.
- **Sector TOP3 table:** rank, sector, verified catalyst (date), turnover/volume acceleration, breadth, foreign/institutional flows when verified, source confidence, score.
- **TOP5 execution table:** sector, stock, why it stands out, verified score, latest close/as-of, DAILY structural stop, first/second buy range, no-chase cap, target, reward/risk, action. No price if unverified.
- **C3/K100 state:** C3 one-position focus; K100 current four Core positions tracked separately; latest available holdings/cash must be reconfirmed when stale.
- **Required Next Data:** only the few missing inputs genuinely blocking today's verdict.

## Timing and trust
- 08:35 KST: US macro/overnight *preview*; no invented Korea close, no blind buy.
- **16:00 KST**: the 15:30 *regular-session* close may be analyzed separately and labeled REGULAR_SESSION_CLOSE_PRELIMINARY; this is **not** the completed full KRX extended-session price/flow tape. The KRX after-market is open until 20:00. Keep OHLC data's session basis explicit; regular close and last after-market trade are not interchangeable.
- **20:10 KST onwards**: a same-day *full-session* source is eligible for validation. Full-session as-of defaults in `scripts/krx_session_clock.py`, `scripts/daily_asof_gate.py`, `scripts/sector_first_daily.py` and both v18 source collectors must agree; the weekday heuristic does not certify exchange holidays or actual provider completion.
- GitHub is not a trading terminal; all outputs research-only, user executes orders manually.
- Block approvals for stale, mismatched, thin-coverage, estimated-as-verified, survivorship-biased, or otherwise incomplete market/sector evidence.
- Backtests, ATR refinements, statistical studies and new indicators are supporting tasks, never replace the top-down sector-first deliverable.
- Free data source outages: record failure, publish CASH and diagnostics rather than recycle yesterday's TOP3 as if fresh.

## World-first news intelligence: active development contract (2026-10-22)
- Discover global news before relying on delayed Korean coverage: US, EU, China, Taiwan, Japan and other countries. Use source-country and language metadata, not a location inferred from English headlines. Important subjects include semiconductors, AI/data centers, transformer grids, shipbuilding/LNG, defense, battery supply, commodity prices, Fed policy and export controls.
- Free GDELT DOC 2.0 collector is configured for 16 non-biotech KRX-aligned sector queries plus four global macro queries. The global_sector_morning.yml gathers discovery before 08:35 KST on weekdays; sector_first_daily.yml gathers again after market close. Existing Korean Naver news and OpenDART remain complementary.
- Separate GLOBAL_EARLY_WATCH from domestic-verified TOP3. Show foreign press links, country and GDELT first-seen time. Independent foreign source mentions are research signals only; they are neither proven facts nor positive catalysts. GDELT seen time is not original publication time; no claim that an article preceded the Korean press without corroborated timestamps.
- Trace the causal chain: global event -> affected supply chain -> which listed Korean firms have demonstrable exposure -> dated catalysts/earnings revisions -> domestic capital flow and favorable entry. Include negative implications, regulation, sanctions, customer capex cuts and adverse FX/rate effects, not merely optimistic stories.
- Require article text and original company/government/filing corroboration before upgrading from headline discovery to a verified positive catalyst, and validate that news did not already get priced in before assigning final sector score. Headlines/volume alone never approve buy or fill any missing points of the sector 100-point rubric.
- If overseas collection is stale/rate-limited/missing, report source failure and keep CASH instead of inventing or recycling a global signal. Early watch can influence research priority but never override missing domestic price/flow or verified trade score.

## What the free v18 pipeline actually implements now
The daily *provisional research* TOP3 has been changed to a flow-first relative priority: constituent 5-day foreign+institution net buying 40%, as-of constituent reported turnover 30%, constituent advancing breadth 20%, and 5-day relative strength 10%. This research priority index is NOT the final 100-point sector score above, cannot establish turnover acceleration by itself, and does not include independently verified positive catalysts or forward earnings. The data covers dated ETF constituent proxies, not all stocks in the economic sector. Unknown constituent turnover or coverage blocks the provisional rank. The separate news/OpenDART index lists source links but never upgrades headlines to positive catalysts without validating substance. Every unverified trade gate remains CASH.

## 2026-10-22 reporting and account-state amendment (authoritative)
- C3: user explicitly reported **all shares of 세방전지(004490) sold**. Status is *CASH / no C3 position reported*; prior Sebang investment thesis is **retired**. Do not recycle the historical 4 shares @64,700 as active or anchor recommendations on the old view. Exit price, realized P&L, and broker-confirmed orderable cash remain unknown. See `config/c3_position_state.json`. New unrelated user fills supersede this snapshot.
- Sector discovery now includes verified **positive one-day money-flow sectors before 60% breadth** as research watch, with narrow breadth and 0% advancing labeled risky. This does not approve trades.
- **Data pending ≠ verified zero:** when KRX source dates, OHLC integrity, or constituent flow validation are missing/conflicting, `sector_selection_outcome=PENDING_DATA_VALIDATION` and `stock_selection_outcome=PENDING_DATA_VALIDATION`. Do not publish numbered "unselected" pseudo-ranks, "TOP3=0 confirmed", or "TOP5=0 good stocks" for an incomplete run.
- **Verified zero:** only a validated, sufficiently covered session with no qualifying positive sector net flow may use `VERIFIED_NO_QUALIFYING_SECTOR` and sector count 0. Missing final 80-point company/entry validation still implies **BUY approvals = 0**, not that research candidates do not exist.
- Keep workflow execution SUCCESS/FAILURE, market-data integrity, research selections, and trade authorization in distinct fields. Failed workflows never imply the exchange had no investable companies.
- All active mobile reports and reminders must apply this 80/100 *final verified score* minimum in addition to market, structural daily stop, 2R cost-adjusted and actual-account gates. Do not present relative research index as final score.

## 2026-10-23 KRX after-market source integrity amendment
- KRX's 16:00–20:00 after-market began 2026-09-14; an **18:20 market source snapshot was mid-session**, contrary to the earlier completion assumption. Previous OHLC violations cannot be conclusively attributed to session mixing without paired real-source verification.
- v18 standalone weekday cron is now **20:15 KST**, post-close cutoff **20:10 KST**; the explicit v18 backfill has the same full-session timestamp guard. Never silently normalize closes to fit highs/lows.
- A nominal 20:10 cutoff means only *eligible for validation*. OHLC inequality anomalies, request-vs-data quality, stale ETF-member files, non-matching as-of dates, unknown trading holiday or unverified investor flows all keep TOP3/TOP5 as PENDING_DATA_VALIDATION and BUY count 0.
- KRX regular-vs-after-market comparison is read-only and stores exact capture timestamps; samples outside the requested capture windows are not evidence of what happened at 15:30 or 20:00.
- Report workflow success, price/flow source validation, number of research candidates and actual BUY approvals separately. Do not imply a 22:15 alarm has the completed archive if GitHub's delayed 20:15 v18 job remains in progress.

## Implementation priority
P0. Validate and complete today's free sector evidence (membership + turnover + breadth + verified net flow + fresh catalysts).
P1. Join sector TOP3 to constituents and financial candidates; enforce ordinary stock / non-biotech filters.
P2. Apply completed daily-bar support/stop/retest geometry and 80-point verified final gate.
P3. Produce mobile-ready final report (and CSV/JSON with source timestamps), test against frozen historical as-of data.
P4. Add optional refinements only after the above end-to-end path works.

This document is the project-specific objective for subsequent C3/K100 development; it is not evidence that the above market-data integration is already complete.
