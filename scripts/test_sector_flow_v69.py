"""Offline v6.9: real-sourced five-day flow sums, ETF proxy limitations."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from test_liquidity_watch_v68 import scan_fixture,synthetic_turnover,write
from liquidity_watch_v68 import run as liquidity_run,write_outputs as save_liquidity
from sector_flow_v69 import evaluate,write_outputs,SCHEMA,REQUIRED_FLOW_COLUMNS
from forward_ledger_v63 import digest

ASOF="2026-10-23"
DAYS=["2026-10-19","2026-10-20","2026-10-21","2026-10-22","2026-10-23"]
SECTORS=[
    ("CONSTRUCTION","건설","010000",2,30,200000000,100000000,"True"),
    ("INSURANCE","보험","010001",1,35,50000000,50000000,"True"),
    ("AUTO","자동차","020000",-2,45,60000000,40000000,"True"),
    ("BANK","은행","010002",-3,10,-10000000,0,"True"),
    ("HEALTH","헬스케어","020001",12,55,200000000,300000000,"False")
]
def setup(work):
    scan=scan_fixture(work)
    for t,day,prior in (("010000",15_000_000_000,4_000_000_000),
                        ("010001",4_000_000_000,2_000_000_000),
                        ("020000",6_000_000_000,2_000_000_000)):
        synthetic_turnover(scan,t,day,prior)
    report,liqs,c,k=liquidity_run(scan)
    save_liquidity(scan,report,liqs,c,k)
    v18=Path(work)/"sector_v18"
    (v18/"diagnostics").mkdir(parents=True,exist_ok=True)
    (v18/"diagnostics/collection_status.json").write_text(
        json.dumps(dict(asof=ASOF,orders_enabled=False,
            datasets=dict(flows=dict(status="OK"),holdings=dict(status="OK")))))
    membership=[]
    sectors=[]
    for sid,name,t,rs,breadth,foreign,institution,ready in SECTORS:
        market="KOSPI" if t.startswith("01") else "KOSDAQ"
        membership.append(dict(sector_id=sid,etf="000000",
            snapshot_date="2026-10-19",ticker=t,weight_pct=1.0,
            name=name,collected_at="2026-10-23T12:10:00+00:00",
            source="KRX_ETF_PDF_dated_request",
            point_in_time_status="PROVIDER_DATED_NOT_INDEPENDENT_VINTAGE_VERIFIED"))
        sectors.append(dict(date=ASOF,sector_id=sid,sector_name=name,etf="000000",
            snapshot_date="2026-10-19",stock_members=1,
            membership_status="PROVIDER_DATED_PROXY_NOT_STRICT_PIT",
            money_scope="ETF_stock_constituents_unweighted_net_buy_not_entire_industry",
            foreign_net_buy_5d_krw=foreign*5,
            institution_net_buy_5d_krw=institution*5,rs_5d_pp=rs,
            breadth_up_5d_pct=breadth,
            member_turnover_krw=20000000000,
            foreign_5d_coverage=1,institution_5d_coverage=1,
            price_flow_proxy_ready=ready,
            full_sector_score="",live_selection_authorized=False,
            availability_assumption="2026-10-23T18:10:00+09:00_not_historical_vintage_verified"))
    write(v18/"market/sector_membership_dated.csv",list(membership[0]),membership)
    write(v18/"research/sector_evidence_latest.csv",list(sectors[0]),sectors)
    for d in DAYS:
        for inv, label in (("foreign","외국인"),("institution","기관합계")):
            for market in ("KOSPI","KOSDAQ"):
                flows=[]
                for sid,name,t,rs,breadth,fr,ins,ready in SECTORS:
                    if ("KOSPI" if t.startswith("01") else "KOSDAQ")!=market:
                        continue
                    net=fr if inv=="foreign" else ins
                    sell=max(0,-net)+100000000
                    buy=sell+net
                    flows.append(dict(date=d,market=market,ticker=t,name=name,
                        investor=label,buy_krw=buy,sell_krw=sell,
                        net_buy_krw=net,unit="KRW",source="KRX_via_PyKrx",
                        collected_at="2026-10-23T12:22:56+00:00",
                        availability_assumption="final_after_18KST_not_intraday_PIT_verified"))
                write(v18/"market/daily_flows"/market/(d+"_"+inv+".csv"),
                      REQUIRED_FLOW_COLUMNS,flows)
    return v18,scan

class SectorMoneyTests(unittest.TestCase):
    def test_dated_5day_flow_replay_and_only_two_strong_not_fake_top3(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            r,sectors,stocks,top3,qualified=evaluate(v18,scan)
            self.assertEqual(r["schema"],SCHEMA)
            self.assertEqual(r["total_proxy_sectors"],5)
            self.assertEqual(r["strict_strong_proxy_sector_count"],2)
            self.assertFalse(r["third_strong_sector_confirmed"])
            self.assertEqual(set(r["strict_strong_sectors"]),{"CONSTRUCTION","INSURANCE"})
            self.assertEqual(top3[-1]["strength_status"],"FLOW_POSITIVE_WEAK_TREND_WATCH")
            self.assertEqual(len(top3),3)
            # 010001 is a valid insurance-sector 5d inflow but has only
            # KRW 4bn traded today, below C3's KRW 5bn gate.
            self.assertEqual(set(r["selected_strong_sector_and_liquid_tickers"]),{"010000"})
            self.assertEqual(r["validated_flow_dates"],DAYS)
            self.assertEqual(r["decision"],"CASH")
            self.assertFalse(r["full_80_score_not_certified"] is False)
            self.assertTrue(all(x["trade_approved"] is False for x in stocks))
            self.assertTrue(all(x["sector_proxy_pit_vintage_verified"] is False for x in sectors))
            result=Path(tmp)/"result"
            write_outputs(result,r,sectors,stocks,top3,qualified)
            text=(result/"sector_money_v69_mobile.md").read_text(encoding="utf-8")
            self.assertIn("세 번째",text)
            self.assertIn("외국인",text)
            self.assertIn("CASH",text)

    def test_direct_member_sum_exact_against_sector_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            _,groups,stocks,_,_=evaluate(v18,scan)
            construction=next(x for x in groups if x["sector_id"]=="CONSTRUCTION")
            self.assertEqual(construction["foreign_5d_krw"],1_000_000_000)
            self.assertEqual(construction["institution_5d_krw"],500_000_000)
            self.assertTrue(construction["source_report_totals_reconciled"])
            stock=next(x for x in stocks if x["ticker"]=="010000")
            self.assertEqual(stock["foreign_plus_institution_5d_krw"],1_500_000_000)
            self.assertTrue(stock["both_investor_types_net_buy_positive_5d"])
            self.assertFalse(stock["regular_1530_verified"])

    def test_tampered_flow_net_value_rejected_by_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=v18/"market/daily_flows/KOSPI/2026-10-23_foreign.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]["net_buy_krw"]="123456789"
            write(p,fields,rows)
            with self.assertRaisesRegex(ValueError,"FLOW_NET_BUY_ACCOUNTING_NOT_RECONCILED"):
                evaluate(v18,scan)

    def test_flow_edit_that_keeps_buy_sell_consistent_still_rejected_by_5day_sector_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=v18/"market/daily_flows/KOSPI/2026-10-23_foreign.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]["buy_krw"]=str(int(rows[0]["buy_krw"])+999)
            rows[0]["net_buy_krw"]=str(int(rows[0]["net_buy_krw"])+999)
            write(p,fields,rows)
            with self.assertRaisesRegex(ValueError,"SECTOR_5DAY_REPORTED_TOTAL_DIFFERS"):
                evaluate(v18,scan)

    def test_partial_sector_member_does_not_become_zero_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=v18/"market/daily_flows/KOSPI/2026-10-22_institution.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows=[r for r in rows if r["ticker"]!="010000"]
            write(p,fields,rows)
            report,sectors,stocks,*_=evaluate(v18,scan)
            construction=next(x for x in sectors if x["sector_id"]=="CONSTRUCTION")
            self.assertFalse(construction["all_member_flows_5d_complete"])
            self.assertEqual(construction["strength_status"],"EVIDENCE_INCOMPLETE")
            self.assertIsNone(construction["combined_5d_krw"])
            self.assertEqual(report["strict_strong_proxy_sector_count"],1)
            candidate=next(x for x in stocks if x["ticker"]=="010000")
            self.assertIsNone(candidate["foreign_plus_institution_5d_krw"])
            self.assertFalse(candidate["foreign_institution_buy_signal_research_only"])

    def test_missing_one_market_flow_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            (v18/"market/daily_flows/KOSDAQ/2026-10-23_foreign.csv").unlink()
            with self.assertRaisesRegex(ValueError,"MISSING_ONE_MARKET_INVESTOR"):
                evaluate(v18,scan)

    def test_pharma_proxy_excluded_even_strong_positive_momentum(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            report,sectors,*_=evaluate(v18,scan)
            pharm=next(x for x in sectors if x["sector_id"]=="HEALTH")
            self.assertEqual(pharm["strength_status"],"SECTOR_EXCLUDED")
            self.assertNotIn("HEALTH",report["strict_strong_sectors"])

    def test_member_future_vintage_cannot_upgrade_strong_sector(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=v18/"research/sector_evidence_latest.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]["snapshot_date"]="2026-10-26"
            write(p,fields,rows)
            report,sectors,*_=evaluate(v18,scan)
            val=next(x for x in sectors if x["sector_id"]=="CONSTRUCTION")
            self.assertFalse(val["all_member_flows_5d_complete"])
            self.assertEqual(val["strength_status"],"EVIDENCE_INCOMPLETE")

    def test_stale_v68_liquidity_report_cannot_permit_market_flow_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=scan/"liquid_watch_v681_all.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]["c3_liquid_eligible"]="True" if rows[0]["c3_liquid_eligible"]=="False" else "False"
            write(p,fields,rows)
            with self.assertRaisesRegex(ValueError,"V681_LIQUIDITY_RESULT_TAMPERED"):
                evaluate(v18,scan)

    def test_sector_evidence_wrong_day_or_live_authorization_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            v18,scan=setup(tmp)
            p=v18/"research/sector_evidence_latest.csv"
            with p.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]["live_selection_authorized"]="True"
            write(p,fields,rows)
            with self.assertRaisesRegex(ValueError,"SECTOR_EVIDENCE_DATE_OR_LIVE_APPROVAL"):
                evaluate(v18,scan)

if __name__=="__main__":unittest.main()
