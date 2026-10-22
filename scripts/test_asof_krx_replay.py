#!/usr/bin/env python3
"""Offline checks: KRX as-of honesty, ETF overlap and historical pivot prices."""
import io,json,tempfile,unittest,zipfile
from pathlib import Path
from datetime import date,timedelta
from asof_krx_replay import eligible_research,study,replay,floor_quote

class DatedKRXTests(unittest.TestCase):
    def test_sector_money_and_independent_breadth_gate(self):
        sectors=[
         dict(sector_id="SEMICON",name="반도체",day_net_bn=660.7,
              day_turn_bn=10157.9,day_breadth_pct=100),
         dict(sector_id="IT",name="IT",day_net_bn=490.2,
              day_turn_bn=11101.9,day_breadth_pct=85,duplicate_inflow=True),
         dict(sector_id="ROBOT",name="로봇",day_net_bn=656.8,
              day_turn_bn=10001.7,day_breadth_pct=62.5,duplicate_inflow=True),
         dict(sector_id="POWER",name="전력설비",day_net_bn=41,
              day_turn_bn=501,day_breadth_pct=83.3),
         dict(sector_id="CONSTRUCTION",name="건설",day_net_bn=31,
              day_turn_bn=235,day_breadth_pct=68.8),
         dict(sector_id="BANK",name="은행",day_net_bn=-16,
              day_turn_bn=395,day_breadth_pct=75)]
        self.assertEqual([x["sector_id"] for x in eligible_research(sectors)],
            ["SEMICON","POWER","CONSTRUCTION"])
    def test_no_forced_top3_when_market_has_one_eligible_sector(self):
        out=eligible_research([dict(sector_id="POWER",name="전력설비",
             day_net_bn=4,day_turn_bn=5,day_breadth_pct=63)])
        self.assertEqual(len(out),1)
    def test_pivot_stops_only_use_confirmed_past_daily_prices(self):
        start=date(2026,7,1)
        bars=[]
        for i in range(85):
            d=start+timedelta(days=i)
            low=85 if i==77 else 95
            bars.append(dict(Date=d.isoformat(),Open=100,High=110,
                  Low=low,Close=100,Volume=1))
        asof=bars[-1]["Date"]
        out=study(bars,asof)
        self.assertEqual(out["status"],"STRUCTURAL_STOP_REFERENCE_ONLY")
        self.assertLess(out["stop_reference"],out["close"])
    def test_no_lookahead_and_missing_asof_day_fails_closed(self):
        bars=[dict(Date="2026-10-20",Open=90,High=110,Low=80,Close=100)]*70
        bars.append(dict(Date="2026-10-22",Open=120,High=140,Low=110,Close=130))
        result=study(bars,"2026-10-21")
        self.assertEqual(result["status"],"MISSING_65_ASOF_BARS")
    def test_krx_quote_increment_applied_to_price_reference(self):
        self.assertEqual(floor_quote(201272),201000)
        self.assertEqual(floor_quote(183059),183000)
        self.assertEqual(floor_quote(45337),45300)
        self.assertEqual(floor_quote(41052),41050)
        self.assertEqual(floor_quote(None),None)

    def test_archive_asof_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"evidence.zip"
            with zipfile.ZipFile(file,"w") as z:
                z.writestr("diagnostics/collection_status.json",json.dumps({"asof":"2026-10-20"}))
            with self.assertRaisesRegex(ValueError,"ASOF_MISMATCH"):
                replay(file,"2026-10-21")
if __name__=="__main__":unittest.main()
