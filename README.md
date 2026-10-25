# KRX C3 / K100 — 무료 주식분석 자동화

## 최신 v6.6·v6.7 — KRX 가격출처 원인 추적과 120일 이력 재구성 (2026-10-25)

- **[v6.6–v6.7 실제 GitHub 분석 보고서](docs/PRICE_SOURCE_REBUILD_V66_V67_20261025.md)**.
- [v6.6 82종목 × 3방법 가격민감도 재생 성공, 10/10 테스트 #40158461663](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40158461663). 공식 KRX EOD와 v18의 OHLCV는 **82/82종목 정확히 일치**. 반면 복구 스캔의 **시가0·고가20·저가6·종가59·거래량64 종목**에서 차이. 마지막 1일만 공식 가격으로 교체 시 **기존 17신호→15연구신호, 패턴4건 변경, ATR14 21종목 변경**.
- **[v6.7 전체 120거래일 출처 일원화 성공, 9/9 테스트 #40158834723](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40158834723)**. 82종목 전부 날짜 매칭, **78종목에 역사적 OHLCV 불일치**, 그중 12종목은 일봉 무효. 120일 종가 2,099건·고가 1,119건·저가 913건 불일치. 동일한 v18 시장전체 120일 이력으로 계산한 연구 신호는 **17→13건**, 방법별 판정 24건 변경. 단, 120일 전체가 공식 API·정규장으로 인증됐다는 뜻은 아님.
- **[KRX 수집시각 차단·8/8 테스트 통과 #40159081214](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40159081214)**. 기존 `scripts/run.py`는 16:10 이후를 당일 완료로 오판했고 기존 복구 스캔은 16:45 KST 실행 예정. 이제 2026년 KRX 20:00 애프터마켓 종료를 고려해 **20:15 이후만 당일 완료 후보**, 자동 복구 스캔은 **20:45 KST** 실행. 스캔 전체는 다음 거래일에 확인해야 하며, 이번 성공은 오프라인 시각 정책 테스트 결과임.
- 종목별 `pykrx.get_market_ohlcv_by_date(...adjusted=True)`과 시장전체 `pykrx` 조회 **함수·수집시각 차이는 확인**했지만 시세 차이를 장후 거래/수정주가 탓으로 확정하지 않음. **원래 frozen 가격을 조용히 덮어쓰지 않고 모든 신규 BUY·자동주문 거부, CASH**.


## 최신 실제 KRX API 키 등록 후 3원본 대조 성공 (2026-10-25)

- **[실제 승인된 KRX OPEN API 호출과 KOSPI·KOSDAQ 2,764개 일봉 수집 성공 #40156628275](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40156628275)**. 인증키의 존재·승인과 실데이터 수집은 확인됨; 인증키 값은 어떤 보고서에도 기록하지 않음.
- **10월 23일 후보 82종목 3원본 대조:** 공식 KRX EOD = v18 **59종목**, 공식 KRX EOD = v18 = recovery **22종목**, 비정상 원본 일봉 **1종목**. 기존 59종목 종가 차이는 전부 KRX 공식 EOD와 **v18 일치 / recovery만 불일치**로 원본을 좁혔음. 그러나 v18과 KRX가 동일한 원천에 의존했을 수 있으므로 두 독립적 검증 완료로 주장하지 않음.
- frozen 기술신호 실제 16종목 중 **12종목이 recovery 종가와 다르며, 공식 KRX EOD·v18 종가는 일치**. 단 v18/공식 EOD가 정규장 15:30 종료 전용이라는 확인은 아직 없음.
- v6.5 인증키 미연결 `AUTH_KEY_NOT_CONNECTED` 상태는 **과거 실행 #40152003678에서만** 발생했으며, 지금은 `OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED`로 해소. [최신 v6.5 검증 문서](docs/KRX_OFFICIAL_EOD_V65_20261025.md)에 실제 수집 성공 결과도 기록.
- 남은 핵심은 **recovery 가격의 종가 차이 원인 분석(수정주가·수집원·장후 여부) 및 정규장 09:00~15:30 근거 확인**. 공식 KRX 일봉을 받았다는 이유만으로 매수·5일 기대수익을 승인하지 않음. **CASH / BUY 승인 0 / 자동주문 0**.


## 최신 v6.5 KRX 공식 일별매매정보 연동 검증기 (2026-10-25)

- **[v6.5 정규장 15:30 인증과 공식 EOD를 분리한 개발·설정 보고서](docs/KRX_OFFICIAL_EOD_V65_20261025.md)**.
- [v6.5 실제 GitHub 성공 #40152003678](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40152003678): **비밀키 없는 환경을 포함한 14/14 오프라인 테스트 통과**, 10/23 v6.4 후보 82종목 원본을 정확한 거래일로 인계.
- 공식 [KRX OPEN API](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)의 **유가증권/코스닥 주식 일별매매정보**를 승인된 `KRX_AUTH_KEY` GitHub Actions Secret이 있을 때만 사용. Secret이 없으면 **`AUTH_KEY_NOT_CONNECTED`**, 공식 수집 0종목, 매수/손익검증 보류. 현재 실제 10/23 실행은 이 연결 대기 상태임.
- 승인된 공식 EOD 자료를 수집하더라도 **KRX도 2026-09-14 이후 16:00~20:00 After Market 운영**. 공식 데이터가 15:30 정규장만 포함함이 인증되지 않으면 `krx_1530_regular_session_certified=false` 및 **CASH, BUY 0, 자동주문 0** 유지.
- **[평일 08:45 KST 자동 KRX 공식 EOD 비교](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/krx_official_eod_v65_daily.yml)**: GitHub Actions 무료 서버로 실행하며 고정 IP 클라우드·개인 노트북을 사용하지 않음. 비밀키는 소스/로그/파일에 기록하지 않으며 KRX API별 이용승인이 별도로 필요할 수 있음.
- 기존 v6.4 **82종목 중 종가 충돌 59 / 일치 22 / 원본 무효 1**과 frozen **34개 진입안 24개 격리·10개 인증미완료** 판정은 그대로 보존함.


## 최신 v6.4 거래일 가격 출처 대조·신호 안전격리 (2026-10-25)

- **[v6.4 가격 출처 교차검증·자동화 개발보고서](docs/SOURCE_PROVENANCE_V64_20261025.md)**.
- [82종목 종가 전수 교차검증·9/9 테스트 성공 #40151275009](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151275009): **두 수집원 종가 불일치 59개 / 유효하게 일치 22개 / 비정상 복구 일봉 1개**. 종가 1% 넘는 불일치는 29개. 두 수집원이 같아도 정규장 09:00–15:30 인증이 아니다.
- [동결 34개 1차·2차 시나리오 안전격리·8/8 테스트 성공 #40151473487](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151473487): 종가 출처가 충돌하는 **24개 가상 진입안 차단**, 나머지 10개도 독립 정규장 가격 인증 미완료로 매수 승인·공식 수익률 출력 금지.
- **[최근 거래일 원본을 자동 짝짓고 같은 규칙으로 재검증 성공 #40151559797](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151559797)**. [v6.4 평일 23:30 KST 자동 분석](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/source_provenance_v64_daily.yml)은 SHA-256 동결 신호·원본 스캔 실행번호·같은 날짜 전체시장 소스를 정확하게 결합하며 휴대폰 아티팩트로 보고.
- **CASH / BUY 0건 / 자동주문 없음**. 키움 증권 고정 IP·유료 클라우드·노트북 상시 연결 불필요. 가격 불일치 원인과 최종 전략 승률은 아직 증명되지 않았다.


## 최신 v6.3 SHA-256 동결·7시장일 전진검증 연결 (2026-10-25)

- **[v6.3 실제 GitHub 테스트·운영 보고서](docs/FORWARD_LEDGER_V63_20261025.md)**. [신호 고정 성공 #40144815020](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40144815020) · [두 시장 일봉 경량화 성공 #40145125003](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40145125003) · [진짜 이후 날짜 관찰 자동화 성공 #40145258020](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40145258020).
- 10/23 스캔 82종목 × 3진입 방법 = 246 분석행 가운데 기술 신호 **17건**을 1차·2차 **34개 독립 대체가격**으로 SHA 고정. 원본 v5.8/복구수집 실행번호 및 가격·손절·목표가의 SHA-256 저장. 1차 목표를 2차에 그대로 적용하던 옛 v5.9 계산 오류 수정 원칙 유지.
- Sector Evidence v18의 KOSPI 940, KOSDAQ 1,824 등 **2,764개 날짜별 증권코드**를 2개의 소형 CSV와 SHA-256 메타데이터로 분리. 혼합 영문 종목코드도 원형 보존. **정규장/장후 독립 가격 인증을 의미하지 않음**.
- 이후 시장일이 7개 쌓일 때까지 **수익률 계산 보류(PENDING)**. 2026-10-25 기준 23일 이후 관찰 **0/7시장일**. 그 뒤에도 주문체결이 아니라 원본시세 불확실성을 표시하는 **가상 결과(PROVISIONAL)**.
- 자동화: [일일 신호동결](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/forward_freeze_v63.yml) / [종합시장 가격분리](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/forward_market_slice_v63.yml) / [7일 전진검증](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/forward_watch_v63.yml). 무료 GitHub Actions·아티팩트 90일 저장. **CASH / 실거래 매수 승인 0 / 자동주문 0**.


## 최신 v6.2 이미 회복한 저항과 신규 돌파 구분 (2026-10-25)

- **[v6.2 실제 10월 23일 저장자료 재생·검증 보고서](docs/WICK_BARRIER_RELIABILITY_V62_20261023.md)** · [전체 GitHub 실행 성공·16개 테스트 통과 #40141098419](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40141098419).
- 과거 196개 신호 × 1·2차 진입안 = **392행**. 가까운 일봉 고가가 신호일 **이전에도 종가로 돌파된 기록 310행**; 신호 발생일 기준으로 이미 고가 위에서 마감한 **317행**. 하루 저항을 과도하게 강하게 판단하는 문제 탐지.
- 이후 5거래일에 그 저항 위로 종가 마감한 312행 가운데, **신호일에는 아래였다가 새롭게 돌파한 51행**과 **이미 돌파된 저항 위에 있었던 261행**을 엄격히 분리. 312행을 새 돌파 성공률로 오해하지 않도록 검증.
- [v6.2 무료 일일 자동 분석](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/wick_barrier_reliability_v62_daily.yml)은 성공한 v6.1 저장 아티팩트의 정확한 거래일·원본 실행번호를 이어받고, 모바일 보고서에 분류와 근거를 기록.
- **실제 매수승인 0, CASH 유지**. 과거 82종목 선정편향·KRX 정규장/장후 종가 출처 충돌·1차/2차 대체 매매 체결 미확인으로 수익률·승률 인증 불가능. 먼 목표를 즉시 매수 목표로 승격하지 않음.


## 최신 v6.1 스윙 고점·군집 저항증거 분리 (2026-10-25)

- **[v6.1 392개 타점 저항 진단 및 결과](docs/RESISTANCE_TIERS_V61_20261023.md)** · [완료된 실데이터 재생/11개 테스트 #40139027642](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40139027642) · [v6.0→v6.1 정확한 원본 연결 및 자동 보고 성공 #40139210532](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40139210532).
- 과거 196개 동일 신호 × 1·2차 대체 타점 392행에서, **확정 스윙 피벗 목표까지만 2R인 경우 37개**를 추가로 식별. 하지만 **더 가까운 고가 저항이 있어 매수 승인 0개**, CASH 유지.
- 좌우 2개 완료봉으로 확인된 스윙 피벗과 2개 이상의 고점 군집을 일회성 고가와 구분. 먼 피벗으로 가까운 저항·손절 위험을 임의로 건너뛰지 않음. 하루 고가의 틱 단위 반올림 경계도 신호 차단.
- 무료 [일일 v6.1 자동 연결](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/resistance_tiers_v61_daily.yml)은 v6.0의 정확한 v5.9/recovery 원본 실행번호와 날짜를 인계해 실데이터 보고. 정규장 독립 인증·시점별 전체시장 PIT 백테스트 미완료 → 실제 주문가·수익예측 아님.


## 최신 v6.0 수익·체결가능성 프런티어 (2026-10-25)

- **[v6.0 전체 보고서 — 23일 기준 196 신호 × 5가지 가격안](docs/ENTRY_FILL_FRONTIER_V60_20261023.md)**.
- [v6.0 실제 GitHub 계산·10/10 테스트 통과](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40136294979) · [v5.9 목표가 과대평가 수정·25/25 테스트](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40136210930) · [무료 일일 자동 연결 성공](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40136417640).
- 82종목의 과거 **196개 기술 신호를 고정**하고 1차, 피벗 2차, 0.5ATR, 1ATR, 비용후 2R 경계가격 총 **980개의 가상 체결** 비교. 실제 가상 체결 건수 순서대로 **125 / 12 / 65 / 28 / 1건**.
- **중요 손익비 정정:** 이전 v5.9의 2차 `2R 84건·1건 체결`은 1차 저항 목표를 2차에 재사용한 **과대평가 수치(폐기)**. 진입가별 가까운 저항 재산출 후 v5.9는 **2R 1건·체결 0건**, v6.0은 2ATR 거리·지지검증까지 적용해 **실제 매수 적격 0건**.
- v6.0 자동 보고: [일일 v5.9→v6.0 실행](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/entry_fill_frontier_v60_daily.yml). 비용반영 진입가·손절·목표·미체결률과 탈락사유를 모바일에서 확인. 전진검증/PIT/정규장 독립 가격은 미완료, **CASH · 자동주문 불허**.


## 이전 v5.9 5거래일 그림자 검증 (2026-10-25 정정)

- [v5.9 연구·테스트 보고서](docs/FIVE_DAY_SHADOW_V59_20261023.md) · [25개 안전테스트·목표 수정 재생 성공 #40136210930](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40136210930) · [수정된 일일 v5.8→v5.9 자동연결 성공 #40136396292](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40136396292).
- 23일 선정 82종목의 *과거* 기술신호 196개를 연구용 모의 체결. 1차·2차 대체안 392개 중 가격별 가까운 저항 재산출 후 **2R 이상 구조 신호 1개, 가상 체결 0개**. **목표가에 닿았어도 거래비용 후 순손실인 71건**도 기록.
- **종목선정 편향 및 정규장 일봉 미인증**: 위 성과를 승률·예상 급등확률·실전 수익률로 사용하지 않는다. 기존 84/1은 폐기하고 정정된 1/0 수치만 사용.
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
