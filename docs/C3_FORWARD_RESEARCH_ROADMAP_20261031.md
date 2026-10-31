# C3 Forward Research Roadmap — 2026-10-31

## Objective

Determine whether C3 selects usable early leaders at **pre-registered, realistically reachable prices**. Never interpret code execution or historical examples as profit validation. **Paper trades do not execute through a broker.** The experiment is prospective from registration.

## Research questions, in order

1. **P&L cohort survivorship fix (implemented in main on 2026-10-31)**. Previously an early full exit stopped the 5/10/20-session clock, excluding early losers/winners from comparative cohorts. Now retain *realized* net exit performance at these forward horizons, with no hindsight filling of a missing day. Add early-T2, early-stop, terminal gap tests. **Remote workflow success still needs verification**.
2. **Real KRX regular-session price provenance**. Existing pykrx OHLCV is declared but 09:00-15:30-only scope is not independently verified. For example, the 2026-10-30 technical dataset supplied scanner closes Orion 114200/Dongseo 28400, while separately checked 09:00-15:30 quotations were 114800/28450. Do not relabel scanner values as certified closes or silently adjust structure stops. Store per-ticker matched date, provider and SHA, and block production approval when differing.
3. **Reachable entry**, not tight stop+3% or blanket cash by score. Pre-register two genuinely different unambiguous plans for each eligible first-impulse leader: (A) structural pullback at confirmed support; (B) breakout/retest continuation with its own structurally justified stop. Never use an unobserved far-away target in place of the first actual resistance. Compare **plan opportunity rate**, missed breakout rate, gap-under-band exclusion and first-target risk/reward with costs.
4. **Automated new-day TOP2.** The Oct30 v5 and its portrait render are still research-branch examples. The daily main branch collects 2K+ stock original data, but it has not yet been bridged to a fresh dated dynamic v5 rank and large chart artifact. A new plan must be registered before any future trading session, not backfilled from already-observed success. Keep previous positions as separate immutable IDs.
5. **Market regime and sector relative strength.** Track broad 5/20-day median, breadth, verified turnover, actual foreign/institution flows when available, and drawdown risk. Compare the same predeclared rule in up / down / sideways markets; a strong stock on a sharply bearish day may only be *watch*.
6. **Catalysts & finance: helpful but not eligibility hurdles.** A missing headline or provisional DART record is neutral; red flags are evidence-based and require source-date attribution. No future-disclosed favorable news is attributed to an earlier decision.

## Fixed forward-test definitions (as of Oct31)

- Universe: Korean common-equity KOSPI/KOSDAQ; do not silently count a sample of 96 as a whole-market financial scan. Exclude biotech/pharma as requested.
- Source: completed same-date daily original full-universe scan, per-ticker OHLCV with source identity. Both date and source scope must be labeled; regular-session certification remains outstanding.
- Selection at after-close; pre-register plan_id, selection_date, registered_day, original close, band, stop, closest first/second observed resistance, version, source run. No registration-day low as a prospective entry.
- Eligible observation: **only a later, actually observed completed daily bar**. Enter one synthetic unit when the pre-existing entry range is touched subject to gap restrictions. This is *hypothetical OHLC touch*, **not fill proof**; document it separately from broker fills.
- Intraday chronological ambiguity: do not count entry-bar first/second target prices if an OHLC high could precede the entry touch.
- Expenses: buy 0.15%, sell 0.50%; first target half, second target remainder (research assumptions, not guaranteed obtainable).
- Close below pre-registered daily stop -> next **actually observed** opening auction as synthetic exit; never choose later favorable open if the next completed session was missing. Real loss can exceed structure stop in a gap.
- Plans canceled if support is broken before entry, first resistance reached without entry, or 5 *observed* sessions expire; no hindsight extensions.
- **Comparability fix**: closed early at target or stop remains in forward **5/10/20-session** cohorts at its *realized net result*; open positions use cost-adjusted close marks. Missing sessions => do not compute a fake forward mark.
- At the plan level, distinguish: registered, eligible observed, never entered, entered paper, exited paper, missed target without entry, stop invalidation, expired, terminal data gap. Do not use only profitable fills as the denominator.
- After sufficient observations, compare: plan opportunity rate, qualifying OHLC touch count, first target reach **after** entry, closed profit/loss after costs, near-stop rebound with no lookahead, 5/10/20 forward results, market-adjusted return, win/loss distribution and max adverse excursion. Report count and confidence/coverage limitations. **No fabricated success rate, no automatically executable trade.**

## Next engineering gates / current verified state

- [x] Prospective paper ledger and daily 22:12 KST trigger code in main.
- [x] Early-closed 5/10/20-session cohort carry-forward code in main; additional targeted tests added.
- [ ] GitHub-hosted workflow run success and a durable first paper_ledger.json actually confirmed.
- [ ] Independent price source concordance and regular-only certification.
- [ ] Automated current-date v5 TOP2 source, full-price large portrait charts, and **new plan registration** after original verification; research PR #28 still draft.
- [ ] Two strategies A/B registered at same decision time and evaluated without lookahead.
- [ ] Multi-month forward cohort with complete actual observation calendars and realistic liquidity/queue/slippage uncertainty.

This roadmap does not change existing alarms except adding data checks to the already configured report; no real orders, Telegram integration or brokerage access.
