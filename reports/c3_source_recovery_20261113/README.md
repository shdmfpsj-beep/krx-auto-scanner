# 강현AI PRO · C3 TOP2 — 2026-11-12 신규일 복구 검증

공식 KRX 2,770종목 확보, 기존 캐시 전수 일치 및 실제 신규일 전체시장 연구 분석·최종 PNG 생성까지 main에서 실행했습니다. 전체 실전 매수·Telegram 전달 완료를 의미하지 않습니다.

| 단계 | 실제 결과 |
|---|---|
| 공식 데이터 | KOSPI 936 / KOSDAQ 1,834, KONEX 107 제외 |
| 원본 비교 | 코드·이름·OHLCV·거래대금 2,770개 일치, 불일치 0 |
| 원본 기준일·최종 수집 | 2026-11-12 / 2026-11-13T10:21:30.127979+09:00 |
| 전체시장 분석 | 분석 1,988 / 기술 146 / 기존 B 41 |
| 관측 재무·RS·유동성 | 17개; 재무 원문 PIT 인증은 별도 보류 |
| 구조·범위 | 146개 중 독립 집계: 손절 105 / 범위 19 |
| 최종 연구 결과 | 동시 적합 0개, 분석 완료 CASH |
| 실제 매수·전송 | BUY 미승인, 전송 0, 날짜 claim 생성 0 |

## 실행과 수정

[PR109](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/109) · [PR110](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/110) · [최종 main 실행](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43344240563) · [전송 보류 검증](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43345105922)

운영 코드: `40ce64f463fd25287dbadc747a05e7e1313fc2a6`

0행 성공 처리 방지, 원본·아티팩트·실행번호 전달, 등록 종료 후 동일 state 읽기, 이전 연구 가격의 읽기 전용 복원, 과거 TOP2 대체 차단, PNG 실행번호를 수정했습니다. 선정·진입·손절 연구 규칙과 기존 일정은 바꾸지 않았습니다.

복구 회귀 163개와 최종 경계 통합 41개가 각각 통과했습니다. 원본/원장 68개·Telegram 기록 19개의 보호 해시는 변경되지 않았습니다.

## Gate 판정

| Gate | 판정 |
|---|---|
1 | 통과 — 공식 신규일 원본 확보 |
2 | 부분 — 일별 필드·해시 대조 통과, 정규장·독립 상장/기업행위·재무 PIT 증거 미완료 |
3 | 통과 — 11/12 실제 신규일 전체시장 분석 |
4 | 통과(연구) — 분석 완료 CASH, 실전 승인 아님 |
5 | 부분 — 배포 main 경로 실제 성공, 다음 예약 시각 실행은 미관측 |
6 | 부분 — PNG 날짜·실행·해시 일치, Telegram은 안전 보류 |

## 해시

- 정규화 원본: `922e237b6d50650ae30f36f946835e90cd6ac046be3736ebc4f83dd0dcf01d92`
- 연구 원본 payload: `d70835a6c1f329197ca32954d471b61e50bbacecec3ef531ea634b1b383f726f`
- 최종 연구 JSON payload: `646c2efc1322e8f1b39dfd4b64352321e9fc50b2acd6cacd3d3f8a34e3e24b92`
- 최종 자동 보고 PNG: `bc9bfe04127dbf24d006df4eba98b461b7ee965ace0df2ea798114bfcceb729b`
- 기존 원장·영수증 보호: `8a7757b621100aa3dff9b7bcc79a0bae22bea8238b397cc371aa5aaf1d623820`

전체 API 응답 행수·SHA256, 등록 커밋·경로, Actions 아티팩트 및 변경 파일은 [verification.json](verification.json)에 보존했습니다. API 키와 수신처 개인정보는 포함하지 않습니다.

## 변경 파일

- `.github/workflows/c3_morning_integration_v1.yml`
- `.github/workflows/c3_new_session_recovery_v1.yml`
- `.github/workflows/c3_operations_deploy_v18.yml`
- `.github/workflows/c3_research_daily_caller.yml`
- `config/c3_morning_deploy_request.json`
- `scripts/c3_morning_final_v1.py`
- `scripts/c3_morning_source_v1.py`
- `scripts/c3_new_source_publish_v1.py`
- `scripts/c3_source_recovery_analysis_v1.py`
- `scripts/c3_source_recovery_v1.py`
- `scripts/test_c3_morning_v1.py`
- `scripts/test_c3_source_recovery_v1.py`

## 남은 필수 조건

1. 정규장 전용·재무 원문 PIT 인증.
2. 실제 다음 예약 트리거의 관측. 오늘 누락된 트리거의 내부 원인은 확정하지 못했습니다.
3. 개장 전 승인 원본 등록과 실제 전달 조건. 늦은 연구를 과거 실전 신호로 만들지 않으며, 이번 Telegram은 보류 상태입니다.
