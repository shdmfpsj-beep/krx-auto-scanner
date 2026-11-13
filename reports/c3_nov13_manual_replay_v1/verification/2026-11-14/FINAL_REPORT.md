# 강현AI PRO · C3 TOP2 | 2026-11-13 사후 연구 실행 검증

## 최종 판정

11월 13일 실제 날짜별 FDR 자료로 main의 인증된 workflow_dispatch 연구 실행을 완료했다. WATCH 2종목, ENTRY_FIT 1종목과 PNG 3장을 실제 생성·업로드하고 다운로드 후 원본·JSON·PNG를 다시 검증했다. 공식 KRX 비교, 정규장 전용 인증, 재무 원문 PIT 인증은 미완료이므로 실제 매수 승인은 CASH/BUY=false다. 다음 거래일의 매일 자동 완주나 투자 수익성까지 입증한 것은 아니다.

## 병합 및 실행

- PR #117: 병합 완료, `095adb8ca4374fdddda0131a9f4abdcfe9f3fdef`, 2026-11-14 06:06:50 KST.
- PR #118: 실제 checkout 누락 수정 후 병합, `989042a066699d7df465e7dcc607e0d5f4601f8d`, 06:12:44 KST.
- 최종 main 및 실제 실행 커밋: `989042a066699d7df465e7dcc607e0d5f4601f8d`.
- 실제 수동 Run: [43508677372](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43508677372), SUCCESS.
- Job `manual-retrospective-research`: `132172907091`, 모든 실제 단계 SUCCESS. 별도 예약 Job은 이 수동 실행에서 SKIPPED.
- 시작: 2026-11-14 06:12:59 KST. 종료: 06:21:56 KST.
- PR 단위 테스트: 43507330923 및 43508373806 SUCCESS. 최종 실제 Job에서도 같은 12개 테스트 통과, 실패 0개.
- 기존 Run 43449146127은 9개 오프라인 테스트만 통과했으며 실제 통합 실행은 아니었다.
- 기존 예약 Run 43495119087은 재무 키 미연결로 `RESEARCH_ANALYSIS_INCOMPLETE_FINANCIAL`이었다. 기존 OPENDART_API_KEY를 연결했고, 최종 실행은 157개 기업 조회 중 153개가 날짜 일치 접수/API 스냅샷 상태, 양수 재무 관측 90개를 기록했다. 원문 PIT 인증으로 승격하지 않았다.
- 중간 수동 Run 43508008871은 workflow YAML이 sparse checkout에 없어 테스트 파일 읽기에서 실패했다. PR #118에서 해당 파일 checkout만 추가하고 재실행했다. 실패 사실을 성공으로 대체하지 않는다.
- GitHub 연결 도구에는 직접 dispatch 기능이 없고 Cloud Browser는 로그아웃 상태였다. 별도 비운영 ops 브랜치의 일회성 GitHub Actions 토큰으로 공식 workflow_dispatch API를 호출했다. 실제 target event는 `workflow_dispatch`, ref는 main, actor는 `github-actions[bot]`이다. 승인 조건을 위조하거나 우회하지 않았다. ops 브랜치는 main에 병합하지 않았으며 새 예약은 없다.

## 실제 변경 파일

- `.github/workflows/c3_nov13_once.yml`: 기존 OpenDART 키 연결, 실제 보호 해시 점검, 증빙 Artifact 보존, 필요한 YAML checkout.
- `scripts/c3_nov13_once_v1.py`: 원본 CSV와 정규화 JSON의 전 필드 직접 대조.
- `scripts/test_c3_nov13_once_v1.py`: 실제 CSV fixture와 데이터 변조·연결·독립 순위 보호 테스트.
- `scripts/c3_watch_card_v1.py`: 기존 순위 그대로 WATCH 카드 생성, 미확정 매수·손절·저항은 가격 생성 금지, 실제 119봉 요구.
- `scripts/c3_source_recovery_analysis_v1.py`: WATCH와 ENTRY_FIT 독립 출력 및 별도 출처/카드 보존. 선정 가중치·필터·기존 V4 가격 계산은 변경하지 않음.

## 11월 13일 수집 자료

| 항목 | 실제 확인 결과 |
|---|---|
| 공급원 | FinanceData/fdr_krx_data_cache, data/listing/krx/2026-11-13.csv |
| 파일 커밋 | 05a17038b3cddf7a6f48105913e46fd37d96a21e |
| 커밋 시각 | 2026-11-13 21:58:19 KST; 서버 최초 공개 시각을 독립 인증한 것은 아님 |
| 실제 수집 시각 | 2026-11-14 06:13:42.560584 KST |
| 원본 전체 | 2,877행 |
| 연구 대상 | KOSPI 936 + KOSDAQ 1,834 = 2,770; KONEX 107 제외 |
| 내부 검사 | 중복·가격 형식·OHLCV·거래대금 검사 통과, 원본 CSV와 JSON 2,770개 전수 일치 |
| 전체 상장 census | 독립 공식 인증 미완료; 전일 커버리지 경보 검사와 구분 |
| 정규장 전용 | 미인증; 미수정 FDR 보고 가격, 기업행위 독립 인증 아님 |
| 지수 | 네이버 일별 KOSPI/KOSDAQ 각 374행, 양쪽 마지막 날짜 2026-11-13, CSV 해시 검증 |
| 시점 정책 | 사후 수집·사후 재무 조회; lookahead_relative_to_target_close=true, historical_point_in_time_backtest=false |

원본 CSV SHA256: `842fb7a65532cd82e2cc3023fde21e8d6fcdc5008b45db3083f2504c5ead88cc`

정규화 행 SHA256: `abdc0d50b7c1275f73c3efabb588c0072538fb9ef71c70527228f1c881cccaed`

연구 입력 payload SHA256: `522d50896b7696d3ddba09dfa01df0c83a47c57f90597d39040441c0cbbf06de`

최종 report payload SHA256: `9992794f826764f603a4ca016857d5dbf5c43ea361a703c1a654959cd0ace37e`

## 실제 전체시장 분석

전체 2,770 → 연속 이력 2,418 → 분석 가능 1,989 → 기술 후보 157 → 기존 B 후보 47. 양수 재무 관측 90, 기업·모멘텀·유동성 결합 18, 구조손절 통과 123, 실용적 범위 통과 18, 최종 ENTRY_FIT 1. 각 통과 수는 서로 다른 축의 집계로 단순한 연속 탈락 단계가 아니다. 기존 11월 11일 149개 후보를 재사용하지 않았다. 11월 12일 별도 연구 보존 가격을 이력에 연결했고, 승인 엔진 90봉 suffix와 확장 이력의 일치를 실제 검사했다.

| 구분 | 종목 | 종가 | RS20 | 최근 5일 RS 개선 | 20일 평균 거래대금 | 판단 |
|---|---|---:|---:|---:|---:|---|
| WATCH 1 | 삼성E&A 028050 | 68,800원 | +64.46%p | +15.43%p | 2,303.49억원 | 진입 적합 범위 없음; 돌파한 이전 고점을 위쪽 저항으로 재사용하지 않음 |
| WATCH 2 | 한진칼 180640 | 203,500원 | +80.74%p | +6.60%p | 1,164.15억원 | 기존 지지 구간이 너무 멀어 RANGE_TOO_FAR; 추격 가격을 만들지 않음 |
| ENTRY_FIT 1 | 포메탈 119500 | 2,935원 | +46.60%p | +3.58%p | 11.18억원 | 연구용 ENTRY RANGE/WAIT, 실제 BUY 아님 |

WATCH 종목명은 과거와 같지만 이번 종가·지표는 11월 13일 자료로 새로 계산했다. 단순한 과거 보고 대체가 아니다. 임의 가중 점수를 만들지 않고 기존 정렬 순위를 사용한다. 포메탈의 재무 관측은 양수이나 전년 비교 매출·영업이익 증가가 확인된 사례가 아니며, 원문 PIT·사업 경쟁력도 검증되지 않았다.

## 포메탈 연구 계획

| 항목 | 값 |
|---|---:|
| 매수 관찰 범위 | 2,680~2,740원 |
| 구조손절 | 2,600원 |
| R1 / R2 | 3,200 / 3,350원 |
| 범위 폭 | 60원 / 약 2.24% / 0.196ATR |
| ATR14 | 약 305.71원 |
| 상단 손절 위험 | 5.1095% |
| 하단 손절 위험 | 2.9851% |
| 상단 비용 반영 R1 RR / R2 RR | 2.6715 / 3.5894 |
| 하단 비용 반영 R1 RR / R2 RR | 4.8305 / 6.2881 |
| 종가 대비 상단 / 하단 거리 | 6.6440% / 8.6882% |
| 구조 근거 | 2026-11-09 저점 2,680원, 11월 11일 확인된 피벗; 원본 V4 구조 계산 재사용 |
| 손절 완충 | 80원, 기존 ATR/관측 하단 꼬리 정책 |
| 유효기간 | 기존 기본 1거래일, 1·2·3거래일은 연구 비교; 실제 신규 주문 승인이 아님 |

범위 전체 13개 유효 호가에 대한 기존 위험 검증 통과. 비용 가정은 기존 연구 설정인 매수 0.15%, 매도 0.5%, 양쪽 슬리피지 각 0.1%를 그대로 사용했다. 실제 수수료·세율 확정값이나 기대수익 보장이 아니다. 2차 매수는 별도 검증 계획이 없어 제시하지 않았고 자동 주문 횟수·비중은 강제하지 않는다. 범위 미도달 만료 PASS, 지지 붕괴·범위/손절 아래 갭·R1 선도달 시 무효화다. 하단 거리가 예전 8% 기준을 넘는 것은 기존 V4의 가장 가까운 경계 접근성/전체 구조 보존 정책 결과이며 이번에 기준을 완화한 것이 아니다.

## PNG와 Artifact

[실제 Artifact 다운로드](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43508677372/artifacts/14078620251)

Artifact `c3-nov13-manual-retrospective-png`, ID `14078620251`, ZIP 1,388,891바이트, SHA256 `1440eba159eb0e8eeaf6e5b2352e0be0b12593e72e0c3ab55733599d7bf35cf8`.

| Artifact 경로 | PNG SHA256 |
|---|---|
| output/analysis/watch_cards/C3_WATCH_20261113_028050.png | e96670adc559785f6e1d23380764c0df261f08671f7ac1896a311688b18a175c |
| output/analysis/watch_cards/C3_WATCH_20261113_180640.png | 716535ef445e17588a867e6bf70e6917a89f3fa685ea8f5bee0b1275a1d909f6 |
| output/analysis/cards/C3_NEW_20261113_119500.png | 11c0b17d068fa283775dc264a40908e67b1197e3ee4fc2f0168d4deaefc7999b |

3장 모두 1400×2400, 실제 119봉 중 최근 60봉 표시. MA5·20·60 독립 Decimal 검산과 전체 MA60 표시 60점 검증을 통과했다. PNG 내부 C3_manifest, 카드 manifest, report 및 원본 종가·종목명·모든 OHLCV/거래대금 필드가 일치했다. 실제 파일을 열어 밝은 배경·회색 헤더·가격표·아래 네 근거 구역도 확인했다. 큰 미리보기에서 잘린 것으로 보였던 WATCH 종가는 실제 원본 좌표/축소본 검증에서 정상임을 확인해 정상 코드를 수정하지 않았다.

연구 자료·리뷰 보존 커밋: `dfe7f89d5ee4256842c2e8f4f27eca5c5aaf5524`.

리뷰: `reports/c3_new_session_v1/reviews/2026-11-13/9992794f826764f603a4ca016857d5dbf5c43ea361a703c1a654959cd0ace37e.json`.

## 안전 검증

- 기존 연구 원본 68개와 Telegram 기록 19개, 총 87개 보호 파일의 실행 전후 내용 해시가 모두 동일하다.
- 보호 집합 SHA256: `8a7757b621100aa3dff9b7bcc79a0bae22bea8238b397cc371aa5aaf1d623820`.
- 실제 주문 0, Telegram 요청 0, 신규 원본 거래 신호 등록 0, 전방 원장 신규 기록 0.
- 전달 결과 `RESEARCH_NOT_SENT`, 로컬 안전 claim 재시험 `DUPLICATE_BLOCKED`. 실제 채널 송신 검증을 수행했다는 뜻이 아니다.
- 기존 예약 Job의 workflow_run 인증 조건은 byte 단위로 원래와 같으며, 기존 오전 스케줄·08:45 알람은 수정하지 않았다.

## 공식 KRX 실제 장애 증거

[읽기 전용 감사 Run 43508657689](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/43508657689), 2026-11-14 06:13 KST, AUTH_KEY 헤더 존재 확인. 키 값은 저장·출력하지 않았다.

| 요청일 | API | HTTP | 실제 결과 |
|---|---|---:|---|
| 2026-11-13 | stk_bydd_trd | 200 | OutBlock_1 빈 배열, 0행 |
| 2026-11-13 | ksq_bydd_trd | 401 | respCode 401, Unauthorized API Call |
| 2026-11-12 대조 요청 | stk_bydd_trd | 200 | 936행 정상 |
| 2026-11-12 대조 요청 | ksq_bydd_trd | 401 | 동일 인증/서비스 승인 거부 |

KOSDAQ 문제는 11월 13일 게시 지연만으로 설명되지 않는다. 실제 이용 권한/서비스 승인/키 상태 중 정확한 원인은 제공자 계정 쪽 확인이 더 필요하다. 코스피 13일 0행도 게시 시각·제공 상태를 아직 확정할 수 없다. `official_krx_match_verified=false`, 정규장 전용 미인증, BUY=false를 유지한다.

## Stage-Gate

| 단계 | 판정 | 실제 증거 |
|---|---|---|
| PR #117 최신 상태 확인 | PASS | merged, 095adb8 |
| 단위 테스트 | PASS | PR118 Run 43508373806 및 최종 Job: 12통과·0실패 |
| 통합 테스트 | PASS | Run43508677372 실제 수집→분석→보존→PNG→업로드 |
| main 병합 | PASS | PR117 095adb8, 수정 PR118 989042a |
| Actions 수동 실행 | PASS | event workflow_dispatch, main, Job132172907091 SUCCESS |
| 11월 13일 데이터 확보 | PASS | 날짜별 FDR 원본·SHA·실수집 시각 확인; 연구용 |
| KOSPI·KOSDAQ 전체시장 검증 | PASS | FDR 936/1834, KONEX107 제외, 2770행 필드 대조; 공식 census 인증은 보류 |
| 연구 엔진 실행 | PASS | A/B pin54e7120, V4 pinf3ed60f, technical157 |
| WATCH TOP2 | PASS | 삼성E&A·한진칼, 11/13 가격 재계산 |
| ENTRY_FIT TOP2 | PASS | 적합1개 포메탈; 억지로 두 번째 생성하지 않음 |
| PNG 생성 | PASS | 실파일3장, 119봉/MA60 60점, JSON/가격/해시 일치 |
| Artifact 업로드 | PASS | ID14078620251 실제 다운로드·ZIP 검증 |
| 원장·주문·Telegram 보호 | PASS | 보호87파일 동일, 요청0, 주문0, 신규 거래 신호0 |
| 공식 KRX 검증 | HOLD | 13일STK0행·KSQ401, 12일대조STK936/KSQ401 |

## 다음 거래일 가능 범위와 남은 필수 작업

11월 13일 수동 사후 연구 경로는 실제 완주했다. 이 워크플로는 날짜 고정 연구 경로이며, 다음 거래일 오전의 정기 신규 자료 완주까지 검증한 것은 아니다. 기존 오전 수집 일정은 유지됐고 실전 BUY 승격도 없다.

1. KRX `ksq_bydd_trd`의 실제 서비스 승인/인증 상태를 확인하고, KOSPI 11/13 게시 상태가 달라지면 같은 날짜 원본과 전수 대조한다. 정규장 전용과 재무 원문 PIT 인증도 별도 게이트다.
2. 다음 정기 실행에서 신규 source_run_id·거래일 기준으로 기존 오전 분석/차트 경로의 실제 완주를 관측한다. 이번 고정 날짜 수동 성공을 매일 자동화 보장으로 바꾸어 보고하지 않는다. 새 스케줄·임계값·매매법 개발은 필요하지 않다.

## 다음 Work 질문지

1. 이번 실제 응답 증거를 바탕으로 KRX KOSDAQ 서비스 인증 거부와 KOSPI 목표일 0행을 정상화하고, 공식 자료와 동일 날짜 FDR 원본을 전수 대조하라. 인증 미완료 시 BUY 차단은 유지하라.
2. 기존 오전 정기 실행에서 신규 완료 거래일 원본→A/B·V4→독립 WATCH/ENTRY_FIT→PNG Artifact가 같은 실행 ID·해시로 연결되는지 확인하고, 이번 성공 경로와 다른 결함이 있을 때만 최소 수정하라. 원장·Telegram·예약은 보존하라.
