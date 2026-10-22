#!/usr/bin/env python3
"""Synthetic dated-KRX quality tests; full October 21 archive in Actions job."""
import csv,io,json,tempfile,unittest,zipfile
from pathlib import Path
from sector_daily_money import Evidence,daily_evidence,render

ASOF="2026-10-21"
def table(rows):
    if not rows:return ""
    s=io.StringIO();w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return s.getvalue()

def make_archive(root,wrong_date=False,drop_flow=None,stale_holdings=False,weak_breadth=False):
    sectors=[("SEMICON","반도체","091160",[f"{i:06d}" for i in range(1,6)]),
             ("IT","IT","091180",[f"{i:06d}" for i in range(1,11)]),
             ("POWER","전력설비","091170",[f"{i:06d}" for i in range(11,16)]),
             ("CONSTRUCTION","건설","091200",[f"{i:06d}" for i in range(16,21)])]
    d="2026-10-20" if wrong_date else ASOF
    features=[dict(date=ASOF,sector_id=sid,sector_name=name,etf=etf,
                   snapshot_date="2026-10-01" if stale_holdings else "2026-10-19",
                   foreign_net_buy_5d_krw="-100",institution_net_buy_5d_krw="-200",
                   price_flow_proxy_ready="True") for sid,name,etf,tickers in sectors]
    market=[]
    foreign=[]
    institution=[]
    def money(t):
        i=int(t)
        if i<=5:return 10
        if i<=10:return -4
        if i<=15:return 6
        return 5
    for i in range(1,21):
        t=f"{i:06d}"
        market.append(dict(ticker=t,Date=ASOF,Open=90,High=110,Low=70 if weak_breadth else 88,Close=80 if weak_breadth else 100,
                           Volume=10000,TurnoverKRW=10000000))
        if t!=drop_flow:
            foreign.append(dict(ticker=t,net_buy_krw=money(t)*1e9))
        institution.append(dict(ticker=t,net_buy_krw=0))
    contents={
        "diagnostics/collection_status.json":json.dumps({
            "asof":d,
            "datasets":{k:{"status":"OK"} for k in (
                "prices","flows","holdings","normalization")}}),
        "research/sector_evidence_latest.csv":table(features),
        "market/daily_prices/KOSPI/"+ASOF+".csv":table(market),
        "market/daily_flows/KOSPI/"+ASOF+"_foreign.csv":table(foreign),
        "market/daily_flows/KOSPI/"+ASOF+"_institution.csv":table(institution),
    }
    for i in range(1,21):
        t=f"{i:06d}"
        contents[f"market/prices/{t}.csv"]=table([
            dict(Date="2026-10-20",Close=90,Open=88,High=100,Low=85),
            dict(Date=ASOF,Close=80 if weak_breadth else 100,Open=90,High=110,Low=70 if weak_breadth else 88)])
    for sid,name,etf,tickers in sectors:
        contents[f"market/raw_holdings/{etf}/"+(
            "2026-10-01" if stale_holdings else "2026-10-19")+".csv"]=table(
            [dict(티커=t,구성종목명="테스트"+t) for t in tickers]+
            [dict(티커="010010",구성종목명="원화현금")])
    path=Path(root)/"evidence.zip"
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,body in contents.items():z.writestr(name,body)
    return path

class SectorDailyMoneyTests(unittest.TestCase):
    def test_money_top3_excludes_cash_and_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=make_archive(tmp)
            evidence=Evidence(path)
            try:out=daily_evidence(evidence,ASOF)
            finally:evidence.close()
            self.assertEqual([x["sector_id"] for x in out["selected_top3"]],
                ["SEMICON","POWER","CONSTRUCTION"])
            self.assertTrue(out["complete_three"])
            self.assertEqual(out["selected_top3"][0]["cash_lines_excluded"],1)
            it=next(x for x in out["sector_samples"] if x["sector_id"]=="IT")
            self.assertEqual(it["day_net_flow_krw"],30_000_000_000)
            self.assertIn("CASH",render(out))
            self.assertFalse(out["trade_approved"])
    def test_positive_money_without_breadth_is_watch_only_no_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev=Evidence(make_archive(tmp,weak_breadth=True))
            try:data=daily_evidence(ev,ASOF)
            finally:ev.close()
            self.assertEqual(data["selected_top3"],[])
            self.assertEqual(len(data["watch_only_positive_flow_top3"]),3)
            self.assertTrue(all(x["day_breadth_pct"]==0
                                for x in data["watch_only_positive_flow_top3"]))
            self.assertTrue(all(x["trade_approval"]=="NO"
                                for x in data["watch_only_positive_flow_top3"]))
            self.assertIn("매수 제외된 수급 관찰 섹터",render(data))
            self.assertEqual(data["decision"],"CASH")

    def test_asof_mismatch_cannot_trick_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev=Evidence(make_archive(tmp,wrong_date=True))
            try:
                with self.assertRaisesRegex(ValueError,"ASOF_MISMATCH"):
                    daily_evidence(ev,ASOF)
            finally:ev.close()
    def test_missing_investor_flow_reduces_coverage_not_turned_to_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev=Evidence(make_archive(tmp,drop_flow="000011"))
            try:data=daily_evidence(ev,ASOF)
            finally:ev.close()
            power=next(x for x in data["sector_samples"] if x["sector_id"]=="POWER")
            self.assertEqual(power["price_flow_coverage"],0.8)
            self.assertFalse(power["base_eligible"])
            self.assertNotIn("POWER",[x["sector_id"] for x in data["selected_top3"]])
    def test_stale_etf_membership_disqualifies_all_sectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev=Evidence(make_archive(tmp,stale_holdings=True))
            try:data=daily_evidence(ev,ASOF)
            finally:ev.close()
            self.assertEqual(data["selected_top3"],[])
            self.assertFalse(data["complete_three"])
    def test_isolated_industries_have_separate_net_inflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev=Evidence(make_archive(tmp))
            try:data=daily_evidence(ev,ASOF)
            finally:ev.close()
            self.assertEqual(data["selected_top3"][1]["overlap_with_prior_sector_count"],0)
            self.assertEqual(data["selected_top3"][2]["overlap_with_prior_sector_count"],0)
    def test_absent_zip_data_blocks_research_not_claim_no_inflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"empty.zip"
            with zipfile.ZipFile(path,"w"):pass
            ev=Evidence(path)
            try:
                with self.assertRaisesRegex(ValueError,"MISSING_EVIDENCE_STATUS"):
                    daily_evidence(ev,ASOF)
            finally:ev.close()

if __name__=="__main__":unittest.main()
