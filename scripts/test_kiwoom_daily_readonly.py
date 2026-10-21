import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from kiwoom_daily_readonly import normalize,check_ok

class KiwoomReadOnlyTests(unittest.TestCase):
    def test_daily_normalization(self):
        sample={"return_code":0,"stk_dt_pole_chart_qry":[
            {"dt":"20261020","open_pric":"100","high_pric":"110",
             "low_pric":"95","cur_prc":"105","trde_qty":"1200"},
            {"dt":"20261019","open_pric":"-90","high_pric":"-100",
             "low_pric":"-80","cur_prc":"-95","trde_qty":"500"}]}
        rows=normalize(sample,"005930")
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["Close"],95)
        self.assertEqual(rows[-1]["Date"],"2026-10-20")
    def test_invalid_bar_excluded(self):
        rows=normalize({"return_code":0,"stk_dt_pole_chart_qry":[
            {"dt":"20261020","open_pric":"100","high_pric":"101",
             "low_pric":"99","cur_prc":"110"}]},"005930")
        self.assertEqual(rows,[])
    def test_business_error_rejected(self):
        with self.assertRaises(ValueError):
            check_ok({"return_code":-1,"return_msg":"sensitive error"})
    def test_no_missing_list_silently_accepted(self):
        with self.assertRaises(ValueError):normalize({"return_code":0},"005930")

if __name__=="__main__":unittest.main()
