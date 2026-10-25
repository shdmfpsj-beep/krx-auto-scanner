# C3·K100 v6.5 — 한국거래소 공식 일별매매정보 선택적 연동과 정규장 인증 분리

## 2026-10-25 12:01 KST 이후 정정 — KRX 인증키 등록·실제 수집 성공

- **[인증키 연결 후 실데이터 수집 성공 #40156628275](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40156628275)**. KRX 공식 API KOSPI·KOSDAQ **2,764개 종목 실제 일봉** 다운로드, GitHub Artifacts `free-v65-official-eod-vs-v64-regular-session-uncertain`.
- **23일 82후보 기준:** 공식 KRX EOD가 **v18과 일치하고 recovery와 불일치: 59**. **3원본 모두 종가 일치: 22**. **원본 일봉 무효: 1**. 동결 신호 16종목 중 충돌 12종목도 공식 KRX EOD와 v18이 일치.
- 이전 본문에서 `AUTH_KEY_NOT_CONNECTED`로 표기된 것은 **최초 테스트 실행 #40152003678 시점**만의 상태다. 새 실행은 `OFFICIAL_EOD_AVAILABLE_SESSION_SCOPE_UNCERTIFIED`로 확인.
- **정규장 인증은 아직 미완료**. 공식 EOD가 15:30 정규장만의 종가를 보장한다는 소스 필드/시각증빙이 아직 없고, v18과 공식 KRX 자료가 같은 원천일 가능성도 있다. 가격 불일치의 원인을 장후 수집 때문이라 확정하지 말고 recovery 데이터 수집·가공 과정을 먼저 조사한다.
- 갱신 전에 발급받은 구 인증키가 사진에 전체 노출된 적이 있으므로 **노출된 구 키를 무효화했는지 점검**한다. GitHub Secret 등록만으로 이전 키가 자동 폐기되는 것은 아니다. 인증값은 문서·스크린샷·채팅에 남기지 않는다.


**개발·실행 날짜: 2026-10-25 일요일 KST · 현재 데이터 기준: 2026-10-23 (금).**

**최종 결론: CASH / 신규 BUY 승인 0 / 자동주문 실행 0 / 검증된 실전 5일 승률 없음.**

## 1. 이번에 실제로 끝낸 개발

- [v6.5 GitHub 실데이터 작업 + 14개 안전 자동테스트 전부 통과 #40152003678](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40152003678)
- 원본: [v6.4 날짜별 정규장 출처 대조·전진검증 차단 성공 #40151559797](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40151559797)
- 프로그램: `scripts/krx_official_eod_v65.py`, `scripts/test_krx_official_eod_v65.py`.
- 자동화: `.github/workflows/krx_official_eod_v65_daily.yml`. 일정: **월~금 08:45 KST**, 업로드는 모바일에서 수동 실행도 가능.
- 산출물: `krx_v65_source_comparison_status.json`, `krx_v65_source_comparison_all.csv`, `krx_v65_mobile.md`, 공식 API 사용 성공 시에만 `official/KOSPI_official.csv` 및 `official/KOSDAQ_official.csv` (아티팩트 보존 90일).
- 이전 17개 기술신호, 16종목, 34개 1차/2차 대체 진입안은 변경하지 않으며, 가용현금 미확인 및 가격 출처 불일치로 **CASH 유지**.

### 이번 10월 23일 실제 출력

| 항목 | 결과 |
|---|---|
| GitHub 자동테스트 | **14/14 통과** |
| v6.4 비교에 포함된 후보 | **82종목** |
| 기존 두 소스의 유효 종가 불일치 | **59종목** |
| 공식 KRX OPEN API 키 연결 상태 | **`AUTH_KEY_NOT_CONNECTED`** |
| 이번 실행의 공식 KRX 주권 시세 확보 수 | **0종목 (미연결)** |
| 정규장 15:30 독립 인증 종목 | **0** |
| 실제 투자에 사용할 공식 승률/매수가 | **없음** |

**주의:** 82종목은 신규 KRX API로 실제 조회된 것이 아니라 v6.4 입력으로 불러온 후보입니다. 인증키가 없어 KRX API는 호출되지 않았습니다. 오인하지 않도록 응답에 명시했습니다.

## 2. 공식 API를 선택한 근거

공식 한국거래소 데이터 마켓플레이스의 API 서비스 목록에서 다음 서비스 제공을 확인했습니다.

- **유가증권시장 일별매매정보:** `GET https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?basDd=YYYYMMDD`
- **코스닥시장 일별매매정보:** `GET https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd?basDd=YYYYMMDD`
- 헤더: `AUTH_KEY` (KRX 발급·승인된 비밀키). 응답: `OutBlock_1` 의 `ISU_CD`, `BAS_DD`, `TDD_CLSPRC`, `TDD_OPNPRC`, `TDD_HGPRC`, `TDD_LWPRC`, `ACC_TRDVOL`, `ACC_TRDVAL`.

공식 서비스 목록: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd

유가증권시장 서비스 상세: https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC

코스닥시장 서비스 상세: https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=hZjGpkllgCBCWqeTsYFj

**KRX OPEN API 운영 데이터는 이용신청·관리자 승인 조건이 있을 수 있습니다.** 단순 홈페이지 방문이나 예제 호출 가능 여부가 내 계정의 승인 여부를 뜻하지 않습니다. 사용료 및 승인 조건은 KRX 마이페이지에서 최신 정보를 확인해야 합니다.

## 3. 실제 구현한 14개 안전 테스트

실제 KRX API 인증이 없는 상황에서도 **인터넷을 호출하지 않는 가짜 응답**으로 다음을 검증했습니다.

- API 비밀키가 없으면 `AUTH_KEY_NOT_CONNECTED`로 정확하게 표기하며 공식 시세 0건.
- 승인 거절(HTTP 401/403), 서비스 오류, 응답이 비어 있는 경우 결측 공식 자료로 처리.
- 승인된 연결이 실재하는 경우에만 KOSPI·KOSDAQ **두 시장 모두** 자료를 받아 완전한 동일 날짜 자료를 저장.
- 한 시장이라도 날짜가 틀리거나 종목코드 중복 또는 API 구조가 틀리면 전부 폐기; KRX API 오류를 기존 시세로 조용히 대체하지 않음.
- `ISU_CD`에 12자리 국제증권식별번호가 왔다면 **6자리 코드를 임의로 유추해 생성하지 않음**.
- `1,234` 형태 천 단위, 거래정지 0거래량, 빈칸 등을 안전하게 처리.
- 원본 JSON 해시와 최종 CSV의 SHA-256을 보존하되 **비밀키 자체는 파일·로그에 기록하지 않음**.
- 공식 일봉이 구해지면 회복 스캔과 v18 중 어느 쪽 종가와 일치하는지 각 종목별로 7개 상태로 진단.
- 공식 두 종가가 모두 일치해도 최종 `trade_approved=false`, `orders_enabled=false`를 강제.

## 4. 가장 중요한 구분: 'KRX 일별매매정보' != 자동으로 '15:30 정규장 종가'

**2026-09-14부터 한국거래소도 16:00~20:00 애프터마켓을 운영합니다.** 현재 검토한 OPEN API 일별매매정보 필드에는 `KRX_NORMAL_1530_ONLY`와 같은 매매 세션 식별자가 확인되지 않았습니다.

공식 API에서 응답을 받는 경우:
- `krx_eod_authenticated=true` (API 인증 연결에 성공)
- `official_dataset_usable=true` (KOSPI·KOSDAQ 당일 자료와 해시 확보)
- **`independent_1530_regular_session_certified=false` (정규장만 포함했다는 공식 검증 미실시)**
- `trade_approved=false`, `orders_enabled=false`

즉 공식 일별 종가가 세 번째 증거로 유용하지만, **2026년 현재 정규장/애프터 세션 구분과 수정주가 포함 여부를 제공 계약에서 확인하기 전에는 주문 근거로 승격하지 않습니다.** 두 수집원의 종가가 달랐던 이유를 애프터마켓으로 단정해서도 안 됩니다.

### 모바일에서 KRX API 키를 연결하려면

**1. KRX 인증키·서비스 이용 승인**

스마트폰에서 https://openapi.krx.co.kr/ 로 이동해 계정을 사용하고 **마이페이지 → API 인증키 신청**, 필요한 경우 **서비스 이용신청** 메뉴에서 유가증권 일별매매정보와 코스닥 일별매매정보 각각을 승인받습니다. 키 발급과 개별 API 승인 상태를 모두 확인합니다.

**2. GitHub에서 비밀키 저장**

스마트폰 브라우저로 https://github.com/shdmfpsj-beep/krx-auto-scanner/settings/secrets/actions 에 로그인한 뒤, **New repository secret**을 눌러 아래와 같이 저장합니다. 모바일에서 메뉴가 가려지면 브라우저의 **데스크톱 사이트**를 선택합니다.

- Secret 이름: `KRX_AUTH_KEY`
- 값: KRX에서 발급받은 본인 API 키 (채팅에 복사해 보내지 말 것)

**3. 스마트폰에서 실제 실행**

https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/krx_official_eod_v65_daily.yml

여기서 **Run workflow**를 누르면 10월 23일 완료된 v6.4 원본과 대응해 공식 API를 호출하려고 시도합니다. 키·권한이 완비됐다면 응답이 있는지 판정하며, 권한이 없다면 `KRX_AUTH_OR_SERVICE_APPROVAL_MISSING`이라고 안전하게 보고합니다.

키가 없다면 **설정이 요구되지 않고 작업은 `AUTH_KEY_NOT_CONNECTED`로 완료**됩니다. 무료 GitHub Actions만 사용하므로 고정 IP 클라우드, 개인 노트북 상시 가동이 필요하지 않습니다. 단, 실제 KRX API의 접근 제한/이용자 승인 조건은 해당 서비스에 따릅니다.

## 5. 다음 v6.6 개발 대상

1. 공식 API 사용 승인 이후 3개 소스(복구/v18/KRX 공식)의 **종목별 종가뿐 아니라 시고저·실측 거래대금** 대조.
2. 공식 API 정규장 데이터 범위·수정주가 반영 여부 확인. 필요하면 **명시적인 15:30 거래소 정규장 종가 근거**를 따로 수집해 세션 인증 게이트 구성.
3. 전체 종목의 과거 시점 보통주/우선주/ETF/ETN 분리 및 회계 실적의 최초 공시 시각 고정(PIT).
4. 정규장·날짜별 전체시장 자료와 최종 80점이 인증되기 전에는 지표점수·매수가 숫자를 **투자 권고로 제시하지 않음**.

**Required Next Data:** KRX API 두 서비스의 실제 승인 및 키 연결(선택사항), 공식 자료가 표시하는 시각/정규장 구분 문서, 이후 2026-10-26 거래일 원본, 실제 계좌 현금·보유 및 매수/손절 판단에 유효한 정규장 확정 일봉.
