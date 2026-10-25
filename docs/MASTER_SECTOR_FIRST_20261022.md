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


## 2026-10-25 v6.28 MARKED MONTHLY RISK AUDIT (RESEARCH ONLY)

- C3 월별 성과보고에서 **청산일 손익만 반영한 수치**와 **월말 아직 보유한 단일 가상 포지션의 시가평가손익을 포함한 수치**를 명확히 구분한다. 월말 가상 평가금액을 보유 주식의 해당 일자 완료 **정규장 종가(인증된 경우만)**와 현금에 합산하고 일별 평가잔고의 Peak-to-Trough 낙폭을 별도로 제시한다. 종목이 월을 넘겨 보유되면 청산월에 모든 손익을 몰아 적립하지 말 것.
- 2026-10-25 v6.28 소급 연구: 과거 날짜가 있는 069500 ETF로 **전월 마지막 완료 거래일**의 월간 변화율/20일선/60일선과 **신호일 D의 완료 종가** 시장규칙을 4 후보선정·5 청산조합 등 90개 사후 기간별 결과로 재분석. HMA+Darvas 10% 익절 총 모의복리 기존 +12.70%(16건)지만 전월 ETF 상승일 때만 거래하면 -7.69%(11건), 전월 ETF MA20 위 기준 -2.91%(13건). WaveTrend 7% 추적은 +39.69%(10건)에서 전월 양수만 보면 +18.93%(6건). **이 시장 단순 필터는 검증된 수익 개선이 아니므로 신규 BUY 요건으로 강제 추가하지 않는다**. 원본 v18 regular-only/PIT/총수익 인증 미확보.
- 종가 평가 일별 max drawdown은 HMA+Darvas 10% 연구 -13.72%(기존 청산 기준 -12.34%)이고 WaveTrend -7.09%(기존 -3.61%); 이는 과거 가상 월중 보유를 고려한 위험을 드러내지만 실제 키움 체결·계좌 손실과 구별할 것.
- 순차 운용 월별 보고는 **① 해당 월 청산 거래 건수와 비용후 실현손익, ② 월말 보유 수량/평가손익, ③ 현금 포함 월말 총평가액 변화율, ④ 일별 평가잔고 최대 낙폭**을 함께 표기한다. 만약 실제 잔고/정규장-only 현물 가격 미확인 시 ③④는 연구가정으로만 표현한다.
- v6.28 전체 코드/로컬 12개 검증/CSV는 해당 사용자 대화의 `C3_v628_profit_regime_research.zip`. 읽기 전용 순수 시장컨텍스트 CI는 연구 브랜치 `scripts/market_month_lag_guard_v628.py`, `scripts/test_market_month_lag_guard_v628.py`만이며 전체 90개 비교가 GitHub Actions에서 실행됐다고 주장하지 말 것. 2026-10-26 이후 새 완료 정규장 데이터를 고정된 가설의 독립 전진검증으로 누적할 것.
- 기존 규칙: 개별주식 최종 검증 점수 80점 이상, 공식 정규장 전용 65봉/원본 기업공시, 주도 섹터, 보통주 및 비제약바이오, 실제 키움 가용현금/최소 1주/단일 C3, 확정 일봉 구조손절 우선, 확인된 저항 비용차감 2R 이상, 악장 시 CASH, 주문 자동실행 비활성. K100 운용과 혼동 금지.


## 2026-10-26 v6.29 ENTRY-EXECUTION RESEARCH — PRICE CONTACT IS NOT FILL

- 2026-10-26 장전 시점(국내 미개장) 최신 연구 원본 2026-10-23까지의 **v6.25 804개 동결 신호** 사용. 연구판정은 10/26 장중 실거래/수익이 아님.
- HMA+Darvas 122, WaveTrend 33, 기존 RS5 537 등 692개 모형·종목 신호를 당일 완료 일봉 정보만으로 각 모델/날짜 1종목으로 고정해 213개의 관찰 기회(59/24/130)를 구성. 연구는 4개 진입: D+1 시초가, D+1 종가-0.2ATR, D+1~D+2 종가-0.65ATR, D+1 종가 지지반등 확인→D+2 시초가. 7% 추적손절/10% 익절 각각 비교, 총 1704 모형·기회 연구와 15개 로컬 안전 테스트; 실행 코드/CSV는 해당 대화의 `C3_v629_entry_and_profit_frontier.zip`. 상세문서 연구브랜치 `docs/C3_V629_PRACTICAL_ENTRIES_PROFIT_AUDIT_20261026.md`.
- 조건부 **실제 접촉된 주문만 비교하지 말 것**: WaveTrend 깊은 재시험은 시초가와 *모두 가격 접촉된* 8건에서 +2.977%p 가상 개선이나, 미접촉=현금 0까지 포함한 24개 D-기회에서는 **-0.428%p**. HMA+Darvas D+1/D+2 깊은 눌림은 고정 59개 기회당 +1.108%p vs D+1 시초가이지만 서로 중첩된 기회이며 1슬롯 포트폴리오의 앞선 구간 평균은 -0.122%, 최근 구간 +1.338%. 진짜 미래 검증 전 BUY가 아닌 WATCH 가설.
- D 종가 종목 우선순위는 D+1 시초가/저가를 보기 **전에 고정**, D+1 gap -2%~+2.5% 이외에서는 취소해도 같은 날 2위 종목으로 소급 교체 금지. 수동 호가 지정가 주문은 D+1 시가 확정 이후 실제 가능 여부를 확인하여 연구; 주문가격을 KRX 유효 호가단위로 내림 처리. D+1 저가가 지정가를 통과한 사실은 체결 증거 아님. D+1 확인봉은 D+2 이후에만 이용.
- 새 알람 보고에는 모델 명칭, D-시점 고정 후보, 1차 지정가·미체결 대체가격·확정 일봉 손절, 갭 취소 및 미체결, 정확한 본장 종료시각과 **가격 접촉 / 실제 브로커 체결**을 나누어 기록하라. 2026-10-26 이후 새 정규장만 진정한 이후 평가, 공시PIT/현금/저항2R/80점/65봉/비제약바이오/한종목 검증 없으면 CASH 유지.
- 앞서 반복 열람한 2026-01~10/23 모의수익과 95% 단순 날짜 bootstrap은 독립 미래 검증이 아니며 통계적 편향 가능. HMA 깊은 재시험 가설 외 다른 기법에 임의 점수 가점하거나 자동주문 활성화 금지. K100 변경 없음.


## 2026-10-26 v6.30 SMALL-C3 ACCOUNT PRACTICAL RETEST — RESEARCH ONLY

- 2026-10-26 장전 v6.30: 10/23까지 완료된 **v6.29 1,704건 연구자료/639건 고정 타점 비교**에만 기반하여, 269,230원(2026-10-13 사용자 과거 확인, **현재 미확인**) 또는 500,000원 가상자금, 계좌당 손실예산 1%/2%, 왕복수수료·슬리피지 가정 0.65%, 정수 최소 1주를 재평가. **손절을 종목가의 1%/2%로 고정한 것이 아니며, 모델의 일봉 구조손절을 먼저 선정**. 일봉 구조손절·갭 실제 실현은 인증된 게 아님.
- HMA+다바스 7% 추적손절 **269,230원/위험 1% 1종목 가상현금원장**: D+1 시초가 11회 진입 -0.966%(-2,601원), D+1 종가-0.20ATR 지정가 8회 -0.990%(-2,666원), D+1~D+2 종가-0.65ATR 깊은 눌림 8회 **+0.859%(+2,312원)**. 이는 저가 접촉을 100% 모의 체결 처리한 가격분석 성과이지 실제 키움 계좌손익이 아님. 500,000원/위험 2% 깊은 눌림 13회 +2.214%도 완전 가정값.
- 모의 저가접촉 주문의 조건부 실제 체결 확률은 **측정되지 않았음**. 임의 75%/50% 가상 미체결을 500회 반복하면 269,230원/위험 1% 깊은 눌림의 중앙값 계좌수익률 **+0.731%/+0.091%**이며 50% 가정 하위5%는 **-1.810%**. 모델 수익은 실행조건 변화에 취약하며 BUY 승인 점수 추가 금지.
- v6.29 59개 **고정 D-일 기회**의 평균 +1.108%p 깊은 눌림 우위는 8개월 중 7개월 양수이지만 HMA+다바스 조합과 깊은 지정가를 지난 반복 실험에서 선택했고 달/업종 자료가 독립 표본이 아니므로 어떠한 부트스트랩 양수도 실제 수익성이 검증되었다는 증거로 간주 금지.
- 신규 연구브랜치 `docs/C3_V630_CAPITAL_LIMIT_FILL_PROFIT_AUDIT_20261026.md`; 읽기전용 `scripts/capital_aware_retest_v630.py` + 10개 unit tests + 무료 연구CI. 상세 가상 원장/재현용 코드/부모 v6.29 체크섬 및 CSV/14개 로컬 테스트는 사용자 대화 파일 `C3_v630_cash_realism_research.zip`. **전체 48개 소액계좌 실험은 로컬 실행**이며 GitHub CI가 그것을 수행했다고 주장하지 않는다.
- 08:35/13:00/16:00/18:30 및 평일 연구 리포트는 **실제 키움 최신 가용현금·최소1주·계좌총액 중 선택한 위험예산·현재 1종목 상태**를 가격/손절 산정 이후 확인. 미충족이면 CASH; 체결되지 않은 주문은 0 수익의 현금 기회로 따로 기록. 실제 점수 >=80, 장중 본장 인증 65봉, D-정보로 확정 피벗 손절, 확인된 2R 저항, 정규장 수급·업종, 비제약바이오/기업행사 PIT 모두 없으면 BUY 금지. 이 연구를 근거로 새 자동주문 활성화/기존 K100 변경 금지.


## 2026-10-26 v6.31 GST WINNER ASOF PATTERN AND D+5→D+12 WATCH (NO LIVE BUY)

- 사용자 확인 **GST(083450) 실제 성공매매는 2026-09-22 5주@49,000원 매수 → 2026-10-13 5주@54,000원 매도**, 비용 전 수익 +25,000원/+10.204%. **9/30 매수**는 이전 채팅의 **보유확인 시점과 혼동한 날짜**라 신규 과거 매매원장에 사용 금지.
- 2026-09-21 GST 완료 정규장 후보 시점: 종가 48,300원 > 직전20일고점 47,800원, MA5 46,670>MA10 45,605>MA20 44,762.5 **단 MA20 < MA60 45,520**, RVOL20 1.051배(장중/다음날 거래량을 당일 종가 이전부터 알고 있던 것으로 소급하면 안 됨). GST 거래는 5거래일 전량익절보다 긴 12거래일 추세보유 사례이며 기존 v6.25 후보신호에서 실제 진입 전일을 놓쳤음.
- 새 **GST-TRANSITION-WATCH**는 HMA+다바스, WaveTrend와 병렬로만 연구: 20일 고점 돌파, MA5>MA10>MA20, MA20<MA60인 중기 추세 전환 전 구간, 최소 당일 거래대금 30억원, RVOL>=0.75, 5일 상승률 3~17%, ATR14/가격<=12%, 완료봉 강도 >=0.65, D 고정 후보와 **일봉 구조손절 선결정**, 가상 손절 위험<=8%. 그날 계산 가능한 자료로만 선별하고 실제 D+1 시초가가 전일종가 -2%~+2.5% 범위가 아니면 추격/갭 위험을 다시 판정하며 2위 종목으로 소급 대체 금지.
- **D+5까지 보유한 뒤 종가수익+3% 이상·손절 이탈 없음일 때만 D+12까지 연장**과 '5일 무조건 청산'을 병렬 검증. 7% 이전 완료봉 고점 추적손절, +10% 익절 및 비연장(CASH) 비교는 연구 가설이지 사용자 실제 GST 매도 원인 또는 실전 기본 타점 아님. 실제 검증 뒤에만 적용, 정규장-only, PIT 및 주문실행 우위 없음.
- v6.31 **로컬 전체 2,870 가격코드/1,613 모형별 사건** 재검토: 완화형 MA20≈MA60 12일 고정청산 상반기 315건 +3.089%, 최근 72건 **-4.404%**; 사후 선택한 MA20<MA60 & 구조위험<=8% 상반기 82건 +3.793%, 최근 26건 +0.132%이고 최고1건 제거하면 -1.078%. 5일차 +3% 강세인 경우에만 12일까지 추적 연장한 최근 26건 모의평균 +0.248%도 최고1건 제거하면 -0.279%; **여러 차례 같은 데이터로 연구한 사후조건이라 수익모델로 검증된 것이 아님.**
- 연구 ZIP/모바일 보고서는 사용자 대화의 `C3_v631_GST_entry_research.zip`, `C3_v631_GST_success_pattern_report.md`; 연구브랜치 `docs/C3_V631_GST_SUCCESS_TRADE_PATTERN_AND_FORWARD_PROTOCOL_20261026.md`에 원장과 실패사유. 로컬 12개 테스트 통과. 전체 실험 GitHub CI 성공으로 허위 표현 금지.
- 모든 08:35/13:00/16:00/18:30 및 평일 수익성연구 알람에서 GST형은 별도 **WATCH/검증대상**으로만 비교하며 자동 신호 점수 상승, 실전 BUY, 자동매수 활성화 근거가 아님. 현재 C3 현금/포지션 별도 확인, 정규장-only 65+봉, 회사종류·비제약바이오·기업행사PIT, 일봉 확정 피벗 손절, 실적·촉매, 산업주도, 최종주식점수>=80/100, **검증된 저항 비용후R:R>=2**, 유효호가/1주/계좌 현금/1종목 모두 통과 전에는 CASH. K100 변경 없음.
- 진정한 외부 샘플은 2026-10-26 이후 새 완료 세션부터 기록하며 미래 수익이 나오기 전 D일에 후보 순위와 가격을 동결한다. 이미 살핀 2026 1~10/23 데이터는 별도 홀드아웃이라고 주장하지 말 것.


## 2026-10-26 v6.32 GST D-ONLY RANK VS 5/12D HOLD (RESEARCH ONLY)

- v6.31 GST형 초기돌파 패턴의 **D+1 시초가/갭/예정된 향후 이상 가격**을 보고 D일 후보를 가려내던 탐색용 사후 선별 위험을 수정. v6.32는 **신호일 D 완료봉의 종목점수로 모델/날짜당 상위 1종목만 먼저 고정**한 뒤, D+1 갭(-2%~+2.5%)·가용 현금·지정가 가능성 등을 검사. 갭 불리하면 매수취소만 하고 D+1 가격을 보고 2위 종목을 소급 매수하지 말 것.
- GST의 실제 2026-09-21 신호는 5>10>20일선, 20일선/60일선 접근, D일 이전 20일 고점 돌파 조건에 걸리나, **해당 신호일 GST(083450)는 당일 기준 점수 1순위에 선정되지는 않음**(연구 1순위 074600). 이는 실제 과거 사용자의 GST 성공거래를 복제하는 모델이 완성됐다는 뜻이 아님.
- 846 모델 중복 D-시점 연구후보/372 코드, 308개 모델별 당일 1순위 고정, 다섯 청산 연구 1540개 가상 청산·갭취소 기록. 2026 H1/H2 각각 `MA20/MA60=0.92~1.02`·D구조위험 2~8% GST형 7% 이전봉 고점 추적은 44건 +1.570%/20건 +1.076% 모의 평균이나 최근 중앙값 **-1.364%**, 최고 1건 제거 평균 **+0.014%** → 불안정. GST형 5일 시점 보유연장 결정은 같은 5일 종가로 청산되었다고 가정하지 말고 **6번째 거래일 시초가 이후** 집행 가능.
- 가상 과거 269,230원(2026-10-13 확인, 현재 잔고 아님), 계좌위험 1%, 정수 최소1주, 0.65% 왕복 비용으로 1종목씩 `NEAR60_RISK8+7%추적` 14번 모의거래 총 +10,325원(+3.835%)이나 최고 수익 2건 합계 **+10,996원**, 그 외 12건은 약 -670원. 실현위주 모의원장으로 월말 미실현·진짜 최대 낙폭과 증권사 체결을 증명하지 않는다.
- 연구기록 `research/v615-usable-entry-frontier-20261025/docs/C3_V632_GST_D_ONLY_RANK_VS_HOLD_20261026.md`, 실행 전체 Python·15개 로컬 테스트·CSV는 사용자 대화 첨부 `C3_v632_GST_rank_and_hold_research.zip`. 신호/결과가 이미 반복 연구된 과거 2026-01~10/23 범위에만 해당, 10/26 국내 본장 신규 종가 아님.
- 검증된 실제 정규장 09:00~15:30 원본·상승섹터/진짜 리더의 당시 지위·당시의 보통주·비제약바이오/기업행사 공시·확정 일봉 피벗·비용후 확인 저항 >=2R·최종 80/100·현금/포지션/실제 체결 등이 없으면 **BUY 0/CASH**. GST 성과를 보장하거나 5일→12일 보유 연장 자동실행 금지. K100 및 자동주문 영향 없음.


## 2026-10-26 v6.33 GST D-RANK RESEARCH — BALANCED SCORE NOT APPROVED

- v6.32 GST형 동결 신호 846건/가격코드 372개/모델-일자 308그룹(경쟁종목 2개 이상 170그룹)을 이용해 D일 완료 정보만으로 6가지 순위모델을 검증한 **v6.33 과거 탐색 연구**: `research/v615-usable-entry-frontier-20261025/docs/C3_V633_GST_D_ONLY_LEADER_RANKING_20261026.md`. 같은 2026년 1~10/23 과거 자료를 이전 연구에서 반복 봤으므로 독립 미래 검증 아니며, 오늘 10/26은 장전으로 당일 완료 본장 데이터가 아직 없음.
- 종합 `BALANCED_LEADER`(시장 ETF 대비 RS5/RS20, 거래대금 가속, 돌파 강도, 일봉 구조손절위험)의 NEAR60_RISK8 12거래일/7% 추적/가상 269230원·1% 계좌위험/0.65% 비용 가상 계좌는 13회 +4.329%, 기존 V632_BASE 14회 +3.835%. **그러나 D일 고정 75개 신호기회를 0원 현금취소까지 짝비교하면 종합형은 기존 대비 평균 -0.592%p 하락**; 10/75일만 실제로 1위가 달라짐. 보유/매수가능 자금이 다르게 흐르는 누적계좌 성과를 종목선정 우위로 해석 금지.
- 동일 D일 후보 중 무작위 1개 선정·갭/자본제약/비용/구조손절 적용 200개 모의단일계좌 비교: 중간값 +2.330%, 5~95백분위 -0.188~+5.710%. 종합형은 약 82.5백분위/기존 77백분위에 불과. 이미 탐색한 구간에서 여러 점수를 고른 데이터마이닝을 감안하면 수익우위 확증 아님.
- 2026-09-21 GST(083450) 5일 수익 +10.53%, 20일 평균 대비 거래대금 가속 1.12배, 가상 구조손절위험 6.06%. 동시 경쟁 074600 5일 +12.31%, 거래대금 가속 1.30배, 위험 6.54%; 기존/RS/돈흐름/종합 순위에서 **074600 1위, GST 2위**. 동일 9/22 시초가 가정 후 12일 추적손절의 비용후 모의수익은 GST +8.31%, 074600 +6.57%로 **두 후보 모두 플러스**. GST만을 특정해 과거 순위를 사후 수정해서는 안 됨.
- 신규 가중치 `BALANCED_LEADER`는 **시험용 Challenger 태그**만 가능, 기존 확정 종목점수/80점 문턱/실제 TOP5 순위에 임의 가점이나 교체 금지. 당시 공식 업종맵과 동종주의 거래대금 강도, 선행 보통주·비제약바이오 분류, 실제 공시 및 기업행사, KRX 09:00~15:30 본장 확인을 확보하기 전 "GST 업종 1위" 주장은 불가.
- 로컬 전종목 결과 `C3_v633_GST_leader_ranking_research.zip`, 13개 로컬 안전검증; 연구 브랜치의 순위 계산만 하는 `scripts/gst_d_only_leader_rank_v633.py`와 별도 13개 fixture 테스트, 무료 CI는 **전체 5,544개 모의진입이 원격 통과했음을 의미하지 않음**. 실전 주문/실계좌 현금/실제 체결 인증도 없음. 확인된 일봉 구조손절·비용후 2R 저항·최종 종목 80점·실제 가용현금·단일포지션 이전에는 신규 BUY 0/CASH. K100·기존 자동주문 비변경.


## 2026-10-26 v6.34 EVIDENCE QUALITY RESET — NO OVERFIT MODEL PROMOTION

- 질문 "C3 방향이 맞고 수익을 주는가?"에 대한 **검증 결과**: 2026-10-23까지 GST, HMA+다바스, WaveTrend의 가상 플러스 손익은 있어도 **독립 신기간/실제 체결/비용후 일관 우위가 확보된 수익형 모델은 0개**, 그러므로 CASH/PENDING_DATA_VALIDATION. 2026-10-26 새 정규장 완결 시세는 기존 연구에 아직 없음. 2026년 과거를 여러 번 탐색해서 새 최고수익 설정으로 승격하는 개발을 중단.
- v6.34 실행된 **v6.33 단일 계좌 6랭킹 대 무작위 200개 비교에 대한 선택 편향 감사**: GST형 NEAR60_RISK8 최상위 BALANCED_LEADER 과거 +4.329%(13개 가상매수), 동일 날짜 무작위 200개 중 **35개(17.5%)**가 이를 초과/동률. 여섯 개의 **상호 독립** 무작위 시도 중 하나 이상 성공한다는 **설명용 가정**은 `1-(1-.175)^6 = 68.47%`. **이것은 모델별 상관, 다른 패턴/청산 사후 선택 및 반복연구를 포함하지 못한 예시 확률이지 엄밀한 검정 p값이 아님**. 원본 기존 vs 종합 신호 D날 75건 직접비교는 종합형 -0.592%p 열세.
- GST NEAR60_RISK8 종합형 가상 13회 총 +11,656원 중 최고 2건 합계 +10,995.51원, 남은 11건 약 +660.52원(단순 기여도 산술분해); 기존형 14회 총 +10,325원 중 최고 2건 +10,995.51원, 남은 12건 약 -670.05원. **이익 의존도 높음**, 수익 최고 2건 제거 후 잔고 재시뮬레이션이 아니므로 실제 독립 기대수익이나 MDD 인증 아님.
- 공식 새 연구는 **v6.32 D시점 GST 기존 Rank, v6.33 GST BALANCED_CHALLENGER, v6.30 HMA+다바스 첫 깊은 재시험, v6.24 WaveTrend**의 사전 규칙을 고정해 2026-10-26 이후 순수 KRX 09:00~15:30 실데이터만 누적. 임의 점수 가중치·매도 목표를 사후 조정하지 말고 후보 D일 고정→D+1 갭/지정가 미체결과 실제 키움 체결을 따로 기록→완료 5/12거래일 수익, 현금 포함 월말 평가, 보유중 일별 MDD, 비용 추가 0.3%p, 최고2개 수익 의존, 동일날 무작위 대조/시장지수 비교.
- **연구 검토 최소 운영기준**은 신규 독립 체결거래 >=30, 3개 이상 실제 진입월, 비용후 순이익/중앙값 플러스, 최고2개 수익기여를 빼도 플러스, 추가비용 스트레스와 현금/벤치마크/동일 D기회 우위, 최대낙폭 공개. 표본 기준만으로 유의미함이 증명되지는 않음. 이행 실패 시 무조건 CASH, 자동 주문 금지. 리포트에는 "실측 신규 검증 거래 n"와 "이미 탐색한 과거 거래 n"를 명확히 구분. 약한 장세/최종 주식점수 80미만도 CASH.
- 로컬 완료 파일 `C3_v634_proof_not_backtest_research.zip`에 4개 모델·200 무작위 결과 재계산 CSV, 원본 3종 재현 데이터, 읽기 전용 전진 연구차단 코드, 동결 JSON, **25개 로컬 테스트 통과**. 연구 PR #25에는 문서 및 더 작은 7개 안전 fixture 테스트용 GitHub source/workflow 추가. **GitHub CI 새 통과 미확인, 원격 전체 과거 백테스트 수행 주장은 금지**.
- 반복 알람 08:35/13:00/16:00/18:30 및 평일 저녁 연구에서 정규장 자료가 없거나 새로운 기간 표본이 없다면 최신 BUY/수익률 지어내지 말 것. 실제 키움 가용현금, 최소1주, C3 단일 포지션, 제약·바이오/보통주/PIT 기업행사, 검증 진입·일봉 구조손절·저항 비용후 R>=2 및 최종 80점 이상 필수조건 유지. K100 관리 별개.


## 2026-10-26 v6.35 RESEARCH PRINCIPAL 1,000,000 KRW — ACTUAL CASH UNCHANGED

- 사용자 명시 요청으로 2026-10-26부터 **C3 수익모델 연구용 가상 시작자금을 1,000,000원으로 변경**. 과거 v6.30 기본연구액 269,230원은 계좌 연구 초기값으로 더 이상 쓰지 않음. **실제 키움 주문가능금액, 사용자가 현재 보유한 현금·주식 및 K100 실제자산을 100만 원으로 덮어쓰지 않는다**. 입금·계좌이체·자동주문·실제 잔고조작 0건.
- 거래당 **C3 가상계좌 자산의 1%(시작 10,000원)**를 최대 계획손실 연구 예산으로 설정; 이는 종목가의 1% 손절을 뜻하지 않음. 확인된 본장 일봉 구조저점 S를 먼저 정하고 매수가 P, 실제 현재 확인된 주문가능 현금 C, 가상 연구계좌 자산 E에 대해 `min(floor(C/P), floor(E*0.01/((P-S)+P*0.0065)))` 정수 수량(최소1주). 가용현금보다 많이 주문/담보·신용·동시 2종목 금지. 0.5%는 보수 민감도, 2%는 위험 스트레스 가정일 뿐 **현장 기본위험 2%로 자동 증액 금지**. 거래비용/슬리피지 합산 왕복 0.65% 가상 기준 및 0.95% 비용 스트레스. 실제 급락갭·체결지연은 계획손실 10,000원보다 커질 수 있음.
- **v6.35 로컬 재계산 완료**: 기존 2026-10-23까지 반복 연구한 v6.29 1704행 + v6.33 5544행의 **D일 후보/전략/청산 파라미터를 변경 없이 동결**, 5개 연구경로(4개 핵심가설+HMA 시초가 대조) ×0.5/1/2% 위험 ×0.65/0.95% 비용 **30개 가상계좌 시나리오**. 가상 시작 100만원/위험1%/비용0.65%에서는 GST 기존 D순위 52건 **+7.5296%**, GST BALANCED 50건 **+3.3319%**, HMA·다바스 깊은 눌림 28건 **-1.4208%**, HMA 시초가 35건 **-4.3988%**, WaveTrend 시초가 14건 **-0.1182%**. GST 기존 순위조차 비용0.95%에서는 **+4.8805%**로 둔화 및 거래 중앙값 **-0.20%**, 전진 신기간 검증이 아니라 과거 수익성과 표본 의존성 진단만 완료한 것.
- 가상가격 저가접촉≠실제 체결, 청산월만 집계한 계좌손익≠월말 미실현손익·일별 평가MDD. 역대 상위2개 가상거래 손익 기여 제외 성과는 현금경로 재실행 값 아님. 최초 정규장 시세가 2026-10-26 **15:30에 완료된 후** 공식 09:00~15:30 전용성까지 실제 인증되기 전에는 이날 새 독립 표본/BUY 확정 금지. 기존 연구성과를 새 2026-10-26 신호라고 바꾸지 말 것.
- 새 연구 기준 `research/v615-usable-entry-frontier-20261025/configs/c3_v635_1m_virtual_research.json`, 설명 `docs/C3_V635_1M_CAPITAL_FROZEN_PROOF_PROTOCOL_20261026.md`, 순수 계산 코드 `scripts/c3_virtual_capital_gate_v635.py`; 30개 현금 시나리오/16개 로컬 테스트/CSV 및 모바일 보고서는 이 대화의 `C3_v635_100만원_검증중심_연구자료.zip`. 1백만원 연구기준 변경은 **사용자 기존 시황 알람의 실제 잔고/체결 기록 갱신이 아님**, 조사 모델·규모 가정에만 적용한다. 새 GitHub Actions 전체 백테스트 성공이나 주문체결을 주장하지 않음.
- **연구방향:** 지표 가중치 과거재최적화 중단, GST v6.32 기존 D순위 우선 가설 + GST v6.33 종합 도전자 + HMA 깊은 첫 눌림 + WaveTrend를 동결. 2026-10-26 이후 독립 완료된 공식 KRX 본장 세션 D-일로만 선택/다음날 취소-미체결까지 순차 기록. 실제 주식유형/제약바이오/공시시각/PIT·기업행사, 확인된 상승섹터/실적촉매, 구조손절/유효저항 비용후 >=2R, 최종 종목 점수 >=80, 현재 실제 계좌현금·보유종목·최소1주가 모두 검증되지 않으면 CASH. 연구 최소 기준 새 완료매매30건/매수월3개/비용후·상위2건 손익기여 제외·중앙값 플러스/일별 평가 낙폭·시장대조, 그러나 이 기준만으로 수익 확정되지 않음.
- C3 실제 매수승인/자동주문은 꺼둔다. K100 실제 계좌 변경·주문 없음. 상시 보고 상단 'RESEARCH_PRINCIPAL_1M_VIRTUAL / REAL_CASH_UNKNOWN_OR_VERIFIED' 분리 표시.


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
