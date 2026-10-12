import unittest
import krx_preignition_integrated_v90 as m

class IntegratedBacktestTests(unittest.TestCase):
    def test_filing_not_known_on_same_day(self):
        rows=[{'ticker':'000001','filing_date':'2026-04-01','available_date':'2026-04-02',
               'revenue_yoy_pct':'15','op_profit_yoy_pct':'20','op_margin_pct':'8','debt_ratio_pct':'50','receipt_no':'20260401000001'}]
        f,reject=m.build_filings(rows)
        self.assertIsNone(m.asof_financial(f,'000001','2026-04-01'))
        self.assertTrue(m.fin_pass(m.asof_financial(f,'000001','2026-04-02')))
    def test_reject_filing_same_day_as_release(self):
        f,r=m.build_filings([{'ticker':'000001','filing_date':'2026-04-02','available_date':'2026-04-02',
                         'revenue_yoy_pct':'5','op_profit_yoy_pct':'8','op_margin_pct':'5','debt_ratio_pct':'100','receipt_no':'20260402000001'}])
        self.assertFalse(f);self.assertEqual(r['INVALID_FILING_OR_TIMING'],1)
    def test_reject_financial_negative_or_debt(self):
        ff=m.Filing('000001','2026-04-01','2026-04-02',10,-1,5,50,'r')
        self.assertFalse(m.fin_pass(ff))
        ff=m.Filing('000001','2026-04-01','2026-04-02',10,10,5,250,'r')
        self.assertFalse(m.fin_pass(ff))
    def test_membership_never_backfill(self):
        rr=[{'ticker':'000001','sector':'반도체','valid_from':'2025-01-01','available_date':'2026-04-02',
              'valid_to':'','source':'20260402 original dated evidence','verified':'true'}]
        mm,_=m.build_memberships(rr)
        self.assertIsNone(m.asof_membership(mm,'000001','2026-04-01'))
        self.assertEqual(m.asof_membership(mm,'000001','2026-04-02').sector,'반도체')
    def test_unverified_membership_blocked(self):
        rr=[{'ticker':'000001','sector':'IT','valid_from':'2025-01-01','available_date':'2025-01-01',
              'valid_to':'','source':'new snapshot','verified':'false'}]
        mm,rej=m.build_memberships(rr)
        self.assertIsNone(m.asof_membership(mm,'000001','2026-01-01'))
        self.assertEqual(rej['UNVERIFIED_CLASSIFICATION'],1)
    def test_entry_next_session_not_signal_close(self):
        b=[{'date':'2026-01-01','o':100,'h':102,'l':99,'c':100,'v':100},
           {'date':'2026-01-02','o':103,'h':104,'l':102,'c':103,'v':100}]
        s={'stop':95,'no_chase_above':106,'ideal_buy_high':100,'atr14':2}
        e,status=m.plan_entry(b,0,s,'E2_NEXT_OPEN')
        self.assertEqual(e,(1,103))
        e,status=m.plan_entry(b,0,s,'E3_NEXT_CLOSE_PROXY')
        self.assertEqual(e,(1,103))
    def test_no_chase_gap_canceled(self):
        b=[{'date':'2026-01-01','o':100,'h':101,'l':99,'c':100,'v':1},
           {'date':'2026-01-02','o':120,'h':125,'l':118,'c':121,'v':1}]
        s={'stop':95,'no_chase_above':106,'ideal_buy_high':99,'atr14':2}
        self.assertIsNone(m.plan_entry(b,0,s,'E2_NEXT_OPEN')[0])
    def test_both_target_and_stop_same_bar_means_stop_first(self):
        b=[{'date':'2026-01-01','o':100,'h':111,'l':94,'c':105,'v':100}]
        tr,status=m.simulate_exit(b,0,100,95,'E2_NEXT_OPEN','X10_FULL',hold=1,cost_bps=35)
        self.assertEqual(status,'CLOSED')
        self.assertEqual(tr['exit_reason'],'STOP_FIRST')
        self.assertFalse(tr['hit10_before_stop'])
    def test_close_entry_does_not_use_same_session_low_high(self):
        b=[{'date':'2026-01-01','o':100,'h':120,'l':80,'c':100,'v':100},
           {'date':'2026-01-02','o':102,'h':103,'l':100,'c':102,'v':100}]
        tr,status=m.simulate_exit(b,0,100,95,'E3_NEXT_CLOSE_PROXY','X10_FULL',hold=2,cost_bps=35)
        self.assertEqual(tr['exit_reason'],'TIME')
    def test_future_bar_required(self):
        b=[{'date':'2026-01-01','o':100,'h':100,'l':100,'c':100,'v':100}]
        self.assertEqual(m.simulate_exit(b,0,100,95,'E2_NEXT_OPEN','X10_FULL',hold=2)[1],'PENDING_FUTURE')
    def test_sector_gate_uses_only_dated_member_prices(self):
        from datetime import date,timedelta
        start=date(2026,1,1)
        bars={};rows=[]
        for n in range(15):
            ticker=f'{n+1:06d}'; is_leader=n<4
            bb=[]
            for j in range(45):
                price=100*(1.016**j if is_leader else 1.0)
                bb.append({'date':str(start+timedelta(days=j)),'o':price,'h':price*1.01,'l':price*.99,'c':price,
                           'v':1000*(1.020**j if is_leader else 1.0)})
            bars[ticker]=bb
            if is_leader:rows.append({'ticker':ticker,'sector':'반도체','valid_from':'2026-01-01',
                                      'available_date':'2026-01-01','valid_to':'','source':'archived dated sector list','verified':'true'})
        mem,rej=m.build_memberships(rows)
        ix,benchmark=m.calc_market_per_date(bars)
        d=bars['000001'][35]['date']
        v,status=m.sector_gate('000001',d,mem,bars,ix,benchmark,{})
        self.assertEqual(status,'OK')
        self.assertGreater(v['sector_excess5_pp'],1.5)
        self.assertGreater(v['sector_turnover_accel'],1.05)
        # Despite identical price history, a source only known in the future must not pass.
        future_rows=[{**row,'available_date':'2026-03-01'} for row in rows]
        future,_=m.build_memberships(future_rows)
        v,status=m.sector_gate('000001',d,future,bars,ix,benchmark,{})
        self.assertEqual(status,'MISSING_ASOF_SECTOR')
    def test_scorecard_empty_ok(self):
        self.assertEqual(m.scorecard([]),[])

if __name__=='__main__':unittest.main()
