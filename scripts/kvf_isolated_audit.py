"""C3 KVF isolated research. No trading, no workflow modification.
Run: python scripts/kvf_isolated_audit.py --tickers 271560 026960 --end 2026-10-30
Requires FinanceDataReader, pandas, numpy. Prices are downloaded when run.
"""
import argparse, json
import numpy as np
import pandas as pd

def kalman_logvolume(volume, q=0.05, r=1.0):
    obs=np.log1p(np.asarray(volume,dtype=float))
    state=float(obs[0]); var=1.0; out=[]
    for z in obs:
        var+=q
        gain=var/(var+r)
        state+=gain*(z-state)
        var=(1-gain)*var
        out.append(state)
    return pd.Series(out)

def signals(raw):
    x=raw.copy().sort_index()
    if len(x)<150: return None
    v=x['Volume'].astype(float)
    x['ma20']=x.Close.rolling(20).mean()
    x['prevhigh20']=x.High.shift(1).rolling(20).max()
    x['rvol']=v/v.shift(1).rolling(20).mean()
    base=(x.Close>x.Open)&(x.Close>x.ma20)&(x.Close>x.prevhigh20)&(x.rvol>=1.0)
    ema=np.log1p(v).ewm(span=10,adjust=False).mean()
    kvf=kalman_logvolume(v).set_axis(x.index)
    x['base']=base
    x['ema']=base&(ema>ema.shift(1))&(ema.shift(1)>ema.shift(2))
    x['kvf']=base&(kvf>kvf.shift(1))&(kvf.shift(1)>kvf.shift(2))
    return x

def audit_one(ticker, raw, train_end='2024-12-31'):
    x=signals(raw)
    if x is None:return {'ticker':ticker,'error':'insufficient_bars'}
    rows=[]
    for i in range(125,len(x)-21):
        if not bool(x.base.iloc[i]):continue
        entry=float(x.Open.iloc[i+1])
        if not np.isfinite(entry) or entry<=0:continue
        date=str(x.index[i].date())
        for h in (5,10,20):
            exit_price=float(x.Close.iloc[i+h])
            net=exit_price*(1-0.005)/(entry*(1+0.0015))-1
            for strategy in ('base','ema','kvf'):
                rows.append({'ticker':ticker,'date':date,'split':'train' if date<=train_end else 'holdout','horizon':h,'strategy':strategy,'accepted':bool(x[strategy].iloc[i]),'net_return':net})
    return rows

def summarize(rows):
    df=pd.DataFrame(rows)
    if df.empty:return []
    out=[]
    for (split,h,strategy),g in df.groupby(['split','horizon','strategy']):
        sel=g[g.accepted]
        rejected=g[~g.accepted]
        out.append({'split':split,'horizon':int(h),'strategy':strategy,
                    'candidates':int(len(g)),'accepted':int(len(sel)),
                    'missed_positive':int((rejected.net_return>0).sum()),
                    'avoided_negative':int((rejected.net_return<0).sum()),
                    'mean_net_return':float(sel.net_return.mean()) if len(sel) else None,
                    'win_rate':float((sel.net_return>0).mean()) if len(sel) else None})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tickers',nargs='+',required=True)
    p.add_argument('--start',default='2022-01-01')
    p.add_argument('--end',required=True)
    p.add_argument('--output',default='kvf_isolated_results.json')
    a=p.parse_args()
    import FinanceDataReader as fdr
    rows=[]; failures=[]
    end=(pd.Timestamp(a.end)+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for ticker in a.tickers:
        try:
            raw=fdr.DataReader(ticker,a.start,end)
            result=audit_one(ticker,raw)
            if isinstance(result,list):rows+=result
            else:failures.append(result)
        except Exception as exc:failures.append({'ticker':ticker,'error':type(exc).__name__})
    result={'source':'FinanceDataReader','asof_requested':a.end,'train_end':'2024-12-31',
            'method':'next_open_entry_fixed_horizon_close_exit; costs 0.15% buy, 0.50% sell',
            'limitation':'not structural-stop or resistance exits; current listing survival bias possible',
            'trade_approved':False,'observations':len(rows),'failures':failures,'summary':summarize(rows)}
    with open(a.output,'w',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
