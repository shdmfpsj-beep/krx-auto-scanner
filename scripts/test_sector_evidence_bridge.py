#!/usr/bin/env python3
"""Deterministic guardrails for the research-only bridge."""
import tempfile
import unittest
from pathlib import Path
import csv
from sector_evidence_bridge import stock_watchlist, rank_stock_research, stock_market_metrics, historical_pattern_review, build, REQUIRED

class BridgeTests(unittest.TestCase):
    def test_prior_verified_evidence_is_research_only(self):
        status={"asof":"2026-10-20","datasets":{k:{"status":"OK"} for k in REQUIRED}}
        _,summary=build(status,[],"2026-10-21")
        self.assertTrue(summary["core_data_verified"])
        self.assertFalse(summary["evidence_scan_dates_aligned"])
        self.assertTrue(summary["research_uses_prior_evidence_snapshot"])
        self.assertEqual(summary["data_date_gate"],"PRIOR_VERIFIED_RESEARCH_ONLY")
        self.assertEqual(summary["decision"],"CASH")
        self.assertEqual(summary["trade_approvals"],0)
        _,future=build(status,[],"2026-10-19")
        self.assertFalse(future["core_data_verified"])
        _,same=build(status,[],"2026-10-20")
        self.assertTrue(same["evidence_scan_dates_aligned"])

    def test_balanced_and_unique_watchlist(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"market/sector_membership_dated.csv"
            p.parent.mkdir(parents=True)
            with p.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["sector_id","snapshot_date","ticker","weight_pct","name"])
                w.writeheader()
                for s,k in [("A",100),("B",200),("C",300)]:
                    for i in range(8):
                        w.writerow(dict(sector_id=s,snapshot_date="2026-10-20",
                                        ticker=f"{k+i:06d}",weight_pct=10-i,name="Test"))
            rows,status=stock_watchlist(Path(d),["A","B","C"],"2026-10-20")
            self.assertEqual(len(rows),20)
            self.assertEqual([sum(r["sector_id"]==s for r in rows) for s in "ABC"],[7,7,6])
            self.assertEqual(len({r["ticker"] for r in rows}),20)
            self.assertTrue(all(r["trade_approval"]=="NO" for r in rows))
    def test_missing_prices_never_approve(self):
        with tempfile.TemporaryDirectory() as d:
            watch=[dict(ticker="000001",sector_id="A",name="Test")]
            rows=stock_market_metrics(Path(d),watch,"2026-10-20")
            self.assertEqual(rows[0]["price_flow_ready"],"NO")
            self.assertEqual(rows[0]["structure_stop_verified"],"NO")
            self.assertEqual(rows[0]["trade_approval"],"NO")
            self.assertEqual(rank_stock_research(rows),[])
    def test_pattern_review_requires_complete_forward_window(self):
        bars=[]
        for i in range(35):
            close=100+i
            bars.append((f"2026-09-{i+1:02d}",(close,100000,close-1,close+0.5)))
        result=historical_pattern_review(bars)
        self.assertEqual(set(result),{"BREAKOUT_20D","RISING_SMA20_PULLBACK",
                                      "RECLAIM_10D_HIGH"})
        self.assertEqual(result["BREAKOUT_20D"]["count"],1)
        self.assertGreater(result["BREAKOUT_20D"]["mean_forward_5d_pct"],0)
        shortened=historical_pattern_review(bars[:29])
        self.assertTrue(all(v["count"]==0 for v in shortened.values()))

    def test_daily_bar_risk_outcomes_partition_signals(self):
        bars=[(str(i),(100+i,100000,99+i,100.5+i)) for i in range(35)]
        stats=historical_pattern_review(bars)["BREAKOUT_20D"]
        total=sum(stats[k] for k in ("risk_first_count","target_first_count",
                    "ambiguous_same_bar_count","neither_count",
                    "risk_reference_invalid_count"))
        self.assertEqual(total,stats["count"])
        self.assertEqual(stats["risk_reference_invalid_count"],0)

    def test_missing_ohlc_blocks_pattern_review(self):
        bars=[(str(i),(100+i,100000,None,None)) for i in range(40)]
        result=historical_pattern_review(bars)
        self.assertTrue(all(v["count"]==0 for v in result.values()))

    def test_ranking_does_not_create_entry(self):
        rows=[]
        for i in range(3):
            rows.append(dict(ticker=f"{i+1:06d}",price_flow_ready="YES",
                             close=100+i,sma20=95,return_5d_pct=3+i,
                             avg_turnover_5d_krw=100000+i,
                             foreign_net_5d_krw=1000+i,
                             institution_net_5d_krw=2000+i,
                             extension_warning="FIVE_DAY_RALLY_GE_10PCT" if i==2 else "",
                             trade_approval="NO"))
        ranked=rank_stock_research(rows)
        self.assertEqual(len(ranked),3)
        self.assertEqual(ranked[-1]["ticker"],"000003")
        self.assertTrue(all(r["trade_approval"]=="NO" and
                            r["entry_price"]=="" and r["stop_price"]==""
                            for r in ranked))

if __name__=="__main__":
    unittest.main()
