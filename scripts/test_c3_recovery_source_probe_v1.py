import unittest
from c3_recovery_source_probe_v1 import kiwoom_probe


class ReadOnlyProviderProbeTests(unittest.TestCase):
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
