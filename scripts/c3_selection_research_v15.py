"""C3 research watchlist: selection is not trading approval."""
import csv,json,argparse
from pathlib import Path

def build(rows):
    out=[];excluded=0
    for r in rows:
        name=r.get("name","")
        if any(w in name for w in ("제약","바이오","녹십자")):
            excluded+=1
            continue
        try:
            score=float(r["c3_preliminary_score"])
            extension=float(r["extension_vs_ma20_pct"])
            rvol=float(r["rvol20"])
        except (ValueError,KeyError,TypeError):
            continue
        if not all(map(lambda x: abs(x)<1e10,(score,extension,rvol))):
            continue
        priority=round(score-max(0,extension-8)-2*max(0,rvol-5),2)
        out.append({"ticker":r["ticker"],"name":name,
          "price_date":r.get("latest_date"),"stage":r.get("setup"),
          "research_priority":priority,"source_warnings":r.get("warnings",""),
          "entry_status":"재산정 대기","entry_range":None,
          "stop":None,"nearest_resistance":None,"registered_at":None,
          "buy_approved":False})
    out.sort(key=lambda x:(-x["research_priority"],x["ticker"]))
    return {"input_count":len(rows),"name_excluded":excluded,
      "research_pool_count":len(out),"provisional_watch_top2":out[:2],
      "decision":"CASH","buy_approvals":0,
      "limitations":"Name exclusions incomplete; sector, fundamentals, regular-session source, and entry geometry unverified."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="reports/c3_preliminary.csv")
    p.add_argument("--output",default="reports/c3_selection_research_v15.json")
    a=p.parse_args()
    with open(a.input,encoding="utf-8-sig",newline="") as f:
        result=build(list(csv.DictReader(f)))
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("research_pool",result["research_pool_count"],"BUY",0)
