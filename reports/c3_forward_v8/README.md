# C3 연구용 TOP2·가상매매 통합 보고 읽기

반드시 연구 브랜치 `research/c3-ledger-integrity-audit-20261104`를 조회한다. 기본 브랜치의 같은 경로는 이 전방 연구 원장이 아니다.

- 작은 JSON: `mobile/summary.json`
- 모바일 텍스트: `mobile/mobile_report.md`
- 모바일 차트: `mobile/종목코드_structure.png`
- 전체 결과: `latest.json`
- 결정/가격/관찰/정정 원본: `decisions/`, `markets/`, `observations/`, `corrections/`

보고 순서: report_day_kst 및 실행 source_run_id → source_price_asof / source_received_at → 시도한 거래일과 probe_received_at → preview_price_asof → 연구 TOP2의 실제 등록 여부 → 신규 신호 수 → 선정/가상매매 성과 → 오류와 실전 CASH 판단.

source_price_asof가 null이면 새 가격을 확보하지 못한 것이다. preview_price_asof의 오래된 후보를 오늘 새로 선정·등록한 것으로 쓰지 않는다. current_scope가 null이면 마지막 확인 종목 수를 오늘 분석 가능한 고정 종목 수로 표시하지 않는다. 실전 CASH와 연구 후보 기록 여부는 별개이며, 미래 기간의 성과를 미리 확정하지 않는다.

GitHub 정기 호출은 아직 배포되지 않았다. 연구 브랜치 config/c3_forward_v8_request.json을 바꾸는 push 경로의 실행과 연구 브랜치 자동 저장을 검증했다. 원래 ChatGPT 알림의 일정/활성 상태는 변경하지 않았다.
