import datetime
import io
import unittest
import zipfile

import c3_monthly_202611 as monthly
from c3_monthly_xbrl import parse_archive, payload_for


class TradeTests(unittest.TestCase):
    def trade(self, bars, **changes):
        signal=dict(signal_date='20261102',code='000001',entry_low=100,
                    entry_high=105,stop_ref=96)
        signal.update(changes)
        quotes={(day,'000001'):dict(zip(('open','high','low','close'),bar))
                for day,bar in bars.items()}
        return monthly.evaluate_trade(signal,['20261102','20261103','20261104','20261120'],quotes)

    def test_next_session_only_no_late_fill(self):
        r=self.trade({'20261103':(110,115,106,112),'20261104':(104,108,100,106)})
        self.assertEqual(r['fill_status'],'PASS')

    def test_signal_on_evaluation_day_is_pending(self):
        self.assertEqual(self.trade({},signal_date='20261120')['fill_status'],
                         'PENDING_AFTER_EVALUATION')

    def test_stop_realized_and_high_after_stop_excluded(self):
        r=self.trade({'20261103':(102,104,100,103),'20261104':(103,120,95,97),
                      '20261120':(130,140,129,135)})
        self.assertEqual(r['exit_price'],96)
        self.assertAlmostEqual(r['current_return_pct'],(96/102-1)*100,places=3)
        self.assertEqual(r['highest_return_pct'],round((104/102-1)*100,4))
        self.assertTrue(r['peak_uncertain'])

    def test_high_before_pullback_not_claimed(self):
        r=self.trade({'20261103':(110,120,103,106),'20261104':(106,108,104,107),
                      '20261120':(107,109,106,108)})
        self.assertEqual(r['fill_price'],105)
        self.assertEqual(r['highest_day'],'20261120')
        self.assertEqual(r['possible_highest_day'],'20261103')

    def test_rebound_with_same_bar_stop_is_uncertain(self):
        r=self.trade({'20261103':(98,105,95,102),'20261120':(107,109,106,108)})
        self.assertTrue(r['sequence_uncertain'])
        self.assertEqual(r['fill_status'],'STOPPED')

    def test_gap_below_stop_does_not_enter(self):
        self.assertEqual(self.trade({'20261103':(95,108,94,106)})['fill_status'],
                         'PASS_GAP_BELOW_STOP')

    def test_later_gap_stop_at_open(self):
        r=self.trade({'20261103':(102,104,100,103),'20261104':(90,95,89,92),
                      '20261120':(107,109,106,108)})
        self.assertEqual(r['exit_price'],90)


class OriginalTests(unittest.TestCase):
    def original(self, members='', duplicate='', default=False):
        instance='''<xbrl xmlns="http://www.xbrl.org/2003/instance"
          xmlns:i="http://www.xbrl.org/2003/instance"
          xmlns:d="http://xbrl.org/2006/xbrldi" xmlns:ifrs="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full">
          <context id="now"><entity><identifier scheme="test">x</identifier>MEMBERS</entity>
            <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
          <unit id="won"><measure>iso4217:KRW</measure></unit>
          <ifrs:Revenue contextRef="now" unitRef="won">123456789012345678</ifrs:Revenue>DUPLICATE</xbrl>'''
        instance=instance.replace('MEMBERS',members).replace('DUPLICATE',duplicate)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('file.xbrl',instance)
            if default:
                z.writestr('file_def.xml','''<linkbase xmlns:x="http://www.w3.org/1999/xlink"><definitionLink>
                  <loc x:label="axis" x:href="tax#ConsolidatedAndSeparateFinancialStatementsAxis"/>
                  <loc x:label="member" x:href="tax#ConsolidatedMember"/>
                  <definitionArc x:arcrole="http://xbrl.org/int/dim/arcrole/dimension-default" x:from="axis" x:to="member"/>
                  </definitionLink></linkbase>''')
        return stream.getvalue()

    def test_actual_default_scope_and_exact_digits(self):
        facts,_=parse_archive(self.original(default=True))
        p=payload_for(facts,2025,'11011','CFS','20260331000001')
        self.assertEqual(p['list'][0]['thstrm_amount'],'123456789012345678')

    def test_unknown_scope_fails_closed(self):
        facts,_=parse_archive(self.original())
        self.assertEqual(facts,{})

    def test_conflicting_original_facts_do_not_choose_one(self):
        duplicate='<ifrs:Revenue contextRef="now" unitRef="won">999</ifrs:Revenue>'
        facts,_=parse_archive(self.original(duplicate=duplicate,default=True))
        self.assertEqual(payload_for(facts,2025,'11011','CFS','20260331000001')['list'][0]['thstrm_amount'],'')

    def test_future_amendment_does_not_replace_original(self):
        source=monthly.Sources.__new__(monthly.Sources)
        source.filings=lambda corp:dict(status='000',list=[
            dict(report_nm='사업보고서 (2025.12)',rcept_dt='20260331',rcept_no='20260331000001'),
            dict(report_nm='[기재정정]사업보고서 (2025.12)',rcept_dt='20261119',rcept_no='20261119000001')])
        self.assertEqual(source.receipt('corp',2025,'11011',datetime.date(2026,11,2)),
                         '20260331000001')

    def test_same_production_ast_extracts_without_image_execution(self):
        self.assertEqual(len(monthly.code_nodes()),3)


if __name__=='__main__':
    unittest.main()
