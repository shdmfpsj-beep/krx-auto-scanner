"""Rendering and dated-fact faults, not simulated trading-performance evidence."""
import copy,json,tempfile,unittest,time
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from datetime import datetime,timezone
import requests
from c3_classic_theme import validate_bars,moving_average,audit_averages,chart_geometry,notes,create_cards,MA_COLORS
from PIL import Image,ImageColor
from c3_report_context import publication_ok,parse_statement,quarter_series,attach_context,DartClient,digest


def bars():
    start=date(2026,6,1)
    return [{'date':(start+timedelta(days=i)).isoformat(),'open':100+i,'high':105+i,'low':95+i,'close':102+i,'volume':0 if i==89 else 1000,'turnover_krw':(102+i)*1000} for i in range(91)]


def accounts(receipt='20260814003849',year=2026,code='11012'):
    common={'rcept_no':receipt,'bsns_year':str(year),'reprt_code':code,'currency':'KRW','fs_div':'CFS'}
    return [{**common,'sj_div':'IS','account_id':'ifrs-full_Revenue','account_nm':'매출액','thstrm_amount':'120','thstrm_add_amount':'220','frmtrm_q_amount':'100'},
        {**common,'sj_div':'IS','account_id':'dart_OperatingIncomeLoss','account_nm':'영업이익','thstrm_amount':'12','thstrm_add_amount':'15','frmtrm_q_amount':'-2'},
        {**common,'sj_div':'CF','account_id':'ifrs-full_CashFlowsFromUsedInOperatingActivities','account_nm':'영업활동현금흐름','thstrm_amount':'30'}]


class ChartQualityTests(unittest.TestCase):
    def setUp(self):self.bars=bars();self.row={'ticker':'000001','close':192,'reference_close':192}
    def test_chart_shows_sixty_actual_candles_with_full_ma_warmup(self):
        from c3_classic_theme import VISIBLE_SESSIONS
        self.assertEqual(VISIBLE_SESSIONS,60)
        g,av=chart_geometry(self.bars,self.row,None)
        self.assertEqual(len(self.bars)-g['offset'],60)
        self.assertEqual(g['paths']['5'][0]['date'],self.bars[-60]['date'])
        self.assertEqual(g['paths']['20'][0]['date'],self.bars[-60]['date'])
        self.assertEqual(g['paths']['60'][0]['date'],self.bars[-60]['date'])
        self.assertEqual(g['paths']['60'][-1]['date'],self.bars[-1]['date'])
        self.assertEqual(g['last_candle_x'],g['paths']['60'][-1]['x'])

    def test_actual_last_candle_and_all_ma_paths_end_together(self):
        g,av=chart_geometry(self.bars,self.row,None)
        for n,path in g['paths'].items():
            self.assertEqual(path[-1]['date'],self.bars[-1]['date'])
            self.assertEqual(path[-1]['x'],g['last_candle_x'])
            self.assertTrue(all(p['x']<=g['last_candle_x'] for p in path))
        self.assertEqual(g['endpoint_label_style'],'STRAIGHT_PRICE_BADGE_NO_LEADER_POLYLINE')
    def test_independent_audit_rejects_displaced_index_and_fake_last_ma(self):
        for error in ('shift','extra','zero','missing'):
            av={n:moving_average(self.bars,n) for n in (5,20,60)}
            if error=='shift':av[5][-1]=av[5][-2]
            elif error=='extra':av[5].append(av[5][-1])
            elif error=='zero':av[5][-1]=0
            else:av[5][-1]=None
            with self.assertRaises(ValueError):audit_averages(self.bars,av)
    def test_last_five_ma_have_independent_known_arithmetic_means(self):
        av={n:moving_average(self.bars,n) for n in (5,20,60)};audit=audit_averages(self.bars,av)
        self.assertEqual(audit['5']['last5'],[186,187,188,189,190])
        self.assertEqual(audit['20']['last5'],[178.5,179.5,180.5,181.5,182.5])
    def test_duplicate_or_missing_last_date_rejected(self):
        for mode in ('duplicate','missing'):
            sample=copy.deepcopy(self.bars)
            if mode=='duplicate':sample[-1]['date']=sample[-2]['date']
            else:sample=sample[:-1]
            with self.assertRaisesRegex(ValueError,'DATE'):validate_bars(sample,self.bars[-1]['date'],192)
    def test_zero_volume_is_valid_but_zero_price_is_rejected(self):
        self.assertEqual(validate_bars(self.bars,self.bars[-1]['date'],192)[-2]['volume'],0)
        self.bars[-1]['close']=0
        with self.assertRaisesRegex(ValueError,'OHLCV'):validate_bars(self.bars,self.bars[-1]['date'],0)
    def test_price_axis_encloses_every_level_without_moving_labels(self):
        p={'low':150,'high':151,'stop':99,'resistance':193,'resistance2':999}
        g,_=chart_geometry(self.bars,self.row,p)
        for _,v,_ in g['levels']:self.assertTrue(g['axis_min']<=v<=g['axis_max'])
        self.assertEqual([v for _,v,_ in g['levels']],[192.,151,150,99,193,999])
    def test_mixed_adjustment_or_unresolved_action_is_rejected(self):
        for key,value in [('price_basis','ADJUSTED'),('corporate_action_unresolved',True),('segment',1)]:
            rows=copy.deepcopy(self.bars)
            for r in rows:r['segment']=0
            rows[-1][key]=value
            with self.assertRaisesRegex(ValueError,'BASIS|SEGMENT'):validate_bars(rows,rows[-1]['date'],192)
    def test_nonfinite_turnover_is_rejected(self):
        self.bars[-1]['turnover_krw']=float('nan')
        with self.assertRaisesRegex(ValueError,'TURNOVER'):validate_bars(self.bars,self.bars[-1]['date'],192)
    def test_render_has_no_ma_pixels_beyond_last_candle_or_clipped_reason_text(self):
        rows=copy.deepcopy(self.bars)
        for r in rows:r['volume']=0
        report={'source_price_asof':rows[-1]['date'],'research_top2':[dict(self.row,ticker=t,name='SYNTHETIC',chart_bars=rows,chart_price_basis='KRX_UNADJUSTED_AS_TRADED') for t in ('000001','000002')]}
        with tempfile.TemporaryDirectory() as tmp:
            paths=create_cards(report,tmp);diag=json.loads(Path(tmp,'render_diagnostics.json').read_text())
            colors={ImageColor.getrgb(c) for c in MA_COLORS.values()}
            for path,d in zip(paths,diag['cards']):
                with Image.open(path) as im:
                    x=int(d['geometry']['last_candle_x'])+6
                    pixels=im.crop((x,392,1348,1016)).tobytes()
                    self.assertFalse(colors & set(zip(pixels[::3],pixels[1::3],pixels[2::3])))
                    self.assertEqual(im.size,(1400,2400))
                self.assertEqual(d['visible_rows'],60)
                self.assertEqual(d['visible_first_date'],rows[-60]['date'])
                self.assertEqual(d['visible_last_date'],rows[-1]['date'])
                self.assertTrue(all(x['lines']<=3 and x['text_right_max']<=1002 for x in d['layout']))


class DatedContextTests(unittest.TestCase):
    def setUp(self):self.filings=[{'rcept_no':'20260814003849','rcept_dt':'20260814'}]
    def test_three_month_profit_is_not_half_year_total_and_loss_base_has_no_fake_yoy(self):
        p=parse_statement(accounts(),2026,'11012',self.filings,'2026-11-05');q=quarter_series([p])[0]
        self.assertEqual(q['revenue_krw'],120);self.assertAlmostEqual(q['revenue_yoy_pct'],20)
        self.assertEqual(q['operating_profit_krw'],12);self.assertIsNone(q['operating_profit_yoy_pct'])
        self.assertEqual(q['profit_transition'],'LOSS_TO_PROFIT');self.assertEqual(p['operating_cashflow_ytd_krw'],30)
    def test_annual_report_cannot_be_mislabeled_as_fourth_quarter(self):
        p=parse_statement(accounts(year=2025,code='11011'),2025,'11011',self.filings,'2026-11-05')
        self.assertEqual(quarter_series([p]),[])
    def test_fourth_quarter_needs_same_year_nine_month_values(self):
        p=parse_statement(accounts(year=2025,code='11011'),2025,'11011',self.filings,'2026-11-05')
        q3=copy.deepcopy(p);q3.update(report_code='11014',period='2025.3Q');q3['revenue']['ytd_krw']=100;q3['operating_profit']['ytd_krw']=10
        q=next(q for q in quarter_series([p,q3]) if q['period']=='2025.4Q')
        self.assertEqual(q['revenue_krw'],20);self.assertEqual(q['operating_profit_krw'],2)
    def test_unlisted_future_restated_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError,'RECEIPT'):parse_statement(accounts('20261116000001'),2026,'11012',self.filings,'2026-11-05')
    def test_standalone_currency_and_ambiguous_metrics_rejected(self):
        for mode in ('standalone','currency','duplicate'):
            rows=accounts()
            if mode=='standalone':rows[0]['fs_div']='OFS'
            elif mode=='currency':rows[0]['currency']='USD'
            else:rows.append(dict(rows[0],thstrm_amount='999'))
            with self.assertRaises(ValueError):parse_statement(rows,2026,'11012',self.filings,'2026-11-05')
    def test_future_and_date_only_same_day_news_do_not_become_historical_reasons(self):
        self.assertTrue(publication_ok({'published_on':'2026-10-22'},'2026-11-05',28))
        self.assertFalse(publication_ok({'published_on':'2026-11-05'},'2026-11-05'))
        self.assertFalse(publication_ok({'published_on':'2026-11-06'},'2026-11-05'))
    def test_enrichment_preserves_selection_prices_and_rank(self):
        report={'source_price_asof':'2026-11-05','research_top2':[{'ticker':'028050','model':'B','rank':1,'score':99,'close':64300,'entry_plans':{'A':'SYNTHETIC_UNCHANGED'}}]}
        before=copy.deepcopy(report['research_top2'])
        with tempfile.TemporaryDirectory() as tmp:
            attach_context(report,tmp)
            out=json.loads(Path(tmp,'company_context.json').read_text())
        self.assertEqual([{k:v for k,v in r.items() if k!='company_context'} for r in report['research_top2']],before)
        self.assertEqual(out['selection_hash_before'],out['selection_hash_after'])
        self.assertEqual(report['research_top2'][0]['company_context']['selection_use'],'POST_SELECTION_ONLY')
    def test_official_quarter_not_future_estimate(self):
        report={'source_price_asof':'2026-10-21','research_top2':[{'ticker':'028050'}]}
        with tempfile.TemporaryDirectory() as tmp:attach_context(report,tmp)
        self.assertNotIn('2026.3Q',[q['period'] for q in report['research_top2'][0]['company_context']['quarters']])
    def test_transport_failure_cannot_expose_secret_url(self):
        session=Mock();session.get.side_effect=requests.RequestException('https://host/?crtfc_key=SYNTHETIC_SECRET')
        with tempfile.TemporaryDirectory() as tmp:
            c=DartClient('SYNTHETIC_SECRET',tmp,session)
            with self.assertRaisesRegex(ValueError,'DART_CONTEXT_TRANSPORT_FAILURE') as exc:c.fetch('list.json',{})
            self.assertNotIn('SYNTHETIC_SECRET',str(exc.exception));self.assertEqual(c.audit,[])
    def test_budget_prevents_whole_market_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=DartClient('SYNTHETIC_SECRET',tmp,Mock());c.requests=28
            with self.assertRaisesRegex(ValueError,'BUDGET'):c.fetch('list.json',{})
            c.session.get.assert_not_called()
    def test_public_mapping_cache_avoids_another_full_corporation_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'mapping.json');mapping={'000001':'00123456'}
            path.write_text(json.dumps({'mapping':mapping,'sha256':digest(mapping),'collected_at':datetime.now(timezone.utc).isoformat()}))
            c=DartClient('SYNTHETIC_SECRET',tmp,Mock())
            with patch.dict('os.environ',{'C3_DART_CORP_CACHE':str(path)}):self.assertEqual(c.mapping(),mapping)
            c.session.get.assert_not_called()
    def test_slow_cold_mapping_does_not_prevent_the_financial_phase(self):
        class SlowMapping:
            audit=[]
            def mapping(self):self.started=time.monotonic()-300;return {'000001':'00123456'}
            def company(self,*args):
                if time.monotonic()-self.started>180:raise ValueError('DART_REPORT_CONTEXT_REQUEST_BUDGET')
                return {'status':'COLLECTED','quarters':[],'periodic_statements':[],'recent_disclosures':[]}
        report={'source_price_asof':'2026-11-05','research_top2':[{'ticker':'000001'}]}
        with tempfile.TemporaryDirectory() as tmp:attach_context(report,tmp,SlowMapping())
        self.assertEqual(report['research_top2'][0]['company_context']['dart_status'],'COLLECTED')


if __name__=='__main__':unittest.main()
