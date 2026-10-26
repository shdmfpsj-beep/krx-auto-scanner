# C3 v6.41 (2026-10-26) — User-confirmed OPTIONAL 2nd buy in high-confidence trends

**Priority clarification, overrides any interpretation of v6.40 as automatically requiring a 3–4% account risk budget or mandatory -7..-10% add.**

The user tolerates up to approximately **-10% price excursion from a FIRST entry ONLY for unusually strong, convincingly bullish stocks where a better 2nd entry emerges**. This is NOT permission to mechanically buy at -10% down, NOT an account-level -10% maximum loss and NOT automatic approval of 3–4% account risk. There is no validated probabilistic accuracy or quantified guaranteed likelihood; the thesis must be supported by as-of independent sector/issuer/technicals.

### Guardrails implemented and locally tested

1. Keep immutable v6.38 A/B models with old 1% *research assumption* exactly as frozen; v6.41 is **new model C conditional 2-leg study**. The user did not retroactively approve risk alterations to published v6.38 backtests.
2. First entry, *before order*: identify truly bullish sector and stock, real issuer catalyst and verified financial quality, documented daily confirmed support, stop, near-term supply/resistance, no lookahead as-of D, and reserve cash for possible OPTIONAL future second.
3. Second entry is a **choice, not an obligation**, can be considered at -3%, -5%, or -10% first-entry drawdown after actual confirmed rebound/support reclaim, not necessarily at -7 to -10%. If original daily pivot failed at any point, the sector and stock leadership deteriorated, company catalyst failed, event data not verified or market is weak: **NO ADD**, regardless of discount. The first stop can NEVER be lowered merely to allow averaging.
4. On a completed as-of D confirmation, only D+1 (or later) may potentially contain a second *paper* order. The daily low touching a limit is NOT broker fill.
5. Before any proposed 2nd: verify pre-declared issuer stock score >=80, dated real overhead net reward/risk >=2 *after combined buys*, completed regular-session 09:00–15:30 source, corporate action PIT, actual broker cash and min1-share (when available). Unverified inputs = CASH.
6. No automatic account loss fraction. Compare **1%, 2%, 3%, 4% only as case-specific explicit research scenarios**, with normal filled-at-stop account loss and an additional gap-far-below-stop stress; a budget is NOT a loss guarantee. The user DID NOT select a permanent 3/4% trading allowance. Default code `risk_budget_pct=None` blocks any proposed staged quantities until research scenario is explicitly chosen.
7. To prevent reckless Martingale scaling, research soft cap **2nd shares <= 1st shares**, model total nominal ≤ 50% of 1000000, and no third or subsequent purchases. These are provisional conservative **research** caps, not permanent agreed trading allocations.

### Example study ONLY (hypothetical +10%? No! First 50000, second 45000 at -10%, original stop 43000)
Assume **fictitious** dated resistance 58000, buy 0.15%, sell 0.50%, user later confirms support/reclaim. These prices/confirmation flags are illustrative, not a present trade or demonstrated probability. The 58000 resistance is NOT chart-verified.

| Research risk scenario | First+second shares | Planned stop+cost combined loss | At 40000 gap-exit actual-price modeled loss |
|---|---:|---:|---:|
| 1% of hypothetical 1m | 0+0, cannot afford first share at frozen first-risk reserve | no trade | no trade |
| 2% | 1+1 | 9572.50 KRW (0.957%) | 15542.50 KRW (1.554%) |
| 3% | 2+2 | 19145 KRW (1.915%) | 31085 KRW (3.108%) |
| 4% | 3+3 | 28717.50 KRW (2.872%) | 46627.50 KRW (4.663%) |

**These are arithmetic guardrail examples with price inputs invented for explanation, NOT measured after-cost returns.** Existing user real Kiwoom cash not replaced by the 1m paper amount, order enabled False, K100 untouched.

### Actual work this turn

- New local Python `/mnt/data/c3_v641/conviction_add_v641.py` (24 locally passing fixture tests `test_conviction_add_v641.py`), `v641_research_config.json`, `v641_hypothetical_risk_scenarios.csv` and Korean markdown explanatory report.
- Complete runnable ZIP `C3_v641_조건부_2차매수_연구코드.zip` in user conversation; this GitHub entry is a **research ledger only**, not a claim that the full v6.41 Python source/CI ran on Github. The existing v6.38 frozen implementation hashes are not changed.
- **Unverified research edge, no new post-2026-10-26 completed out-of-sample trades; 0 live orders and 0 approved BUY.** Production model remains CASH until certified source, 2R, final80, broker and actual market conditions are validated.

Future study: compare v6.41 C candidate against the frozen original v6.38 A/B 1-leg setups under the same new verified as-of day, actual future available second-add evidence, time-ordered fill/cancel, one-slot cash accounting, realized+marked monthly return, drawdown/gap loss and true broker-verified fills. Do not optimize second drawdown thresholds on already mined earlier 2026 data.
