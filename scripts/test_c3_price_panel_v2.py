import copy
import tempfile
import unittest
from c3_price_panel_v2 import normalized_rows,reference_event,audit_panel,collect_panel

DAY="2026-11-03"
def raw(**kwargs):
    r=dict(ISU_CD="000660",ISU_NM="TEST",BAS_DD="20261103",TDD_OPNPRC="100",TDD_HGPRC="110",
           TDD_LWPRC="95",TDD_CLSPRC="99",ACC_TRDVOL="100",ACC_TRDVAL="10000",CMPPREVDD_PRC="-1",FLUC_RT="-1.0",LIST_SHRS="1000",MKTCAP="99000")
    r.update(kwargs);return r
def norm(r=None,market="KOSPI"):
    return normalized_rows({"OutBlock_1":[r or raw()]},DAY,market,"hash")[0]

class PricePanelTests(unittest.TestCase):
    def test_negative_delta_preserved_for_reference_price_analysis(self):
        r=norm();self.assertEqual(r['change'],-1);self.assertTrue(r['tradable'])
    def test_duplicate_security_not_silently_removed(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            normalized_rows({'OutBlock_1':[raw(),raw()]},DAY,'KOSPI','hash')
    def test_mismatched_source_date_rejected(self):
        with self.assertRaisesRegex(ValueError,"DATE_MISMATCH"):
            norm(raw(BAS_DD='20261102'))
    def test_unsupported_isin_not_truncated_into_ticker(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_SECURITY"):
            norm(raw(ISU_CD='KR7000660001'))
    def test_suspended_zero_ohlc_is_retained_without_fill_eligibility(self):
        r=norm(raw(TDD_OPNPRC='0',TDD_HGPRC='0',TDD_LWPRC='0',ACC_TRDVOL='0'))
        self.assertTrue(r['halt_like']);self.assertFalse(r['tradable'])
    def test_invalid_traded_ohlc_remains_visible_for_exclusion(self):
        r=norm(raw(TDD_HGPRC='80'))
        self.assertFalse(r['ohlc_valid']);self.assertFalse(r['halt_like'])
        responses=[dict(date=DAY,market=m,status='OK') for m in ('KOSPI','KOSDAQ')]
        a=audit_panel([r],[DAY],responses)
        self.assertEqual(len(a['invalid_rows']),1);self.assertFalse(a['dated_eod_consistency_passed'])
    def test_split_candidate_is_dated_and_not_retroactive_adjustment(self):
        p=norm(raw(TDD_CLSPRC='100'));c=norm(raw(TDD_CLSPRC='55',CMPPREVDD_PRC='5',LIST_SHRS='2000'))
        original=copy.deepcopy(p)
        e=reference_event(p,c)
        self.assertEqual(e['kind'],'SHARE_COUNT_REBASE_CANDIDATE');self.assertEqual(e['factor_known_on_event_date'],.5)
        self.assertFalse(e['corporate_action_confirmed']);self.assertEqual(p,original)
    def test_dividend_like_rebase_not_asserted_as_verified_cash_dividend(self):
        p=norm(raw(TDD_CLSPRC='100'));c=norm(raw(TDD_CLSPRC='98',CMPPREVDD_PRC='0'))
        self.assertEqual(reference_event(p,c)['kind'],'REFERENCE_PRICE_REBASE_UNRESOLVED')
    def test_ordinary_negative_change_is_not_a_corporate_action(self):
        self.assertIsNone(reference_event(norm(raw(TDD_CLSPRC='100')),norm()))
    def test_small_reference_discrepancy_with_unchanged_shares_is_not_a_split(self):
        p=norm(raw(TDD_CLSPRC='10000'));c=norm(raw(TDD_CLSPRC='10005',CMPPREVDD_PRC='0'))
        self.assertEqual(reference_event(p,c)['kind'],'REFERENCE_PRICE_REBASE_UNRESOLVED')
    def test_one_missing_market_blocks_complete_dataset(self):
        a=audit_panel([norm()],[DAY],[dict(date=DAY,market='KOSPI',status='OK')])
        self.assertEqual(a['missing_market_dates'],[dict(date=DAY,market='KOSDAQ')])
        self.assertFalse(a['dated_eod_consistency_passed']);self.assertFalse(a['regular_only_certified'])
    def test_cross_market_duplicate_security_cannot_inflate_universe(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_PANEL'):
            audit_panel([norm(),norm(market='KOSDAQ')],[DAY],[])
    def test_auth_failure_does_not_generate_large_request_batch(self):
        calls=[]
        def fail(*args):
            calls.append(args[:2]);raise ValueError('KRX_AUTH_OR_SERVICE_APPROVAL_MISSING')
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'NO_OFFICIAL_SEED_RESPONSE'):
                collect_panel([DAY,'2026-11-04'],t,'SYNTHETIC',interval=0,fetcher=fail)
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
