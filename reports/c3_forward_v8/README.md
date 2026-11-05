# C3 연구용 TOP2·가상매매 통합 보고 읽기

반드시 연구 브랜치 `research/c3-ledger-integrity-audit-20261104`를 조회한다. 기본 브랜치의 같은 경로는 이 전방 연구 원장이 아니다.

- 작은 JSON: `mobile/summary.json`
- 모바일 텍스트: `mobile/mobile_report.md`
- 모바일 차트: `mobile/종목코드_structure.png`
- 전체 결과: `latest.json`
- 결정/가격/관찰/정정 원본: `decisions/`, `markets/`, `observations/`, `corrections/`

보고 순서: report_day_kst 및 실행 source_run_id → source_price_asof / source_received_at → 시도한 거래일과 probe_received_at → preview_price_asof → 연구 TOP2의 실제 등록 여부 → 신규 신호 수 → 선정/가상매매 성과 → 오류와 실전 CASH 판단.

source_price_asof가 null이면 새 가격을 확보하지 못한 것이다. preview_price_asof의 오래된 후보를 오늘 새로 선정·등록한 것으로 쓰지 않는다. current_scope가 null이면 마지막 확인 종목 수를 오늘 분석 가능한 고정 종목 수로 표시하지 않는다. 실전 CASH와 연구 후보 기록 여부는 별개이며, 미래 기간의 성과를 미리 확정하지 않는다.

9차에서는 가격 원본 거래일과 실제 결정일을 분리했다. 신규 원본은 2026-11-06 이후만 허용하며, 지연 EOD도 다음 가능한 개장 전 실제 결정 시각을 보존해야 한다. decisions의 파일 키는 원본 가격 세션이고 decision_date는 실제 결정일일 수 있다. 같은 원본의 재실행은 새 결정으로 집계하지 않는다. 연구용 후보와 실전 CASH 판단은 별개다.

invocation의 event·mode·engine_sha·state_sha·run_id와 automatic_event_observed를 확인한다. push/research_smoke 성공은 매일 자동 운영의 증거가 아니다. 테스트 통과·보고 생성과 최신 가격 수집 성공도 구분한다.

GitHub 정기 호출은 아직 배포되지 않았다. 9차 실행 42091677209에서 기존 v8 워크플로의 실제 재사용 호출과 연구 브랜치 자동 저장을 확인했고 641개가 통과했다. 기본 브랜치 연결부는 [초안 PR #31](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/31)로 준비했으나 병합하지 않았다. 원래 ChatGPT 알림의 일정/활성 상태는 변경하지 않았다. 파일 접근 확인과 실제 22:30 예약 전달 확인은 별개다.

최신 진단: 11/6 04:13 KST 조회에서 11/5 공식 EOD는 두 시장 모두 HTTP 200·빈 OutBlock으로 실패했다. 신규 등록 0건, 신규 5/10/20일 완료·미완료 등록 표본 0건, CASH다. 마지막 확인 가격 11/4의 종목·차트는 오래된 미등록 미리보기다. 현재 시장 분석 가능 종목 수는 미확인이며 과거 1,983개를 고정해서 사용하지 않는다.

[9차 실행·배포 상세](../../docs/C3_RUNTIME_STABILIZATION_20261106.md) · [원본 증거](../c3_work9_20261106/execution_evidence.json)
