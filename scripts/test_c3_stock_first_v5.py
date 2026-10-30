"""C3 v5 selection and practical-entry unit tests; no historical P/L backtests."""
import os,tempfile,unittest
from pathlib import Path
import pandas as pd
from c3_stock_first_v5 import run,pullback_plan,breakout_plan,read_verified_flows,prioritize

ARCHIVE=os.getenv('C3_STOCK_FIRST_SOURCE_ZIP')

class TestV5StockFirst(unittest.TestCase):
    def row(self,**changes):
        r={'close':114200,'atr14':3500,'stop':109600,'support':110300,
           'first_resistance':131500,'second_resistance':141700,
           'pullback_low':110900,'pullback_high':113700,'rvol20':.7,
           'track':'EARLY_LAUNCH','stock_strength_score100':55,
           'r5_pct':3,'r20_pct':7,'r60_pct':-10,
           'overhead_supply':'LOW_CONFIRMED_SELL_PRESSURE'}
        r.update(changes);return r

    def test_valid_orion_pullback_not_over_tight(self):
        p=pullback_plan(self.row(),'SUSTAINED_EARLY_LEADER',1.1)
        self.assertEqual((p['watch_low'],p['watch_high']),(110900,113700))
        self.assertEqual(p['pullback_state'],'PULLBACK_SETUP_WATCH')
        self.assertGreater(p['first_obstacle_net_r_at_upper'],2)

    def test_heavy_supply_dongseo_is_not_top_entry(self):
        p=pullback_plan(self.row(close=28400,atr14=893,stop=26900,
           support=27100,first_resistance=29550,second_resistance=None,
           pullback_low=27600,pullback_high=27950,
           overhead_supply='HIGH_SUPPLY'),'SUSTAINED_EARLY_LEADER',.95)
        self.assertEqual(p['pullback_state'],'PIVOT_HEAVY_SUPPLY_WAIT')

    def test_near_wall_blocks_false_buyable_leader(self):
        p=pullback_plan(self.row(close=34900,atr14=1407,stop=32900,
           first_resistance=35650,pullback_low=33600,pullback_high=33950),
           'SUSTAINED_EARLY_LEADER',1.4)
        self.assertEqual(p['pullback_state'],'OVERHEAD_TOO_CLOSE_TO_LATEST_CLOSE')

    def test_far_breakout_is_watch_data_not_buy_trigger(self):
        b=pd.DataFrame({'high':[30000]*20+[28400]})
        p=breakout_plan(self.row(close=28400,atr14=893,stop=26900,
             first_resistance=29550,second_resistance=None),b,
             'SUSTAINED_EARLY_LEADER')
        self.assertEqual(p['breakout_state'],'TRIGGER_TOO_FAR_NO_CHASE')
        self.assertIsNone(p['breakout_trigger'])

    def test_claimed_official_flow_is_not_ranking_bonus(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'flow.csv'
            prefix='ticker,asof,foreign_net_buy_krw,institution_net_buy_krw,session,source,value_verified\n'
            p.write_text(prefix+'271560,2026-10-31,100,100,KRX_REGULAR_ONLY,KRX_OFFICIAL,true\n')
            with self.assertRaisesRegex(ValueError,'ASOF_DATE_MISMATCH'):
                read_verified_flows(p,'2026-10-30')
            p.write_text(prefix+'271560,2026-10-30,100,100,KRX_REGULAR_ONLY,KRX_OFFICIAL,true\n')
            f,_=read_verified_flows(p,'2026-10-30')
            x=prioritize(self.row(),'SUSTAINED_EARLY_LEADER',
                {'pullback_state':'PULLBACK_SETUP_WATCH'},
                {'breakout_state':'FUTURE_CLOSE_BREAKOUT_ELIGIBLE_WATCH'},
                1.0,f['271560'])
            self.assertEqual(x['real_investor_flow_points'],0)
            self.assertIn('NOT_AUDITED',x['investor_flow_state'])

    @unittest.skipUnless(ARCHIVE,'Original Oct30 scan artifact required')
    def test_frozen_market_selection_not_order_permission(self):
        with tempfile.TemporaryDirectory() as root:
            s,rows=run(ARCHIVE,root)
        self.assertEqual(s['source_run_id'],'41051723762')
        self.assertEqual((s['price_stage_cases'],s['structured_candidates']),(457,96))
        self.assertEqual([x['ticker'] for x in s['top2']],['271560','026960'])
        self.assertEqual(s['category_counts']['PRIORITY_PULLBACK'],1)
        self.assertFalse(s['trade_approved'])
        self.assertFalse(s['orders_enabled'])
        self.assertTrue(s['no_profitability_backtests'])
        self.assertTrue(all(not x['buy_approved'] for x in rows))
        self.assertEqual(s['top2'][1]['pullback_state'],'PIVOT_HEAVY_SUPPLY_WAIT')

if __name__=='__main__':unittest.main()
