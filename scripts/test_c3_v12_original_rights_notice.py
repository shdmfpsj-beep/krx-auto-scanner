import unittest,sys,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_v12_original_rights_notice import parse_rights

def doc(code,date,price,cause="무상증자"):
 return (f'<DOCUMENT><BODY><TABLE><TR><TD>1. 회사명</TD><TD>TEST</TD></TR>'
   f'<TR><TD>3. 단축코드</TD><TD>A{code}</TD></TR>'
   f'<TR><TD>4. 기준가(원)</TD><TD>{price}</TD></TR>'
   f'<TR><TD>5. 권리락 실시일</TD><TD>{date}</TD></TR>'
   f'<TR><TD>6. 사유</TD><TD>{cause}</TD></TR></TABLE></BODY></DOCUMENT>')

class RightsEvidenceTests(unittest.TestCase):
 def test_exact_header_and_strict_original_notice(self):
    d=parse_rights(doc("475460","2026-09-16","2,765"),"475460",dt.date(2026,9,15))
    self.assertTrue(d["original_structured_notice_approved"])
    self.assertEqual(d["parsed_reference_price_krw"],2765)
 def test_original_krx_two_row_headings_values(self):
    txt=('<TABLE><TR><TD>1. 회사명</TD><TD>2. 주권종류</TD><TD>3. 단축코드</TD>'
       '<TD>4. 기준가(원)</TD><TD>5. 권리락 실시일</TD><TD>6. 사유</TD></TR>'
       '<TR><TD>미트박스</TD><TD>보통주식</TD><TD>A475460</TD>'
       '<TD>2,765</TD><TD>2026-09-16</TD><TD>무상증자</TD></TR></TABLE>')
    r=parse_rights(txt,"475460",dt.date(2026,9,15))
    self.assertTrue(r["original_structured_notice_approved"])
    self.assertEqual(r["parsed_reference_price_krw"],2765)
    self.assertEqual(r["parsed_ex_date"],"2026-09-16")
 def test_wrong_ticker_fails(self):
    d=parse_rights(doc("475460","2026-09-16","2,765"),"001000",dt.date(2026,9,15))
    self.assertFalse(d["original_structured_notice_approved"])
 def test_date_before_disclosure_fails(self):
    d=parse_rights(doc("475460","2026-09-14","2,765"),"475460",dt.date(2026,9,15))
    self.assertFalse(d["original_structured_notice_approved"])
 def test_missing_price_must_not_be_guessed(self):
    d=parse_rights(doc("475460","2026-09-16","N/A"),"475460",dt.date(2026,9,15))
    self.assertIsNone(d["parsed_reference_price_krw"])
    self.assertFalse(d["original_structured_notice_approved"])
 def test_paid_rights_not_free_bonus(self):
    d=parse_rights(doc("475460","2026-09-16","2,765","유상증자"),"475460",dt.date(2026,9,15))
    self.assertFalse(d["original_structured_notice_approved"])
if __name__=="__main__":unittest.main()
