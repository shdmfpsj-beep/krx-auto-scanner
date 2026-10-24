# KRX C3 / K100 — 무료 주식분석 자동화

## 최신 v5.9 수익성 검증 프로토타입 (2026-10-24)

- [v5.9 연구·테스트 보고서](docs/FIVE_DAY_SHADOW_V59_20261023.md) · [24개 자동 안전테스트 포함 전체 재생 성공 #40098931203](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40098931203) · [일일 v5.8→v5.9 자동연결 성공 #40099062677](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40099062677).
- 23일 선정 82종목의 *과거* 기술신호 196개를 연구용 모의 체결. 1차·2차 대체안 392개 중 비용 반영 **2R 이상 구조 신호 84개, 가상 체결 1개**. **목표가에 닿았어도 거래비용 후 순손실인 64건**도 기록.
- **종목선정 편향 및 정규장 일봉 미인증**: 위 성과를 승률·예상 급등확률·실전 수익률로 사용하지 않는다. 2R 충족 집단의 1건만 체결된 결과를 `승률 100%`로 표시하지 않음.
- 당일 기술신호 17건의 1차/2차 대체 계획을 `forward_seed_v59_asof.csv` **34행**으로 생성하되, 23일 이후 미래 5거래일 미관찰로 **체결·수익률 미정**. 1차 후 2차 물타기 금지.
- [무료 일일 연계 GitHub Actions](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/shadow_five_day_v59_daily.yml): v5.7 날짜와 v5.8 완료된 가격 연구 실행번호를 그대로 인계받아 가상 연구와 미관찰 추적만 실행. **CASH/BUY 승인 0건**.
 

## 최신 v5.8 3가지 타점 비교와 1·2차 구조진입 (2026-10-24)

- [v5.8 23일 재생 및 매수 보류 근거](docs/ENTRY_STRATEGY_V58_20261023.md).
- [전체 자동 테스트·정규장 원본 연결 성공 #40095818288](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40095818288) · [타점 안전 테스트 15/15 #40095664047](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40095664047).
- 82종목 × 3개 매매법 = 246행 평가. 첫 눌림 재돌파 0건 / 돌파 후 재시험 1건 / 상승추세 눌림 16건. **비용 반영한 1차·2차와 구조손절·근거리 2R을 동시에 통과한 종목 0**.
- **손절 먼저 → 조건부 1차가격 → 1차 미체결 시 2차 대체가격 → 실제 이전 60일 가까운 저항 → 각각의 비용차감 2R** 순서. 2차를 물타기로 자동 집행하지 않는다. 일봉 지지가 확인되지 않으면 가격을 만들어 채우지 않는다.
- 실행가능성 검사: 1차 진입가가 최근 종가보다 1ATR 이상 낮으면 `WAIT_DEEP_PULLBACK_NO_CHASE`; TOP5 억지 선정 없이 `CASH`.
- [일일 무료 자동 연구 워크플로](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/entry_strategy_v58_daily.yml)는 성공한 v5.7 가격 진단에서 **거래일과 원본 수집 실행번호**를 넘겨받아 이어서 실행. 매수/손절 기준은 시장 독립인증 미완료로 **연구용**이며 계좌·주문 연동은 없다.


## 최신 v5.7 가격출처 정밀감식 (2026-10-24 실행 성공)

- [v5.7 전체 보고서: 10월 23일 정규장 가격 불일치 59건 정밀분류](docs/REGULAR_SOURCE_V57_20261023.md)
- [GitHub Actions 실제 성공 #40085866717](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40085866717) · **신규 테스트 12/12 통과**.
- [날짜 자동결합 v5.7 실행 성공 #40086156734](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40086156734) · 서로 다른 수집 작업의 **실제 거래일이 일치할 때만** 가격 비교. 날짜가 다르면 보고를 차단.
- 공통 81종목 중 **22개 OHLC 일치, 34개 종가만 불일치, 25개 고저가도 불일치**. 그중 14개는 다른 쪽 고저가 범위를 이탈한 종가. 불일치 원인 확정은 **미완료**.
- KIS KRX 정규장 분봉 `J`만 선택적 교차검증할 수 있는 엄격한 날짜/09:00~15:30 증거 검사 개발. 23일 원본에 유효 분봉이 없어서 인증 **0개**.
- **정규장 독립 출처 미확인 → CASH / 자동 BUY 없음.** 외국인·기관 매수는 선택적 참고. 1차·2차·손절가 연구계산은 실거래 지시가 아님.


## 최신 개발 v5.6 (2026-10-24 · 10월 23일 원본 고정 재생)

- **[v5.6 전체 가격 대조 및 첫 눌림 최종 복기](docs/FIRST_PULLBACK_V56_20261023.md)** — 이전 v5.5의 15개 사례 표기·구형 R:R보다 우선.
- **[GitHub 실제 실행 성공: 24개 단위 테스트 + 원본 재분석](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40075553719)**.
- 82개 기술후보 중 정상 23일 OHLC 81개, **두 자료 공통 81개 중 종가 불일치 59개 전체 개별 표시**; 050090 비정상 0원 OHLC 감지.
- 23일 첫 눌림 재돌파 확정 **0종목**; 정규장 세션 인증 미완료, 신규매수 **CASH**. 눌림 관찰은 재돌파 후보로 승격하지 않음.
- 1차 진입과 손절 위험 양쪽에 비용 반영. 원본 시세와 증권계좌가 확인되기 전에는 가격이 주문가로 승인되지 않음.


## 2026-10-23 첫 눌림 연구 v5.5 (2026-10-24 테스트 성공)

- [최종 개발·23일 검증 보고서](docs/FIRST_PULLBACK_V55_20261023.md)
- [무료 첫 눌림 자동 실행 및 모바일 보고서](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/first_pullback_v55_free.yml)
- 23일 기술 후보 **82개 → 상승전환 26개, 눌림 관찰 3개, 확정 재돌파 0개, 매수 0개**. 13개 자동 단위 테스트 통과.
- 정규장 OHLC 독립 인증 및 59/81 종가 충돌 해소 전 **CASH**. 일반주식·실제 거래대금 검증 및 비용 반영 2R 미충족 종목은 TOP5 강제 선정하지 않음.
- 사용 중인 무료 GitHub Actions와 기존 소스 아카이브만 재활용. 데이터 수집 성공·분석 테스트 통과·매수 승인·수익 증명은 서로 다른 단계.

> **2026-10-24 기준: 무료 GitHub Actions 버전 / 자료 검증 단계. 자동매매·매수승인은 꺼져 있습니다.**

## 안드로이드에서 확인하기
- [GitHub Actions 실행 이력](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions)
- `KRX regular-only 18:00 safe final report` → `krx-regular-only-18h-final` 아티팩트 → `regular_only_final_mobile.md`
- `KRX daily candidate scan` → `krx-scan-report` 아티팩트 → `v84_price_integrity_audit.json`
- `KRX sector pipeline daily health audit` → `sector-pipeline-health` 아티팩트
- [무료 가격검증 자동 테스트 (5건 통과, 2026-10-24)](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40065565154)

## 운영 원칙
1. 기존 유료 클라우드 및 상시 작동 노트북 요구 없음. 일반 GitHub Actions 호스팅을 사용합니다.
2. KRX 정규장 **09:00–15:30** 시세·거래대금만 실전 전략 자료로 인정합니다. 장후 시간외·애프터마켓은 별도 진단만 합니다.
3. 키움 REST API는 GitHub 공유 실행기의 가변 출구 IP 때문에 **기본 데이터 경로에서 제외**합니다. 키움 APP KEY가 있어도 IP 인증이 통과했다는 의미가 아닙니다.
4. 외국인·기관 순매수 데이터는 없으면 `NOT_PROVIDED`로 기록하고 임의 추정하지 않습니다. 누락만으로 섹터 평가를 감점하지 않습니다.
5. 일봉 65개, 시장 자료 세션 보증, 섹터 TOP3·개별종목 최종점수(80/100 이상), 일봉 구조손절→1·2차 진입가→거래비용 반영 손익비 순서로 평가합니다. 증거 부족/진입 불리 시 `CASH`.
6. C3 1종목 집중, K100 기존 Core와 신규 Tactical 별도 관리. 모든 계좌 주문은 수동이며 `trade_approved=false` 유지합니다.

## 2026-10-24에 반영한 무료버전 수리
- `.github/workflows/sector_pipeline_health.yml`: 테스트가 필요로 하는 워크플로 자체를 안전한 sparse checkout 목록에 포함
- `.github/workflows/opendart_v91.yml`: 비정상적으로 긴 과거 저장소 경로가 전체 checkout을 깨던 문제를 우회
- `.github/workflows/opendart_v942.yml`: 같은 방식으로 제한적 금융·공시 연구 워크플로 복구
- `scripts/krx_price_integrity_v84.py`: 존재하지 않아 스캔이 중단되던 가격 품질 확인 스크립트 신규 복구. 동일 제공자 내부 가격비교와 날짜가 적힌 수동 교차검증을 구분하고, 일치해도 정규장 가격 인증이라고 주장하지 않음
- `scripts/test_krx_price_integrity_v84.py` + `free_price_integrity_checks.yml`: 가격충돌, 기준일 불일치, 오인된 매수승인, 자료 일치 사례를 검증하는 무료 자동 테스트
- `.github/workflows/daily.yml`: 위 스크립트·테스트를 정규 스캔에 연결

## 아직 완료되지 않은 부분
- GitHub 예약 실행은 지연될 수 있습니다. 2026-10-23 KRX 정규장 관찰 작업은 16:15 KST에 시작하여 `MISSED_REGULAR_ISOLATION_WINDOW`로 판정되었습니다.
- 날짜만 반환하는 PyKRX 데이터가 정규장 시세만 포함한다는 인증은 아직 없고, 일부 KIS 분봉의 확인으로 2,600여 종목 전체를 검증할 수 없습니다.
- 2026-10-24 자동 **테스트 성공**은 실제 2026-10-26 장중/종가 수집 성공이나 5거래일 수익 검증이 아닙니다.
- 연구 점수(섹터/기술 예비점수)와 실제 주문 승인(개별 종목 최종 80점)은 구분합니다. 수익률을 보장하지 않습니다.

분석 설계 세부사항: [MASTER_SECTOR_FIRST_20261022.md](docs/MASTER_SECTOR_FIRST_20261022.md)
