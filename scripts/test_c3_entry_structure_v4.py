import copy,unittest
from unittest.mock import patch
from c3_entry_structure_v4 import zone_geometry,review_v4,reasons
from c3_filter_audit_v4 import exclusion_audit
from test_c3_range_structure_v3 import fixture as base_fixture

def fixture(pivot=False):
    bars,plan=base_fixture(pivot);plan["support_known_on"]=bars[-1]["date"];return bars,plan

class IntactZones(unittest.TestCase):
    def test_distance_does_not_carve_a_fake_sliver(self):
        r=zone_geometry(100,110,97,140,None,114,10,True)
        self.assertTrue(r['valid']);self.assertEqual(r['low'],100);self.assertTrue(r['lower_edge_exceeds_old_distance_limit']);self.assertTrue(r['old_fragment_was_too_narrow'])
    def test_every_price_still_meets_risk_and_cost_rr(self):
        r=zone_geometry(100,110,97,140,None,110,10,True)
        self.assertTrue(r['all_legal_ticks_passed']);self.assertLessEqual(r['endpoints']['upper']['stop_risk_pct'],8);self.assertGreaterEqual(r['min_net_r1_rr'],1.5)
    def test_narrow_real_support_is_not_blanket_rejected(self):
        r=zone_geometry(100,101,95,130,None,101,10,True)
        self.assertTrue(r['valid']);self.assertEqual(r['status'],'NARROW_BUT_STRUCTURALLY_VALID')
    def test_unconfirmed_support_never_passes_even_with_high_rr(self):
        self.assertFalse(zone_geometry(100,101,95,130,None,101,10,False)['valid'])
    def test_whole_zone_too_far_still_waits(self):
        r=zone_geometry(100,110,97,140,None,140,10,True)
        self.assertFalse(r['valid']);self.assertEqual(r['reason'],'RANGE_TOO_FAR')
    def test_missing_resistance_cannot_make_range(self):self.assertFalse(zone_geometry(100,110,97,None,None,110,10,True)['valid'])
    def test_no_reward_fixes_by_stop_or_target_mutation(self):
        self.assertFalse(zone_geometry(100,110,97,102,None,110,10,True)['valid'])

class TypedEvidence(unittest.TestCase):
    def test_first_pullback_can_use_one_confirmed_reclaim(self):
        b,_=fixture();old=dict(plans=[],best=None,reason=None)
        with patch('c3_entry_structure_v4.confirmed_turn',return_value=90),patch('c3_entry_structure_v4.phase',return_value='FIRST_PULLBACK_RECLAIM'),patch('c3_entry_structure_v4.first_pullback_context',return_value=100),patch('c3_entry_structure_v4.active_resistances',return_value=([dict(price=140)],[])):
            r=review_v4(b,old)
        a=next(p for p in r['plans'] if p['method']=='FIRST_PULLBACK');self.assertFalse(a['stop_reliability']['two_contacts_required'])
        self.assertEqual(a['invalidation_low'],min(x['low'] for x in b[100:]));self.assertEqual(a['stop_reliability']['status'],'STRUCTURAL_STOP_CONFIRMED')
    def test_second_reclaim_not_relabelled_first(self):
        b,_=fixture()
        with patch('c3_entry_structure_v4.confirmed_turn',return_value=90),patch('c3_entry_structure_v4.phase',return_value='FIRST_PULLBACK_RECLAIM'),patch('c3_entry_structure_v4.first_pullback_context',return_value=None):r=review_v4(b,dict(plans=[],best=None))
        self.assertFalse(any(p['method']=='FIRST_PULLBACK' for p in r['plans']))
    def test_pivot_path_preserved_without_two_extra_contacts(self):
        b,p=fixture(True);old=dict(plans=[p],best=p);saved=copy.deepcopy(old)
        r=review_v4(b,old);self.assertEqual(old,saved);self.assertTrue(any(p['method']=='CONFIRMED_PIVOT' for p in r['plans']))
    def test_failed_breakout_retest_is_not_rescued(self):
        b,p=fixture();p.update(method='FIRST_PULLBACK_RETEST',support=100,evidence=dict(breakout_date=b[-6]['date'],breakout_volume_ratio=2,post_breakout_structure=dict(invalidation_low=100)))
        b[-3].update(open=94,low=88,close=90,high=98)
        with patch('c3_entry_structure_v4.confirmed_turn',return_value=None):r=review_v4(b,dict(plans=[p],best=None))
        self.assertFalse(any(p['method']=='BREAKOUT_RETEST' for p in r['plans']))
    def test_future_information_does_not_change_prefix(self):
        b,p=fixture(True);old=dict(plans=[p],best=p);r=review_v4(b,old)
        b.append(dict(b[-1],date='2027-01-01',low=1,close=1))
        self.assertEqual(r,review_v4(b[:-1],old))

class FailureAccounting(unittest.TestCase):
    def row(self,t,rs,liq,fin):return dict(ticker=t,momentum_pass=rs,liquidity_pass=liq,financial=dict(observed_positive=fin,status='LATER_API_CONTEXT_NOT_ORIGINAL_PIT'),range_review=dict(plans=[],best=None,v3_review=dict(plans=[],best=None)))
    def test_overlapping_counts_are_not_summed_as_unique_failures(self):
        rows=[self.row('A',False,False,False),self.row('B',True,False,True)]
        a=exclusion_audit(rows);self.assertEqual(sum(a['v4']['exclusive_reason_combinations'].values()),2);self.assertEqual(a['v4']['multiple_failures'],2)
        self.assertEqual(a['v4_sequential_funnel'][0]['passed'],1)
    def test_negative_rs_not_promoted_by_a_pretty_range(self):
        r=self.row('A',False,True,True);self.assertIn('RS_NOT_POSITIVE_AND_IMPROVING',reasons(r))
    def test_data_hold_and_no_candidate_are_separate(self):
        a=exclusion_audit([self.row('A',False,False,False)])['cash_interpretation'];self.assertFalse(a['absence_of_marketwide_profitable_stocks_proven']);self.assertFalse(a['over_exclusion_ruled_out'])

if __name__=='__main__':unittest.main()
