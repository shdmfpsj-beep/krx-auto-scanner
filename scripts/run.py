import json, os, time, traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from pykrx import stock

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports'; OUT.mkdir(exist_ok=True)
NOW=datetime.now(ZoneInfo('Asia/Seoul'))
# At 15:00 KST the close is not final. Require post-close run for new-day signals.
TODAY=NOW.date()
CUTOFF=TODAY if (NOW.hour, NOW.minute)>=(16,10) else TODAY-timedelta(days=1)
END=CUTOFF.strftime('%Y%m%d')
START=(CUTOFF-timedelta(days=550)).strftime('%Y%m%d')
status={'run_kst':NOW.isoformat(),'requested_end':END,'universe':0,'download_attempted':0,'download_succeeded':0,'valid_ohlcv':0,'screened':0,'failed':0,'external_screener_count':0,'full_chart_verified':0,'duplicates_removed':0,'market_data_date':None,'errors':[],'note':'Candidate scan only; no trade approvals. Flows, volume profile and account cash not verified.'}

def save_status():
 (OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')

def fail(message):
 status['errors'].append(str(message)[:350]);save_status()

def fetch_universe():
 # Discover listed symbols from a recent trading day; no holiday fallback masquerading as today.
 for offset in range(0,12):
  day=(CUTOFF-timedelta(days=offset)).strftime('%Y%m%d')
  try:
   a=stock.get_market_ticker_list(day,market='KOSPI')
   b=stock.get_market_ticker_list(day,market='KOSDAQ')
   codes=sorted(set(a)|set(b))
   if len(codes)>1000:
    status['market_data_date']=day
    status['duplicates_removed']=len(a)+len(b)-len(codes)
    return codes
  except Exception as e: status['errors'].append(f'universe {day}: {str(e)[:90]}')
  time.sleep(1)
 return []

def classify(df):
 c=df['종가'].astype(float);v=df['거래량'].astype(float)
 ma20=c.rolling(20).mean();ma60=c.rolling(60).mean();ma120=c.rolling(120).mean()
 rvol=v.iloc[-1]/v.iloc[-21:-1].mean() if v.iloc[-21:-1].mean()>0 else None
 high20=df['고가'].astype(float).iloc[-21:-1].max()
 # Strict, transparent heuristic labels, not proven entries.
 breakout=bool(c.iloc[-1]>high20 and rvol is not None and rvol>=1.5 and c.iloc[-1]>ma60.iloc[-1])
 pullback=bool(ma20.iloc[-1]>ma60.iloc[-1]>ma120.iloc[-1] and abs(c.iloc[-1]/ma20.iloc[-1]-1)<=.035 and c.iloc[-1]>ma20.iloc[-1])
 reversal=bool(c.iloc[-2]<ma60.iloc[-2] and c.iloc[-1]>ma60.iloc[-1] and ma20.iloc[-1]>ma20.iloc[-6])
 weekly=c.resample('W-FRI').last().dropna();monthly=c.resample('ME').last().dropna()
 w_ok=bool(len(weekly)>=30 and weekly.iloc[-1]>weekly.rolling(10).mean().iloc[-1])
 m_ok=bool(len(monthly)>=8 and monthly.iloc[-1]>monthly.rolling(6).mean().iloc[-1])
 return {'close':int(c.iloc[-1]),'ma20':round(ma20.iloc[-1],2),'ma60':round(ma60.iloc[-1],2),'ma120':round(ma120.iloc[-1],2),'rvol20':round(rvol,3) if rvol else None,'breakout':breakout,'first_pullback_proxy':pullback,'reversal_proxy':reversal,'weekly_filter':w_ok,'monthly_filter':m_ok,'score':int(breakout)*3+int(pullback)*3+int(reversal)*3+int(w_ok)+int(m_ok)}

def main():
 codes=fetch_universe();status['universe']=len(codes);save_status()
 if not codes: fail('Universe download unavailable; no candidate report generated.');return
 rows=[]
 for code in codes:
  status['download_attempted']+=1
  try:
   df=stock.get_market_ohlcv_by_date(START,END,code,adjusted=True)
   if df is None or df.empty: raise ValueError('empty')
   df=df[~df.index.duplicated(keep='last')].sort_index()
   if len(df)<150: raise ValueError(f'only {len(df)} sessions')
   for col in ('시가','고가','저가','종가','거래량'):
    if col not in df: raise ValueError('missing '+col)
   if (df['종가'].tail(120)<=0).any(): raise ValueError('nonpositive close')
   status['download_succeeded']+=1
   rec=classify(df);status['valid_ohlcv']+=1
   if any(rec[k] for k in ('breakout','first_pullback_proxy','reversal_proxy')):
    rec.update(ticker=code,latest_date=str(df.index[-1].date()),sessions=len(df))
    rows.append(rec)
   status['screened']+=1
  except Exception as e:
   status['failed']+=1
   if len(status['errors'])<30: status['errors'].append(f'{code}: {str(e)[:110]}')
  if status['download_attempted']%50==0:save_status()
  time.sleep(float(os.getenv('REQUEST_DELAY','0.2')))
 if rows:
  pd.DataFrame(rows).sort_values(['score','rvol20'],ascending=False).to_csv(OUT/'candidates.csv',index=False,encoding='utf-8-sig')
 elif (OUT/'candidates.csv').exists(): (OUT/'candidates.csv').unlink()
 save_status()
 print(json.dumps(status,ensure_ascii=False))

if __name__=='__main__':
 try:main()
 except Exception as e:fail('Fatal: '+repr(e));traceback.print_exc();raise
