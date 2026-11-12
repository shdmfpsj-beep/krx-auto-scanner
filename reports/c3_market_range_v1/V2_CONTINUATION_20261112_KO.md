# 강현AI PRO — 매수 가능 범위 V2 지속 개발 검증 (2026-11-12)

## 사용자 최신 원칙
- **'단 한 번만 진입' 의무 삭제**. 진입 횟수·체결 수량·시점은 사용자가 정한다.
- AI가 제공하는 것은 **하나의 연속된 매수 가능 가격 범위**, 구간 전체의 손절 위험, 가까운 유효 저항 R1/R2, 진입 보류·무효화 사유이다.
- 고정 1차/2차 분할매수, 50:50 분할 또는 추가매수를 AI가 자동 지시하지 않는다.
- **자동 주문·실전 BUY 승인 없음**. 자율 주문 정책은 위험 관리 게이트를 우회하지 않는다.
- 과거 자료와 연구 기록은 삭제하지 않고 구버전 원본 그대로 보존한다.

## 실제 반영한 사항
- 코드 및 프로토콜: `C3_MARKET_ENTRY_RANGE_V2` 및 `USER_DISCRETION_NO_PRESCRIBED_COUNT` 채택. `maximum_purchases_per_opportunity=1`, `additional_purchases_allowed=false` 등의 거래 횟수 의무 삭제.
- 모바일 PNG: "한 번만 진입", "추가매수 금지" 문구 대신 사용자 주문 방식 자율 및 자동 주문 없음으로 수정.
- 전방 연구 원장: 단일매수 의무를 강제하던 필드 검사 삭제. 해시 기반 불변 원장·중복/변경 차단 기능은 유지. 기존 성공/실패 연구의 원본 기록은 수정하지 않음.
- `evaluate_user_fills(plan, fills, planned_capital_krw)` 추가: 사용자가 입력한 가상 가격·정수 수량의 **개수 제한 없이** 유효 가격 구간, 총매수비용, 가중평균 가격, 미투입 계획자금, 구조손절까지의 합산 위험과 비용 반영 R1 손익비를 계산한다. 잘못된 호가·가격·수량, 계획자금 초과는 거부한다. 시장 갭으로 실제 손실이 더 커질 수 있으며 **실제 체결을 증명하거나 주문을 생성하지 않는다**.
- 상·중·하단 3가지 과거 **독립 가격 시나리오**는 연구 비교로 유지하나 실전 매수 횟수 제한을 뜻하지 않는다.

## 실제 GitHub Actions 검증
- 검증된 코드 커밋: `a337e1b869bf33a06f39594ce573949127c8f3bd`, 이후 README만 변경한 최종 브랜치 커밋 `8d35f2d38d54434c0cb0c70905975964fb6d3702`.
- [연구 전체 실행 #43189300566](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43189300566): **SUCCESS**, 11/11 원본 재현·글로벌 분석·차트 생성·원본 해시 보존 확인.
- [독립 PR 테스트 #43189343650](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43189343650): **SUCCESS**, 회귀 테스트 **167개 통과 / 실패 0건**.
- [전체 실행 아티팩트 #13929543440](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43189300566/artifacts/13929543440) ZIP SHA256: `2dd603730e06d6940bb417d9685d1d7614c4b4b400d5773bfed017a347e761aa`.
- 아티팩트 `evidence/market-range/report.json`는 model_version `C3_MARKET_ENTRY_RANGE_V2`, execution_policy `USER_DISCRETION_NO_PRESCRIBED_COUNT`이고 기존 강제 진입 횟수 키 없음.
- 모바일 WATCH PNG 2장 재생성: 삼성E&A/한진칼. 기준 주가 데이터는 **2026-11-11**이므로 11/12 신규 매수 추천이 아니다.
- 원본 68개 + 텔레그램 영수증 19개의 전후 보호 SHA256이 모두 `8a7757b621100aa3dff9b7bcc79a0bae22bea8238b397cc371aa5aaf1d623820`로 동일. `main` 불변, 원장 쓰기0, 텔레그램 실제 요청0, 주문0.

## 최신 신규 거래일 데이터 점검
- 2026-11-12 **18:14 KST**에 연구 실행에서 당일 KRX 공식 API 재조회.
- KOSPI `stk_bydd_trd`, KOSDAQ `ksq_bydd_trd` 모두 HTTP200이나 `OutBlock_1=[]`, 반환 종목 **0건**.
- `official_dataset_usable=false`, 정규장 전용 인증 미완료. 임의로 11/11을 11/12 신규 신호로 소급 전환하지 않음.
- 11/11 연구 WATCH(삼성E&A·한진칼), 연구용 매수범위 등 기존 결과는 **과거 재현 결과로만 유지**.
- 최근 완료 거래일의 **새 등록 원본·가격인증이 확보돼야** 이후 실제 관찰 후보와 새 날짜 전방 성과 원장을 생성할 수 있다.
- 모의 Telegram 0/1/2장만 검증되었고 실전송은 하지 않았다.

## 후속 순서
1. 새 완료 거래일의 KRX 공식 EOD/정규장 출처, 동일 실행 원본 등록과 이력 확보 상태를 다시 검사하고 실패 원인을 출처별로 분리한다.
2. 검증된 **신규 날짜**에서만 연구 WATCH 카드와 진입 범위를 생성하도록 일일 호출 경로를 연결한다. Telegram 발송은 사전 승인·중복 방지·실제 영수증 검증 전 불허.
3. `c3_range_forward_v1.py`의 append-only 신규 관찰/5·10·20거래일 업데이트를 영속 연구 저장소에 연결하되 과거 시뮬레이션을 전방 신호로 등록하지 않는다.

## 승격 판단
**연구 기능 수정·실행 검증 완료 / 자동 실전 BUY·Telegram 승격 보류**.
