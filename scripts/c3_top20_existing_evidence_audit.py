"""As-of-safe coverage audit of existing historical OHLCV and DART snapshots for C3 TOP20.

This does not certify adjusted price consistency, regular-session turnover, or
provisional OpenDART snapshots. All outputs are read-only research diagnostics.
"""
import csv,json,math
from collections import defaultdict
from datetime import date
from pathlib import Path

def load_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def inspect(snapshot,histories,financials):
    asof=snapshot['asof'];rows=snapshot['candidates']
    codes={r['ticker'] for r in rows}
    bars=defaultdict(list);filings=defaultdict(list)
    for r in histories:
        if r.get('ticker') in codes and r.get('date','')<=asof:
            bars[r['ticker']].append(r)
    for r in financials:
        if r.get('ticker') in codes and r.get('available_date','')<=asof:
            filings[r['ticker']].append(r)
    out=[]
    for r in rows:
        t=r['ticker'];series=sorted(bars[t],key=lambda x:x['date'])
        valid=True;seen=set()
        for b in series:
            try:
                d=b['date'];o,h,l,c,v=(float(b[k]) for k in ('open','high','low','close','volume'))
                if d in seen or not all(map(math.isfinite,(o,h,l,c,v))) or not 0<l<=min(o,c)<=max(o,c)<=h or v<0:
                    valid=False;break
                seen.add(d)
            except (KeyError,ValueError,TypeError):valid=False;break
        latest=series[-1]['date'] if series else None
        fresh=bool(valid and len(series)>=60 and latest==asof)
        reports=sorted(filings[t],key=lambda x:(x['available_date'],x.get('receipt_no','')))
        last=reports[-1] if reports else None
        dated=bool(last and last.get('receipt_no') and last.get('validation_status'))
        out.append({'ticker':t,'rank':r['rank'],'ohlcv_bars':len(series),
                    'ohlcv_latest_date':latest,'ohlcv_structurally_valid':valid,
                    'ohlcv_60_bars_asof':fresh,
                    'ohlcv_provenance':'PYKRX_HISTORICAL_CACHE_NOT_INDEPENDENTLY_CERTIFIED',
                    'dated_financial_receipt':last.get('receipt_no') if dated else None,
                    'financial_available_date':last.get('available_date') if dated else None,
                    'financial_validation_status':last.get('validation_status') if dated else None,
                    'financial_approved':False,'entry_approved':False,
                    'blocking_reasons':(['OHLCV_60_BAR_ASOF_MISSING'] if not fresh else [])
                      +(['FINANCIAL_FILING_MISSING'] if not dated else ['FINANCIAL_SNAPSHOT_NOT_PIT_VERIFIED'])
                      +['REGULAR_SESSION_TURNOVER_UNVERIFIED']})
    return {'schema':'C3_TOP20_EVIDENCE_COVERAGE_V1','asof':asof,'candidates':out,
            'ohlcv_60bar_asof_count':sum(x['ohlcv_60_bars_asof'] for x in out),
            'dated_financial_receipt_count':sum(bool(x['dated_financial_receipt']) for x in out),
            'buy_approved_count':0,'current_action':'CASH','orders_enabled':False}

def run(top20,history,finance,out):
    result=inspect(json.loads(Path(top20).read_text(encoding='utf-8')),load_csv(history),load_csv(finance))
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('C3_TOP20_EVIDENCE_COVERAGE '+json.dumps({'asof':result['asof'],
          'ohlcv_60bar_asof_count':result['ohlcv_60bar_asof_count'],
          'dated_financial_receipt_count':result['dated_financial_receipt_count'],
          'buy_approved_count':0},ensure_ascii=False))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for name in ('top20','history','finance','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.top20,a.history,a.finance,a.out)
