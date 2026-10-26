# C3 v6.37 — execution, eligibility and structural-stop research

The previous frozen-account replay hid recent positions by requiring twelve future candles, did not mark daily equity, and used a rolling three-day low as a structural-stop proxy. The v6.33 candidate pool also included preferred shares and pharmaceutical/biotech issuers. This change adds a chronological, one-slot paper engine and explicitly separates those deficiencies from profitability evidence. **No live engine is enabled; PR remains draft, CASH, no orders, K100 unchanged.**

The v6.36 corrected 30 account/cost scenarios were reproduced before this work. The superseded v6.35 `Series.asof`-polluted account returns remain invalid. Do not replace the corrected v6.36 baseline with the newly explored returns as though it were the same experiment.

**Completed retrospective work**

- Initial raw cohort: 197 NEAR60 signals, 171 tickers, 75 D dates; 494 portfolio replays, including 400 same-date random selectors.
- Snapshot-cleaned cohort: 169 signals, 146 tickers, 68 D dates; 910 replays, including 800 random portfolios. Removed 13 non-common-equity signals and 15 pharma/bio signals. The KRX base-info request date is Oct23, fetched Oct25; the KIND industry-file vintage is unknown. Historical PIT eligibility is still unverified.
- Additional stop-only sensitivity: 16 replays using a most-recent daily low confirmed by two left/two right candles. These were added after initial results, are exploratory, and retain the D rank unchanged to isolate stop sensitivity.
- All use Jan02–Oct23 2026, 197 archive sessions, hypothetical KRW1m, planned account risk 1%, integer shares, one slot, 0.65% / 0.95% assumed two-leg costs. They do not apply verified final-score80 / overhead2R / regular-only / total-return / broker-fill approval.

| Same basic D rank and retest entry | Base paper ROI | Stress paper ROI | Completed base trades |
|---|---:|---:|---:|
| Rolling-three-day-low stop, legacy trailing7, max12 | +2.8001% | +2.2932% | 14 |
| Rolling-three-day-low stop, profit-activated ATR, max12 | +5.6544% | +4.3964% | 13 |
| Confirmed daily pivot stop, profit-activated ATR, max12 | +1.5298% | +1.0588% | 13 |

Balanced rank / confirmed pivot / retest / ATR gives +3.6089% base, +3.0488% stress, 12 closed proxies, but was explored after seeing other results and is **not** a promoted champion. Rolling-stop ATR base loses -0.5751% when its two strongest signal dates are omitted and the whole portfolio is replayed. The legacy retest control retains +0.8914% in that diagnostic. Within-family monthly max-t diagnostics do not establish significant edge; minimum diagnostic value ~0.147, only ten already-seen months and unknown prior trial count. Random-selector percentiles are not future profit probabilities.

**Implementation**

`c3_event_replay_v637.py` precommits quantity at a D-known cap, reserves buy costs, processes daily order/position events, distinguishes exact limit touches from trade-through proxies, uses only earlier completed bars for active stops, liquidates stop gaps at the opening price proxy, and marks outstanding shares after assumed sell costs. It never discards a recent signal just because its planned horizon is incomplete. Missing held-stock bars or large corporate-action-like gaps halt evaluation instead of silently switching ticker. Monthly PnL includes open inventory. Marked drawdown is end-of-day, not intraday or broker-certified.

Open-gap cancellation followed by an assumed opening-price fill is an OHLC execution proxy; an actual next-tick price, auction cancellation timing, limit queue priority and intraday ordering are unavailable. Chronological daily processing does not certify those intrabar assumptions.

`c3_eligibility_v637.py` verifies KRX base-info file hashes, explicit security group/share kind, SPAC and pharma/bio exclusions. Missing industries are unapproved. Snapshot cleanup explicitly does not prove historical eligibility.

`c3_forward_freeze_v637.py` derives D-only NEAR60 candidates with the frozen cooldown, records both stop definitions and rank/exit comparisons separately, and rejects overwriting an existing same-date result. An Oct23 rehearsal scanned 2,261 snapshot-eligible files out of 2,870 historical price codes and found zero new NEAR60 signals. This is not a completed Oct26 observation or an all-strategy market verdict. No scheduler or live order integration is added.

**Validation and reproduction**

74 new tests pass locally. Each initial/cleaned 72-scenario table reconciles trade PnL, monthly PnL and ending equity. All 72 cleaned scenarios reproduce identically from an exact-member compact archive. Full remote historical execution is not claimed. The workflow runs unit tests on research pushes and offers an optional manual replay; the original artifact expires Jan21 2027.

The original source is GitHub run `39948306433`, artifact `12502033196`, SHA256 `7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30`. Frozen candidate input and snapshot audit are under `research/c3_v637/`. With the original archive downloaded as `work/source.zip`:

```bash
python -m unittest discover -s scripts -p 'test_c3_*v637.py'
python scripts/c3_research_v637.py --source-zip work/source.zip --candidates research/c3_v637/frozen_candidates_v633_NEAR60.csv --eligibility-csv research/c3_v637/eligibility_snapshot.csv --out work/v637
python scripts/c3_structure_sensitivity_v637.py --source-zip work/source.zip --candidates research/c3_v637/frozen_candidates_v633_NEAR60.csv --eligibility-csv research/c3_v637/eligibility_snapshot.csv --out work/structure
```

Independent completed forward trades remain **0**. Actual current account balance, score80, independent regular-only OHLC, dated executable resistance2R, dividends/corporate actions, sector/company context and real fills remain unresolved. Keep the existing research controls; do not activate orders, merge the research stack into production, or modify K100 based on these exploratory returns.
