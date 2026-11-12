# C3 Market Entry Range V2 — independent research

One continuous price range is one research observation. There is **no mandated number of purchases, no fixed 50:50 split and no automated trading**. Order timing, quantity and frequency remain entirely the user's decision. The AI reports a risk/price interval, not a compulsory trade-count rule. This is a V2 policy amendment; V1 results stay archived and unchanged.

The frozen integration driver reproduces the original Nov 11 market first (2769 / 1988 / 149 / 50 / 4 / 0). Global context observed on Nov 12 and later-collected DART API snapshots are labelled as current review context, not historical selection inputs. Confirmed financial quality still requires original PIT evidence. Unknown values do not become positive signals.

Stock WATCH ranking uses logical financial observations, positive/improving own-board RS and liquidity, with a current-membership sector price proxy. It is frozen before the entry calculation. A missing entry leaves WATCH intact and does not create a forced TOP2 trade. There are no arbitrary weighted scores or optimized indicators.

Range generation reuses ATR14, confirmed pivots, MA support/reclaim and all-post-breakout retest lows. Structural stops are frozen before intersection with research risk limits. Already broken high pivots are excluded before resistance clustering by an optional extension to the reused primitive; existing callers keep their default behavior. The engine audits every legal tick and reports lower/middle/upper risk, costs, distance and reward separately. The inherited 8%/8%/1.5 and one-ATR limits are research assumptions, not validated live rules.

Cards require 119 real contiguous daily bars for 60 visible candles and full MA60. Exact source date, source collection time, render time, source run ID and hashes are preserved. One shaded area represents one range, never two buy orders. Invalid deep supports remain diagnostics and are not presented as an approved stop/target plan.

Historical comparisons use separately evaluated upper/middle/lower **reference-price scenarios** with identical cash, fees, expiry, stop-first and gap rules. These isolated simulations do not prescribe the user's actual number of orders. No range is CASH and remains in opportunity denominators. This history has already been used in earlier research and is not independent validation. Daily-bar fills are models, not proven executions.

For optional user-supplied hypothetical fills, `evaluate_user_fills(plan, fills, planned_capital_krw)` checks each actual price against the same validated range and reports total cost, weighted average, unused cash, and **combined loss at the structural stop relative to the full planned capital**. It accepts any positive number of fill rows. It neither proposes a split nor places an order; no user trade history is inferred.

`c3_range_forward_v1.py` supports exclusive immutable observations, conflict rejection, 5/10/20-session price and benchmark outcomes, dated append-only updates and an update CLI. Archived replays cannot create new forward observations. A daily caller must supply persisted research observations and newly validated price/index inputs. The new research model is not wired into the production morning schedule in this Draft PR.

The workflow has read-only repository/Actions permissions and no Telegram secrets. It probes the most recently completed KRX session once per board and holds if the new same-run registered original is unavailable. The frozen fallback is explicitly Nov11, never substituted for a current recommendation. The real Telegram multipart parser is exercised behind fake HTTP for zero/one/two candidates, including a dedicated hold card for zero. Research identifiers are separate from operational receipt keys. No live channel send is implemented or enabled.

Main, the approved A/B engine, original signals/stops, receipts, 120-day collection and 08:10/20/30 plus ChatGPT 08:45 schedules are unchanged. Read-only before/after checks compare all 87 protected original/receipt blobs.
