import csv,json,tempfile,unittest
from pathlib import Path
from c3_daily_evidence_gate_v14 import run

class GateTests(unittest.TestCase):
    def test_uncertified_remains_watch_only(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"c.csv";out=Path(d)/"o.json"
            with source.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","name","close","ma20","ma60","rvol20","turnover_krw","latest_date","instrument_type","turnover_source","data_source"])
                w.writeheader()
                from datetime import datetime,timezone,timedelta
                w.writerow({"ticker":"005930","name":"Samsung","close":"100","ma20":"90","ma60":"80","rvol20":"2","turnover_krw":"1000000","latest_date":datetime.now(timezone(timedelta(hours=9))).date().isoformat(),"instrument_type":"UNKNOWN","turnover_source":"ESTIMATED_CLOSE_X_VOLUME","data_source":"pykrx"})
            r=run(source,out)
            self.assertEqual(r["evidence_pass"],0)
            self.assertEqual(r["research_top2"],[])
            self.assertEqual(r["uncertified_watch_top2"][0]["ticker"],"005930")
            self.assertEqual(r["buy_approvals"],0)
            self.assertTrue(out.exists())

if __name__=="__main__":unittest.main()
