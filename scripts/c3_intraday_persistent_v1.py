"""Safe persistent observation ledger for C3 TOP2 research.
GitHub Actions artifact persistence: download previous artifact, merge, upload new artifact.
No fabricated prices or fills. No writes to production branch.
"""
import argparse,csv,json
from pathlib import Path
from c3_intraday_ledger_v1 import FIELDS,merge
def load(path):
    if not Path(path).exists():return []
    with open(path,encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    if any(not set(FIELDS).issubset(row) for row in rows):raise ValueError("BAD_LEDGER_SCHEMA")
    return rows
def summarize(rows):
    result={}
    for row in rows:
        ticker=row["ticker"]
        d=result.setdefault(ticker,{"observations":0,"watch_zone":0,"below_zone":0,"above_zone":0})
        d["observations"]+=1
        key={"WATCH_ZONE":"watch_zone","BELOW_ZONE":"below_zone","ABOVE_ZONE":"above_zone"}.get(row["status"])
        if key:d[key]+=1
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--watch",required=True)
    p.add_argument("--previous",default="history/c3_intraday_observations.csv")
    p.add_argument("--out",default="output/c3_intraday_observations.csv")
    p.add_argument("--summary",default="output/c3_intraday_summary.json")
    a=p.parse_args()
    previous=load(a.previous)
    watch=json.loads(Path(a.watch).read_text(encoding="utf-8"))
    merged,new=merge(previous,watch)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(merged)
    summary={"observations_total":len(merged),"new_verified_observations":len(new),
             "tickers":summarize(merged),"paper_fills":0,"trade_approved":False}
    Path(a.summary).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
