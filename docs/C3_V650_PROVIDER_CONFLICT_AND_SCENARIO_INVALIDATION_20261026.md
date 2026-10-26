# C3 v6.50 — Evidence-backed one-stock trading report, 2026-10-26

**Research-only release, NO BUY, NO BROKER ORDERS.** Users receive screenshot-level detail (A/B/C entry, structure stop, recorded overhead, target conditions, holder/new-buyer different actions, current invalidation), but **NO invented live price**, verified foreign/institutional flow, volume POC/VAH/VAL, company catalyst or growth probabilities. Do not let old BUY level survive when scenario is no longer valid. User handles own capital and shares: no KRW1m, 1% rule, or quantity in price-engine inputs.

## Newly detected material source conflict
For **삼아알미늄 006110**, 2026-10-19 screenshot was at 83,800 KRW *intraday* with historical A/B buy bands 74,000–76,500 / 78,500–80,500, old scenario invalidation approx 72,000 and aspirational 90,000–105,000 targets. These CANNOT be reused as current entry/target.

Historical provider close conflict (not official KRX audited venue data):
| Historical session | Investing.com | StockPulse | Difference |
|---|---:|---:|---:|
| 2026-10-20 | 83,800 | 82,400 | 1,400 |
| 2026-10-22 | 73,600 | 72,500 | 1,100 |
| 2026-10-23 | 67,500 | 67,400 | 100 |

Source links:
- https://kr.investing.com/equities/sam-a-aluminiu-historical-data
- https://sangsoo.synology.me/stocks/006110
- https://alphasquare.co.kr/home/stock-summary?code=006110

**Both Oct23 close suppliers BELOW screenshot 72k invalidation reference.** 2026-10-26 different-time *delayed intraday* prices ~59,800–60,500 were also below; never cross-compare delayed intraday snapshots as if they were the same fully closed KRX regular session. **Old plan status = ARCHIVED_PLAN_BROKEN / REBUILD**, **not proof that investor's stop-order filled at 72k**. Intraday low around 58,800–58,900 and high around 65,400 only historical same-day *provisional observation markers*, NOT newly verified support/resistance or valid BUY orders.

**Why providers disagree is not established**. Historical adjusted prices, trading venue NXT/regular aggregation, provider feeds, corp action or publication time are hypothetical root causes and should not be presented as findings. Review authentic KRX regular-only dated bar as source of truth before projecting exact new chart levels.

## What is actually coded

- GitHub core `research/c3_v650/evidence_gate.py`: compare independent providers by identical completed-session ticker/date; flag even small 100 KRW close mismatch and >0.5% spread; no mixing asof intraday quotes; differentiate two independent completed closes under the old floor from only an intraday dip; timezone validation, future bar rejection; hard return `trade_approved=False, orders_enabled=False`.
- GitHub fixture `research/c3_v650/test_evidence_gate.py`, read-only no-secret workflow `.github/workflows/c3_v650_evidence_only.yml`. **No new GitHub Actions CI success claimed** unless actually checked in actions list. This GH core is a *compact subset* of the local full module.
- User's full offline, deeper read-only module `c3_v650/c3_technical_evidence_v650.py`: additionally tracks dated price levels and converts old support above current quote into potential overhead review, forbids fake POC or invented price targets, handles every level with provenance and temporal guards, and auto-generates JSON from an anchored Sam-A case. **33 local fixture tests passed and separately unzipped execution reproduced identical output**.
- Deliverables in conversation: `C3_v650_증거검증형_트레이딩방법서_코드_테스트.zip` SHA256 `1982f4f703c2fc833515942cdf0b17237482f7fcbe8aa56ed5e9c626e84e2107`, `c3_v650/C3_v650_검증형_트레이딩방법서_연구보고서.md`, `sama_20261026_cross_source_fixture.json`, `sama_multisource_audit.json`, `SHA256SUMS.txt`. Local ZIP also includes preserved v6.49 original invalidation guard source and its 21 tests. **This release does not include a new live market data integration, and no historical full-market backtest was run.**

## Stop automated unsupported claim inflation
- Screenshots / portal OHLC should be marked **OBSERVED THIRD-PARTY**, not independently verified KRX certified 09:00–15:30. An HTTPS URL or input JSON boolean does not certify market provenance.
- Moving averages / daily OHLC cannot reconstruct actual price-by-volume POC/VAH/VAL. Reference https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/
- A support zone which is now **ABOVE** current quote must NEVER be reused as buyable support. May be future overhead, but that too requires new price structure confirmation.
- A new ticker actionable report should have date-stamped completed current quote, market and industry momentum, direct issuer catalyst and source publication day, completed pivots and immediate resistance, exact structure stop as **thesis invalidation** and new upside conditions; unconfirmed fields must say **미확인/대기** rather than copied screenshot levels. Note original stock-selection profitability is still *not* independently proven.
- Keep Work v6.38 A/B research benchmark frozen, optional second-buy nonmechanical. The 2670 prior v6.48 simulations are retrospective, not official broker fills. User handles position sizing; no capital management reports.
- **Research PR #25 remains DRAFT, K100 unchanged, no trading engine merge or autoorder.**

## Next profitable-strategy work
First audit source quality, then **market/sector relative leadership + stock-specific catalyst and durable swing structure as-of D** (not just lowering unfilled price bids). Test the same fixed candidate before next regular session, verify entry probabilities with eligible market prices and actual broker order timestamps. Evaluate results including misses, support failure and invalidation; never infer high win rate from a screenshot.
