import unittest
from unittest.mock import Mock,patch
from c3_recovery_source_probe_v1 import kiwoom_probe,strict_source_post


class ReadOnlyProviderProbeTests(unittest.TestCase):
    def test_strict_transport_is_documented_contract_without_redirects(self):
        reply=Mock(status_code=200,content=b'{}',headers={});reply.json.return_value={'return_code':0}
        with patch('c3_recovery_source_probe_v1.requests.post',return_value=reply) as send:
            strict_source_post('/oauth2/token',{'Content-Type':'application/json;charset=UTF-8'},
                               {'grant_type':'client_credentials','appkey':'PRIVATE','secretkey':'PRIVATE'})
            self.assertEqual(send.call_count,1)
            self.assertIs(send.call_args.kwargs['allow_redirects'],False)
            self.assertEqual(send.call_args.kwargs['headers']['api-id'],'au10001')
            self.assertEqual(send.call_args.kwargs['headers']['Accept'],'application/json')
        with self.assertRaisesRegex(ValueError,'READ_ONLY'):
            strict_source_post('/api/dostk/ordr',{'api-id':'kt10000'},{})

    def test_missing_pair_never_requests_token(self):
        def never(*args):raise AssertionError('NO_CREDENTIAL_NO_REQUEST')
        for env in ({},{'KIWOOM_APP_KEY':'SYNTHETIC_KEY'},{'KIWOOM_APP_SECRET':'SYNTHETIC_SECRET'}):
            x=kiwoom_probe(env,never);self.assertEqual(x['requests'],0)
            self.assertFalse(x['regular_market_wide_certified'])

    def test_no_account_order_or_telegram_paths_and_no_credentials_in_output(self):
        calls=[]
        def fake(path,headers,body):
            calls.append((path,headers.get('api-id')))
            if path=='/oauth2/token':return {'return_code':0,'token':'SYNTHETIC_TOKEN'},{}
            return {'return_code':0,'stk_dt_pole_chart_qry':[{'dt':'20261111'}]},{}
        out=kiwoom_probe({'KIWOOM_APP_KEY':'SYNTHETIC_KEY','KIWOOM_APP_SECRET':'SYNTHETIC_SECRET'},fake)
        self.assertEqual(calls,[('/oauth2/token',None),('/api/dostk/chart','ka10081'),('/api/dostk/chart','ka11081')])
        self.assertFalse(out['regular_market_wide_certified'])
        for value in ('SYNTHETIC_KEY','SYNTHETIC_SECRET','SYNTHETIC_TOKEN'):self.assertNotIn(value,str(out))

    def test_provider_rejection_is_not_source_certification(self):
        def fake(*args):return {'return_code':3,'return_msg':'[8002: invalid] DO_NOT_LOG'},{}
        out=kiwoom_probe({'KIWOOM_APP_KEY':'SYNTHETIC_KEY','KIWOOM_APP_SECRET':'SYNTHETIC_SECRET'},fake)
        self.assertEqual(out['status'],'AUTH_OR_CHART_REQUEST_FAILED')
        self.assertNotIn('DO_NOT_LOG',str(out));self.assertFalse(out['regular_market_wide_certified'])


if __name__=='__main__':unittest.main()
