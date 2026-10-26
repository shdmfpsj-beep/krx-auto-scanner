# C3 v6.52 (2026-10-26) — ETF group dated membership, leadership and negative absolute returns

**Read-only. CASH/WAIT. 0 independent forward broker trades.** Price-first user-owned capital; no 100만원/1% position sizing involved in stock ranking, entry, structural stop or documented target. Work A/B frozen; K100 untouched.

## New usable source discovered in archived v18 (source max close 2026-10-23)

This study materially revises v6.51's earlier "sector information not present" assumption: the archived `v18-market-source.zip` in fact has:
- **17 ETF theme/sector groups** in `research/sector_evidence_daily.csv`, 41 research days (Aug24–Oct23) ×17 = **697 dated observations**.
- `market/sector_membership_dated.csv` with **7,228 dated ETF constituent records**, 16 dated snapshot sessions from Jul9–Oct19.
- Exact 17 traded ETF price series and KODEX200 ETF proxy `069500` through Oct23.
- D-day 5/20day group-vs-market relative-strength, positive-breadth of ETF basket, dated-query institutional/foreign member flows. **These flows are summed across constituent stock baskets, NOT an entire economic industry and NOT shares proven as pastaneously publicly available.**
- Source declares `point_in_time_status=PROVIDER_DATED_NOT_INDEPENDENT_VINTAGE_VERIFIED`, `membership_status=PROVIDER_DATED_PROXY_NOT_STRICT_PIT`, `live_selection_authorized=False` for **ALL** evidence rows. Despite snapshot-date labels, vintage was collected later. No production trade gate can be passed. Exact classification of **non-pharma/biotech ordinary shares** remains unverified even when ETF `HEALTH` excluded as a group.

## 5-session sector ETF actual future PRICE diagnostic (not realizable account ROI)

After excluding HEALTH ETF at the ETF GROUP level and omitting dates lacking a subsequent 5-session closing price, **16 ETFs × 36 dates = 576 overlapping sector-date research points over just 8 unique calendar weeks**, with strong overlapping future windows. A sector return is D ETF close to D+5 ETF close, excluding fees, dividends and actual after-D fill; `069500` is comparison index ETF proxy.

| Frozen D sector criterion | n sector-date | next-5d ETF absolute mean | next-5d excess vs 069500 | all 576 sector-date opportunities with rejected=0 CASH |
|---|---:|---:|---:|---:|
| All | 576 | -1.757% | +0.724 pp | -1.757% |
| As-of sector 5day RS >0 pp | 293 | **-2.232%** | +0.216 pp | -1.135% |
| ETF member group 5day advancing >=50% | 184 | **-2.537%** | +1.403 pp | -0.811% |
| Both RS>0 and breadth>=50% | 130 | **-2.881%** | +1.534 pp | -0.650% |
| Foreign+institution summed 5day netbuy positive | 227 | **-1.957%** | +0.401 pp | -0.771% |

**Interpretation**: positive relative strength to a dropping market or more-positive breadth did **NOT** forecast positive absolute 5day ETF returns in these 36 dated positions. Forgoing losing positions (CASH0) can improve the mean but does NOT prove tradable gains. Eight-week bootstrap (2,000 draws, resample whole weeks of multiple correlated dates/sectors) gives for RS>0 vs unconditional an improvement +0.622pp with 95% empirical interval **[-0.282, +1.544]pp**, including zero. Four tested gates and retrospective discovery/multiple tries reduce credibility. NOT independent out-of-sample validation.

## Actual Work D-selected swing stock signals and ETF-membership coverage

Existing v6.51 study had 264 completely observed past historical Work 5-day entry/exit proxies; only **32** occur within the Aug24–Oct23 sector evidence date window (20 distinct D days). For any 006xxx ticker membership, first find the **latest FULL ETF snapshot for each group** at/before that date, and ONLY THEN check whether the ticker remained a member. This corrected an initial bug where a removed ticker from an older snapshot was incorrectly carried forward: **15/32** attach to at least one non-HEALTH ETF group; **17/32 unclassified**; **4/15** belong to multiple ETF groups. If there is more than one ETF, a deterministic highest D-sector-relative-strength representative is marked for exploratory analyses, but all memberships remain listed in source and no claim of unique real economic industry.

| Research candidate group | n D stock signals | next-5d original Work one-entry proxy mean |
|---|---:|---:|
| All date-window signals |32| -1.962% |
| Any non-HEALTH member |15| -1.793% |
| Member sector RS>0 |10| **-4.112%** |
| Sector RS>0 and member breadth>=50% |7| **-3.553%** |

These are **not independent stock trades**, brokers not confirmed and entire parent history repeatedly mined. This very small sample **contradicts promoting the strongest proxy sectors to automatic C3 BUY**.

## Last recorded as-of 2026-10-23 sector watch, NOT Oct26 current
- CONSTRUCTION ETF `117700` RS5 **+8.305pp** vs 069500, 5d positive ETF basket members **25%**.
- INSURANCE `140700` RS5 **+1.674pp**, basket advancing **45.45%**.
- CONTENT `266360` RS5 **-0.806pp**, advancing **15.79%**.
- ROBOT `445290` RS5 **-1.034pp**, advancing **12.50%**.
- RENEWABLE `385510` RS5 **-2.177pp**, advancing **11.39%**.
- **0 of 16 non-HEALTH ETF baskets on Oct23** simultaneously had positive rs5 and majority rising members. These do not authorize any stock price or target or next-day BUY. The current Oct26 full certified industry panel has not been supplied in research ZIP.

## Reproducible release and new GitHub code

Local **30 regression tests PASS**; portable conversation ZIP `C3_v652_업종주도력_수익성검증_연구자료.zip` SHA256 `34717ea2a9e0bcb422b1deb5c6bc3e7d1d1cc4b3a720afbcb9382f1ca1bd638e`. Contains:
- Pure Python `sector_leadership_v652.py`, local `run_v652.py`, `test_sector_v652.py`.
- **20 original v18 byte-identical CSVs** repackaged small `input_research_v652_compact.zip` (membership, sector evidence and 18 ETFs including benchmark), per-member SHA256 manifest and 32 historical Work signals in a fully portable 392KB download. Original big v18 archive SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30`. This package intentionally does NOT include 2,870 whole-market ticker prices; outcomes from immutable earlier v6.51 source. 
- All 697 ETF dated rows with 5d results/benchmarks and all 32 candidate joins, 17-group and candidate summaries, week-bootstrap CSV/JSON and Oct23 watch CSV, Korean detailed report.
- A **completely new directory clean extraction executed 30/30 tests and 6 output CSV/JSON SHA256 matched byte-for-byte**. This is reproducibility of already mined prices, not fresh profitability.
- Github research source `research/c3_v652/sector_provenance_gate.py`, fixture test `research/c3_v652/test_sector_provenance_gate.py`, workflow `.github/workflows/c3_v652_sector_provenance.yml`. These GitHub files constitute **one small ETF membership/PIT safety subset**, not the full on-GitHub 30-test market replay. **Remote CI completion NOT asserted.** This documentation was committed; do not merge research draft to production or modify K100.
 
## What to build next

1. Need independently timestamped original ETF PDF publication file and actual 09:00–15:30 KRX venue regular-only prices before category membership considered actionable.
2. Distinguish **absolute ETF rising vs positive excess to falling market**, issuer standalone catalysts/earnings and genuine sector transaction breadth at D-close; maintain company PIT / non-biotech ordinary share filter.
3. Deliver requested rich **one-stock trading manual**: A chart-confirmed support entry, B realistic pullback, C conditional breakout, original daily structural stop, verified overhead and 1st/2nd extension objectives, evidence-stamped higher/lower upside with hold/sell scripts. **Where verified current price/resistance cannot be established, show DATA REQUIRED / CASH**, not fake figures.
4. Carry a frozen contemporaneous snapshot into new completed days (starting 2026-10-26 after complete regular-market archive is independently verified), compare actual future 5–12 sessions, missed quotes/orders, and negative case labels before changing any score weights.

Academic orientation: Moskowitz & Grinblatt (1999), *Do Industries Explain Momentum?*, https://doi.org/10.1111/0022-1082.00146 studies industry momentum on materially longer horizons, not proof of 5-session C3 Korean stocks. ETF PDF and dated fund data source KRX https://data.krx.co.kr/ .

**Status: cash/observation, 0 live BUY, 0 new independent completed trades, orders disabled, original A/B frozen, K100 unchanged, PR #25 DRAFT.**
