"""Experimental Yahoo Finance reference prices; never certify independent upstream.

Yahoo symbol .KS/.KQ must be selected explicitly and checked by operator.
Adjusted/unadjusted definitions may differ from pykrx; mismatches are research
diagnostics, not automatic trade signals.
"""
import argparse
import csv
import json
from pathlib import Path

def normalize(frame,ticker):
    if frame is None or frame.empty:
        raise ValueError("EMPTY_YAHOO_RESPONSE")
    rows=[]
    for index, record in frame.iterrows():
        day=index.strftime("%Y-%m-%d")
        vals={key:float(record[key]) for key in ("Open","High","Low","Close","Volume")}
        if not (0<vals["Low"]<=min(vals["Open"],vals["Close"])<=max(vals["Open"],vals["Close"])<=vals["High"]):
            raise ValueError("INVALID_YAHOO_OHLC")
        rows.append(dict(ticker=ticker,date=day,open=vals["Open"],high=vals["High"],
                         low=vals["Low"],close=vals["Close"],volume=vals["Volume"]))
    return rows

def main():
    parser=argparse.ArgumentParser()
    for field in ("plans","start","end","output","status"):
        parser.add_argument("--"+field,required=True)
    parser.add_argument("--symbols",required=True,help="Explicit experimental ticker-to-Yahoo mapping CSV")
    args=parser.parse_args()
    with open(args.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    with open(args.symbols,encoding="utf-8-sig",newline="") as f:
        symbol_rows=list(csv.DictReader(f))
    symbols={r["ticker"]:r["yahoo_symbol"] for r in symbol_rows}
    if len(symbols)!=len(symbol_rows) or set(symbols)!={p["ticker"] for p in plans}:
        raise ValueError("INVALID_EXPLICIT_YAHOO_SYMBOL_MAPPING")
    status=dict(schema="C3_YAHOO_REFERENCE_EXPERIMENT_V1",provider="Yahoo Finance via yfinance",
                upstream_independence_verified=False,price_adjustment_comparable=False,
                regular_only_certified=False,trade_approved=False,orders_enabled=False,
                results={},errors={})
    rows=[]
    try:
        import yfinance as yf
        from datetime import date,timedelta
        for plan in plans:
            ticker=plan["ticker"]
            # No implicit exchange suffix: avoid mapping a KOSDAQ name to KOSPI.
            symbol=symbols.get(ticker,"").strip()
            if not symbol or symbol not in (ticker+".KS",ticker+".KQ"):
                status["errors"][ticker]="YAHOO_SYMBOL_NOT_VERIFIED"
                continue
            try:
                frame=yf.download(symbol,start=args.start,
                                  end=(date.fromisoformat(args.end)+timedelta(days=1)).isoformat(),
                                  auto_adjust=False,actions=False,progress=False,
                                  threads=False,multi_level_index=False)
                out=normalize(frame,ticker)
                rows.extend(out)
                status["results"][ticker]=dict(symbol=symbol,rows=len(out))
            except Exception as exc:
                status["errors"][ticker]=type(exc).__name__+":"+str(exc)[:160]
    except Exception as exc:
        status["errors"]["provider"]=type(exc).__name__+":"+str(exc)[:160]
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["ticker","date","open","high","low","close","volume"])
        writer.writeheader()
        writer.writerows(rows)
    Path(args.status).write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False))
    # Experimental feed failure is reported, never silently treated as validation.
    raise SystemExit(0 if len(status["results"])==2 and not status["errors"] else 2)

if __name__=="__main__":
    main()
