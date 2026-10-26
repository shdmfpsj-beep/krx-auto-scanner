# C3 v6.51 — Retrospective as-of market breadth vs 5-day swing continuance (2026-10-26)

**Status: exploratory challenger, NOT a profitable live strategy. CASH / no actual BUY, Work A/B frozen, K100 unchanged.** User explicitly manages all money/share sizing, so no account capital or account-risk cap influences stock/entry/structure-stop/known-target quality. Primary aim is to find stocks **that continue rising**, not to optimize a deeper never-filled bid.

## Actual market data processing (executed locally)

- Parent Work successful v6.38 GitHub run `40250900699`, artifact `12621175343`; frozen v6.48 entry outcomes; v18 archive SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30` (prices complete **only through 2026-10-23**).
- Parsed **2,870** `market/prices/*.csv` stock-code files. **2,824** have at least one completed 2026 sample with 60-session trailing price. All 197 past research dates have a historical breadth row, source 10/23 final analyzed-code count **2,741**. D close relative to self 20-day moving average above fraction **15.7607%**, self 60-day above **24.9179%**, positive vs 5 sessions prior **17.6213%**. These are **archive universe proxies**, NOT certified KRX full common-share market statistics, issuer PIT/nonbiotech eligibility, NXT exclusion, true sector group breadth, or a new 10/26 completed tape.
- Work original D-only 267 signals / 195 tickers. Cross-joined by immutable model+date+ticker to prior v6.48 `OPEN_D1`, 5-session-stop-first terminal proxy returns. **264** completed observational returns across **94 distinct D dates**; 3 records not fully evaluable, NOT filled forward artificially. Costs inherited from parent price-only research ~0.65% roundtrip assumed, not broker fills.
- New **hypotheses set before running this iteration**, still applied to the SAME REPEATEDLY RESEARCHED January–Oct23 prices: breadth20>=0.5; 5-session ticker-vs-market `rs5>0`; reported `turnover_accel>=1`; combinations. Do NOT optimize 50% to 45% or 60% on these data or classify old wins as fresh proof.

## Retrospective 5-day return diagnostics (not account ROI)

| D-selection | Candidate complete observations | Conditional modeled mean net (%) | All 264 D-opportunity mean with passed=modeled, failed=CASH0 (%) |
|---|---:|---:|---:|
| No D gate | 264 | +0.6135 | +0.6135 |
| **breadth20>=50%** | **168** | **+1.6884** | **+1.0744** |
| Market-relative rs5>0 | 147 | +1.4055 | +0.7826 |
| Turnover acceleration>=1 | 207 | +0.5616 | +0.4403 |
| breadth>=50% AND rs5>0 | 98 | +2.5358 | +0.9413 |
| breadth>=50% AND rs5>0 AND turnover>=1 | 92 | +2.0753 | +0.7232 |

**Date-cluster bootstrap** (2,500 deterministic draws of trading dates, preserving correlated same-day candidates) for breadth>=50% vs ungated open on the SAME 264 signal-opportunity denominator: improvement **+0.4609 percentage point**, 95% date-resampling interval **[-0.0879,+1.0858] pp**, crosses zero. Inverse strong proof is NOT available; multiple testing and old repeatedly mined vintage make this optimistic. RS gate delta +0.1691 pp [-0.5839,+0.9084]; turnover-only gate **-0.1732pp** [-0.7645,+0.3650]. Do not add indiscriminate trade-value score weight.

**Last part Jul–Oct23 only** has 40 completed old shadow opportunities over 28 D dates: ungated open mean **-1.6898%**; breadth>=50% **11 signals mean -0.1265%**; breadth + RS **9 signals mean +0.2414%**, but **best-2 removed recent mean -1.076%**, only 6 D days for latter group. No retrospective month-based BUY suppression may be shipped. Sector breadth and issuer new official flows are unverified, cannot call this sector 1-3 leader filter.

## C3 reporting update

C3 full stock trading manual v6.49/v6.50 now adds an optional **D-known market participation / market width** evidence row, explicitly `RESEARCH_HYPOTHESIS`. A/B/C *chart* entry ranges, true structural stop and time-known resistance targets still come from company stock chart, not breadth or simulated account amount. Market breadth below half may be a **caution** (or CASH if other evidence weak), **NOT** permission to fabricate precise technical entry/stop/target. Inference quality is separated from verified session/industry/PIT provenance.

C3 Sam-A 006110 photographed Oct19 at 83,800 is a useful invalidation case: old 72k invalidation breached by multiple independent Oct23 THIRD-PARTY closes 67,400/67,500. New Oct26 third-party rows quote 59,950 vs 60,300 for daily close (feed/source mismatch unresolved), plus KOSPI historical provider discrepancies. Do not resuscitate old 74k–80.5k buy bands or target 90k–105k as current; no made-up new numbers while official KRX regular bar and dated issuer catalysts are absent.

## Reproduction artifacts

In user conversation **`C3_v651_시장폭_상승지속_연구자료.zip`**, SHA256 **`72f20b2c1cba25faa74b46e1a7934cef913ab21e04af96c4a17b009de03b6aa5`**; <200KB mobile package with frozen original 267 candidate rows & previously created v6.48 full 2670 scenario audit, 197 market breadth values, source SHA manifest, complete selection/bootstraps results, D-only pure code, **35 local tests passed**, reproduced independently from a clean ZIP extraction and **3 output CSVs hashed identical**. `c3_v651/C3_v651_시장폭_상승지속_연구보고서.md` gives all findings and methodological caveats.

**Data portability**: the 197-row derived breadth dataset and every D-candidate outcome are included for a standalone **264-row historical replay**. Full 2,870-code breadth rebuilding from price panels requires the separate 55MB frozen `v18-market-source.zip` with the exact parent SHA above; it is intentionally not duplicated in the small ZIP. Do not claim an unprovided complete raw archive is included. Local full source was actually run this iteration, remote GitHub Actions backtests are **NOT asserted**.

**No verified official 10/26 complete all-issuer source, no 5/12-session fresh independent result, no broker fill, no new final BUY.** Research PR#25 DRAFT, autoorders off, K100 unchanged. Next innovation must prioritize **as-of contemporaneous real sector membership & peer breadth**, issuer catalysts, source/venue official timestamps and new forward execution shadow testing; not arbitrary chart or indicator parameter tuning.
