# C3·K100 무료 자동분석 v6.4 — 가격출처 대조·전진수익 원천 격리

**개발 및 검증: 2026-10-25 KST | 실제 검증 기준일: 2026-10-23 (금)**

**최종 판정: CASH / 매수 추천 0 / 자동주문 0 / 검증된 실거래 승률 없음.**

## 1. GitHub에서 실제로 동작하는 코드 및 검증 결과

| 기능 | 실제 성공 실행 | 검사 |
|---|---|---|
| 2026-10-23 동일 거래일 전체 후보 시세 교차검사 | [#40151275009](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151275009) | 9/9 안전 테스트, 82개 전수 종가·OHLC 비교 |
| 신호별 1차/2차 모의 결과 소스 차단 | [#40151473487](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151473487) | 8/8 안전 테스트, 34개 원본 가격 SHA 고정 |
| 일일 자동 소스 매칭·안전 차단 통합 | [#40151559797](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151559797) | 9+8 테스트, 동일날짜 1세트 자동 매칭, 실데이터 재생 완료 |

**코드:** `scripts/source_consensus_v64.py`, `scripts/forward_source_gate_v64.py`, `scripts/test_source_consensus_v64.py`, `scripts/test_forward_source_gate_v64.py`.

**자동화:** `.github/workflows/source_consensus_v64_free.yml`, `.github/workflows/forward_source_gate_v64_free.yml`, `.github/workflows/source_provenance_v64_daily.yml`.

**휴대폰 GitHub Actions → 해당 실행 → Artifacts:**
- `free-v64-asof-source-close-discrepancy`: `source_consensus_v64_status.json`, `source_consensus_v64_all.csv`, `source_consensus_v64_mobile.md`
- `free-v64-forward-risk-gate-20261023`: `forward_source_gate_v64_status.json`, `forward_source_gate_v64_all.csv`, `forward_source_gate_v64_mobile.md`
- `free-v64-daily-source-audit-and-forward-gate`: 날짜별 `consensus`, `gate` 폴더 전체. 자동 신규거래일 매칭 지원

## 2. 2026-10-23 실제 가격자료 검증

동일 거래일, 동일 종목코드의 두 원본을 비교했다.

- KRX Recovery 원본: GitHub run **39923708922**, `candidates.csv` 82종목 및 120개 완료 일봉 히스토리.
- Sector Evidence v18 원본: run **39948306433**, 2026-10-23 KOSPI 940개·KOSDAQ 1,824개 등 **총 2,764개 증권코드**. 별도의 v6.3 SHA 고정 일별 CSV run **40145125003** 사용.
- frozen 신호: v6.3 원본 run **40144815020**, 신호 **17개**(실제 종목 **16개**), 1차·2차 대체안 **34개**. 동일 신호에 대한 두 대체가격은 동시 보유/물타기로 간주하지 않음.

| 출처 일치 판정 | 종목수 |
|---|---:|
| 두 원본의 유효한 종가 일치 (정규장 증명은 아님) | **22** |
| 두 원본의 유효한 종가 불일치 | **59** |
| 복구스캔의 일봉 고가·저가 또는 거래량 무효 | **1** |
| 합계 | **82** |
| 위 59종목 중 종가차이가 복구원 대비 1% 초과 | **29** |

*특정 오류 사례:* `050090`은 복구본의 같은 날짜 고가·저가·시가가 0이고 거래량도 0이어서, 종가 숫자가 보인다는 이유로 유효 일봉 처리하지 않았다.

**원인 단정 금지:** 이 차이는 KRX/NXT 시간외 거래 혼입인지, 수정주가 처리 차이인지, 일시적 데이터 공급 문제인지 추가 독립 근거 없이 판단할 수 없다. v6.4은 원본 가격을 수정·덮어쓰지 않고 양쪽 가격과 차이율·사유·출처 실행번호를 보존한다.

## 3. 34개 동결된 1·2차 타점의 실제 격리 결과

| 기존 날짜별 연구 신호 | 1차·2차 대체안 합계 |
|---|---:|
| 서로 다른 종가로 **가격 근거 불일치, 격리** | **24개** |
| 두 종가 일치하지만 정규장 분리·독립 인증 미완료 | **10개** |
| 실전 신규매수·최종 80점 인증 허용 | **0개** |
| 정규장 인증을 거친 매매손익 데이터 | **0개** |

위 24개는 12종목 × 각각 1차·2차이며, 10개는 나머지 4종목에 해당하는 10개의 방법별 대체 시나리오다. 서로 다른 기술전략의 중복 신호가 있어 종목수와 건수는 다르다.

`forward_source_gate_v64.py`는 v6.3에서 미리 SHA 고정된 `ticker / method / variant / first or second / stop / nearest target / asof close`를 검증하고, 소스 대조 결과의 같은 종목·방법과 모두 일치해야 통과한다.

- 불일치·비정상 시세: `SOURCE_CLOSE_CONFLICT_OR_INVALID_QUARANTINED`
- 유효한 양쪽 종가 일치하나 정규장 인증 미완료: `AGREED_CLOSE_BUT_REGULAR_SESSION_UNCERTIFIED`
- **두 유형 모두** `trade_approved=false`, `orders_enabled=false`, `net_return_pct=null`. 과거 모의결과에 우연히 5일 수익률이 있어도 이 보고서에서는 실전 손익으로 전환하지 않는다.
- 동결된 매수/손절/목표가가 나중에 바뀌거나 최초 SHA·날짜·원본 정보가 다르면 전체 대조를 실패 처리한다.

## 4. 일일 자동화가 실제로 하는 일

`source_provenance_v64_daily.yml`은 **평일 23:30 KST** 예약 실행되며 모바일에서 수동 실행도 가능하다.

1. 성공한 최근 40개 v6.3 신호 동결 run과 시장가격 슬라이스 run, 최근 성공한 v6.3 전진관찰 보고서를 검색.
2. **정확한 거래일과 SHA로만** 짝을 만든다. 같은 날짜에 가격이 다른 시장슬라이스가 둘이거나 같은 거래일 frozen 계획이 서로 다르면 중단. 자료가 아직 없으면 새 거래일 결과를 조작하지 않고 `NO_DATED_PAIRS_YET`를 저장.
3. frozen manifest가 기록한 **바로 그 KRX recovery run ID**를 조회하여 성공 실행이었는지 확인하고 다운로드.
4. 종목별 82개 같은 식의 가격 대조 및 임의의 해당 날짜 신호 1차·2차 안전 검증 수행.
5. 날짜별 모바일 보고서를 업로드하며 소스가 불완전하거나 정규장 인증이 없다면 언제나 CASH.

스케줄은 GitHub Actions 스케줄 실행과 상위 데이터 수집 작업의 성공 여부에 종속된다. 일정 시각에 **반드시** 모든 시장자료가 존재한다고 보장할 수는 없다.

## 5. 현재 한계 및 다음 개발 우선순위 v6.5

**가장 큰 미완료 요건은 정규장 가격의 독립적인 확인이다.** 두 수집원 모두 같은 기간의 일봉을 제공한다는 사실은 KRX 정규장 09:00–15:30 종가로 제3자 입증됐다는 뜻이 아니다. 이름만 regular라고 표시하는 가짜 메타데이터로 인증하지 않는다.

v6.5에서는 무료로 확보 가능한 공식 거래소/증권사의 시각별 거래기록, 거래시간·수정주가 정책 등을 비교하되, API 인증 또는 유료서비스가 불가능하면 **정규장 가격을 인증했다고 주장하는 대신 차이 원인 미상과 미인증 상태를 그대로 유지**해야 한다.

또한 날짜별 전체시장 보통주/거래정지 구분, 실제 거래대금, 투자자 수급, 외부 원본관찰 자료 수집, C3 계좌 현금·K100 보유주, 최종 80점 평가 등이 이루어지기 전에는 연구 점수를 매매 지시로 승격하지 않는다.

**Required Next Data:** 2026-10-26 이후 v18 수집 원본과 정규장 15:30 종료가 증빙된 별도 공급원, 그날 최종 OHLCV/거래대금, 당시 PIT 종목분류·공시, 계좌 현재 보유·주문가능금액, 완성된 5~7시장일 실제 가격 기록.
