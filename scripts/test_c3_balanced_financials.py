"""Financial arithmetic, actual API shapes and safety boundaries; no returns."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import c3_balanced_financials as model
from c3_top5_financial_selection import select, financial_points
from test_c3_top5_financial_selection import candidate, record, evidence
from c3_balanced_validation import recent_signals, embedded
from unittest.mock import patch

DAY = date(2026, 11, 20)
ANNUAL_RECEIPT = '20260320000001'
INTERIM_RECEIPT = '20261116000001'


def statement(year=2025, report='11011', receipt=ANNUAL_RECEIPT):
    values = dict(cash=40, current_assets=140, current_liabilities=50,
        inventory=20, receivables=30, ocf=14, icf=-20, capex=20,
        interest_expense=2, net_income=10, tax_expense=2, pretax_profit=12,
        depreciation=3, amortisation=1, equity=150, revenue=100, operating_profit=12)
    values['interest_expense_cf_adjustment']=2
    rows = []
    for name, (section, ids) in model.METRICS.items():
        now = values[name]
        prev = dict(revenue=80, operating_profit=8, ocf=10).get(name, now)
        rows.append(dict(sj_div=section, account_id=sorted(ids)[0],
            thstrm_amount=str(now), frmtrm_amount=str(prev), bfefrmtrm_amount=str(prev),
            thstrm_add_amount=str(now), frmtrm_add_amount=str(prev),
            rcept_no=receipt, bsns_year=str(year), reprt_code=report, fs_div='CFS', currency='KRW'))
    for name, val in [('ifrs-full_Assets', 250), ('ifrs-full_Liabilities', 100)]:
        rows.append(dict(sj_div='BS',account_id=name,thstrm_amount=str(val),
            frmtrm_amount=str(val),rcept_no=receipt,bsns_year=str(year),reprt_code=report,fs_div='CFS',currency='KRW'))
    for ids, value in zip(model.DEBT_IDS, [20, 0, 20, 0]):
        rows.append(dict(sj_div='BS',account_id=sorted(ids)[0],thstrm_amount=str(value),
            rcept_no=receipt,bsns_year=str(year),reprt_code=report,fs_div='CFS',currency='KRW'))
    return dict(status='000',list=rows)


def request(endpoint, params, key):
    if endpoint == 'list.json':
        return dict(status='000', total_page=1, list=[
            dict(report_nm='사업보고서 (2025.12)', rcept_dt='20260320', rcept_no=ANNUAL_RECEIPT),
            dict(report_nm='분기보고서 (2026.09)', rcept_dt='20261116', rcept_no=INTERIM_RECEIPT)])
    if endpoint == 'company.json':
        return dict(status='000', stock_code='111111', induty_code='264')
    if endpoint == 'accnutAdtorNmNdAdtOpinion.json':
        return dict(status='000', list=[dict(rcept_no=ANNUAL_RECEIPT, stlm_dt='2025-12-31',
            bsns_year='2025', adt_opinion='적정', emphs_matter='해당사항 없음')])
    if params['reprt_code'] == '11011':
        return statement()
    return statement(2026, '11014', INTERIM_RECEIPT)


class BalancedFinancialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = model.SnapshotCache(self.tmp.name)

    def collect(self, custom=request):
        return model.collect_balanced(DAY,[dict(ticker='111111',name='제조기업')], 'a'*40,
            DAY,self.cache,custom,lambda key: {'111111':'00111111'})

    def test_cash_flow_capex_and_fcf_definition(self):
        m=model.statement_metrics(statement())
        self.assertEqual(m['ocf'],14)
        self.assertEqual(m['icf'],-20)
        self.assertEqual(m['fcf'],-6)
        self.assertIn('excludes intangible',m['fcf_definition'])
        self.assertEqual(m['interest_bearing_debt_excluding_leases'],40)
        self.assertEqual(m['net_debt_excluding_leases'],0)
        self.assertEqual(m['interest_coverage'],6)
        self.assertEqual(m['current_ratio'],2.8)

    def test_roe_and_roic_are_explicit_formulae(self):
        m=model.statement_metrics(statement())
        self.assertAlmostEqual(m['roe_pct'],100/15)
        self.assertAlmostEqual(m['roic_pct'],(12*(1-2/12))/150*100)

    def test_missing_capex_or_debt_is_never_zero(self):
        p=statement()
        p['list']=[r for r in p['list'] if r['account_id'] not in model.METRICS['capex'][1] | model.DEBT_IDS[1]]
        m=model.statement_metrics(p)
        self.assertIsNone(m['fcf'])
        self.assertIsNone(m['net_debt_excluding_leases'])

    def test_exact_large_cash_flow_digits(self):
        p=statement()
        for row in p['list']:
            if row['account_id'] in model.METRICS['ocf'][1]:row['thstrm_amount']='9,007,199,254,740,993'
        self.assertEqual(model.statement_metrics(p)['ocf'],9007199254740993)

    def test_conflicting_standard_account_does_not_choose_first(self):
        p=statement(); extra=copy.deepcopy(p['list'][0]);extra['thstrm_amount']='999';p['list'].append(extra)
        self.assertIsNone(model.statement_metrics(p)['cash'])

    def test_interim_earnings_use_ytd_not_three_months(self):
        p=statement(2026,'11014',INTERIM_RECEIPT)
        for row in p['list']:
            if row['sj_div']=='IS':row['thstrm_amount']='9999'
        m=model.statement_metrics(p,interim=True)
        self.assertEqual(m['operating_profit'],12)
        self.assertEqual(m['ocf'],14)

    def test_recent_cash_slowdown_affects_quality_without_automatic_failure(self):
        annual=model.evaluate_accounts(statement(),'CFS');m=model.statement_metrics(statement())
        recent=copy.deepcopy(m);recent.update(ocf=5,previous_ocf=10,period_basis='INTERIM_YTD_CF_AND_IS_CURRENT_BS')
        interim=dict(current_ytd_operating_profit_krw=12,previous_ytd_operating_profit_krw=8)
        q=model.quality_score(m,annual,interim,recent)
        self.assertEqual(q['components']['improvement']['earned'],0)
        self.assertEqual(q['cash_quality_basis'],'INTERIM_YTD_CF_AND_IS_CURRENT_BS')
        risk=model.assess(annual,interim,m,dict(state='PASS'),'OTHER_NONFINANCIAL',recent)
        self.assertEqual(risk['state'],'PASS')
        self.assertIn('RECENT_EARNINGS_CASH_FLOW_DIVERGENCE',risk['risk_flags'])

    def test_negative_cash_flow_is_flag_not_auto_exclusion(self):
        out=self.collect(); item=out['researched'][0]
        self.assertTrue(item['financial_risk_gate_pass'])
        self.assertIn('NEGATIVE_FCF_CAPEX_OR_WORKING_CAPITAL_REVIEW',item['risk_assessment']['risk_flags'])
        self.assertEqual(select(dict(asof='20261120',candidates=[candidate()]),out)['selected_count'],1)

    def test_score_has_exact_weights_and_no_80_point_gate(self):
        item=self.collect()['researched'][0]
        self.assertEqual(sum(item['quality_100']['weights'].values()),100)
        item['quality_100']['score']=40
        self.assertEqual(financial_points(item),12)
        r=select(dict(asof='20261120',candidates=[candidate()]),evidence(item))
        self.assertEqual(r['selected_count'],1)

    def test_missing_score_feature_has_partial_coverage_not_zero(self):
        m=model.statement_metrics(statement());m['roic_pct']=None
        q=model.quality_score(m,dict(assets_krw=250,equity_krw=150),dict())
        self.assertIn('roic_pct',q['missing_features'])
        self.assertFalse(q['complete'])
        self.assertEqual(q['components']['capital_efficiency']['available'],8)

    def test_different_score_coverage_uses_common_observed_features(self):
        a=self.collect()['researched'][0];b=copy.deepcopy(a);b['ticker']='222222'
        b['quality_100']['comparison_signature'].remove('roic_pct')
        del b['quality_100']['feature_scores']['roic_pct']
        r=select(dict(asof='20261120',candidates=[candidate(),candidate('222222')]),evidence(a,b))
        self.assertEqual(r['selected_count'],2)
        self.assertNotIn('roic_pct',r['selected'][0]['financial_ranking_features'])
        self.assertEqual(r['selected'][0]['financial_ranking_score_100'],r['selected'][1]['financial_ranking_score_100'])

    def test_incomparable_or_unexplained_scores_are_not_ranked(self):
        a=self.collect()['researched'][0];b=copy.deepcopy(a);b['ticker']='222222'
        b['quality_100']['comparison_signature']=['UNEXPLAINED_METRIC']
        r=select(dict(asof='20261120',candidates=[candidate(),candidate('222222')]),evidence(a,b))
        self.assertEqual(r['decision'],'ERROR')

    def test_source_metadata_has_receipts_division_and_observation(self):
        r=self.collect(); x=r['researched'][0]
        self.assertFalse(r['point_in_time_snapshot_verified'])
        self.assertEqual(x['statement_division'],'CFS')
        self.assertEqual(x['annual_receipt_no'],ANNUAL_RECEIPT)
        self.assertTrue(all('sha256' in event for event in x['source_observations']))
        self.assertNotIn('a'*40,''.join(p.read_text() for p in Path(self.tmp.name).glob('*.json')))

    def test_future_or_restated_statement_rejected(self):
        for change in (dict(rcept_no='20261121000001'),dict(rcept_no='20260321000001'),
                       dict(bsns_year='2024'),dict(fs_div='OFS'),dict(currency='USD')):
            p=statement();p['list'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                model.validate_payload(p,'CFS',2025,'11011',ANNUAL_RECEIPT,DAY)

    def test_old_signal_rejects_future_amendment_not_just_its_label(self):
        def changed(ep,params,key):
            p=request(ep,params,key)
            if ep=='fnlttSinglAcntAll.json' and params['reprt_code']=='11011':
                for row in p['list']:row['rcept_no']='20261123000001'
            return p
        r=self.collect(changed)
        self.assertEqual(r['status'],'FAILED_FINANCIAL_EVIDENCE')
        self.assertIn('RECEIPT',r['excluded'][0]['error'])

    def test_cache_reuses_same_receipt_and_refetches_new_receipt(self):
        calls=[]
        def req(*args):calls.append(args);return dict(status='000',list=[])
        for receipt in ('20260320000001','20260320000001','20260321000001'):
            self.cache.request('accnutAdtorNmNdAdtOpinion.json',{},'secret',req,receipt)
        self.assertEqual(len(calls),2)
        self.assertEqual(self.cache.events[1]['state'],'HIT')

    def test_cache_errors_are_not_cached_or_downgraded_to_success(self):
        for _ in range(2):self.cache.request('x',{},'s',lambda *a:dict(status='020'),'r')
        self.assertEqual(list(Path(self.tmp.name).glob('*.json')),[])

    def test_cache_tampering_is_rejected(self):
        self.cache.request('x',{},'s',lambda *a:dict(status='000',list=[]),'r')
        p=next(Path(self.tmp.name).glob('*.json'));d=json.loads(p.read_text());d['payload']['list']=[1];p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'CACHE_INTEGRITY'):
            self.cache.request('x',{},'s',lambda *a:self.fail('remote'),'r')

    def test_api_failure_is_not_cash(self):
        def failed(*args):raise TimeoutError('https://example?crtfc_key=PRIVATE')
        r=self.collect(failed)
        self.assertEqual(select(dict(asof='20261120',candidates=[candidate()]),r)['decision'],'ERROR')
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_modified_audit_and_going_concern(self):
        for opinion,state in [('부적정','FAIL'),('한정의견','FAIL'),('의견거절','FAIL'),('미확인','REVIEW_REQUIRED')]:
            p=request('accnutAdtorNmNdAdtOpinion.json',{},'');p['list'][0]['adt_opinion']=opinion
            self.assertEqual(model.audit_evidence(p,2025,ANNUAL_RECEIPT)['state'],state)
        p=request('accnutAdtorNmNdAdtOpinion.json',{},'');p['list'][0]['emphs_matter']='계속기업 불확실성'
        self.assertEqual(model.audit_evidence(p,2025,ANNUAL_RECEIPT)['state'],'REVIEW_REQUIRED')

    def test_actual_dart_current_audit_duplicates_and_prior_labels(self):
        base=request('accnutAdtorNmNdAdtOpinion.json',{},'')['list'][0]
        current={**base,'bsns_year':'제43기\n(당기)'}
        prior={**base,'bsns_year':'제42기\n(전기)','adt_opinion':'의견거절'}
        p=dict(status='000',list=[current,copy.deepcopy(current),prior])
        audit=model.audit_evidence(p,2025,ANNUAL_RECEIPT)
        self.assertEqual(audit['state'],'PASS')
        self.assertEqual(audit['current_row_count'],2)
        p['list'][1]['adt_opinion']='한정의견'
        self.assertEqual(model.audit_evidence(p,2025,ANNUAL_RECEIPT)['state'],'FAIL')
        p['list']=[prior]
        self.assertEqual(model.audit_evidence(p,2025,ANNUAL_RECEIPT)['state'],'REVIEW_REQUIRED')

    def test_sector_mapping_uses_industry_not_just_company_name(self):
        for industry,expected in [('612','TELECOM'),('411','CONSTRUCTION'),('264','SEMICON_EQUIPMENT'),
            ('303','AUTO_PARTS'),('351','UTILITY'),('471','RETAIL_CONSUMER'),('211','EXCLUDED_PHARMA_BIO'),
            ('641','FINANCIAL_SPECIAL_MODEL_REQUIRED'),('', 'UNKNOWN')]:
            self.assertEqual(model.sector_profile(industry),expected)

    def test_construction_notes_and_finance_never_assumed_safe(self):
        x=self.collect()['researched'][0]
        for sector in ['CONSTRUCTION','FINANCIAL_SPECIAL_MODEL_REQUIRED','UNKNOWN']:
            r=model.assess(dict(equity_krw=150,liabilities_krw=100,operating_profit_krw=12,assets_krw=250),{},x['metrics'],dict(state='PASS'),sector)
            self.assertEqual(r['state'],'REVIEW_REQUIRED')

    def test_300pct_boundary_is_unchanged(self):
        x=self.collect()['researched'][0]
        for liabilities,state in [(450,'PASS'),(451,'FAIL')]:
            r=model.assess(dict(equity_krw=150,liabilities_krw=liabilities,operating_profit_krw=12,assets_krw=600),{},x['metrics'],dict(state='PASS'),'OTHER_NONFINANCIAL')
            self.assertEqual(r['state'],state)
        self.assertFalse(r['leverage_policy_changed'])

    def test_low_liquidity_needs_mitigants_review(self):
        x=self.collect()['researched'][0];x['metrics']['current_ratio']=.8
        r=model.assess(dict(equity_krw=150,liabilities_krw=100,operating_profit_krw=12,assets_krw=250),{},x['metrics'],dict(state='PASS'),'OTHER_NONFINANCIAL')
        self.assertEqual(r['state'],'REVIEW_REQUIRED')

    def test_turnaround_and_persistent_losses_are_different(self):
        m=model.statement_metrics(statement())
        annual=dict(equity_krw=150,liabilities_krw=100,assets_krw=250,
                    operating_profit_krw=-10,previous_operating_profit_krw=-8)
        for current,expected in [(12,'PASS'),(-2,'FAIL')]:
            risk=model.assess(annual,dict(current_ytd_operating_profit_krw=current),m,dict(state='PASS'),'OTHER_NONFINANCIAL')
            self.assertEqual(risk['state'],expected)
        annual['previous_operating_profit_krw']=8
        risk=model.assess(annual,dict(current_ytd_operating_profit_krw=-2),m,dict(state='PASS'),'OTHER_NONFINANCIAL')
        self.assertEqual(risk['state'],'REVIEW_REQUIRED')

    def test_no_candidates_is_distinct_from_missing_key(self):
        r=model.collect_balanced(DAY,[],'a'*40,DAY,self.cache)
        self.assertEqual(r['status'],'NO_CANDIDATES')

    def test_paginated_filings_are_requested_until_complete(self):
        pages=[]
        def paged(ep,params,key):
            if ep!='list.json':return request(ep,params,key)
            pages.append(params['page_no']);r=request(ep,params,key);r['total_page']=2
            if params['page_no']==1:r['list']=[]
            return r
        self.assertTrue(self.collect(paged)['financial_data_complete'])
        self.assertEqual(pages,[1,2])

    def test_read_only_duplicate_signals_counts_actual_sessions(self):
        root=Path(self.tmp.name);receipts=root/'receipts';receipts.mkdir()
        (receipts/'a.json').write_text(json.dumps(dict(asof='20261119',selected_codes=['111111'])))
        ledger=root/'ledger.json';ledger.write_text(json.dumps(dict(positions={'x':dict(plan=dict(selection_date='2026-11-18',ticker='222222'))})))
        before=ledger.read_bytes()
        blocked=recent_signals('20261120',['20261118','20261119','20261120'],receipts,ledger)
        self.assertEqual(blocked,{'111111','222222'})
        self.assertEqual(ledger.read_bytes(),before)

    def test_live_validation_reuses_production_calculation(self):
        code=embedded('Collect KRX sessions and render one classic image per stock')
        self.assertIn('C3_KRX_SOURCE_PREFLIGHT',code)
        self.assertNotIn('sendPhoto',code)

    def test_positive_balanced_png_csv_and_real_delivery_boundary(self):
        # Synthetic financial evidence and bars, clearly an offline contract
        # test; never counted as actual KRX/DART or a selected operating stock.
        from c3_balanced_validation import run, write
        root=Path(self.tmp.name);source=root/'source';source.mkdir()
        c=candidate()
        end=datetime(2026,11,20)
        c['bars']=[dict(date=(end-timedelta(days=59-i)).strftime('%Y%m%d'),
            open=9800,high=10100,low=9700,close=9900,volume=10000+i*100) for i in range(60)]
        expiry='2026-11-23T15:30:00+09:00'
        write(source/'receipt.json',dict(asof='20261120',status='PRE_FINANCIAL_TECHNICAL_PREVIEW_NO_SEND',
            entry_valid_until=expiry,source_integrity=dict(session_count=60,last_session='20261120',
                market_rows_min=dict(KOSPI=935,KOSDAQ=1836))))
        write(source/'entry_geometry_audit.json',dict(asof='20261120',candidates=[c]))
        write(source/'qualified_chart_pool.json',dict(asof='20261120',entry_valid_until=expiry,candidates=[c]))
        financial=self.collect()
        with patch('c3_balanced_validation.collect_balanced',return_value=financial):
            result=run(root/'result',root/'unused-cache',source=source)
        self.assertEqual(result['status'],'COMPLETE',result)
        self.assertEqual(result['final_png_count'],1)
        self.assertEqual(result['delivery_status'],'DRY_RUN')
        self.assertEqual(result['telegram_photos_sent'],0)
        import csv
        with (root/'result/top5.csv').open(encoding='utf-8-sig') as stream: rows=list(csv.DictReader(stream))
        self.assertEqual(rows[0]['code'],'111111')
        self.assertEqual(float(rows[0]['stop_ref']),9600)


if __name__=='__main__':unittest.main()
