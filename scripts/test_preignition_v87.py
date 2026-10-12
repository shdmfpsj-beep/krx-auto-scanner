import unittest,sys,copy,io,datetime,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import krx_preignition_v87 as v

class PreIgnitionTests(unittest.TestCase):
    def bars(self,n=125):
        d=datetime.date(2025,1,1)
        out=[]
        for j in range(n):
            c=100+.06*j+.7*(j%7)/7
            out.append({'date':str(d+datetime.timedelta(days=j)),'o':c,'h':c+1,'l':c-1,'c':c,'v':10000+50*(j%7)})
        return out
    def s(self):
        return {'ticker':'000001','signal_date':'2025-04-21','subtype':'E_TREND_BASE','score':81,
                'signal_close':100,'atr14':2.0,'stop':97.0,'ideal_buy_low':98.5,
                'ideal_buy_high':99.4,'no_chase_above':101,'resistance':102}
    def test_all_entries_are_after_signal(self):
        b=self.bars(125);s=self.s()
        for mode in v.MODES:
            z,status=v.entry(b,111,s,mode)
            if z:self.assertGreater(z[0],111)
    def test_no_chase_next_open(self):
        b=self.bars();b[112].update(o=105,h=106,l=104,c=105)
        z,status=v.entry(b,111,self.s(),'E2_NEXT_OPEN')
        self.assertIsNone(z);self.assertEqual(status,'GAP_CHASE_CANCELED')
    def test_limit_needs_trade_through(self):
        b=self.bars();b[112].update(o=100,h=101,l=99.39,c=100)
        b[113].update(o=100,h=101,l=99.34,c=100)
        z,status=v.entry(b,111,self.s(),'E1_LIMIT_2D')
        self.assertEqual(status,'FILLED');self.assertEqual(z[0],113);self.assertEqual(z[1],99.4)
    def test_auction_proxy_excludes_entry_day_target(self):
        b=self.bars()
        for i in range(110,120):b[i].update(o=100,h=102,l=98.5,c=100)
        b[112].update(o=100,h=113,l=97.5,c=100)
        t,status=v.simulate(b,111,self.s(),'E3_NEXT_CLOSE_AUCTION_PROXY',5,35)
        self.assertEqual(status,'CLOSED');self.assertEqual(t['target1_before_stop'],0)
    def test_same_day_stop_prioritized(self):
        b=self.bars()
        for i in range(110,120):b[i].update(o=100,h=102,l=98.5,c=100)
        b[112].update(o=100,h=110,l=96,c=99)
        t,status=v.simulate(b,111,self.s(),'E2_NEXT_OPEN',5,35)
        self.assertEqual(status,'CLOSED');self.assertEqual(t['exit_reason'],'STOP_FIRST');self.assertEqual(t['target1_before_stop'],0)
    def test_no_future_data_in_candidate(self):
        b=self.bars(145);i=115
        a=v.signal('000001',b[:i+1],i)
        x=copy.deepcopy(b)
        for row in x[i+1:]:row.update(o=300,h=400,l=200,c=350,v=9e8)
        self.assertEqual(a,v.signal('000001',x,i))
    def test_invalid_ohlc_rejected(self):
        b=self.bars()
        b[2]['h']=1
        inp=io.StringIO();w=csv.DictWriter(inp,fieldnames=['Date','Open','High','Low','Close','Volume']);w.writeheader()
        for x in b:w.writerow({'Date':x['date'],'Open':x['o'],'High':x['h'],'Low':x['l'],'Close':x['c'],'Volume':x['v']})
        _,status=v.decode_rows(inp.getvalue().encode())
        self.assertEqual(status,'INVALID_OHLCV')
    def test_unfinished_trade_pending(self):
        b=self.bars(125)
        s=self.s();s['no_chase_above']=110;s['stop']=104
        t,status=v.simulate(b,123,s,'E2_NEXT_OPEN',5,35)
        self.assertIsNone(t);self.assertEqual(status,'PENDING_OUTCOME')

if __name__=='__main__': unittest.main()
