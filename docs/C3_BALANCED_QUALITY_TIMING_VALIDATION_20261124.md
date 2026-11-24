# C3 TOP5 Balanced 최종 통합 검증 — 2026-11-24

최종 운영 판정: **NOT_READY**. main 병합 및 운영 기본 모델 전환을 수행하지 않았다.
이 문서는 PR #202의 11/23 보고서를 대체하는 최신 상태다. 과거 11/20 정상 CASH 검증은 그 날짜와 좁은 재무 요청 범위의 기록으로 보존한다.

## 코드와 보호 경계

- 저장소: shdmfpsj-beep/krx-auto-scanner, PR [#202](https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/202).
- 브랜치: `feat/c3-balanced-quality-timing-20261123`.
- 기준 main: `ab1ca30bfe24f0e7cbc197e1db9468d6807f1f6a`; PR #201 반영된 main을 개발 브랜치에 통합했다. main ref를 갱신하지 않았다.
- 검증 코드: `b5744003b5c387142befbb41462c1379e9dca5d5`.
- 이 PR은 병합 후 Balanced 기본 사용을 **제안**한다. 현재 main은 기존 legacy 동작이다. 필수 미확인이 남아 있으므로 이 기본 전환을 지금 배포하면 안 된다.
- 운영 원장, 기존 전송 영수증, `scripts/c3_top5_session_policy.py`, 운영 concurrency, Telegram 예약/발송/중복 방지 로직, 08:00 cron, 08:45 ChatGPT 운영 확인은 보존했다. 추가한 발송 관련 필드는 판정 메타데이터뿐이다.
- `reports/c3_paper/paper_ledger.json` SHA-256: `c6f7cae01241f50e21443b66957115aed4ae711409e7ee67bf8a621a66ee9270`.
- `receipts/c3_top5_daily/20261119.json` SHA-256: `9fb797c04cb374d9e3c76607daffc5e7b1df20a94c73f5bdf3fdc9e54f972792`.
- 주문, 가상매매, 수익률 백테스트, 유료 서비스, 운영 채팅 시험 발송을 추가/실행하지 않았다.

## 실제 수정

| 파일 | 변경 |
|---|---|
| `scripts/c3_top5_financial_selection.py` | 기술적 관심 후보 전체의 별도 재무 요청 범위(기존 30개 예산), PASS/확정 탈락/미확인/ERROR 및 전체 운영 판정, 진입 적격 종목만 TOP5 허용, 미심사 예산 초과 보류, 선정 JSON에 실행 가격 포함 |
| `scripts/c3_top5_dart_bridge.py` | Balanced 요청 범위 메타데이터 전달, legacy 호환 유지 |
| `scripts/c3_balanced_financials.py` | 일시적 네트워크 실패 재시도, 해시·24시간 TTL 기업코드 캐시, 실제 비유동 차입금/사채 계정 및 유동성사채 수집, 중복/미분류 차입 항목을 총차입금으로 오인하지 않음, 금융업 조기 별도 검토, 기대 공시 식별자와 오류 근거 보존 |
| `scripts/c3_entry_geometry.py` | 기존 지지선/ATR 공식과 방향별 호가 반올림 보존. 교집합이 없으면 실행 구간 없음. 실제 60봉으로 MA5/10/20/60·ATR·지지선·가격·위험 재대조 |
| `scripts/c3_candidate_decisions.py` | 후보별 판정·탈락 사유·공시 기준 및 전체 집계 JSON/CSV |
| `scripts/c3_balanced_validation.py` | 실제 가격 Artifact 재사용, 9개 관심 후보 연결, 중복 이력 읽기 전용 확인, 전 후보 이미지 해시/메타데이터·선정 JSON/CSV 대조, 기존 전달 경계 NO SEND 실행 |
| `scripts/c3_all_candidate_report.py` | 기존 PNG 양식에 재무/제외 상태 및 MA·거래량 메타데이터, 합성 검증 표시 |
| `scripts/c3_dart_document_evidence.py` | 깨진 일반 공시 마크업의 주석 표 복구(자동 적격 근거로 사용 안 함). XBRL은 엄격 파싱 유지. 원문 예산은 확정 탈락 보조자료보다 ERROR·미확인 WATCH 우선 |
| `.github/workflows/c3_top5_daily_telegram.yml` | Balanced 실행 연결·캐시·후보 보고서, legacy 선택 유지. 운영 시간/발송 경계는 보존 |
| `.github/workflows/c3_balanced_quality_validation.yml` | 검증된 최신 가격 Artifact 재사용, 실제 OpenDART 및 합성 TOP5 양성 경로 증거, 새 PR 버전에서 중복 검증 취소, 문서 전용 갱신 시 API 재실행 회피 |
| `scripts/test_c3_operational_integration.py` | 이번 21개 회귀 테스트와 합성 TOP5 증거 생성 |

기존 PR의 100점 모델, 현금흐름/FCF 계산, 업종 분류, 공시/캐시 무결성, PNG와 기술 선정의 검증 코드는 재사용했다. 100점 미만 일괄 탈락, RR 2배 필터, 분할매수는 추가하지 않았다. 기존 300% 부채비율·5% 진입 위험 상한은 변경하지 않았다. 미분류/누락 차입금, 금융원가, CF 이자 조정액을 임의의 총차입금/정식 이자비용으로 대체하지 않았다.

## 실제 시장 자료와 판정

가격은 [기존 실행 45294238532](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45294238532)의 실제 KRX 60거래일 결과를 재사용했다. 새 전수 수집으로 표현하지 않는다.
가격 Artifact [14874774941](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45294238532/artifacts/14874774941), ZIP SHA-256 `692d1732a7395989842f5b330167b6610921293df35096889bf7ecf18bac35a7`을 다운로드 후 검증했다.

- 기준 거래일: 2026-11-23. 검증 당시 한국시간 장중이므로 최신 완료 거래일도 동일하다.
- 가격 범위: 2026-08-26~2026-11-23, 60거래일. KOSPI 935 + KOSDAQ 1,836 = 2,771종목, 유효 60봉 2,488종목.
- 실제 기술적 관심 후보 9, 재무 요청 9. 기존 main 실행의 재무 요청 0을 관심 후보 심사로 확장했다.
- 가격 데이터는 일자·중복·OHLCV·거래정지 의심/무거래·35% 이상 불연속 기본 검사를 통과한 범위다. 공식 정규장/수정주가·기업행위 독립 인증 및 완전한 과거 PIT 인증은 주장하지 않는다.
- 실제 OpenDART는 이번 세션에서 조회했다. 동일 접수번호의 검증 스냅샷은 재사용하며 수집일을 공시일로 소급하지 않았다.

최종 코드 실행에서도 아래 상태를 확인했다. PASS 0 / 확정 탈락 2 / 검토 필요 6 / ERROR 1, 최종 TOP5 0, 전체 `ERROR`다. 정상 CASH 또는 TOP5_READY로 표시하지 않았다.

복합 후보 판정은 ENTRY_READY 0 / NEAR_ENTRY 0 / WATCH 0 / REJECTED 6 / REVIEW_REQUIRED 2 / ERROR 1이다. 기술 단계에서만 WATCH인 2개는 재무 미확인이 남아 복합 판정에서 REVIEW_REQUIRED가 된다. 단계별 수를 혼합하지 않는다.

| 종목 | 재무 판정 | 기술/자료 사유 |
|---|---|---|
| 대한항공 003490 | REJECTED_FINANCIAL_RISK | 연간 부채비율 339.878%, 최근 358.828%; 구간 교집합 없음 |
| 아시아나항공 020560 | REJECTED_FINANCIAL_RISK | 연간 1,370.194%, 최근 2,427.380%; 구간 교집합 없음 |
| 윈스테크넷 136540 | REVIEW_REQUIRED | 차입금 합계·정식 이자비용 미확인; 구조 위험 5.8972% |
| 메가스터디교육 215200 | ERROR | 기대 연간 접수 20260326000491, API 반환 20260318000849. 원본 일치 미검증; 구간 교집합 없음 |
| 롯데손해보험 000400 | REVIEW_REQUIRED | 금융업 전용 모델 필요; 구조 위험 7.0850% |
| 화천기계 010660 | REVIEW_REQUIRED | 필수 차입·이자·감사 근거 추가 확인; 구간 거리 2.91% |
| 아모레퍼시픽홀딩스 002790 | REVIEW_REQUIRED | 차입금 합계·정식 이자비용 미확인; 구간 거리 3.29% |
| 에스원 012750 | REVIEW_REQUIRED | 차입금 합계·정식 이자비용 미확인; 구조 위험 5.3159% |
| 태양금속 004100 | REVIEW_REQUIRED | 차입·이자·감사 및 유동성 보완 필요; 구조 위험 12.5628% |

자료 미확인 6개를 재무 불량으로 판정하지 않았다. 이미 입증된 부채비율 초과 2개는 보조자료 누락으로 확정 탈락을 취소하지 않았다.

매수구간 역전은 선택 지지선이 `MA20 + 0.25 ATR` 상단보다 높아 발생한 공집합이었다. 하단/상단을 바꾸거나 손절을 올리지 않았다. 원래 시도 가격과 구조손절은 진단에 보존하고 실행 구간은 null로 차단했다. 실제 봉 재계산에서 유효 WATCH 두 종목의 원래 가격/손절이 동일하고, 위험 초과 4개도 동일한 수치로 차단됨을 확인했다. NEAR_ENTRY는 기존 `(종가-상단)/종가 <= 2%` 정의를 유지한다.

## 실행과 증거

- 첫 확대 실행 [45300672035](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45300672035): 기업코드 다운로드 URLError, ERROR·미발송. 정상 CASH 아님.
- 재시도 보완 실행 [45301143148](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45301143148): 실제 9개 심사, PASS 0 / 확정 탈락 2 / 검토 6 / ERROR 1. [Artifact 14879546970](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45301143148/artifacts/14879546970), ZIP SHA-256 `4526dd174f34c6746c9f5217795932495027afb0e590016c2543460f3a738f65` 확인.
- 최종 코드 실행 [45304047889](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45304047889): **failure / 실제 전체 ERROR**. 테스트 성공과 시장자료 통합 실패를 구분한다. 오류를 무시하여 초록색 실행으로 만들지 않았다.
- 최종 [Artifact 14880042291](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45304047889/artifacts/14880042291), ZIP SHA-256 `11edf8cd46d178d5c8700d386c772a74aa828e69f053d8fee7b5f0ef2bcf917b`을 직접 다운로드하여 검증했다.
- 실제 산출물: `financial_pool_input.json` 9개, `financial_pool_gate.json` 9개 판정, `candidate_decisions.json/csv`, `entry_zone_replay_audit.json` 9개 실제 봉 재계산, `financial_selection_research.json`, `top5.csv` 0행, `finance_first_delivery_manifest.json`, `delivery_result.json`, `receipt.json`, `all_candidate_report/manifest.json`과 진단 PNG 9장.
- PNG 9장 모두 해시·1400×1710 크기·기준일·메타데이터 일치 재검증. 실제 최종 선정 PNG는 0장이다.
- `c3_positive_fixture/`는 합성 Balanced 적격 5개·PNG 5개·CSV 5행·TOP5_READY·DRY_RUN·발송 0건을 별도로 보존한다. 5장 모두 동일한 검증기로 다시 확인했다. `input_kind=SYNTHETIC_NOT_MARKET_SELECTION`, `live_dart_observation=false`, source_mode 및 PNG 문구에 합성 입력임을 표시했다.
- 최종 테스트: 로컬 및 최종 Actions에서 **194개 통과, 실패 0**. 기존 173개 대비 이번 회귀 21개. [별도 legacy CI 45304047755](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/45304047755)의 115개도 통과했지만 중복 합산하지 않았다.
- 독립 합성 입력은 실제 종목 선정이 아니다. 적격 5개 → PNG 5개 → JSON/CSV/이미지 해시·메타데이터 대조 → Telegram DRY_RUN. 양성 입력의 표기/Manifest에도 SYNTHETIC을 명시했다.
- 실제/합성 모두 Telegram 발송 0건, 운영 예약·영수증 생성 0건. 실제 message_id/SENT·Telegram API 실응답은 미검증이다. 기존 중복·해시·메시지 ID 검사는 오프라인 부정 테스트로 보존했다.
- 실제 계정 확장 결과 아시아나항공의 리스 제외 차입금 합계 1,625,550,944,633원과 그중 유동성사채 189,144,017,923원을 별도 원본 계정으로 확보했다. 다른 미분류 차입 항목·누락 사채를 0으로 대체하지 않았다.
- 공시 원문 보완: 아모레퍼시픽홀딩스 CFS 주석 16개 표, 화천기계 OFS 주석 11개 표를 수집했다. 단위·기간·의미 자동 검증 전이므로 적격/이자보상 판정에 사용하지 않았다. 과거 확보한 윈스테크넷 원문도 수정 파서로 재처리하여 9개 표를 확인했다.
- 메가스터디교육의 기대 접수 20260326000491은 `document.xml` 및 `fnlttXbrl.xml` 모두 OpenDART **014(파일 없음)**을 반환했다. 공개 DART 원문 링크의 별도 조회도 도구에서 접근되지 않았다. API의 다른 접수 자료를 기대 공시 자료라고 재표시하지 않았다.
- 기존 main 실행은 당시 좁은 실행 후보 범위에서 정상 CASH였다. 확대 재무 심사에서 나온 ERROR/HOLD를 정상 CASH로 덮어쓰지 않는다.

## 오전 8시 예약

- `cron: '0 23 * * 1-5'` = KST 화~토 08:00, 그대로 보존. default branch main, 최근 수동 실행 success, 운영 concurrency `cancel-in-progress: false`, timeout 35분, contents write 유지.
- 08:00 변경 커밋 ab1ca30은 **2026-11-24 08:56:46 KST**에 반영됐다. 오늘 08:00에는 이 설정이 없었으므로 새 설정의 첫 예정 시점은 **11/25 수요일 08:00 KST**다. 실제 schedule 성공은 검증 대기다.
- 이전 07:00 schedule은 [11/20 실행 44664347776](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/44664347776)이 11:57:05, [11/21 실행 44859198911](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/44859198911)이 12:04:17 KST에 생성됐다. 실행 생성 지연과 실행 후 API 오류를 구분했다.
- GitHub는 정각 고부하에서 schedule 지연/누락 가능성을 명시한다([공식 문서](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)). 이 저장소의 특정 누락 원인이 GitHub 내부 큐였는지 확정할 서버 증거는 없다. 시간 변경만으로 08:45 이전 완료를 보장하지 않는다.
- 08:45 ChatGPT 읽기 전용 운영 확인과 기존 예약은 변경하지 않았다. 누락 감지를 이유로 Telegram 재발송이나 새 예약을 만들지 않았다.

## 남은 필수 작업과 판정

1. 메가스터디교육의 기대 공시 원문과 API 데이터 버전 일치 검증 또는 정확한 공시 기준 자료 경로 확보. 기존 실패를 없애기 위해 접수번호 검사를 완화하면 안 된다.
2. 검토 필요 기업의 누락 차입금·정식 손익 이자비용·감사·유동성 근거를 확인할 수 있는 좁고 검증된 추출 경로. 기타금융부채/금융원가/CF 조정액 대체 및 누락=0 가정 금지. 건설 PF·금융업 전용 위험은 여전히 별도 검토다.
3. 실제 확대 심사 전체가 정상 CASH 또는 적격 TOP5로 종료되는 증거가 확보되기 전에는 Balanced 기본 모델을 main에 배포하지 않는다.
4. 11/25 이후 실제 08:00 schedule 생성·완료 확인. 실 Telegram SENT는 이번 승인 범위 밖이므로 향후 승인된 경로에서만 확인한다.

단위/양성 통합 경로가 동작하는 것과 실제 재무자료로 운영이 완결되는 것은 구분했다. 현재는 후자의 필수 증거가 부족하므로 **NOT_READY**다.
