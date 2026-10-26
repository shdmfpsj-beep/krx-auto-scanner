# C3 v6.48 — D-day entry price reach vs missed opportunities (research only)

Date 2026-10-26. No official certified regular-only KRX tape or broker fills; all 267 signals are historical through Oct23. 0 independent forward trades, orders disabled. User manages position size/capital; all new price/stop/target geometry is account independent.

**Source**: Original Work v6.38 successful GitHub Action run 40250900699 artifact 12621175343; 267 as-of D pattern signals (125 TREND_FIRST_PULLBACK, 142 NEAR60), 195 ticker price files from v18 source SHA256 7eef1174032105d1790c41144e580d44380bdb9a4500b12afc69865fe6d6fd30. NO new Oct26 complete-session data. Existing D-known structure stop/recorded resistance unchanged. Old A/B frozen.

**Tested 5 D-only advance priced methods**: next-day OPEN proxy; precommitted Dclose-.25*D ATR14 resting D+1 only; same limit resting D+1..D+2 (cancel if stop or already preknown target breached before D+2); already-known MA10 support; highest already-known D support giving RR>=2 using documented resistance. Five methods x [5,12]-session exit = **2670 research state rows**. Buy .15% / sell .50%, stress buy .30% / sell .65%. Sell stops checked first; same-day limit+stop or limit+target price contacts are UNKNOWN PATH rather than winning fills. Broker fill NOT implied by daily low.

**5-session results** (D-valid / contact / intrabar unknown / completed / conditional median):
| method | D-level | price touch/open | unknown | complete | median net proxy |
|---|---:|---:|---:|---:|---:|
| D+1 OPEN | 267 | 265 | 0 | 264 | +0.4076% |
| shallow D+1 limit | 267 | 177 | 20 | 176 | +0.5447% |
| shallow 2-day limit | 267 | 185 | 21 | 184 | +0.7894% |
| MA10 D-known limit | 211 | 49 | 11 | 48 | -2.8629% |
| pre-recorded RR2 support | 38 | 3 | 0 | 3 | +9.8859% |

**Crucial same-D matched opportunity result**, including no-fill as CASH=0, dropping ambiguous/censored pairs rather than awarding them profits. Shallow 1-day relative to open 5-session **-0.4808 pp**, 12-session **-0.7017 pp**. Shallow 2-day **-0.3990 pp**, **-0.2934 pp**. MA10 **-1.2502 pp**, **-1.8831 pp**. Deep RR2 support **-0.5194 pp**, **-1.1862 pp**. These are independent candidate-opportunity averages, NOT one-slot portfolio returns, and candidates overlap across dates/tickers/models. The RR2 strategy has merely 3 assumed contacts and cannot be promoted.

**Time-regime diagnostic only**: H1 Jan–Jun 5-session open mean +1.0249% on 224 exit-complete hypothetical signals vs Jul–Oct23 -1.6898% on 40. H1 shallow1 +1.1416% (142) vs later -0.6701% (34); shallow2 +1.2090% (150) vs later -0.6701% (34). This is NOT evidence to retroactively avoid 7–10月 or a valid seasonal filter. Prospective D-known market/industry liquidity and leadership needed.

**Same-bar ambiguity stress**: pessimistically assume stop after a touched buy in all ambiguous cases: shallow1 5-session opportunity mean -0.0796% (264 evaluable, 20 ambiguous-as-loss), shallow2 -0.0455% (264, 21), open +0.6135% (264). Subjective pessimistic sensitivity, NOT an estimated worst-case guarantee or verified fill.

**Files and checks**: Current conversation download C3_v648_진입타점_실제기회_수익검증.zip SHA256 5512d467d98d9fe4b4f50f031e5cc4d15bcdbb5776beb04b3e83815d38b31667, report c3_v648/C3_v648_진입타점_체결가능성_수익검증_보고서.md; contains full scripts, tests, source archives, 2670 scenario ledger, fee+H1/H2, paired, conservative ambiguity sensitivity and prospective challenger freeze JSON. **31 tests passed locally** and separate clean extraction rerun matched output CSVs byte-for-byte. No new GitHub CI or backtest orders performed. GitHub documentation only, full executable release is in user ZIP.

**Decision:** Deprioritize deeper limit/mandatory second purchases. Leave historical Work v6.38 A/B frozen, propose shallow 0.25ATR next-day (1d/2d) as NEW RESEARCH CHALLENGERS only, no claim of optimality from already-mined 2026 history. Improvement focus is D-known selection of stocks with genuinely continuing sector/issuer momentum and pre-known original structure stop & resistance, not lowering bid to fabricate 2R. Need verified KRX 09:00–15:30 OHLC, issuer historical PIT and corporate action and objective sector flows, original dated overhead, broker order timing and actual fill before any BUY recommendation. CASH; K100 unchanged; PR stays DRAFT.