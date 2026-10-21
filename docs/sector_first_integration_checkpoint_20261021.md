# Sector-first integration checkpoint — 2026-10-21

- Latest confirmed scanner artifact: workflow run 39523533070, market data 2026-10-20.
- Coverage: 2604 / 2625 tickers; 86 preliminary technical candidates; zero trade approvals.
- Existing sector mapping (`reports/v68_investment_sector_members.csv`) is dated 2026-10-08 and `theme_exposure_verified=false`. Do not interpret as verified sector membership or live sector flows.
- Sector-first TOP3 requires independent as-of sector membership, investor net buying, turnover/breadth, and fresh catalysts. Until these are available, no sector or trade should be approved.
- Structural stops and two-stage entries require individual OHLCV histories, not merely the candidates.csv snapshot.
- Preserve all historical research outputs; never overwrite prior backtest results.
