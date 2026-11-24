# C3 TOP5 최종 운영 통합 검증 — 2026-11-24

판정: **PRODUCTION_READY_WITH_LIMITATIONS** — 검증한 PR 코드의 정상 CASH·조건부 TOP5·HOLD·ERROR 경로는 통과했다. **운영 main에는 병합하지 않았으며 실제 Telegram 전송과 새 08:00 예약 첫 실행은 미검증**이다. 아래 제한을 포함해 배포 여부를 판단해야 한다.

## 코드와 변경 범위

- PR [#202](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/202), 브랜치 `feat/c3-balanced-quality-timing-20261123`.
- 시작 HEAD `54fe6f3550c7119ecc783738c5e6eef28eab75c5`. 최종 검증 코드 **`ee9ac0cd4ed510aec306d116b80c52c9c111fb93`**. 중간 정책 코드 `4dbe4829873df0758ed1ad80fc6f0bd363297255`.
- 변경 전후 main **`ab1ca30bfe24f0e7cbc197e1db9468d6807f1f6a`**, PR #201 반영 상태 보존. 현재 main의 legacy와 PR의 Balanced 검증을 혼동하지 않는다.
- 수정: `scripts/c3_top5_financial_selection.py`, `scripts/c3_balanced_validation.py`, `scripts/c3_top5_dart_bridge.py`, `scripts/c3_candidate_decisions.py`, `scripts/c3_balanced_financials.py`(HTTP 상태 기록 1줄), `scripts/test_c3_approval_scope.py`(신규), `.github/workflows/c3_top5_daily_telegram.yml`, `.github/workflows/c3_balanced_quality_validation.yml`, 이 문서.
- 재무 수집/정규화 엔진·100점 배점·300% 기준·현금흐름/업종 모델을 다시 개발하지 않았다. 매수범위/구조손절 계산, 호가 단위, 위험 상한 5%, 기존 2% NEAR_ENTRY, 손익비 자동 탈락 없음, WATCH 비승격을 보존했다.
- 기술 계산 `c3_entry_geometry.py`와 세션 정책 파일은 변경하지 않았다. workflow의 기존 계산식도 그대로이며, 탈락 종목의 **기존 호가 단위 구조손절 계산값을 진단 필드에 추가 보존**했다. 손절을 이동하거나 구간을 확대하지 않았다.

## 재무 관찰과 매수 승인 범위 분리

새 정책 `EXECUTABLE_FINANCIAL_APPROVAL_V1`은 Balanced에서만 명시적으로 사용한다. legacy 및 이전 `ISOLATED_ISSUER_FAILURES_V1`의 계약과 테스트는 유지한다.

1. **관찰 범위**: 기존 기술 관심 후보 전체를 기존 30개 예산 안에서 요청·기록한다. 이번 실제 9개는 모두 재무 심사됐다.
2. **승인 필수 범위**: 기존 `valid_entry`가 승인하는 ENTRY_READY·NEAR_ENTRY의 재무 판정을 반드시 완료한다. PASS 외에는 TOP5에 들어갈 수 없다. 한 후보라도 미확인이 선정의 완전성에 영향을 주면 전체 HOLD하며 검증된 일부만 먼저 보내지 않는다.
3. **당일 비승인 범위**: 명시적 공집합과 실제 시도 가격, 정확한 기존 구조손절과 계산 위험 5% 초과, 또는 모든 기존 기하조건이 유효하지만 진입 거리 밖인 WATCH를 수치로 확인한다. 이 범위의 재무 미확인은 관찰 정보로 남으며 PASS로 바꾸지 않는다.
4. 탈락 사유 문자열만 있거나 구조손절/가격 근거가 없으면 정상 CASH로 만들지 않고 **HOLD_DATA_INCOMPLETE**다.
5. 인증·요청 제한·전체 API 장애·원본/캐시/기업/기간 무결성·잘못된 모델·미래 적격 근거·코드 예외는 비승인 종목에서도 **ERROR**를 유지한다. 필수 후보 미심사/중복 자료도 차단한다.
6. 기존 API 예산 밖에 실행 가능한 후보가 남으면 HOLD한다. 상태는 매 거래일 다시 계산하며 **특정 4개 종목을 영구 제외하거나 면제하는 목록은 없다**.

선정 JSON과 후보별 JSON/CSV에 `technical_approval_scope`, `approval_required_codes/count`, `approval_financial_complete`, `nonblocking_financial_unverified_codes`, 이전 정책 결과를 추가했다. 관찰 전체의 미완료 상태 `all_interest_financial_complete=false`도 보존한다. `approval_financial_complete=true`는 승인 필수 범위에 관한 것으로 전체 기업 재무 완결을 뜻하지 않는다.

## 실제 2026-11-23 결과

원본은 [KRX 실행 45294238532](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45294238532)의 Artifact 14874774941, SHA-256 `692d1732a7395989842f5b330167b6610921293df35096889bf7ecf18bac35a7`을 확인해 재사용했다. 이번 세션에서 60거래일 전수 가격을 새로 수집한 것으로 표시하지 않는다. 실제 OpenDART 공시목록을 재조회하고 동일 접수번호의 검증 스냅샷·원문은 재사용했다.

| 항목 | 결과 |
|---|---:|
| KOSPI / KOSDAQ / 합계 | 935 / 1,836 / **2,771** |
| 유효 60거래일 종목 | **2,488** |
| 기술적 관심 후보 / 재무 요청·처리 | **9 / 9·9** |
| 재무 PASS / 확정 탈락 / 검토 / ERROR | **3 / 2 / 4 / 0** |
| ENTRY_READY / NEAR_ENTRY / 기술 WATCH | **0 / 0 / 2** |
| 승인 필수 후보 / 승인 범위 재무 완결 | **0 / true** |
| 비차단 재무 미확인 | **4** |
| 최종 TOP5 | **0** |
| 이전 보수적 정책 | HOLD_FINANCIAL_UNVERIFIED |
| 새 정책 / 전달 / 프로그램 | **CASH_NO_ELIGIBLE / CASH / COMPLETED** |

재무 판정은 이전과 동일하다. **관찰 자료 미확인 4개를 PASS시키거나 재무 검증을 건너뛰어 CASH를 만든 것이 아니다.** 현재 매수 가능한 후보가 없다는 독립적인 기술 근거가 아래와 같이 모두 확인됐다.

| 종목 / 코드 | 재무 판정 | 현재 매수 불가 근거 | 승인 필수 |
|---|---|---|---|
| 대한항공 / 003490 | 확정 탈락 | 시도 매수구간 **30,350 > 30,200**, 공집합 | 아니오 |
| 아시아나항공 / 020560 | 확정 탈락 | **8,180 > 8,110**, 공집합 | 아니오 |
| 윈스테크넷 / 136540 | PASS | 상단 11,870 / 구조손절 11,170 → **5.8972%** | 아니오 |
| 메가스터디교육 / 215200 | REVIEW_REQUIRED | **40,050 > 40,000**, 공집합 | 아니오 |
| 롯데손해보험 / 000400 | REVIEW_REQUIRED | 상단 2,470 / 구조손절 2,295 → **7.0850%** | 아니오 |
| 화천기계 / 010660 | PASS | 유효 구간 3,475~3,500, 종가 3,605 → 거리 **2.9126%**, WATCH | 아니오 |
| 아모레퍼시픽홀딩스 / 002790 | PASS | 유효 구간 25,850~26,450, 종가 27,350 → 거리 **3.2907%**, WATCH | 아니오 |
| 에스원 / 012750 | REVIEW_REQUIRED | 상단 99,700 / 구조손절 94,400 → **5.3159%** | 아니오 |
| 태양금속 / 004100 | REVIEW_REQUIRED | 상단 2,985 / 구조손절 2,610 → **12.5628%** | 아니오 |

구조손절 위험은 (매수범위 상단−기존 구조손절)/상단이다. WATCH 거리는 (종가−상단)/종가이며 기존 2% 기준을 유지한다. 원래 60봉으로 MA·ATR·지지점·호가 단위 기하조건을 다시 대조했다. 표시용 반올림 숫자로 손절을 맞추지 않았다.

4개 기업의 재무 미확인 사유는 그대로다: 메가의 첨부 정정·차입·이자·감사/유동성, 롯데의 최신 지급여력 산출 중 및 금융 모델, 에스원의 차입 총액, 태양금속의 최근 유동성 보완 근거. 추후 ENTRY_READY·NEAR_ENTRY가 되면 필수 검토가 끝날 때까지 HOLD한다. [직전 재무 복구 보고서의 기업별 접수번호·금액·원문 근거](https://github.com/shdmfpsj-beep/krx-auto-scanner/blob/54fe6f3550c7119ecc783738c5e6eef28eab75c5/docs/C3_BALANCED_QUALITY_TIMING_VALIDATION_20261124.md)는 당시 보수적 정책의 역사적 기록이다.

이번 실행의 거래일은 **11/23**이다. 11/24 종가 자료의 추가 전수 실행은 하지 않았다. 기존 21:00 KST 수집 cutoff를 보존한 실행 시점의 운영 기준일이 11/23이었으며, 이를 11/24 최신 종가 검증으로 표현하지 않는다.

## 실행 상태와 전달 경계

- TOP5: 재무 PASS와 기술 적격의 교집합만 기존 순위로 최대 5개, ENTRY_READY 우선.
- CASH: 필요한 당일 승인 검증이 완료됐고 실행 가능한 후보가 없음.
- HOLD_FINANCIAL_UNVERIFIED: 실행 가능한 후보의 재무 검토 미완료.
- HOLD_DATA_INCOMPLETE: 필수 가격/진입 근거를 확인할 수 없음.
- ERROR: 인증·무결성·코드 등 시스템 실패.

저장소 호출 경로를 조사한 결과, validation CLI의 종료 코드 2는 격리 검증에서 사용되고 있었다. 외부 사용 가능성을 보존해 **기본 종료 코드 계약은 그대로** 유지했다. 새 격리 workflow만 `--operational-exit-codes`를 사용해 정상 처리된 HOLD를 종료 0과 명시적 HOLD 결과로 구분한다. ERROR는 비정상 종료다. main daily도 sender 이후 read-only 결과 요약을 추가해 프로그램 상태, 선정 상태, 전달 상태, 승인 대상 수와 미확인을 표시하며 전송 실패/불일치는 ERROR다.

`execution_outcome.json`, 로그 `C3_EXECUTION_OUTCOME`, GitHub Step Summary를 생성한다. HOLD가 초록이어도 Telegram 승인으로 쓰이지 않으며 기존 HOLD 차단 경로가 예약/네트워크 전 종료한다. 기존 실제 전송·중복 예약·승인·message_id·영수증 기록 코드는 유지했다.

## 테스트와 Artifact 증거

- 기존 **226개 유지 + 신규 25개 = 251개 통과, 0개 실패**.
- 새 회귀: PASS/미확인과 실행 적격·부적격 조합, WATCH 비승격, 공집합·정확한 5% 초과 증거, 미확인 ENTRY_READY/NEAR_ENTRY HOLD, 공통 인증/API 장애, 원본 무결성/미래 자료, 데이터 HOLD, 필수 요청 누락·API 예산, 확인된 재무 탈락 CASH, 최대 TOP5, 원본 입력 불변, 종료 코드 호환, HOLD 무전송 및 daily 결과 요약.
- 기존 기술·OpenDART 원본·PNG·CSV·JSON·Telegram 중복/영수증·legacy 회귀도 그대로 통과했다.
- [최종 실행 45347327876](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45347327876): **pull_request / success**, 코드 `ee9ac0c`, 2026-11-24 **16:21:11~16:22:47 KST**, 약 **1분 36초**. 가격 재사용 검증의 시간이며 신규 60일 전수 수집 시간으로 일반화하지 않는다.
- [최종 Artifact 14899265498](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45347327876/artifacts/14899265498): 다운로드·압축해제 후 SHA-256 **`907eef80fec8fae087fbd2364c9e17a4ef5513fe899b203168910deaa5b4862d`** 재검증.
- 실제: 진단 PNG **9장**, 최종 PNG **0장**, CSV **0행**, 전달 **CASH**, 실발송 **0건**.
- 별도 합성: TOP5 **5개 → PNG 5장·CSV 5행·JSON/이미지 값·메타데이터·해시 대조 → DRY_RUN** 통과. 합성 표시는 유지하며 실제 선정 결과로 표시하지 않는다.
- 최종 Artifact를 로컬에서도 실제/합성 각각 이미지와 CSV 개수·메타데이터·해시로 대조했고 운영 영수증/예약 생성이 없음을 확인했다.
- 실제 Telegram API 응답·SENT·message_id는 **실발송을 하지 않아 미검증**이다. 기존 승인 경계와 운영 중복 방지를 우회하지 않았다.

## 정기 실행과 08:45 확인

- 최신 main의 `cron: '0 23 * * 1-5'` = KST 화~토 **08:00**. permissions·concurrency(cancel-in-progress false)·35분 timeout·예약 설정을 변경하지 않았다.
- schedule 이벤트 100개(2026-11-19~24)를 확인했다. 대상 workflow의 과거 [11/20 성공 44664347776](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/44664347776)과 [11/21 실패 44859198911](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/44859198911)을 확인했다.
- 11/21 실행은 KST **12:04:17 생성**, 약 7분 뒤 전달 검사에서 `FINANCE_FIRST_MANIFEST_NOT_VALID`로 실패했다. KRX 수집 성공과 최종 전달 실패를 구분한다. 지연 생성은 관찰했지만 GitHub 내부의 특정 지연/누락 원인은 확인할 수 없었다.
- 새 08:00 설정 반영 후 첫 예정 실행은 **11/25 08:00 KST**, 아직 관찰 전이다. 이번 PR 수동 성격의 격리 검증 성공을 schedule 성공으로 간주하지 않는다.
- 기존 08:45 운영 확인은 **활성**, 다음 **11/25 08:45 KST**, 월~금 읽기 전용이다. 일정·활성 상태·프롬프트를 변경하지 않았다.
- **알람 본문에는 예전 07:00 설명이 남아 있다.** 또한 새 승인 범위 필드가 아직 명시돼 있지 않다. 운영 보호 범위 때문에 이 세션에서 알람을 수정하지 않았다. 운영 확인 시 최신 main의 cron과 `operational_status`, `approval_required_count`, `approval_financial_complete`, `nonblocking_financial_unverified_codes`, `delivery_result.json`을 우선해야 한다. 시간 경과만으로 완료/전송을 추정하면 안 된다.
- 08:00부터 08:45까지 완료를 보장할 수는 없다. 지연/미완료이면 관찰 대기로 표시하며 자동 재발송·신규 예약을 추가하지 않는다.

## 보호와 남은 작업

main·운영 원장·모든 기존 receipts 파일 변경 없음. 원장 SHA-256 `c6f7cae01241f50e21443b66957115aed4ae711409e7ee67bf8a621a66ee9270`, 기존 20261119 영수증 `9fb797c04cb374d9e3c76607daffc5e7b1df20a94c73f5bdf3fdc9e54f972792`, 기술 계산 파일 `bd527819f2958faa1d59f08f79c384712a0f2bc981e34802600c5934fc066ea2`, 세션 정책 `5b90931ef2767af4f1be0105e4b6c4ac9735943859bcec110bcd1cad76f54fc6` 보존을 확인했다.

1. **필수 기능 오류**: 이번 실제 11/23 경로에서 미해결 차단 오류 없음. 운영 main 적용은 별도 승인과 배포 판단이 남아 있어 수행하지 않았다.
2. **운영 제한/후속 확인**: 새 08:00 실제 schedule 관찰, 승인된 경로의 실제 Telegram 전송, 08:45 본문의 구시각 및 새 정책 정합성, 11/24 이후 실제 자료. 4개 관찰 기업은 향후 진입 후보가 될 때 재무 검토를 완료해야 한다.
3. **유지한 자료 한계**: 수집 시각을 과거 공시일로 소급하지 않으며 불변 PIT 완전 재현을 주장하지 않는다. 기존 정규장·기업행위 독립 인증 미검증 플래그를 유지하고 가격 이상/불완전 시리즈를 제외한다.
4. **현재 불필요**: 전 재무 엔진 재개발, 모든 업종 주석 완전 자동화, 새 유료 API·서버·키움 연결, 수익률 백테스트·가상매매·자동 주문. 추가하지 않았다.

검증한 PR 코드의 판정은 **PRODUCTION_READY_WITH_LIMITATIONS**다. 실제 main 배포 완료나 Telegram 실발송 검증 완료를 뜻하지 않는다.
