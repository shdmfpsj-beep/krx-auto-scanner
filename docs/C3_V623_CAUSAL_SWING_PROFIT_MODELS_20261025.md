# C3 v6.23 — Profit-predicting swing models and causal orderability correction

**Date 2026-10-25; latest historical stock bar 2026-10-23. No real stock BUY, no orders.**

This project extends the v6.22 +20% winner ranker with **7 selection models x 7 exit methods** and evaluates hypothetical one-at-a-time five-session swing positions in April–June and July–October 2026.

## Crucial v6.23 correction: stock selection must precede next day's open

The exploratory first-stage backtest filtered/ranked stock candidates based on prospective D+1 opening gap and stop-distance before selecting the stock on day D. The result was **not decision-time feasible**: HGB expected 5-day return + trailing stop seemed -2.79% for April–June (8 studies) and **+2.94%** for July–October (10 studies). **Do NOT cite the +2.94% as an executable or validated result.**

In the corrected analysis:
1. Compute stock model score and stop-risk **only using D completed-session information**;
2. select exactly one ticker at D close, without looking at next opening;
3. inspect D+1 gap only after the decision; if outside -2% to +2.5% of prior close or below D-defined stop, mark cancellation and **do not retrospectively replace it with another candidate**;
4. assume D+1 open is the hypothetical entry in passing cases (still optimistic/no broker fill);
5. run five chronological market sessions with same-candle stop-first 0.65% total fee/slippage and never more than one active position.

**Results after correction (structure-stop plus 7%-from-prior-high trailing stop; STOP-FIRST):**

| Model | 2026 Apr–Jun | 2026 Jul–Oct | Finding |
|---|---:|---:|---|
| HGB 5d net expectancy | -0.204% / 8 trades | -1.850% / 10 | Neither profitable |
| Ridge 5d net expectancy | -1.665% / 8 | +2.177% / 11 | One positive period only |
| D-date risk 2–8% + historical prior overhead >2R, HGB | -2.151% / 7 | -1.435% / 10 | Both negative |
| HGB + low predicted tail-loss risk + overhead >2R | +0.818% / 6 | -2.983% / 10 | Positive early mean from one exceptional winner; negative median |

The user-requested reward:risk metric is **pre-entry geometric headroom only**, not a model's expected rate or verified resistance source. A D-history 16-bar low minus 0.15 ATR is a structural-*proxy* stop, not certified pivot, and must not be promoted to a live stop recommendation.

**Important uncertainties:** July–October was reviewed already in v6.22, so this is **not a genuinely unseen prospective holdout**. Multiple variants (49 initial combinations plus exploratory gates) increase multiple-testing risks. These OHLC bars have unverified 09:00–15:30 KRX-only provenance, historical issuer common stock, excluded pharma/biotech, corporate action, and point-in-time filings. D+1 opening hypothetical fill is not a proven executable broker price. C3 cash/size/broker fills unverified. USA macro not historically released-time matched in this test.

**Credible conclusion:** Not one repeatedly positive live-deployable C3 model was validated; retain CASH and old >=80/100 stock/2R/capital/market gates. For subsequent *genuinely new sessions*, prioritize a two-stage shortlist: initial trend recovery within strong sectors, only then historical structural pivot + 2R + strictly bounded gap, paper fill/stop/exit and market benchmark, and accumulate independent non-overlapping real-session outcomes before modifying main.

**Artifact:** In the initiating ChatGPT conversation, `C3_v623_profitability_models_research.zip` contains executable Python scripts, full local as-of-corrected comparisons and 8 passing unit tests, along with `C3_v623_profit_model_research_report.md`. v6.23 analyses **ran locally in the ChatGPT container**, not claimed as successful GitHub Actions CI. All script orders disabled and PR remains draft.
