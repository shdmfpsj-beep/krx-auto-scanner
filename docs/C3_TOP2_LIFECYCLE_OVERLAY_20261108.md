# C3 TOP2 매수기회 생명주기 · 읽기 전용 보완 (2026-11-08)

## 목적과 범위

기존 C3 V8 B DAILY TOP2 종목선정, 고정 매수범위·손절·저항·신호 ID,
봉인된 암호화 시장 원장 및 전방 평가 지표를 변경하지 않고
최신 보고서 위에 관찰 상태를 덧붙인다. 실거래 주문과 Telegram·ChatGPT 알림은
생성/수정하지 않는다. 정규장 09:00–15:30 전용 출처는 여전히 독립 인증 미완료다.
실전 buy_approved=false, orders_enabled=false, CASH를 유지한다.

**주의:** 이미 동결된 V8 원본 매수계획의 유효기간은 **다음 1거래일**이다.
아래 D+3/D+5는 매수계획을 연장하는 규칙이 아니라
**종목 관찰·보고서 상태**를 분류하기 위한 절차다. 수익률 우위가 검증된
선정/매수 파라미터로 홍보하거나 TOP2를 강제로 밀어내는 규칙이 아니다.

## 구현

- 코드: scripts/c3_top2_lifecycle_overlay_v1.py
- 테스트: scripts/test_c3_top2_lifecycle_overlay_v1.py
- 읽기 전용 워크플로: .github/workflows/c3_top2_lifecycle_overlay.yml
- 입력: research/c3-ledger-integrity-audit-20261104의 최신 latest.json,
  별도 reports/c3_reference_calendar_v1.json (069500 관찰 거래일 참조),
  이전 실행 아티팩트의 별도 관찰 이력(JSONL; 있으면 사용).
- 출력 아티팩트: c3_top2_lifecycle_status.json,
  c3_top2_lifecycle_mobile.md, c3_top2_observed_history.jsonl.
  모두 새 파생 산출물이며 원래 결정/시장/매매/Telegram 원장에 쓰지 않는다.
- 첫 실행은 관찰 이력의 최초 기록이다. 과거에 한 번도 선정되지 않았다는 뜻이
  아니다. 5거래일 연속 선정 상태는 이후 실제로 날짜별 보관한
  스냅샷에서만 판단한다. 이전 일자가 하나라도 누락되면 HISTORY_GAP_REVIEW.
- 동일 원본 거래일/계획의 반복 보고는 중복 기록하지 않는다.
  같은 날짜의 매수가·신호 ID가 바뀌면 오류로 중단한다.
- 기존 B TOP2가 바뀌면 이전 후보는 out_of_top2에만 표시한다.
  신규 날짜에서 다시 TOP2로 선정되는 것을 금지하지 않는다.
- 진입 밴드/손익비가 먼 사례에는 진단만 표시한다.
  10% 거리, 12% 손절거리, R1 RR 1 기준은 V7의 위험 진단선이며
  성과 검증이 끝난 매수 승인 필터가 아니다.

## 상태 해석

| 상태 | 정확한 의미 |
|---|---|
| FIRST_OBSERVED_TOP2 | 보관된 관찰 이력 기준 첫 관측, 구 선정 이력은 불명 |
| WATCH_CONTINUES | 연속 관찰 1~2거래일 |
| WATCH_REEVALUATE | D+3·4, 새로운 차트·가격·시장 재평가 필요 |
| OLD_WATCH_ARCHIVE_REVIEW | D+5 이상, 구 관찰 근거 종료 검토. 당일 신규 TOP2 순위는 유지 |
| HISTORY_GAP_REVIEW | 이전 거래일 산출물이 누락되어 기간 판단 불가 |
| DATA_PENDING | 날짜 불일치·미등록·소스 준비 미완료, TOP2를 새로 발표하지 않음 |

original_plan_validity=NEXT_ONE_TRADING_SESSION_ONLY와
plan_status_at_source_close=NOT_AN_ACTIVE_ORDER는
사용자/증권사 주문 상태를 조회한 결과가 아니다. 모델의 원래 계획을
실제 실행 주문으로 간주하지 않는 표시다.

## 실행/운영

- PR 검증 또는 수동 workflow_dispatch로 테스트 및 원본 11/6 최신 보고 읽기.
- main 병합 이후 기존 C3 approved research daily caller 성공
  이벤트에만 연동된다. **새 cron 없음, Telegram 없음, 실거래 주문 없음.**
- 이력의 이전 아티팩트가 만료/부재인 경우 자동 복구를 지어내지 않고
  0일 최초 관측으로 재시작한다. 일자별 누락 시에는 fail-closed.
- GitHub Actions 성공은 상태 코드가 작동한다는 뜻이며 투자 수익성의 증명이
  아니다. 11월 9일 이후 새 거래일에 실제 3/5일 이력이 누적되어야
  해당 상태 전환을 실증적으로 확인할 수 있다.
- 메인 보고서/텔레그램 UI 반영은 별도 검증·승인 사항으로 남긴다.
  이번 PR은 읽기 전용 아티팩트까지로 제한한다.

## GitHub Actions dry-run 검증

- 합성 반례: 1거래일 주문 유효기간 불변, 3/5일 관찰 분리,
  동일 날짜 재실행/변조, 데이터 누락, 교체·재선정, 진짜 BUY 오인 방지.
- 원본: 11월 6일 latest.json과 11월 6일까지의 참조 일자를 교차 확인,
  선별 TOP2가 삼성E&A·원익홀딩스 2개인지, CASH인지 검증한다.
