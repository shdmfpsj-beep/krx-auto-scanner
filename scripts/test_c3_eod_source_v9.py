"""Synthetic transport evidence; no real key or market result in these tests."""
import io,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from c3_eod_source_v9 import fetch,collect_day,run

KEY='SYNTHETIC_SECRET_NEVER_A_REAL_KEY';DAY='2026-11-05';NOW=datetime(2026,11,5,18,tzinfo=timezone.utc)


class Response:
    def __init__(self,body,status=200):self.body=body;self.status=status;self.headers={'Content-Type':'application/json'}
    def getcode(self):return self.status
    def read(self,_=-1):return self.body
    def __enter__(self):return self
    def __exit__(self,*a):return False


def payload(day=DAY,code='005930'):
    return {'OutBlock_1':[dict(BAS_DD=day.replace('-',''),ISU_CD=code,ISU_NM='SYNTHETIC',TDD_OPNPRC='100',TDD_HGPRC='110',TDD_LWPRC='90',TDD_CLSPRC='105',ACC_TRDVOL='1000',ACC_TRDVAL='100000')]}


class SourceV9Tests(unittest.TestCase):
    def test_existing_request_method_parameter_and_header_preserved(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),'GET');self.assertIn('basDd=20261105',req.full_url);self.assertNotIn(KEY,req.full_url);self.assertEqual(req.get_header('Auth_key'),KEY)
            return Response(json.dumps(payload()).encode())
        doc,info=fetch('KOSPI',DAY,KEY,opener);self.assertEqual(info['status'],'NONEMPTY_OFFICIAL_JSON');self.assertEqual(info['http_status'],200);self.assertNotIn(KEY,json.dumps(info))

    def test_empty_and_missing_block_distinguished(self):
        for value,status in [({'OutBlock_1':[]},'OUTBLOCK_EMPTY'),({'result':[]},'OUTBLOCK_MISSING_OR_PROVIDER_ERROR'),({'OutBlock_1':{}},'OUTBLOCK_WRONG_TYPE')]:
            _,info=fetch('KOSPI',DAY,KEY,lambda *a,**kw:Response(json.dumps(value).encode()));self.assertEqual(info['status'],status);self.assertIsNotNone(info['body_sha256'])

    def test_auth_rejection_and_key_echo_never_recorded(self):
        def opener(*a,**kw):raise HTTPError('https://example.invalid',403,'Forbidden',{},io.BytesIO(KEY.encode()))
        _,info=fetch('KOSPI',DAY,KEY,opener);self.assertEqual(info['status'],'AUTH_OR_SERVICE_APPROVAL_REJECTED');self.assertNotIn(KEY,json.dumps(info))

    def test_business_error_redacted_and_retained(self):
        _,info=fetch('KOSPI',DAY,KEY,lambda *a,**k:Response(json.dumps({'error_code':'DENIED','message':KEY}).encode()))
        self.assertEqual(info['provider_error']['error_code'],'DENIED');self.assertNotIn(KEY,json.dumps(info));self.assertEqual(info['status'],'OUTBLOCK_MISSING_OR_PROVIDER_ERROR')

    def test_nonjson_and_rate_limit_distinguished(self):
        for body,status,want in [(b'<html>busy</html>',200,'NON_JSON_RESPONSE'),(b'busy',429,'RATE_LIMITED')]:
            _,info=fetch('KOSPI',DAY,KEY,lambda *a,**kw:Response(body,status));self.assertEqual(info['status'],want)

    def test_both_markets_probed_even_if_first_is_empty(self):
        calls=[]
        def opener(req,**kw):
            calls.append(req.full_url);return Response(json.dumps({'OutBlock_1':[]} if '/stk_' in req.full_url else payload(code='001234')).encode())
        with tempfile.TemporaryDirectory() as tmp:
            m=collect_day(DAY,tmp,KEY,NOW,opener);self.assertEqual(len(calls),2);self.assertEqual(m['official_market_rows'],0);self.assertEqual(m['successful_partial_markets'],['KOSDAQ']);self.assertEqual(len(m['raw_response_sha256']),2);self.assertFalse((Path(tmp)/'KOSDAQ_official.csv').exists())

    def test_complete_two_market_set_works_with_v8_adapter(self):
        def opener(req,**kw):return Response(json.dumps(payload(code='005930' if '/stk_' in req.full_url else '001234')).encode())
        from c3_current_candidates_v7 import fresh_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            m=collect_day(DAY,tmp,KEY,NOW,opener);rows,status=fresh_snapshot(tmp);self.assertEqual(m['official_market_rows'],2);self.assertEqual(len(rows),2);self.assertFalse(m['independent_1530_regular_session_certified'])

    def test_current_unfinished_session_does_not_call_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=collect_day('2026-11-06',tmp,KEY,NOW,lambda *a,**kw:self.fail('FUTURE_EOD_REQUESTED'));self.assertEqual(m['status'],'SESSION_NOT_COMPLETED_NO_REQUEST')

    def test_wrong_date_and_duplicate_codes_fail_closed(self):
        for duplicate in (False,True):
            def opener(req,**kw):
                p=payload(day='2026-11-04' if not duplicate else DAY)
                if duplicate:p['OutBlock_1']*=2
                return Response(json.dumps(p).encode())
            with tempfile.TemporaryDirectory() as tmp:
                m=collect_day(DAY,tmp,KEY,NOW,opener);self.assertFalse(m['official_dataset_usable']);self.assertEqual(m['official_market_rows'],0)

    def test_control_date_success_does_not_claim_exact_target_failure_cause(self):
        def opener(req,**kw):
            old='20261104' in req.full_url;p=payload(day='2026-11-04',code='005930' if '/stk_' in req.full_url else '001234') if old else {'OutBlock_1':[]}
            return Response(json.dumps(p).encode())
        with tempfile.TemporaryDirectory() as tmp:
            r=run(['2026-11-04',DAY],tmp,KEY,NOW,opener);self.assertEqual(r['latest_available_asof'],'2026-11-04');self.assertIn('NO_PROVEN_EXACT',r['dates'][1]['control_interpretation']);self.assertNotIn(KEY,json.dumps(r))

    def test_missing_or_malformed_key_is_not_a_network_failure(self):
        for key,want in [(None,'AUTH_KEY_NOT_CONNECTED'),('BAD\nKEY','AUTH_KEY_FORMAT_INVALID')]:
            _,info=fetch('KOSPI',DAY,key,lambda *a,**kw:self.fail('INVALID_KEY_SENT'));self.assertEqual(info['status'],want)


if __name__=='__main__':unittest.main()
