# 기존 08:45 운영 확인 본문 교체안

대상: 기존 ‘강현AI C3 TOP5 · 오전 운영 확인’ 알람.
**검토용 교체안이며 아직 기존 알람을 수정하거나 새 알람을 만들지 않았다.** 기존 월~금 08:45 KST 일정과 활성 상태를 그대로 두고, 본문만 아래 내용으로 맞추는 안이다.

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
