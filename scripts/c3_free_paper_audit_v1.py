"""Read-only free C3 paper-ledger diagnostic. No API, orders, or fabricated data."""
import argparse,json
from pathlib import Path
def audit(ledger):
    data=json.loads(Path(ledger).read_text(encoding="utf-8"))
    rows=[]
    for key,p in data.get("positions",{}).items():
        sessions=int(p.get("sessions_observed") or 0)
        status=p.get("status","UNKNOWN")
        rows.append({"ticker":p.get("plan",{}).get("ticker"),
                     "name":p.get("plan",{}).get("name"),
                     "status":status,"observed_sessions":sessions,
                     "last_observed_date":p.get("last_observed_date"),
                     "has_forward_evidence":sessions>0,
                     "realized_performance_verified":False})
    return {"schema":"C3_FREE_PAPER_AUDIT_V1","positions":rows,
            "all_waiting_without_observations":bool(rows) and all(
               r["status"]=="WAITING" and r["observed_sessions"]==0 for r in rows),
            "no_quote_is_not_zero_return":True,
            "broker_orders_enabled":False,
            "next_action":"CHECK_NEXT_COMPLETED_SESSION_AND_CAPTURE_SOURCE" if rows else "REGISTER_PLANS"}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--ledger",required=True);p.add_argument("--out")
    a=p.parse_args();result=audit(a.ledger)
    s=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:Path(a.out).write_text(s+"\n",encoding="utf-8")
    print(s)
