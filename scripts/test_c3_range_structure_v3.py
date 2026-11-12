import copy,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from PIL import Image
from c3_single_entry_range_v1 import risk_intersection
from c3_range_structure_v3 import stop_review,practicality,reassess,audit_no_anchor_change
from c3_range_card_v1 import render,hold_card


def fixture(pivot=False):
    day=date(2026,5,1);bs=[]
    while len(bs)<125:
        if day.weekday()<5:bs.append(dict(date=str(day),open=121,high=125,low=120,close=123,volume=10000,turnover_krw=1230000,segment=0,tradable=True))
        day+=timedelta(days=1)
    at=-5 if pivot else -2
    bs[at].update(open=105,high=108,low=100,close=106)
    bs[-1].update(open=109,high=114,low=108,close=110)
    p=dict(method='TREND_CONFIRMED_MA10',asof=bs[-1]['date'],reference_close=110,atr14=10,
        support=105,stop=97,r1=140,r2=None,structural_low=100,structural_high=110,
        evidence=dict(observed_low=100,touch_date=bs[at]['date']),
        range=risk_intersection(100,110,97,140,None,110,10),range_valid=True)
    return bs,p

class StructuralEvidence(unittest.TestCase):
    def test_ma_contact_and_rebound_alone_not_confirmed(self):
        b,p=fixture();r=stop_review(b,p)
        self.assertEqual(r['independent_contacts'],1);self.assertTrue(r['rebound_observed']);self.assertEqual(r['status'],'STRUCTURAL_STOP_WEAK')
    def test_completed_pivot_can_confirm_price_structure(self):
        b,p=fixture(True);r=stop_review(b,p)
        self.assertTrue(r['confirmed_pivots']);self.assertEqual(r['status'],'STRUCTURAL_STOP_CONFIRMED')
    def test_future_cannot_make_current_contact_a_pivot(self):
        b,p=fixture();before=stop_review(b,p)
        b.append(dict(b[-1],date=str(date.fromisoformat(b[-1]['date'])+timedelta(days=1)),low=113))
        self.assertEqual(before['status'],'STRUCTURAL_STOP_WEAK')
        self.assertEqual(stop_review(b[:-1],p),before)
    def test_invalidated_older_contacts_do_not_inflate_strength(self):
        b,p=fixture();b[-12].update(low=100,close=106);b[-8].update(low=90,close=93)
        r=stop_review(b,p);self.assertEqual(r['independent_contacts'],1);self.assertEqual(r['last_support_break_date'],b[-8]['date'])
    def test_high_volume_does_not_certify_lone_support(self):
        b,p=fixture();b[-1]['volume']=1e9;self.assertFalse(stop_review(b,p)['research_eligible'])
    def test_noise_buffer_defect_is_separate(self):
        b,p=fixture(True)
        for x in b[-20:-5]:x.update(open=124,low=120,close=124)
        self.assertEqual(stop_review(b,p)['status'],'STOP_TOO_TIGHT_FOR_VOLATILITY')
    def test_original_stop_formula_must_match(self):
        b,p=fixture();p['stop']=98
        with self.assertRaises(ValueError):stop_review(b,p)
    def test_reassessment_never_moves_stop_range_or_resistance(self):
        b,p=fixture();old=dict(plans=[p],best=p,reason=None);saved=copy.deepcopy(old);new=reassess(b,old)
        self.assertEqual(old,saved);self.assertTrue(audit_no_anchor_change(old,new));self.assertIsNone(new['best'])
    def test_deeper_comparison_is_never_automatically_adopted(self):
        b,p=fixture();b[-15].update(low=95,close=106)
        r=stop_review(b,p);self.assertFalse(r['deeper_confirmed_support']['adopted']);self.assertEqual(p['stop'],97)
    def test_narrow_distance_fragment_is_flagged_without_widening(self):
        p=dict(reference_close=14250,atr14=690,structural_low=13350,structural_high=13620,
            range=dict(valid=True,low=13560,high=13620,width_atr=60/690))
        r=practicality(p);self.assertEqual(r['status'],'RANGE_TOO_NARROW');self.assertEqual(r['distance_clip_removed_krw'],210)
        self.assertFalse(r['range_widened']);self.assertEqual(p['range']['low'],13560)
    def test_width_sensitivity_is_not_a_live_minimum(self):
        _,p=fixture();r=practicality(p)
        self.assertIn('NOT_VALIDATED_LIVE_MINIMUM',r['narrow_alert_basis']);self.assertFalse(r['risk_limits_changed'])

class ReferenceCard(unittest.TestCase):
    def report(self,day):return dict(source_date=day,source_run_id='123',source_hash='a'*64,report_payload_sha256='b'*64,
        source_received_at='2026-11-12T01:10:31+00:00',generated_at='2026-11-12T10:00:00+00:00',regime=dict(observed_regime='BEAR'),
        funnel=dict(full_market=2769,analysis_eligible=1988,technical=149))
    def test_reference_palette_sections_prices_and_ma60(self):
        b,p=fixture(True);p['stop_reliability']=stop_review(b,p);p['practicality']=practicality(p)
        r=dict(ticker='000001',name='검증사례',sector='정보기술',market='KOSDAQ',close=b[-1]['close'],own_rs20=10,rs_accel5=1,turnover20=1e9,display_plan=p,research_rank=1)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.png';m=render(r,b,self.report(b[-1]['date']),path)
            with Image.open(path) as im:
                self.assertEqual(im.getpixel((10,10)),(41,43,44));self.assertEqual(im.getpixel((10,150)),(250,249,245))
                saved=json.loads(im.info['C3_manifest']);self.assertEqual(saved['range'],[p['range']['low'],p['range']['high']]);self.assertEqual(saved['stop'],97)
            self.assertEqual(m['ma60_visible_points'],60);self.assertEqual(m['analysis_sections'],['정량·섹터','재무·실적','주요 이슈·수급','리스크·구조손절'])
            self.assertTrue(all(x['text_right_max']<=x['box_right'] for x in m['layout']))
    def test_no_two_order_labels_or_trade_count_rule(self):
        source=Path(__file__).with_name('c3_range_card_v1.py').read_text()
        for forbidden in ('1차 매수','2차 매수','한 번만','50:50'):self.assertNotIn(forbidden,source)
    def test_cash_card_retains_source_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'cash.png';m=hold_card(self.report('2026-11-11'),p)
            self.assertEqual(m['theme'],'USER_REFERENCE_IVORY_GREY_V3');self.assertEqual(m['source_hash'],'a'*64)

if __name__=='__main__':unittest.main()
