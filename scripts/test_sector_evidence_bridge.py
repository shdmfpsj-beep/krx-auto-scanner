#!/usr/bin/env python3
"""Deterministic guardrails for the research-only bridge."""
import tempfile
import unittest
from pathlib import Path
import csv
from sector_evidence_bridge import stock_watchlist, rank_stock_research, stock_market_metrics

class BridgeTests(unittest.TestCase):
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
