# C3 v6.38 — precommitted orders, stop-first screening and frozen forward protocol

The v6.37 opening-gap filter could reject an already resting limit using the subsequently observed opening price. This changes which trades enter the one-slot account. v6.38 models orders submitted before the next session, records a gap-through-support entry instead of retroactively cancelling it, and prevents a later intraday high from supplying a target fill that may have happened before entry. These remain OHLC execution proxies, not broker-confirmed fills.

The first publication is now authorized by the user's Oct26 followup. v6.37 is available at commit `7fd6b9faf2790923a3fe952b8472a24672eeaa06`, with its 74-test GitHub run [40247613481](https://github.com/shdmfpsj-beep/krx-auto-scanner/actions/runs/40247613481). Research stays on PR25; no main strategy merge, orders or K100 changes.

**What was implemented and tested**

- Shared accounting accepts explicit order/exit handlers. All 72 v6.37 account/cost scenarios still reproduce identically; no module-global monkeypatching.
- A pivot's buffer is fixed at its confirmation date. A later ATR cannot rescue a broken pivot; failed latest pivots do not fall back to an older support. This is a defensive improvement: the audited 197 old NEAR60 signals contain **zero observed already-breached v6.37 pivots**. Do not attribute the historical ROI change to nonexistent broken-pivot cases.
- D-only actual structural risk is available for ranking and quantity. A separate legacy setup-compactness feature is retained as a control and is not labelled the actual stop risk.
- Three resting-entry protocols, three exits, market-trend/CASH filter, assumed costs, one-slot reservations, integer shares, gaps, missing candles, end-of-day equity and zero-order defaults.
- Known-cash alternatives may be chosen **at D close**, never after D+1 gaps or missed fills. This optional intervention did not justify changing the default.
- Whole-source scanning: 2,870 historical price files, 2,261 codes allowed by the common-stock/nonpharma snapshot; 267 D-only candidates from 195 tickers. NEAR60 has 142 signals / 64 D dates; first-pullback trend has 125 / 70.
- 1,194 primary/control/stress replays, 923 disclosed adaptive followups, 24 controlled old-cohort ablations and 4 post-shortlist net2R geometry checks: **2,145 repeated historical portfolio replays**, not 2,145 independent trades. The data were already studied, and followups were adapted after seeing results.
- 129 local tests pass. The new GitHub workflow rebuilds source eligibility, runs the full study and compares all 144 primary account/cost outcomes with the committed reference.

**Controlled execution ablation, fixed old cohort**

| D rank and stop | v6.37 opening-filter proxy | v6.38 precommitted resting order |
|---|---:|---:|
| Basic / rolling-three-day proxy / ATR | +5.6544% | +3.9331% |
| Basic / confirmed daily pivot / ATR | +1.5298% | +1.1488% |
| Balanced / confirmed daily pivot / ATR | +3.6089% | +1.1488% |

These ablations hold the old D choices, capital, risk, entry cap and exit fixed. Do not compare them with the expanded-universe results as though only execution changed.

**Frozen research shortlist**

Period Jan02–Oct23 2026, hypothetical KRW1m, planned account risk 1%, one integer-share position. Assumed two-leg costs: 0.65% base, 0.95% and 1.25% stress, applied to each leg's own price. These are assumptions, not verified current brokerage rates.

| Research hypothesis | Closed proxies | Base ROI | 0.95% cost | 1.25% cost | Base daily marked MDD |
|---|---:|---:|---:|---:|---:|
| A: first trend pullback / setup score / one-day resting limit / benchmark trend / day5 close | 14 | +4.8900% | +4.4423% | +3.7219% | -1.2498% |
| B: first trend pullback / actual-structure score / one-day resting limit / benchmark trend / 10% limit target, max12 | 11 | +3.8801% | +3.3655% | not tested | -1.1524% |

A remains +1.6421% after its two strongest D signals are missed and the whole portfolio is replayed (+1.1594% at 0.95%, +0.7760% at 1.25%). Independently presampled 40% missed-order sensitivity has +2.4584% median, +0.4090% minimum across the twenty tested seeds; these are assumed miss rates, not measured broker probabilities. Leave-one-entry-month-out replays range +2.1753% to +5.6420% at base cost.

**The user's net2R gate is not satisfied by the headline returns**

The A/B frozen hypotheses are price-pattern research controls; they do not apply final80, company/sector/cash verification or the user's verified overhead net2R requirement. In particular, **all 14 A and all 11 B original base-cost closed proxies lack an automatic D-high resistance cluster above their D close**. Do not describe their headline ROI as the return of the fully eligible live strategy.

The separate, post-shortlist `scripts/c3_rr_geometry_audit_v638.py` preserves the same D ranking and lowers the resting cap to the cost-adjusted net2R maximum derived from automatic D-high clusters, rejecting missing resistance. It yields only two closed proxies for A (+1.3781% base, +1.3074% stress) and two for B (+1.2388%, +1.1336%). These are different portfolio paths, **not a filtered subset of the original 14/11**, and two proxies provide no reliable profitability inference. Automatic clusters remain unverified real resistance. This audit does not change the frozen A/B protocol or authorize trades.

**Material weaknesses remain**

- A's H2 account contributes only +0.3465%, four closed proxies, versus H1 +4.4486%. Both segments were already seen, not holdouts.
- Changing initial cash changes integer-share eligibility and the subsequent one-slot trade path: KRW269,230 / 1% risk gives +0.0705% (5 proxies); KRW3m / 1% gives **-1.0062%** (17). At KRW1m / 2% risk, ROI is only +1.8519%, marked MDD -3.9250%. Do not scale +4.89% linearly or increase risk as a profitability fix.
- Day3 neighboring exits are negative; some day6/deeper-limit combinations are negative. The five-day result is not a broad parameter plateau.
- A ranks at the 97.5th percentile of the selected same-date random control, but this is not a future win probability. Across the initial 72 designs the within-family monthly max-t diagnostic has minimum ~0.517, only ten already-seen months and unknown earlier trial count. No statistically established edge is claimed.
- Snapshot issuer and industry classification is not historical PIT evidence. Corporate-action total returns, regular-only source fields, auction timing, queue priority and real execution remain unverified. `actual_turnover_krw` is a compatibility name for source-reported turnover; its session scope is separately unverified and must not be called verified regular-only turnover.
- Source-archive benchmark buy-and-hold is +41.0132% at full hypothetical investment. Its risk/exposure differs from this low-notional stop-budget account; the strategy has not demonstrated market outperformance.
- A failed-rebound close rule raises the explored result to +5.0890%, only +0.1990pp. It and affordability/RS filters are kept as controls, not added to the default after seeing the outcomes.

**Forward protocol and quota-efficient reproducibility**

`research/c3_v638/frozen_protocol_v1.json` fixes A/B selection, complete entry/exit/risk parameters and implementation hashes. Existing dated records cannot be overwritten, and changed code cannot silently reuse the protocol. The first fresh D date is Oct26, registered before that session's close. Research review can use verified forward paper prices without putting real money at risk; actual BUY approval still requires current account cash, final80, independently supported net2R, company/sector checks and regular-source evidence.

An Oct23 rehearsal has one first-pullback candidate, but fails the benchmark-trend gate: both hypotheses emit **CASH**. This is not an Oct26 real-time conclusion. Verified fresh completed trades remain **0**; automatic orders remain false.

The workflow `.github/workflows/c3_profit_research_v638.yml` downloads the frozen market and issuer artifacts using the existing GitHub connection, rebuilds eligibility from `reports/kind_sector_master.csv`, runs the study and archives results. It runs on research-code pushes. It is a research reproducibility job, not a new daily live trading schedule.

New-source snapshot mode does **no optimization**. It requires a known artifact digest, the requested completed session, a matching issuer snapshot input, and the frozen protocol. It rejects future or unclosed sessions. Missing regular-only/source/actual-fill proof remains explicitly unverified.

```bash
python -m unittest discover -s scripts -p 'test_c3_*v63[78].py'
python scripts/c3_prepare_v638_inputs.py --market-zip work/market.zip --issuer-zip work/issuer.zip --sector-csv reports/kind_sector_master.csv --out work/inputs
python scripts/c3_research_v638.py --source-zip work/market.zip --eligibility-csv work/inputs/eligibility_snapshot.csv --out work/primary
python scripts/c3_followup_v638.py --primary-dir work/primary --source-zip work/market.zip --out work/followup
```

The parent artifact hashes and the expected primary metrics are committed under `research/c3_v638/`. Sources: [TradingView official strategy execution documentation](https://www.tradingview.com/pine-script-docs/concepts/strategies/) and [Bailey–Lopez de Prado on selection bias](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), as methodological references, not proof of these Korean-stock returns.
