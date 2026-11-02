"""C3 v21 pipeline readiness report; no trading inference."""
import argparse,csv,json
from pathlib import Path

FILES={
 "preliminary":"c3_preliminary.csv",
 "candidate_evidence":"c3_candidate_evidence_v1.csv",
 "selection_v16":"c3_selection_evidence_v16.json",
 "registry_v17":"c3_selection_forward_registry_v17.csv",
 "reference_calendar":"c3_reference_calendar_v1.json",
}
def inspect(root):
    root=Path(root)
    state={}
    for name,filename in FILES.items():
        p=root/filename
        item={"exists":p.is_file(),"nonempty":p.is_file() and p.stat().st_size>0}
        if item["nonempty"]:
            try:
                if p.suffix==".json":
                    data=json.loads(p.read_text(encoding="utf-8-sig"))
                    item["records"]=len(data.get("provisional_watch_top2",[])) if name=="selection_v16" else None
                else:
                    with p.open(encoding="utf-8-sig",newline="") as f:item["records"]=sum(1 for _ in csv.DictReader(f))
            except (ValueError,KeyError,UnicodeError):
                item["parse_error"]=True
        state[name]=item
    missing=[k for k,v in state.items() if not v["nonempty"] or v.get("parse_error")]
    registered=state["registry_v17"].get("records",0)
    return {"schema":"C3_PIPELINE_READINESS_V21","files":state,
      "missing_or_invalid":missing,"registered_rows":registered,
      "forward_evaluation_ready":not missing and registered>0,
      "buy_approvals":0,"decision":"CASH",
      "note":"Readiness only. Existing reference calendar and prices are not certified."}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--reports",default="reports")
    p.add_argument("--out",default="reports/c3_pipeline_readiness_v21.json")
    a=p.parse_args()
    result=inspect(a.reports)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"missing_or_invalid":result["missing_or_invalid"],
                      "registered_rows":result["registered_rows"]}))
