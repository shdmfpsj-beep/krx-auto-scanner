"""Guard future-day chronology, false fills and frozen artifact integrity."""
import json,os,tempfile,unittest
from pathlib import Path
from c3_forward_watch_v2 import (prepare_freeze,validate_freeze,update,
    recovery_state,next_open_state,canonical_sha,CHECKSUM_FIELDS)

SOURCE=os.getenv('C3_REPLAY_ARTIFACT_PATH')
def signal():
    s=dict(ticker='271560',name='오리온',asof='2026-10-30',close=114200.,
      atr14=3564.2857,support=110300.,stop=109700,first_resistance=131500.,
      watch_low=109800,watch_high=112400,buy_approved=False)
    s['signal_id']=canonical_sha(s)
    return s

def freeze():
    f=dict(schema='C3_PROSPECTIVE_PRICE_WATCH_V2_NO_ORDERS',
      asof='2026-10-30',source_run_id='test',source_stage_sha256='sha',
      source_history_sha256='sha',source_rank_sha256='sha',cohort_origin='test',
      frozen_signals=[signal()],source_regular_only_verified=False,
      trade_approved=False,orders_enabled=False)
    f['freeze_sha256']=canonical_sha({k:f[k] for k in CHECKSUM_FIELDS})
    return f

def bar(date='2026-11-02',o=113000,h=115100,l=111000,c=115000):
    return dict(date=date,open=o,high=h,low=l,close=c,volume=150000)

class TestForward(unittest.TestCase):
    def test_pending_without_future_prices_or_orders(self):
        r=update(freeze())
        self.assertEqual(r['states'],{'PENDING_NEXT_OBSERVED_SESSION':1})
        self.assertFalse(r['trade_approved'])
        self.assertFalse(r['orders_enabled'])
        self.assertEqual(r['broker_fills'],0)

    def test_stop_touch_rejects_even_if_close_recovers(self):
        self.assertEqual(recovery_state(signal(),bar(l=109600)),
                         'STRUCTURE_STOP_TOUCHED_REJECT')

    def test_contact_is_not_recovery(self):
        self.assertEqual(recovery_state(signal(),bar(c=112800)),
                         'CONTACT_WITHOUT_STRONG_CLOSE')
        self.assertEqual(recovery_state(signal(),bar(c=114100)),
                         'CONTACT_WITHOUT_STRONG_CLOSE')

    def test_d1_confirmed_cannot_be_traded_until_d2(self):
        s=next_open_state(signal(),bar(),None)
        self.assertEqual(s['d2_state'],'PENDING_D2_OBSERVED_SESSION')
        self.assertFalse(s['broker_fill'])

    def test_d2_valid_still_only_a_paper_price(self):
        x=next_open_state(signal(),bar(),
              bar(date='2026-11-03',o=115000,h=116000,l=114500,c=115500))
        self.assertEqual(x['d2_state'],'D2_OPEN_PRICE_ELIGIBLE_PAPER_ONLY')
        self.assertGreaterEqual(x['hypothetical_first_resistance_net_R'],2)
        self.assertFalse(x['buy_approved'])

    def test_d2_gap_or_risk_cancels(self):
        x=next_open_state(signal(),bar(),
              bar(date='2026-11-03',o=120000,h=121000,l=119000,c=120500))
        self.assertEqual(x['d2_state'],'D2_GAP_TOO_LARGE_NO_CHASE')
        x=next_open_state(signal(),bar(c=117800,h=118000),
              bar(date='2026-11-03',o=118000,h=119000,l=117900,c=118100))
        self.assertEqual(x['d2_state'],'D2_RISK_OR_NET_2R_FAILED')

    def test_no_skipping_calendar_sessions(self):
        with self.assertRaisesRegex(ValueError,'D1_DATE_NOT_NEXT_OBSERVED'):
            update(freeze(),{'271560':bar(date='2026-11-04')},
                   session_order=['2026-10-30','2026-11-02','2026-11-04'])

    def test_tampering_detected(self):
        f=freeze();f['frozen_signals'][0]['stop']=1
        with self.assertRaisesRegex(ValueError,'FREEZE_SHA256_MISMATCH'):
            validate_freeze(f)

    def test_self_reported_regular_scope_does_not_authorize(self):
        x=update(freeze(),regular_only_verified=True)
        self.assertFalse(x['source_regular_only_certified'])
        self.assertFalse(x['trade_approved'])

    @unittest.skipUnless(SOURCE,'Original dated scan artifact not supplied')
    def test_20261030_cohort_9_and_top2_immutable(self):
        p=Path(os.environ['C3_REPLAY_OUTPUT_DIR'])
        f=prepare_freeze(SOURCE,p/'c3_corridor_replay_v1.csv',
              p/'c3_corridor_replay_v1_status.json')
        self.assertEqual((f['asof'],len(f['frozen_signals'])),('2026-10-30',9))
        self.assertEqual([x['ticker'] for x in f['frozen_signals'][:2]],
                         ['271560','012630'])
        validate_freeze(f)
        self.assertEqual(update(f)['states'],{'PENDING_NEXT_OBSERVED_SESSION':9})

    @unittest.skipUnless(SOURCE,'Original dated scan artifact not supplied')
    def test_tampered_ranking_even_with_rehashed_csv_is_rejected(self):
        p=Path(os.environ['C3_REPLAY_OUTPUT_DIR'])
        meta=json.loads((p/'c3_corridor_replay_v1_status.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            altered=(p/'c3_corridor_replay_v1.csv').read_bytes().replace(b'109800',b'109900',1)
            q=Path(tmp)/'forged.csv';q.write_bytes(altered)
            meta['csv_sha256']=__import__('hashlib').sha256(altered).hexdigest()
            s=Path(tmp)/'forged.json';s.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'REPLAY_NOT_DERIVED_FROM_FROZEN_SOURCE'):
                prepare_freeze(SOURCE,q,s)

if __name__=='__main__':unittest.main()
