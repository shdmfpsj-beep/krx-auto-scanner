# 안드로이드 스마트폰으로 OpenDART 연결하기 (2026-10-22)

**현재 GitHub에서 확인한 연결 상태: `MISSING_DART_KEY`**

코드는 준비되어 있지만 GitHub Actions의 `DART_API_KEY` 값이 비어 있습니다.
이는 OpenDART 홈페이지에서 인증키를 발급받았는지와 별개의 문제입니다.

## 처음 한 번만 설정

1. 휴대폰 Chrome에서 [저장소 Actions 비밀키 설정](https://github.com/shdmfpsj-beep/krx-auto-scanner/settings/secrets/actions)을 엽니다.
2. `Settings → Secrets and variables → Actions → New repository secret`로 이동합니다.
   메뉴가 잘 안 보이면 브라우저 메뉴에서 **데스크톱 사이트**로 전환합니다.
3. **Name:** `DART_API_KEY` (대소문자와 밑줄 정확히 입력).
4. **Secret:** 본인이 발급받은 OpenDART API 인증키를 붙여 넣습니다.
5. `Add secret`을 탭합니다. 키 값을 채팅·이슈·로그·소스코드에 작성하지 않습니다.
6. [OpenDART 무료 연결 검사](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/dart_financial_connection_checks.yml)에서 `Run workflow`를 눌러 검사를 실행합니다.

## 성공 여부 판정

해당 워크플로 로그의 `OPEN_DART_CONNECTIVITY_STATUS`를 확인합니다.

| 결과 | 뜻 | 조치 |
|---|---|---|
| `MISSING_DART_KEY` | GitHub Secret 값이 없음 | Secret을 등록 |
| `INVALID_DART_KEY_FORMAT` | 길이/형식 부적합 | 정확한 원본 값 확인 |
| `CORPCODE_DOWNLOAD_FAILED_...` | 고유번호 API 조회 실패 | 인증키 유효성·API 서버 상태 확인 |
| `NO_ELIGIBLE_DATED_ANNUAL_FILING` | 해당 기준일에 적격 연간 사업보고서 검색 실패 | 접수일·회사별 공시 확인 |
| `ANNUAL_RESEARCH_READ` | 검증 가능한 대상의 연간 재무 수치 수집 성공 | 수익률·타점 별도 확인 |
| `PARTIAL_FINANCIAL_RESEARCH` | 일부 회사만 공시 수치/계정 확인됨 | 금융업/별도재무제표/계정 누락 등을 점검 |
| `HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS` | 과거 날짜에 미래 API 자료가 뒤섞이는 오류 차단 | 당시 시점 보존 아카이브가 있을 때만 회고 |

## 재무 분석 기준과 주의

- 최초 수집은 **상위 섹터 내 최대 20개 종목**만 대상으로 합니다.
- 상장종목 6자리 코드를 OpenDART 고유번호 8자리와 연결합니다.
- **해당 분석 기준일 이전에 실제 제출된 사업보고서**가 있어야 합니다.
- 연결재무제표를 우선하고, 연결이 없거나 불완전하면 별도재무제표로 표기합니다.
- 같은 사업보고서의 당기·전기 연간 매출액·영업이익을 비교하고 자산 = 부채 + 자본을 검사합니다.
- 은행/증권/보험의 일반 영업이익률 심사는 별도 업종 모델이 필요하므로 일괄 통과시키지 않습니다.
- OpenDART 연간 실적은 기업의 과거 수치일 뿐, 주가가 5거래일 내 상승할 확률이나 85점 투자 승인으로 자동 변환되지 않습니다.
- GitHub에서는 **비밀키를 로그나 CSV/JSON 보고서에 남기지 않도록** 구성했습니다.
- 매일 밤 22:00 분석 후 `financial_research_mobile.md`와 `sector_first_with_financials.json`이 생성됩니다.
  만약 키·공시가 없으면 성공으로 위장하지 않고 정확한 미수집 상태를 표시합니다.

공식 문서: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
