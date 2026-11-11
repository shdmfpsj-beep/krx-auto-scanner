import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_three_model_pit_matrix import matrix
class MatrixTests(unittest.TestCase):
 def bars(self):
  return [{"ticker":"000001","date":f"2026-{1+i//28:02d}-{1+i%28:02d}",
   "open":100+i*.2,"high":102+i*.2,"low":99+i*.2,
   "close":100+i*.2,"volume":1000} for i in range(82)]
 def snapshot(self,day):
  return {"ticker":"000001","asof":day,"receipt_date":"2026-01-01",
   "financial_screen_pass":True,"annual_plus_interim_growth_pass":True,
   "recent_financial_weakening_veto":False,"point_in_time_snapshot_verified":True}
 def test_same_day_all_models_have_slots(self):
  b=self.bars();r=matrix(b,[self.snapshot(b[80]["date"])])
  self.assertEqual(r["cohort_dates"],1)
  self.assertEqual(len(r["opportunities"][0]["models"]),3)
  self.assertFalse(r["performance_publication_allowed"])
 def test_future_filing_excluded(self):
  b=self.bars();s=self.snapshot(b[80]["date"]);s["receipt_date"]="2027-01-01"
  self.assertEqual(matrix(b,[s])["cohort_dates"],0)
 def test_unverified_snapshot_excluded(self):
  b=self.bars();s=self.snapshot(b[80]["date"]);s["point_in_time_snapshot_verified"]=False
  self.assertEqual(matrix(b,[s])["cohort_dates"],0)
if __name__=="__main__":unittest.main()
