# Android OpenDART 연결 가이드 (2026-10-22 수정)

**기존 등록명 `OPENDART_API_KEY` 유지 — 새 비밀키를 생성하거나 인증키를 다시 붙여 넣을 필요 없음.**

사용자 GitHub 화면에서 기존 `OPENDART_API_KEY`의 **Update secret** 페이지가 확인됐습니다.
기존 보고의 `MISSING_DART_KEY`는 새 일일 금융 분석 코드가 실수로
`DART_API_KEY`만 읽었던 **워크플로 연결 오류**입니다.

이제 일일 스크리너/섹터 증거 수집/접속 검사에서 GitHub 비밀키를 다음 순서로 선택합니다.

1. `OPENDART_API_KEY` (기존 이름 최우선)
2. `OPEN_DART_API_KEY` (일부 이전 모듈 호환)
3. `DART_API_KEY` (이전 별칭 호환)

Python 금융 연구 코드에서도 세 이름을 지원합니다. GitHub Secrets의 실제 값은
API·코드·로그에 노출하지 않습니다.

## 실제 연결 확인 (모바일)

1. [연결 검사 워크플로](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/workflows/dart_financial_connection_checks.yml)를 엽니다.
2. 자동 실행된 최근 검사를 선택하거나, `Run workflow`를 눌러 실행합니다.
3. `Check actual official OpenDART API with one Korean listed test company` 단계에서
   `OPEN_DART_CONNECTIVITY_STATUS`를 확인합니다.
4. `MISSING_DART_KEY`가 아니면 이름 불일치 문제는 해결된 것입니다.
   공시/기업 고유번호 다운로드 등 후속 검사가 성공했는지도 별도로 확인해야 합니다.

기존 GitHub `OPENDART_API_KEY` 설정은 바꾸지 마세요.
보안상 비밀키를 채팅이나 GitHub 이슈·코드에 보내지 마세요.

## 성공 여부 판정

해당 워크플로 로그의 `OPEN_DART_CONNECTIVITY_STATUS`를 확인합니다.

| 결과 | 뜻 | 조치 |
|---|---|---|
| `MISSING_DART_KEY` | 이름/값을 찾지 못함 — 기존 OPENDART_API_KEY가 해당 저장소에서 사용되는지 확인 | Secret을 등록 |
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
- OpenDART 연간 실적은 기업의 과거 수치일 뿐, 주가가 5거래일 내 상승할 확률이나 80점 투자 승인으로 자동 변환되지 않습니다.
- GitHub에서는 **비밀키를 로그나 CSV/JSON 보고서에 남기지 않도록** 구성했습니다.
- 매일 밤 22:00 분석 후 `financial_research_mobile.md`와 `sector_first_with_financials.json`이 생성됩니다.
  만약 키·공시가 없으면 성공으로 위장하지 않고 정확한 미수집 상태를 표시합니다.

공식 문서: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
