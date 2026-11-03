import unittest
from c3_entry_geometry_v23 import geometry

class TrendEntryTests(unittest.TestCase):
    def test_no_overhead_resistance_is_not_rejection(self):
        rows=[]
        for i in range(80):
            close=100+i
            rows.append(dict(date=f"2026-01-{i+1:02d}",open=close,high=close+2,low=close-2,close=close))
        # Use valid dates and one confirmed local low.
        from datetime import date,timedelta
        for i,row in enumerate(rows):
            row["date"]=(date(2026,1,1)+timedelta(days=i)).isoformat()
        rows[50]["low"]=rows[50]["low"]-12
        result=geometry(rows)
        self.assertEqual(result["status"],"RESEARCH_GEOMETRY_ONLY")
        self.assertIsNone(result["first_resistance"])
        self.assertEqual(result["trend_state"],"UPTREND")
        self.assertFalse(result["buy_approved"])

if __name__=="__main__":
    unittest.main()
