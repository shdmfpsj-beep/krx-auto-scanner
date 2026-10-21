import sys,unittest,io,json,urllib.error
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from kiwoom_daily_readonly import normalize,check_ok,diagnostic_codes,diagnostic_body_shape,post

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
    def test_safe_embedded_error_code(self):
        code,embedded=diagnostic_codes({"return_code":3,
            "return_msg":"[8002: key invalid] SECRET_VALUE"})
        self.assertEqual((code,embedded),("3","8002"))

    def test_http_400_never_prints_error_body(self):
        response=json.dumps({"return_code":3,
            "return_msg":"[8002: Invalid Key] DONT_LOG_THIS_SECRET"}).encode()
        error=urllib.error.HTTPError("https://api.kiwoom.com/oauth2/token",
            400,"Bad Request",{},io.BytesIO(response))
        with patch("kiwoom_daily_readonly.urllib.request.urlopen",side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                post("/oauth2/token",{"Content-Type":"application/json"},
                     {"grant_type":"client_credentials","appkey":"PRIVATE_APP_KEY",
                      "secretkey":"PRIVATE_APP_SECRET"})
        msg=str(caught.exception)
        self.assertIn("http_status=400",msg)
        self.assertIn("embedded_code=8002",msg)
        self.assertNotIn("DONT_LOG_THIS_SECRET",msg)
        self.assertNotIn("PRIVATE_APP_KEY",msg)
        self.assertNotIn("PRIVATE_APP_SECRET",msg)

    def test_body_shape_never_exposes_response_values(self):
        kind,fields=diagnostic_body_shape(json.dumps({
            "return_msg":"PRIVATE_CREDENTIAL_VALUE",
            "return_code":3}).encode())
        self.assertEqual(kind,"JSON_OBJECT")
        self.assertIn("return_msg",fields)
        self.assertNotIn("PRIVATE_CREDENTIAL_VALUE",fields)
        kind,fields=diagnostic_body_shape(b"<html>PRIVATE_CREDENTIAL_VALUE</html>")
        self.assertEqual((kind,fields),("HTML","none"))

    def test_no_missing_list_silently_accepted(self):
        with self.assertRaises(ValueError):normalize({"return_code":0},"005930")

if __name__=="__main__":unittest.main()
