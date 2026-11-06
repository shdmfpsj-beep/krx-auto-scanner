# C3 report quality checkpoint — 2026-11-06

## Confirmed root causes
- Live code main c1560806ec92a9664252f3c13ca7568817b4f481, same as actual Telegram run 42195022969 after receipt-store hardening.
- Bent black/green tails are price-label collision-avoidance leader polylines, not extra OHLCV or moving-average points. Original Samsung actual close declined 65,500 to 64,300; Wonik 30,100 to 26,950. Keep both declines.
- Both stocks have 91 true KRX bars through 2026-11-05. All 5/20/60 moving-average points match independent pandas rolling exactly, maximum difference 0 KRW. Last-five OHLCV and MA audit is preserved in independent_price_audit.json.
- Original notes() returned fixed missing-financial/news text; no OpenDART call or financial context was wired into the sender. Existing financial workflow uses OPENDART_API_KEY; the older feasibility script's OPEN_DART_API_KEY name is a different legacy path.

## Implemented checkpoint
- Flat current-price badge; no bent level-label leaders. MA paths end at actual last candle, guarded by Decimal independent calculation and geometry diagnostics.
- Post-selection-only dated company context, existing free OpenDART corporation-code reader, bounded CFS quarter/CF/debt/receipt collection, safe error metadata.
- Reviewed Samsung official 2025Q4/2026Q1/Q2/Q3 preliminary releases and Wonik official business description. Date-only same-day and later disclosures excluded. No score/rank/entry-plan changes.
- Local 56 targeted tests passed. Local preview generated; actual OpenDART from GitHub Actions and visual approval are pending at this checkpoint. No additional Telegram send.

## Continue
1. Observe PR self-test preview artifact; verify OPENDART_API_KEY connection and actual two-stock quarterly data.
2. Review regenerated PNGs and zoomed endpoints; fix any layout/data issue.
3. Preserve final artifact hashes, context/source evidence and PASS/FAIL results.
4. Merge report-only PR after green CI; preserve code/evidence in research PR #30.
5. Do not alter config/c3_telegram_example_request.json or existing receipts. 11/5 album already delivered once; do not bypass duplicate protection. Regular schedules and ChatGPT alert unchanged.

## First actual Actions result and resolved obstacle
- PR #37 checkpoint b5965230140d30143e325bb0b96060aef66410c1; run 42203277626; 56 tests passed; artifact 13495362288, SHA256 65709439eb03b9f04064b9434e07979ddcd43ec3fc315b70bc288d7efef2a053.
- Preview/duplicate guard passed, but company financial collection DID NOT complete. The public corporation ZIP (3,635,260 bytes, SHA256 a15d06c93c5d5ffa879ad1d8650e31f5b90063f68c5f4604c25957f285ab4b83) arrived after about 232 seconds and exhausted the original 180-second global budget. Both company requests stopped before financial API calls. Do not misreport that first green workflow as successful financial collection.
- Fix: cache the public listed corporation mapping, start the bounded financial phase after cold mapping acquisition, verify stock-code/corporation identity via company.json, request periodic filings separately from the recent-28-day list so high filing volume cannot hide older quarters.
- Added real PNG pixel-boundary/layout regression (no MA pixel beyond last candle); local 57 tests passed. New Actions verification is pending.

## Actual financial connection succeeded
- Fixed-code run 42204266098 at 1c3bb1945ac348d234c6d7ecd40c152af0b29303 succeeded: 17 OpenDART requests, both stocks COLLECTED, four completed quarters per stock, no context errors. Artifact 13496086878 SHA256 a43bc44715f2c52fa493d85c4efcd05c21d689b937121ec21679be525ee23c04.
- Verified corporation identities: Samsung E&A 00126308 / 028050, Wonik Holdings 00216647 / 030530. Reviewed seeds plus company.json identity confirmation avoid downloading the 3.6 MB corporation archive for these two on every report. Other tickers use a cached official mapping.
- Samsung latest 2026Q3: company preliminary CFS release on Oct22, revenue 29,105억원, operating profit 5,006억원, YoY +45.8%/+183.6%. Four-quarter comparison and H1 cash flow/debt are stored.
- Wonik latest 2026Q2: CFS revenue 176,453,030,786 KRW, operating profit 12,778,540,649 KRW; revenue +11.99% and loss-to-profit YoY (no misleading percentage from negative base). 2025Q3/Q4 and 2026Q1 were operating losses. H1 CF 41,505,670,225 KRW; debt/equity 53.5164%.
- New trusted PR gate verifies actual financial collection and invariant selection hashes rather than accepting PNG creation alone. Final 59-test CI, visual review, deployment and research evidence preservation are the remaining steps.

## Deployed final result
- PR #37 merged to main: c98114a1bdc115c850b2ee2d2565e70a3bd785fc. Tested code 6fa882a161b180fb2531f9775bc9e14bc85432e2.
- Final run 42205886016: 59 targeted tests passed; actual OpenDART 16 requests, both companies COLLECTED, four quarters each, no error, corporation ZIP downloads 0. Source dates/periods and 50 original selected public account rows are preserved.
- Artifact 13496622518 SHA256 7e1bb1d91b4eff3e9207f212b7c091d485d7c94d35fe31ab009fd77036d6945d. Both CI-generated PNGs and magnified endpoints directly inspected: PASS. Local and CI image bytes/pixels differ, so the CI artifact was independently inspected; do not assume local PNG hash equals CI.
- Final PNG SHA256: Samsung 34d96fab0f5298939a6e1dbeb377803cc43fb53d0f8bf131ac452fa06ff3a37a; Wonik a661658af9bf679f3072a75858fd0fcef05f73b552f7776d3fa9f4807de45488.
- Real existing Git receipts returned DUPLICATE_BLOCKED with send_attempts 0. This update performed no Telegram send. Do not alter the existing 11/5 request or receipt to send the same report again.
- Only report rendering/context/targeted tests/workflow and their evidence changed. Receipt-store policy classes/functions and action/order/stale-data guards match the previous AST. Existing C3 strategies, frozen ledgers, scanners and ChatGPT alert are untouched.
- Existing Telegram cron 22:45/09:00 KST retained. A future post-deployment schedule event has not yet been observed; main merge is not evidence of a scheduled send.
- Remaining: external investor flows/whole-sector strength unavailable; independent regular-only price scope incomplete. Company info is dated post-selection research, not retroactive scoring evidence. No new Nov6 TOP2 or simulated profit was generated for this report task.

## Exact next operation
Do not repeat historical collection or resend the example. Inspect next actual live Telegram run and its receipt for newly registered, quality-approved TOP2 only. Continue interpreting company_context missing/error metadata separately from delivery_status. Keep all original source/decision/receipt hashes; do not backfill historical trades.
