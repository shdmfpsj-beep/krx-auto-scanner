"""End-to-end OFFLINE integration test: synthetic quotes are test fixtures only.
Never presented as live KRX prices, and never submitted as paper trades.
"""
import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class TestC3Pipeline(unittest.TestCase):
 def test_two_run_merge_and_followups(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);plans=root/"plans.csv";quotes=root/"quotes.json"
   plans.write_text("ticker,name,watch_low,watch_high,structure_stop\n271560,ORION,110900,113700,109600\n026960,DONGSUH,27600,27950,26900\n",encoding="utf8")
   ledger=root/"ledger.csv"
   for i,(time,price) in enumerate([("10:00",112000),("10:10",113000),("10:10",113000)]):
    quotes.write_text(json.dumps({"quotes":[{"ticker":"271560","price":price,"observed_at":f"2026-11-02T{time}:00+09:00","source":"verified_provider"}]}),encoding="utf8")
    watch=root/f"watch{i}.json";nextledger=root/f"ledger{i}.csv"
    subprocess.run([sys.executable,str(ROOT/"c3_intraday_watch_v1.py"),"--plans",str(plans),"--quotes",str(quotes),"--now",f"2026-11-02T{time}:30+09:00","--out",str(watch)],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT/"c3_intraday_persistent_v1.py"),"--watch",str(watch),"--previous",str(ledger),"--out",str(nextledger),"--summary",str(root/"summary.json")],check=True,capture_output=True,text=True)
    ledger=nextledger
   with ledger.open(encoding="utf8",newline="") as f:rows=list(csv.DictReader(f))
   self.assertEqual(len(rows),2)
   self.assertEqual({x["status"] for x in rows},{"WATCH_ZONE"})
   from c3_intraday_outcomes_v1 import outcomes
   result=outcomes(rows,(30,))
   self.assertEqual(len(result),1)
   self.assertEqual(result[0]["later_observations"],1)
   self.assertFalse(result[0]["is_trade_fill"])
if __name__=="__main__":unittest.main()
