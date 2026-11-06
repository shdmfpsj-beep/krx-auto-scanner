# C3 14차 운영 전환 체크포인트

## 최종 상태 — 2026-11-06 오전 KST

**연구 엔진·재사용 호출·Git 저장 검증 완료. main 배포는 별도 승인 대기이며, 첫 신규 전방 신호는 11/6 장 마감 전이라 아직 없다.**

- 검증 엔진 `0f6ebc67bd755b00945388d431e32d94183ba7fe`, PR #31 caller `5ba5781ac6abd82413855c1cdcf49acd98306267`. 4곳 pin 일치. 배포 파일은 여전히 `.github/workflows/c3_research_daily_caller.yml` 1개 추가(92줄), 기존 main/운영 스캐너 변경 0.
- 실제 직접 실행 [42148787893](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/42148787893) 및 실제 동일 SHA 재사용 실행 [42149047206](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/42149047206) 모두 성공. 각각 **699 검사 / 실패·오류·skip 0**. 기존 693개 보존+필요한 운영 장애 검사 6개. 실제 main schedule/workflow_run은 관측하지 못했다.
- PR #31 파일 검사 [42149046675](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/42149046675) 통과. 초안·미병합이고 별도 승인 없음. 이번 작업 지시/재요청은 병합 승인으로 해석하지 않았다.
- 최종 자동 저장 `25ebb539b7c917def2f6529ff01d2420941f0ff7`. 원본은 **2026-11-05**, 수집 완료 **11/6 11:15:23.977 KST**, 분석 완료 **11:15:31.867**, 보고 생성 **11:15:31.892**. 11/6 EOD 요청 없음. 11/5를 새 전방 신호로 소급하지 않았다.
- KOSPI 938 + KOSDAQ 1,831 = 2,769종목, 정상 OHLCV 2,658 / 거래정지 유사 111 / OHLC 이상 0. 기존 대비 종목 누락·추가 0. 비바이오 분류 2,166 / 연속 이력 분석 가능 1,986 / A 후보 116 / B 후보 105. 이 숫자는 **11/5 자료의 분석 범위**이며 11/6 실제 종목 수가 확인됐다는 뜻이 아니다.
- 직접 KRX 상태 `OFFICIAL_VERIFIED`, 가격 계열 KRX 비수정. 정규장 전용 독립 인증/기업행위 전수 검증은 미완료다. 캐시 게시 준비는 확인했으나 이번 두 실행은 공식 API가 정상이어서 실제 장애 전체 fallback 성공으로 주장하지 않는다. 새 예외 복구 4종은 합성 검사다.
- 신규 결정·등록 신호·관찰 중 신호·가상체결·미체결 거래·손절·종료·5/10/20일 완료/미완료 등록 표본 모두 0. 비용 차감 손익은 null/미확정이다. 마지막 두 미리보기는 신규 TOP2가 아니다. 실전 CASH.
- 암호화 Git bootstrap 3개 복구, 원래 고정 ZIP 다운로드 0. 기존 불변 기록 8개/시장 원본 아카이브 1개/입력 ZIP 3개 복호화·hash 검사 통과. 실제 키 변경/키 값 출력 없음. 기존 파일 덮어쓰기 없음.
- 최신 보고 3개를 GitHub에서 실제 읽었고 다운로드한 실행 아티팩트와 바이트가 전부 일치한다. 원본 아티팩트 `13472200280`(65,369,997 bytes), ZIP SHA256 `70d002cb41a5cf5f9be81a8e4ee24f133dba5be8ec4c81b9cc7f1c3a14897ca7`.
- 22:30 ChatGPT 알림은 활성/Asia-Seoul 평일 22:30을 읽기 확인만 했다. 프롬프트는 연구 PR #30을 참조하며 보고 3개 경로를 직접 지정하지는 않는다. 따라서 PR #30 설명 첫머리에 안정된 보고 링크를 정리했다. 파일 접근/내용 일치와 실제 알림 전달은 별개로, 현재 버전 전달은 미확인이다. 알림 변경 0.
- A/B choose AST와 진입·구조손절·선정 요소 코드 3개 byte가 13차와 동일하다. 과거 전수 비교/백테스트는 반복하지 않았다.

## 승인과 실제 첫 등록 조건

사용자에게 필요한 승인은 **PR #31 배포 1건**이다. 승인 시 모바일 GitHub에서 PR #31 → Files changed 1개/Checks 성공 → Conversation → Ready for review → Merge pull request → Confirm merge. PR #30은 초안 유지. 승인 전 임의 병합/기본 브랜치 수정 없음.

병합 전에는 main 자동 호출이 발생하지 않는다. 병합 후에는 기존 운영 수집 완료와 평일 22:15·08:20 KST에 연구 호출이 가능해지지만 데이터 제공/실행 지연이나 22:30 전달을 보장하지 않는다. 새 caller만 Disable/되돌리면 기존 스캐너에 영향 없이 호출을 중지할 수 있다.

**장 마감 후 실제 11/6+ 가격**이 공급돼야 첫 신규 결정이 등록된다. 지연 가격은 다음 가능한 장 시가 전 실제 분석 완료 시각으로만 등록한다. 이후 실제 다음 세션 OHLCV로 가상매매를 추적하고 5/10/20거래일 완료 전 손익을 만들지 않는다. main 배포 승인과 신규 EOD는 별도의 대기 조건이다.

## 정확한 재개 명령과 파일

```bash
git switch research/c3-ledger-integrity-audit-20261104
git pull --ff-only
```

- 코드: `scripts/c3_supply_runtime_v12.py`(공식 예외→whole-dataset fallback), `scripts/c3_forward_report_v8.py`(운영 상태 분리).
- 원장: `reports/c3_forward_v8/lanes/krx_unadjusted_v12/{markets,decisions,observations,supply_archives,supply_receipts}`. 아직 신규 decisions/observations 0. 기존 암호화 파일을 지우거나 덮어쓰지 않는다.
- 입력 캐시: `reports/c3_forward_v8/bootstrap/`. 고정 과거 ZIP을 다시 다운로드하거나 암호화 실험을 반복할 필요 없음. 키 교체는 13차 별도 절차를 따른다.
- 실제 호출: 승인 후 PR #31을 병합한 경우 Actions → **C3 approved research daily caller → Run workflow(main)**로 최초 배포 후 수동 호출 확인 가능. 이는 schedule 발생 관측과 구별한다. 그 다음 실제 workflow_run/schedule 결과의 `invocation.event/mode`, `operating_status`, state commit, 원본 날짜를 확인한다.
- 배포 전 연구 재현: `.github/workflows/c3_reusable_runtime_v9_smoke.yml`은 검증 엔진에 고정돼 있다. 필요할 때 이 workflow의 push/dispatch를 사용하되 이미 끝난 11/5 검증만 반복하지 않는다. 공급/분석/등록 코드가 바뀌거나 새로운 실제 거래일이 생겼을 때 재검증한다.
- 직접 확인: `reports/c3_work14_20261106/final_execution_evidence.json`, `deployment_review.json`, `validation_tests.json`, `collection_plan.json`, `git_artifact_comparison.json`, `alarm_readonly_check.json`.
- 모바일 입력: `reports/c3_forward_v8/mobile/{summary.json,mobile_report.md}` 및 `reports/c3_forward_v8/latest.json`. 생성 시각과 원본 거래일을 분리해 읽는다.

아래는 중간 보존 이력이며 최종 상태는 위 절을 따른다.

# C3 14차 운영 전환 체크포인트

## 시작 상태 — 2026-11-06T02:07:37.178Z

- 실제 연구 HEAD `4626a3402e1f2044cd2a32376e3887cc75abb6c2`, 검증 엔진 `497b7a60f7feb60acff22cd65df4db1784b83de8` 및 693 통과를 재사용한다. 12차 전수 대조/과거 백테스트/13차 실제 암호화 복구는 반복하지 않는다.
- PR #31 `52d1b56888348eb4713ffd382eb3867b0f57edfa`: 초안, 미병합, workflow 1개만 추가, main 변경 0. 별도 명시 승인과 GitHub review/comment가 없으므로 병합하지 않는다. 이 작업 지시 자체도 승인이 아니다.
- 현재 11/6 정규장 진행 중. 마지막 완료 가격은 11/5 2,769종목 / 분석 가능 1,986종목이다. 11/6 종가 요청·신규 결정·가상체결을 소급 생성하지 않는다. CASH.
- 남은 실제 검증: 공식 수집기의 예외/파일 검사 실패가 검증된 전체 대체 공급원을 막지 않도록 보완; 모바일 보고에 연구/기본 브랜치/자동 이벤트/예약/ChatGPT 전달의 분리된 상태를 표시; 필요한 테스트와 실제 연구 Actions·Git 저장 검증. 선정/진입/손절 함수는 바꾸지 않는다.

## 재개 위치

`scripts/c3_supply_runtime_v12.py`, `scripts/test_c3_supply_runtime_v12.py`, `scripts/c3_forward_report_v8.py`의 필요한 운영 보완부터 이어간다. 엔진 코드 변경 시 PR #31의 4곳 SHA와 재사용 smoke pin도 최종 검증 엔진으로 갱신한다. main은 승인 전 유지한다.

## 실제로 남은 조건

PR #31 별도 병합 승인 및 장 마감 후 실제 11/6 EOD 공급이 필요하다. 연구 브랜치 실행 성공을 기본 브랜치 자동 실행 성공으로 보고하지 않는다. 신규 신호 이후 실제 다음 거래일이 오기 전 가상매매/5·10·20일 결과를 만들지 않는다.

## 운영 보완 — 로컬 검사 완료

- 공식 어댑터 예외·응답 도중 끊김·CSV hash 실패도 검증된 전체 대체 원본으로 복구한다. 일시 통신 예외 재시도는 1회이며, 잘못된 OHLC는 공식 공급 성공으로 표시하지 않는다. 예외 원문은 Secret 노출 가능성 때문에 저장하지 않고 정해진 오류 코드/타입만 남긴다. 원천끼리 필드를 합치지 않는다.
- 보고서 JSON/Markdown/HTML에서 연구 검증, main 호출, 실제 자동 이벤트, schedule 이벤트, ChatGPT 전달을 분리한다. 기존 보고는 invocation이 있을 때 배포 부정 문구를 중립 문구로 바꾸고 있었으므로, 잘못된 배포 판단이 실제로 발생했다고 주장하지 않는다. 이번 보완은 각 상태의 명시적 표시다.
- 필요한 합성 장애 검사 6개 추가. 관련 34개 로컬 검사 성공. 과거 성과/전수 비교는 재실행하지 않았다. 기존 엔진의 A/B 선택·진입·구조손절 계산은 변경하지 않았다.
- 다음: 새 엔진 Actions → PR #31 pin 동기화 → 실제 재사용 호출/보고·Git 저장 대조. 11/6 신규 EOD는 여전히 장 마감 전이므로 요청하지 않는다.

## 새 엔진 실제 Actions 성공

- 엔진 `0f6ebc67bd755b00945388d431e32d94183ba7fe`, 실행 [42148787893](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/42148787893) 성공. **699 검사 / 실패·오류·skip 0**, 연구 자동 저장 `25e190f7e84ccd9b43f9f96b29ab226a37ac8b02`.
- 11/5 공식 2,769종목, 유효 분석 1,986. 수집 11/6 11:12:46.902 KST, 분석 11:12:54.876 KST. 11/6 장 미완료이므로 신규 등록·가상매수 0, CASH. 과거 원본 복호화 기록 7개/시장 원본 1개/bootstrap 3개 정상, 원본 변경 0.
- 다음: 동일 엔진 SHA로 PR #31 4곳과 연구 재사용 호출 3곳을 맞춘 뒤 실제 workflow_call·저장을 확인한다. 별도 사용자 승인 전 main 병합 없음.
