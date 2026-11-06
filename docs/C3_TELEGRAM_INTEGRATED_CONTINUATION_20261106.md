# 강현AI PRO C3 TOP2 사진 전용 보고 — 구현 체크포인트

## 범위와 승인

이번 사용자 지시는 보고 시스템의 검증 후 운영 배포와 기존 강현 AI 그룹으로 과거 연구 예시 앨범 1회 발송을 명시했다. 이 범위의 PR만 검증 후 main에 배포한다. 연구 PR #30, 종목 선정/매수/손절, 연구 원장, 기존 스캐너 및 ChatGPT 평일22:30 알림은 변경하지 않는다. PR #31은 사용자가 이미 병합했다.

## 실제 중복 증거

- 42182176842(16:38 KST) / 42182271221(16:39): 각 `C3_TOP2_FOUR_IMAGE_ALBUM_DELIVERED` 확인.
- 42185606254(17:08) / 42186402466(17:15): 각 `C3_CLASSIC_FOUR_IMAGE_ALBUM_DELIVERED` 확인.
- 원인은 별도 임시 demo가 연속 push마다 receipt를 거치지 않고 직접 send_album을 호출한 것이다. 마지막 main에서는 이미 임시 workflow가 삭제되어 정식 c3_top2_telegram.yml만 남았다.
- 기존 정식 renderer는 종목당2장(총4장)과 첫 이미지 caption을 만들었다. 수동 test 모드는 별도 텍스트를 보냈다. 새 renderer에는 전송 함수를 두지 않고 하나의 notifier로 통합한다.

## 완료한 구현/로컬 검증

- 1400×2120 화이트/골드 종목당1장. 실제 캔들/거래량/5·20·60일선/실제 등락·매수/손절/저항·4개 이유를 한 카드에 통합했다. 2차 매수/미확인 재무·뉴스는 만들지 않는다. 화면 CASH/구조손절/이전 브랜드 표시는 제거하고 내부 CASH/주문금지는 유지한다.
- 예시는 11/5 미등록 삼성E&A·원익홀딩스다. 기존 KRX 11/4까지90봉과 정확한 SHA의 11/5 전체 KRX 캐시에서 해당 종목의 완전한 OHLCV 1봉을 연결한다. 원래 공식/캐시 전수 일치 증거를 재사용하고 가격 계열을 섞지 않는다. 91봉으로 계산하고 최근30봉을 표시해60일선도 모두 유효한 부분만 그린다.
- 운영은 실제 새 원본 날짜/시장 품질/등록 신호/암호화 결정의 해시를 검증하고 그 결정에 고정된 KRX 봉만 표시한다. NAVER/Yahoo history 대체는 제거했다.
- 기존 시간표(22:45/09:00), workflow_run, workflow_dispatch를 정식 workflow 하나로 유지한다. one-time 요청도 같은 workflow/동일 receipt 선점·전송 함수를 통한다. 별도 텍스트 알림 없음.
- durable receipt branch `delivery/c3-top2-telegram`: source date+fixed final report+chat fingerprint로 원자적 신규 claim을 먼저 커밋한다. 상태가 불확실하거나 결과 저장이 실패하면 claim을 남겨 재발송을 막는다. transport POST retry/redirect 없음. 기존 research Telegram receipt도 확인해 migration 중 중복을 차단한다.
- getChat으로 현재 Secret이 가리키는 그룹의 ID/종류/제목을 확인한 뒤 선점한다. Secret과 원본 chat ID는 로그/보고에 출력하지 않는다.
- request `integrated-white-gold-20261106`은 11/5 과거 연구 예시2장 허용이며 동일 요청 재실행은 중복 차단한다. PR 검증에서는 발송 Secret 없이 preview만 만든다. 실제 전송은 검증/시각 확인 후 배포 main push 때 한 번 시도한다.

## 다음 단계

로컬 관련 검사 → focused PR 생성/Actions 실제 preview 검증 → 이미지 확인 → 해당 PR만 main 배포 → 공식 sender의 1회 과거 예시2장 앨범 응답/receipt 확인 → 연구 브랜치에도 코드/증거 보존.

실제 발송/배포/Actions의 성공 여부는 아직 이 체크포인트에서 확정하지 않는다. 애매한 전송 응답에 자동 재시도하지 않는다. 이미 본 과거 백테스트나 전체시장 전수 대조는 반복하지 않는다.
