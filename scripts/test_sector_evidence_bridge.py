#!/usr/bin/env python3
"""Deterministic guardrails for the research-only bridge."""
import tempfile
import unittest
from pathlib import Path
import csv
from sector_evidence_bridge import stock_watchlist, rank_stock_research, stock_market_metrics, historical_pattern_review, historical_pullback_quality_review, plan_research_entry, build, apply_daily_money_rank, REQUIRED

class BridgeTests(unittest.TestCase):
    def test_money_first_one_day_can_include_negative_5d_power(self):
        summary=dict(asof="2026-10-21",core_data_verified=True,
            evidence_scan_dates_aligned=True,research_top3_sector_ids=["IT"],
            decision="CASH",trade_approvals=0)
        original=[dict(sector_id=s,research_eligible="NO",
            research_priority_index=11,warnings="NO_POSITIVE_NET_FLOW_PROXY",
            trade_approval="NO",foreign_net_buy_5d_krw=-5,
            institution_net_buy_5d_krw=-4) for s in ("SEMICON","POWER","CONSTRUCTION","IT")]
        chosen=[]
        for i,s in enumerate(("SEMICON","POWER","CONSTRUCTION"),1):
            chosen.append(dict(rank=i,sector_id=s,flow_coverage=1,
                day_breadth_pct=88,incremental_day_net_flow_krw=1000-i,
                raw_day_net_flow_krw=1500-i,day_turnover_krw=1000000,
                trade_approval="NO"))
        market=dict(schema="sector_daily_money_v1",asof="2026-10-21",
             decision="CASH",trade_approved=False,selected_top3=chosen)
        ranked,res=apply_daily_money_rank(original,summary,market)
        self.assertEqual(res["research_top3_sector_ids"],
             ["SEMICON","POWER","CONSTRUCTION"])
        self.assertTrue(res["daily_money_rank_applied"])
        self.assertFalse(res["final_sector_top3_verified"])
        self.assertEqual(res["decision"],"CASH")
        self.assertEqual(next(x for x in ranked if x["sector_id"]=="POWER")["research_eligible"],"YES")
        self.assertEqual(next(x for x in ranked if x["sector_id"]=="POWER")["research_priority_index"],"")
    def test_stale_daily_money_does_not_invent_rank(self):
        summary=dict(asof="2026-10-21",core_data_verified=True,
            evidence_scan_dates_aligned=True,research_top3_sector_ids=["IT"])
        original=[dict(sector_id="IT",research_eligible="YES")]
        ranked,status=apply_daily_money_rank(original,summary,
            {"schema":"sector_daily_money_v1","asof":"2026-10-20",
             "selected_top3":[],"decision":"CASH","trade_approved":False})
        self.assertEqual(status["research_top3_sector_ids"],[])
        self.assertFalse(status["daily_money_rank_applied"])

    def test_actual_oct_22_pre_expansion_top3_is_promoted_for_research_only(self):
        summary=dict(asof="2026-10-22",core_data_verified=True,
            evidence_scan_dates_aligned=True,research_top3_sector_ids=[])
        specs=[("CONSTRUCTION",43.75,210491705060),
               ("POWER",16.67,31592252630),("DEFENSE",0,28478390000)]
        original=[dict(sector_id=s,sector_name=s,asof="2026-10-22",
                       research_eligible="NO",trade_approval="NO",
                       warnings="PRICE_FLOW_PROXY_UNREADY")
                  for s,_,_ in specs]
        chosen=[dict(rank=i,sector_id=s,flow_coverage=1.0,
                     day_breadth_pct=b,incremental_day_net_flow_krw=n,
                     raw_day_net_flow_krw=n,day_turnover_krw=1000000000,
                     trade_approval="NO") for i,(s,b,n) in enumerate(specs,1)]
        money=dict(schema="sector_daily_money_v1",asof="2026-10-22",
                   selected_top3=chosen,complete_three=True,
                   decision="CASH",trade_approved=False)
        ranked,result=apply_daily_money_rank(original,summary,money)
        self.assertEqual(result["daily_money_gate"],
                         "VERIFIED_1D_EARLY_FLOW_RESEARCH_ONLY")
        self.assertEqual(result["research_top3_sector_ids"],
                         ["CONSTRUCTION","POWER","DEFENSE"])
        self.assertTrue(result["daily_money_rank_applied"])
        self.assertEqual(result["pre_expansion_sector_count"],3)
        self.assertFalse(result["final_sector_top3_verified"])
        self.assertFalse(any(x["trade_approval"]!="NO" for x in ranked))
        self.assertEqual(next(x for x in ranked if x["sector_id"]=="DEFENSE")
                         ["flow_phase"],"DIVERGENT_ALL_DOWN")

    def test_truly_no_positive_flow_does_not_invent_research_top3(self):
        summary=dict(asof="2026-10-22",core_data_verified=True,
            evidence_scan_dates_aligned=True,research_top3_sector_ids=[])
        original=[dict(sector_id="CONSTRUCTION",research_eligible="NO",
                       trade_approval="NO")]
        money=dict(schema="sector_daily_money_v1",asof="2026-10-22",
                   selected_top3=[],complete_three=False,
                   sector_samples=[dict(sector_id="CONSTRUCTION",
                       base_eligible=True,day_net_flow_krw=-1000000000)],
                   decision="CASH",trade_approved=False)
        _,result=apply_daily_money_rank(original,summary,money)
        self.assertEqual(result["daily_money_gate"],"VERIFIED_NO_QUALIFYING_SECTOR")
        self.assertEqual(result["research_top3_sector_ids"],[])
        self.assertTrue(result["daily_money_rank_applied"])
        self.assertFalse(result["final_sector_top3_verified"])

    def test_corrupt_same_day_ohlc_rejects_flow_rank_as_data_invalid(self):
        summary=dict(asof="2026-10-22",core_data_verified=True,
                     evidence_scan_dates_aligned=True,
                     research_top3_sector_ids=["CONSTRUCTION"])
        rows=[dict(sector_id="CONSTRUCTION",research_eligible="YES",
                   trade_approval="NO")]
        report=dict(schema="sector_daily_money_v1",asof="2026-10-22",
                   market_ohlc_quality_verified=False,
                   raw_ohlc_conflict_pct=24.7,
                   selected_top3=[],complete_three=False,
                   sector_samples=[dict(sector_id="CONSTRUCTION",
                       base_eligible=False,day_net_flow_krw=210000000000)],
                   decision="CASH",trade_approved=False)
        ranked,result=apply_daily_money_rank(rows,summary,report)
        self.assertEqual(result["daily_money_gate"],"MARKET_OHLC_CONFLICT")
        self.assertEqual(result["research_top3_sector_ids"],[])
        self.assertFalse(result["daily_money_rank_applied"])
        self.assertFalse(result["final_sector_top3_verified"])
        self.assertEqual(result["decision"],"CASH")
        self.assertEqual(ranked[0]["sector_id"],"CONSTRUCTION")

    def test_pullback_quality_requires_complete_forward_window(self):
        bars=[(str(i),(100+i,100000,99+i,100.5+i)) for i in range(70)]
        result=historical_pullback_quality_review(bars)
        self.assertEqual(set(result),{"FIRST_TOUCH","REPEATED_TOUCH"})
        self.assertEqual(sum(v["count"] for v in result.values()),0)
        self.assertTrue(all(v["mean_mae_5d_pct"]=="" for v in result.values()))

    def test_entry_plan_requires_completed_structure(self):
        bars=[(str(i),(100+i,100000,99+i,100.5+i)) for i in range(65)]
        result=plan_research_entry(bars,"64")
        self.assertEqual(result["plan_trade_approval"],"NO")
        self.assertEqual(result["plan_status"],"NO_VALID_STRUCTURE")
        self.assertEqual(result["plan_first_weight_pct"]+result["plan_second_weight_pct"],100)
        missing=plan_research_entry(bars[:-1],"64")
        self.assertEqual(missing["plan_status"],"INSUFFICIENT_ASOF_OHLC")

    def test_entry_plan_does_not_invent_nearby_stop(self):
        # A completed pivot from >20 bars ago is not a fresh support,
        # even when it would produce an attractive artificial stop.
        closes=[100.0]*65
        closes[10]=80.0
        for i in range(11,65):
            closes[i]=100.0+(i-11)*0.2
        bars=[(str(i),(v,100000,v-1,v+1)) for i,v in enumerate(closes)]
        result=plan_research_entry(bars,"64")
        self.assertEqual(result["plan_trade_approval"],"NO")
        self.assertNotEqual(result["plan_status"],"STRUCTURE_CANDIDATE_REQUIRES_VALIDATION")

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

    def test_sector_rank_prioritizes_real_flow_and_turnover_over_rs(self):
        status={"asof":"2026-10-22","datasets":{k:{"status":"OK"} for k in REQUIRED}}
        specs=[
            ("A",12,75,100,100,10_000_000_000),  # strongest RS, weakest money
            ("B",4,65,900,900,90_000_000_000),   # stronger money and turnover
            ("C",3,60,800,800,80_000_000_000),
        ]
        rows=[]
        for sid,rs,breadth,foreign,inst,turnover in specs:
            rows.append(dict(date="2026-10-22",sector_id=sid,sector_name=sid,
                price_flow_proxy_ready="true",live_selection_authorized="false",
                stock_members="15",rs_5d_pp=str(rs),
                breadth_up_5d_pct=str(breadth),
                foreign_net_buy_5d_krw=str(foreign),
                institution_net_buy_5d_krw=str(inst),
                member_turnover_krw=str(turnover),
                breadth_coverage="1",turnover_coverage="1",
                foreign_5d_coverage="1",institution_5d_coverage="1"))
        result,summary=build(status,rows,"2026-10-22")
        self.assertEqual(summary["research_top3_sector_ids"][0],"B")
        self.assertEqual(result[0]["sector_id"],"B")
        self.assertGreater(result[0]["research_priority_index"],
                           result[-1]["research_priority_index"])
        self.assertEqual(summary["decision"],"CASH")
        self.assertFalse(summary["research_sector_priority_is_final_score"])
        self.assertTrue(all(r["trade_approval"]=="NO" and r["final_sector_score"]==""
                            for r in result))

    def test_missing_member_turnover_never_fakes_flow_first_sector(self):
        status={"asof":"2026-10-22","datasets":{k:{"status":"OK"} for k in REQUIRED}}
        row=dict(date="2026-10-22",sector_id="A",sector_name="A",
             price_flow_proxy_ready="true",live_selection_authorized="false",
             stock_members="10",rs_5d_pp="4",breadth_up_5d_pct="70",
             foreign_net_buy_5d_krw="1000",institution_net_buy_5d_krw="1000",
             breadth_coverage="1",turnover_coverage="1",
             foreign_5d_coverage="1",institution_5d_coverage="1")
        results,summary=build(status,[row],"2026-10-22")
        self.assertEqual(summary["research_top3_sector_ids"],[])
        self.assertEqual(results[0]["research_eligible"],"NO")
        self.assertIn("TURNOVER_OR_MEMBERS_UNVERIFIED",results[0]["warnings"])

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
            expanded,_=stock_watchlist(Path(d),["A","B","C"],"2026-10-20",40)
            self.assertEqual(len(expanded),24)
            self.assertEqual(len({r["ticker"] for r in expanded}),24)
            self.assertEqual([sum(r["sector_id"]==sector for r in expanded)
                              for sector in "ABC"],[8,8,8])
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
