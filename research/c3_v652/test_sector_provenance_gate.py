import unittest
from sector_provenance_gate import most_recent_group_snapshot,research_decision

def members():
    base=dict(sector_id="ROBOT",point_in_time_status="PROVIDER_DATED_NOT_INDEPENDENT_VINTAGE_VERIFIED")
    return [
        dict(base,ticker="123456",snapshot_date="2026-10-06"),
        dict(base,ticker="999999",snapshot_date="2026-10-12"),
        dict(base,ticker="999999",snapshot_date="2026-10-19"),
    ]

def context(day="2026-10-23"):
    return [dict(date=day,sector_id="ROBOT",etf="445290",rs_5d_pp=1.2,
                 breadth_up_5d_pct=25.0,membership_status="PROVIDER_DATED_PROXY_NOT_STRICT_PIT",
                 live_selection_authorized=False)]

class SectorV652(unittest.TestCase):
    def test_removed_member_does_not_carry_forward(self):
        self.assertEqual(most_recent_group_snapshot("123456","2026-10-23",members(),context()),[])
    def test_current_member(self):
        r=most_recent_group_snapshot("999999","2026-10-23",members(),context())
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]["latest_snapshot_date"],"2026-10-19")
    def test_snapshot_in_future_not_used(self):
        m=members()+[dict(members()[-1],ticker="999999",snapshot_date="2026-10-26")]
        self.assertEqual(len(most_recent_group_snapshot("999999","2026-10-23",m,context())),1)
    def test_no_live_trade(self):
        r=most_recent_group_snapshot("999999","2026-10-23",members(),context())
        self.assertFalse(research_decision(r,True)["orders_enabled"])
    def test_no_sector_not_biotech_verification(self):
        r=most_recent_group_snapshot("999999","2026-10-23",members(),context())
        self.assertFalse(r[0]["is_non_biotech_issuer_verified"])
    def test_third_party_backfill_not_approved(self):
        self.assertFalse(research_decision([])["trade_approved"])
    def test_wrong_vintage_rejected(self):
        m=members();m[0]["point_in_time_status"]="STRICT_PIT"
        with self.assertRaises(ValueError):
            most_recent_group_snapshot("999999","2026-10-23",m,context())
    def test_future_evidence_not_used(self):
        r=most_recent_group_snapshot("999999","2026-10-23",members(),context("2026-10-26"))
        self.assertEqual(r,[])
    def test_incompatible_live_data_rejected(self):
        e=context();e[0]["live_selection_authorized"]=True
        with self.assertRaises(ValueError):
            most_recent_group_snapshot("999999","2026-10-23",members(),e)
    def test_one_day_strict(self):
        with self.assertRaises(ValueError):
            most_recent_group_snapshot("999999","2026-10-32",members(),context())
if __name__=="__main__":unittest.main()
