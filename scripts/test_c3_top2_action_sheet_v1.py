"""C3 research chart companion tests: no backtests, broker orders or false fills."""
import os,tempfile,unittest
from c3_top2_action_sheet_v1 import prepare,run

PATH=os.getenv('C3_V5_RANKED_CSV')
ORION=dict(ticker='271560',name='오리온',asof='2026-10-30',
           close=114200,watch_low=110900,watch_high=113700,
           structure_stop=109600,first_obstacle_krw=131500,
           priority_class='PRIORITY_PULLBACK',pullback_state='PULLBACK_SETUP_WATCH',
           breakout_trigger=115300)
DONGSEO=dict(ticker='026960',name='동서',asof='2026-10-30',
           close=28400,watch_low=27600,watch_high=27950,
           structure_stop=26900,first_obstacle_krw=29550,
           priority_class='SECONDARY_WATCH',pullback_state='PIVOT_HEAVY_SUPPLY_WAIT',
           breakout_trigger=None)

class TestTop2ActionSheet(unittest.TestCase):
    def test_orion_close_sized_risk_and_alternative(self):
        x=prepare(ORION)
        self.assertEqual(x['pullback_watch_max_krw'],113700)
        self.assertEqual(x['structural_risk_upper_entry_pct'],3.61)
        self.assertEqual(x['estimated_net_r_to_first_obstacle'],3.53)
        self.assertEqual(x['alternative_future_breakout_krw'],115300)
        self.assertFalse(x['buy_approved'])
    def test_dongseo_supply_wait_and_no_chase(self):
        x=prepare(DONGSEO)
        self.assertEqual(x['estimated_net_r_to_first_obstacle'],1.15)
        self.assertEqual(x['pullback_state'],'RESISTANCE_SUPPLY_CLEARANCE_WAIT')
        self.assertIsNone(x['alternative_future_breakout_krw'])
    def test_invalid_levels_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID_ASOF_OR_STOP'):
            prepare(dict(ORION,structure_stop=114000))
    @unittest.skipUnless(PATH,'Original v5 ranked research required')
    def test_exact_research_top2_action_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=run(PATH,tmp)
        self.assertEqual([x['ticker'] for x in result['top2']],['271560','026960'])
        self.assertFalse(result['trade_approved'])
        self.assertFalse(result['orders_enabled'])

if __name__=='__main__':
    unittest.main()
