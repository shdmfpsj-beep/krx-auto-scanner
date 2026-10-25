# C3 v6.35 — 1,000,000 KRW research principal, frozen-hypothesis sizing audit (2026-10-26 PREMARKET)

## New parameter SET for hypothetical C3 research, NOT Kiwoom actual deposit or balance
- **starting research capital KRW 1,000,000**; **per-trade account-equity risk budget 1% = initial KRW 10,000**. 0.5% is conservative research comparison and 2% is stress only, not an authorized trading increase.
- One open stock maximum, integer shares only, no credit/leverage. Determine confirmed completed daily structural stop **BEFORE** sizing: `Q=min(floor(verified available cash / entry),floor(equity * 0.01 / ((entry-daily-structure-stop)+entry*0.0065)))`. Underlying 1% is **capital-risk, NOT price-stop percentage**. Stop gaps can cause risk above KRW 10k. The user's real current orderable cash and stock holdings MUST be independently verified and NEVER automatically set to 1m.
- Study round-trip total cost/slippage 0.65%, extra-friction stress 0.95%. These are modeling assumptions, not verified broker fees. After-hours/NXT excluded only if source session provenance is actually certified.
- Frozen candidate pool from v6.34: GST v6.32 original NEAR60 rank, GST v6.33 balanced rank, HMA+Darvas 0.65ATR deep D+1/D+2 first retest, WaveTrend D+1 open; separate HMA next-open baseline comparator. **NO NEW HISTORICAL HYPERPARAMETER SEARCH**.

## What was ACTUALLY executed
- Replayed fixed previously generated `v629_entry_mode_all_signal_studies.csv` **1,704** rows and `v633_frozen_rank_outcomes.csv` **5,544** rows, same D-day ticker and unchanged stop/exit in one-slot cash, rescaled to 1m, 3 research risk levels ×2 friction levels ×5 paths = **30 account scenarios**.
- Current-conversation reproducible artifacts `C3_v635_100만원_검증중심_연구자료.zip` and `C3_v635_100만원_수익성_연구보고서.md`, read-only Python script `v635_one_million_resizing.py` and **16 passing local unit tests**. The zipped input-status SHA and per-trade ledgers are included; Github CI/full-source re-execution is NOT claimed. Frozen parent sha256: v629 `f844a773787f4305f6b243eb1ff69a76a143dbe177a06b2078f36ee647fa4056`; v633 `2d76655163a1ddae57990c6e61040d55168d5e608f61fa675c89429dd63003dd`.

## Hypothetical old data (Jan–Oct23 2026), 1m initial balance, 1% risk, 0.65% friction
| Path (prior D-frozen research) | Simulated fills / not broker fills | End balance KRW | ROI | Under 0.95% friction ROI | Remaining additive PnL after removing largest 2 winning trade contributions |
|---|---:|---:|---:|---:|---:|
| GST v6.32 original rank, 12-session trailing7 | 52 | 1,075,296 | **+7.5296%** | **+4.8805%** | +10,694 KRW |
| GST v6.33 balanced rank, same hold | 50 | 1,033,319 | +3.3319% | +2.0479% | -31,284 KRW |
| HMA/Darvas 0.65ATR D+1/D+2 deep retest, trailing7 | 28 | 985,792 | -1.4208% | -1.8565% | -42,463 KRW |
| HMA/Darvas D+1 opening baseline | 35 | 956,012 | -4.3988% | -5.2017% | -66,987 KRW |
| WaveTrend D+1 opening, trailing7 | 14 | 998,818 | -0.1182% | -0.4877% | -27,308 KRW |

**CRITICAL:** Both GST lines previously selected using the same Jan–Oct23 studied market; no new out-of-sample positive evidence. GST ORIGINAL median virtual trade +0.3675% at 0.65% friction, but at 0.95% friction trade median **-0.20%** despite positive overall compound results. Top two profits excluded results are arithmetic attribution without recomputing account cash trajectory. The GST balanced rank **lost -0.592pp per same-D opportunity** in v6.33 audit. More available cash increases filled hypothetical tickets (was n14 original v6.33 at KRW269230, now n52 at KRW1m); do NOT read this as independently improved stock selection.
- Exit-only virtual equity peak drawdown and booked-trade-month realized PnL are available in local output. **Daily marked-to-market portfolio MDD, actual broker share fills, unfilled limit queue probability and session provenance are NOT verified**.
- Excluded company universe/PIT non-pharma-bio, dividend/split/merger corporate actions and contemporaneous sector leadership and certified overhead resistance >=2R remain blockers. 
- Study's **2026-10-26 onward truly new complete and certified regular-session trials = 0** at creation PREMARKET, orders_enabled=false, trade_approved=false, K100 unchanged. Actual live trades remain **CASH/PENDING_DATA_VALIDATION**. 

## Research next stage
Maintain four frozen models and sequentially record post-Oct26 completed 09:00–15:30 KRX D-signals plus D+1 actual broker confirmed cash and order fills or no-fill; 5d/12d returns, PIT corporate actions, month-end virtual marked portfolio drawdown, +0.30pp cost stress and benchmark/cash/placebo checks. Only reconsider at >=30 NEW independently completed eligible trades over >=3 separate entry months, positive net mean and trade median, after-cost and after-largest-two outcome, plus independently certified data. This alone does not establish statistical significance or an authorized BUY. Daily structural stop, independent final stock score >=80 and net overhead >=2R are also mandatory. Draft PR must remain unmerged as a live trading engine.
