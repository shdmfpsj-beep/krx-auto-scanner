# C3 screening evidence

The daily scan writes `c3_candidate_evidence_v1.csv`, its JSON status and a
제갈AI Pro text report after the original ranking and timestamp registration.
All original candidates, prices, ranks and clocks remain available.

`basic_20261023` preserves the already reviewed official KRX base-info snapshot
and its source hashes. The parser explicitly labels it as prior dated evidence
when the scan date is later. A common-share label does not override SPAC, REIT,
preferred-share or foreign-share exclusion. This snapshot is not an industry
taxonomy or independently verified historical vintage.

`business_scope_review_v1.json` is a targeted primary-source analyst review.
Each code keeps its identity, review clock, URL and business reason. No reviewed
business fact enters older historical backtests. Unreviewed companies need
review; a biotech-looking name cannot prove a pharmaceutical business.

Actual source turnover can be read from a separately supplied
`reports/c3_official_eod` v6.5 manifest with both hashed market files. It must
match the scan date. Close times volume remains a separate estimate. The v6.5
dataset has no verified regular-only session scope; authentication or equal
prices cannot create that proof. Current official base-info may be supplied
with the script's `--basic-dir` option after its own integrity review.

This evidence ledger does not approve a trade or calculate an entry, final
score80, profit probability, account quantity or new stop. Company, sector,
flow and genuine first-R1 net2R entry research still determine the next work.
