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
