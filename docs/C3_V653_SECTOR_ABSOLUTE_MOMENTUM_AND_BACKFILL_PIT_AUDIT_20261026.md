# C3 v6.53 — 업종 절대상승과 개별주 지속성: 미래정보·승자편향 감사

2026-10-26 연구기록. 가격원본 마지막 2026-10-23. READ-ONLY, CASH/WAIT, 0 새 독립체결, K100 및 기존 Work v6.38 동결 A/B 불변, 신규 자동주문 0. 사용자는 자금과 비중/매수수량을 관리하며 이 프로젝트는 종목의 실제 진입가·구조손절·확인된 저항과 추가상승 근거를 개발한다.

**v6.53 executed research**: exact 20 v18-sector/ETF source CSV members and 32 frozen Work past D-signals from v6.52 package. 17 ETF groups x41 dated rows=697. Excluding the HEALTH ETF group (this does NOT establish an actual non-pharma/bio issuer filter), 16 ETF groups x36 observable D-to-D+5 ETF closes=576 OVERLAPPING historical observations on just **8 calendar weeks**. 41 local tests passed, full replayed clean ZIP 8 CSV/JSON result files SHA-identical. Complete local code/report/SHA: user conversation C3_v653_상승지속_업종개별주_연구코드.zip, SHA256 b9814f0ca270d9b157bb8fbc95d4150e8bb98cf24674f1e6cbb5e520be5b5ac5. Mobile report c3_v653/C3_v653_종목상승지속_실패사례_연구보고서.md. New GitHub remote CI success is NOT asserted.

**Sector ETF ABSOLUTE PRICE momentum failed as future absolute return picker** (historical, no brokerage execution):
| D-only criteria | n | D+5 ETF price return mean | full 576 opportunities with rejected = CASH 0 |
|---|---:|---:|---:|
| All nonhealth ETF groups | 576 | -1.757% | -1.757% |
| Prior ETF 5day absolute return positive | 223 | **-2.490%** | -0.964% |
| Prior ETF 5d and 20d both positive | 173 | **-2.759%** | -0.829% |
| ETF prior 5d positive and constituent breadth >=50% | 159 | **-2.595%** | -0.716% |
| ETF prior 5d positive and market-relative-strength positive | 152 | **-2.824%** | -0.745% |
| ETF and 069500 prior 5d both positive | 137 | -1.814% | -0.431% |

Full-signal mean +0.793 percentage-point improvement for sector prior5-positive with rejected=0 is NOT proven positive investing edge, and 2000 whole-week resamples across only 8 weeks yield interval **[-0.539,+2.257] percentage points**, includes zero. ETF D-close-to-D+5 return excludes broker costs and is NOT stock D+1-open 5-session return. No retrospective tuning into an authorized BUY rule.

**Actual frozen Work stock-level diagnostic**: 32 D signals in evidence period; 15 linked to most-recent full ETF snapshot before D, 17 unclassified. A chosen ETF in the linked group with prior5 ETF return positive gave **10 stocks mean +0.355%, median +0.772%, 6 winners**, but removing highest single winner changes mean **-1.257%** (removing top two **-1.894%**); all ten already had positive original D stock ret5, so adding this common signal does not improve the 10-stock selection. 32 all mean -1.962%; matched15 mean -1.793%; unclassified17 mean -2.111%. These return values are from old Work stock hypothetical fills and must never be represented as independent future evidence.

**Very important prospective PIT failure**: all **7228 ETF constituent membership rows** have nominal historical snapshot days 2026-07-09 through 2026-10-19 but actual collected_at **2026-10-23 12:23:12–12:32:54 UTC**, equivalent **2026-10-23 21:23–21:32 KST**, AFTER every historical study-date 15:30 KST close. Backfilled snapshot dates are NOT independently audited contemporaneous availability. This does not prove data was not publicly available earlier; it means that this project CANNOT prove it possessed this exact input at the old D time. ALL strictly as-of authorizations FALSE and no live rank score uses those membership snapshots.

**One historical negative case (NOT current levels)**: ticker 373220, Work D=2026-08-31, original signal close 378,000, daily structural invalidation reference 340,500, recorded D overhead reference 422,000, ETF proxy RENEWABLE prior5 gain +8.1139%; parent Work following 5-session hypothetical stock return **-4.7229%**. Using buy fee 0.15% and sell friction 0.50% yields historical price geometry **net payoff/risk about 1.039:1**. A stock can be a current ETF constituent with a strong broad proxy and STILL have a poor entry because confirmed upward room is too short. No present chart support, target, news/catalyst, POC, current BUY or exact stop is asserted. The forward outcome is exposed ONLY in a separately labeled historical postmortem, never in D-only stock ranking.

**Research direction:** stop promoting ETF RS5/ETF absolute5/breadth alone as hard stock pickers. Verify exchange regular-session-only D-date and true real-time ETF PDF vintage, ordinary share and pharma/bio historical eligibility, complete issuer filings/news at D, genuine peer participation, ticker-level price support and dated overhead before rich A/B/C/stop/targets. If live date/source cannot be confirmed, CASH/WAIT without making up prices. Need fresh 2026-10-26+ D snapshots frozen before next open, missed orders included; new broker-confirmed fills =0.

Source discovery: KRX Data Marketplace https://data.krx.co.kr/ exposes ETF PDF and individual-stock investment-flow/price menu, but the presence of a menu is NOT proof an historical file was obtained before D. Research PR #25 stays draft, trading orders disabled.