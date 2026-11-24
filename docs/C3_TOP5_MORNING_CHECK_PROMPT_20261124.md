# C3 TOP5 + WATCH5 · 기존 08:45 운영 확인 본문

Task `6ae53e1be3848191b8bdc818036ed09c`에 2026-11-24 21:55:44 KST 적용 완료. 기존 제목·월~금 08:45 KST 일정·활성 상태를 유지하고 본문만 보강했다. 다음 확인은 2026-11-25 08:45 KST다. 새 알람 없음.

---

한국시간 기준 최신 운영 대상 KRX 거래일에 대해 ‘강현AI PRO · C3 TOP5 운영 확인’을 작성하라. 읽기 전용이다. GitHub 코드·원장·영수증 변경, workflow 재실행, 매매 주문, Telegram 발송/재전송, 새 알람, 수익률 백테스트·반복 연구를 하지 않는다. 사용자가 직접 매매한다.

연결된 GitHub shdmfpsj-beep/krx-auto-scanner의 최신 main SHA, .github/workflows/c3_top5_daily_telegram.yml, 최근 대상 workflow의 실제 run_id/head_sha/event와 생성·시작·완료 시각, job logs, Artifact를 직접 확인한다. 실제 main에 적용된 모델과 PR 검증 모델을 구분한다. PR 검증 성공은 운영 배포 완료나 schedule 성공이 아니다.

현재 GitHub cron은 '0 23 * * 1-5', UTC 월~금 23:00 = KST 화~토 08:00이다. 이 운영 확인의 기존 일정은 월~금 08:45 KST다. 월요일에는 금요일 거래일의 토요일 실행을 읽을 수 있다. 최신 main의 실제 cron이 달라졌다면 그 설정을 우선하고 임의로 변경하지 않는다. GitHub schedule은 지연·누락될 수 있다. 08:45가 됐다는 이유만으로 실행·수집·전송 완료를 가정하지 않는다. 생성/완료 기록이 없거나 진행 중이면 ‘정기 실행 관찰 대기’다. 수동·PR·push 실행과 schedule을 구분한다.

우선 execution_outcome.json, financial_selection_research.json, finance_first_delivery_manifest.json, candidate_decisions.json 및 CSV, all_candidate_report/manifest.json, delivery_result.json을 교차 확인한다. receipt.json과 entry_geometry_audit.json은 원본/기술 근거다. 거래일·양 시장 범위·60세션·중복·무효 OHLCV·가격 불연속 진단을 읽고, 공식 수정주가/기업행위 또는 과거 PIT 완전 인증을 근거 없이 완료로 쓰지 않는다.

새 정책 EXECUTABLE_FINANCIAL_APPROVAL_V1에서는 다음을 구분한다.
- 전체 기술 관심 후보의 재무 관찰: PASS, REJECTED_FINANCIAL_RISK, REVIEW_REQUIRED, ERROR와 각각의 근거를 보존한다.
- 최종 승인 필수 범위: approval_required_count 및 approval_required_codes, approval_financial_complete를 확인한다.
- 비승인 관찰 미확인: nonblocking_financial_unverified_codes와 technical_approval_scope의 실제 가격·공집합·정확한 구조손절 위험·기존 WATCH 거리 근거를 확인한다.
- 승인 필수 후보가 0이고 진입 불가 근거가 모두 검증됐으면, 관찰 미확인 기업이 남아도 CASH_NO_ELIGIBLE은 정상일 수 있다. 이를 재무 미확인 기업의 PASS로 설명하지 않는다.
- ENTRY_READY/NEAR_ENTRY의 필수 재무가 미완료면 HOLD_FINANCIAL_UNVERIFIED다. 근거 없는 기술 탈락/가격 자료 부족은 HOLD_DATA_INCOMPLETE, 인증·원본 무결성·시스템 실패는 ERROR다.
- 원장 중복 제한을 포함해 재무 PASS + 유효 진입 + 구조손절 위험 5% 이내인 ENTRY_READY/NEAR_ENTRY만 최대 5개다. WATCH를 자동 승격하거나 숫자를 채우지 않는다.
- all_interest_financial_complete와 approval_financial_complete는 다른 범위다. 전체 관찰의 미확인을 삭제하거나 정상 CASH를 시스템 오류와 혼동하지 않는다. 오래된 legacy 출력에 새 모델 필드를 추정해 넣지 않는다.

operational_status는 TOP5_READY / CASH_NO_ELIGIBLE / HOLD_FINANCIAL_UNVERIFIED / HOLD_DATA_INCOMPLETE / ERROR 중 실제 값으로 보고한다. GitHub의 초록 표시와 프로그램 COMPLETED만으로 TOP5나 발송 성공을 단정하지 않는다. HOLD는 정상 차단 처리일 수 있다. ERROR를 정상 CASH로 바꾸지 않는다.

Telegram은 delivery_result.json의 status/stage/telegram_photos_sent/photos 종목·이미지 해시·실제 message ID를 기존 영수증과 대조한다. SENT와 유효한 실제 message_id가 있어야 전송 성공이다. CASH는 정상 미전송, DRY_RUN은 실전송 미검증, HOLD/ERROR는 매수 이미지 발송 금지다. 부분 실패는 확인된 성공 수와 실패 단계만 보고한다. 중복 방지를 우회하거나 자동 재발송하지 않는다.

최종 적격 종목이 있을 때만 종목명/코드/기준 종가/매수 하단·상단/구조손절/R1·R2/위험률/ENTRY_READY·NEAR_ENTRY/유효기간을 실제 Artifact 값으로 짧게 제시한다. 진단 PNG와 최종 TOP5 PNG를 구분한다. 범위 미도달 PASS, 종가가 구조손절 미만이면 다음 거래일 사용자가 직접 정리하는 규칙을 유지한다.

보고에는 기준일, main SHA와 run SHA, 실제 event와 실행 시각, 프로그램/선정/전달 상태, 관심 후보·재무 판정 수·승인 필수 수·TOP5 수, PNG·실발송 수, 실제 Actions/Artifact 링크와 남은 확인만 간결히 적는다. 새 정기 실행이 아직 없으면 ‘정기 실행 관찰 대기’를 명시한다.

추가 WATCH5 운영 확인: 정식 TOP5와 WATCH5를 분리해 실제 동일 기준일 Artifact의 watch_delivery_result.json, watch5/manifest.json 및 별도 receipts/c3_watch5_daily/{asof}.json을 확인한다. candidate_decisions.json/CSV, financial_selection_research.json, entry_geometry_audit.json, all_candidate_report/manifest.json과 교차 대조한다. WATCH 전용 결과가 없는 과거 실행은 미실행으로 보고하고, 기존 통합 CI 성공을 WATCH5 실행 성공으로 추정하지 않는다.

WATCH5는 실제 재무 PASS, 기존 WATCH 및 valid_entry(allow_watch=True), 유효한 매수범위·구조손절, 정확한 위험5%이내, (기준일종가-매수범위상단)/기준일종가×100 이격률2%초과~5%이하, 기존 기술·과열·중복 제한이 모두 증명된 종목만 최대5개다. financial_eligibility=WATCH_ONLY는 재무 탈락을 뜻하지 않으므로 실제 financial_verdict와 원본 재무 근거를 확인한다. composite_score 내림차순, 동점은 이격률 오름차순·코드 순이다. 정식 TOP5와 중복 금지, WATCH는 매수 승인·정식 선정 이력·매매 원장 기록이 아니다.

정상 CASH_NO_ELIGIBLE에서도 적격 WATCH5는 별도 관찰 결과로 보고한다. HOLD/ERROR/upstream 실패는 WATCH 발송 차단 상태를 확인한다. 정식 TOP5 0~5장과 WATCH5 0~5장, 전체최대10장 및 실제 PNG 해시·메타데이터·종목·기준일·유효기간 일치를 각각 확인한다. 각 WATCH의 종목명/코드/종가/매수범위/구조손절/R1/R2/위험률/이격률/기준일/유효기간을 실제 값으로 보고하고, 원본에 없는 R2 등은 미확정으로 표시한다. 검증된 WATCH PNG 또는 실제 열 수 있는 링크를 첨부하며 반드시 ‘WATCH5 관찰용 — 매수 승인 아님’을 명시한다.

TOP5 delivery_result.json과 WATCH watch_delivery_result.json의 전송 결과를 각각 보고한다. WATCH status/stage/selected_count/telegram_photos_sent/photos의 실제 telegram_message_id, 목적 채팅 일치 여부 및 이미지 해시를 별도 WATCH 예약과 대조한다. SENT와 실제 유효한 message_id가 확인돼야 전송 성공이며 DRY_RUN·EMPTY·BLOCKED·NOT_APPLICABLE·ERROR·PARTIAL_ERROR는 구분한다. 부분 실패는 확인된 성공 수/ID와 실패·불확실 단계·사유를 기록하며 자동 재전송을 요구하거나 수행하지 않는다. GitHub 실행이 초록이어도 WATCH 결과가 실패일 수 있으므로 별도 결과를 반드시 읽는다. 기존 TOP5 영수증과 WATCH 예약을 혼합하지 않는다. 이 알람은 계속 읽기 전용이며 코드·원장·영수증 변경, 재실행, Telegram 전송/재전송, 새 알람을 수행하지 않는다.
