#!/usr/bin/env python3
"""2026 market holiday candidate cross-check. Source citations are provenance, not API certification."""
import argparse,json
from pathlib import Path
# Published 2026 exchange calendar; validate against exchange machine-readable source before certification.
REFERENCE_2026={
"2026-05-01":"Labor Day","2026-05-05":"Children's Day",
"2026-05-25":"Buddha's Birthday substitute","2026-06-03":"Local elections",
"2026-07-17":"Constitution Day","2026-08-17":"Liberation Day substitute",
"2026-09-24":"Chuseok","2026-09-25":"Chuseok",
"2026-10-05":"National Foundation Day substitute","2026-10-09":"Hangul Day"}
SOURCES=[
"https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp",
"https://mobile.newsis.com/view_amp.html?ar_id=NISX20260520_0003637250"]
def classify(empty_dates):
    return [{"date":d,"candidate_reason":REFERENCE_2026.get(d),
             "classification":"HOLIDAY_REFERENCE_MATCH_UNCERTIFIED" if d in REFERENCE_2026 else "EMPTY_RESPONSE_UNEXPLAINED"}
            for d in empty_dates]
def main():
    p=argparse.ArgumentParser();p.add_argument("--status",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();s=json.loads(a.status.read_text())
    rows=classify(s.get("empty_response_holiday_candidates",[]))
    out={"source_urls":SOURCES,"candidates":rows,"official_calendar_machine_verified":False,
         "all_empty_responses_explained_by_reference":all(x["candidate_reason"] for x in rows),
         "regular_1530_certified":False,"corporate_actions_adjusted_verified":False,
         "delisted_issuers_included_verified":False,"point_in_time_universe_verified":False,
         "performance_publication_allowed":False,"decision":"CASH"}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print("HOLIDAY_REFERENCE_CROSSCHECK",json.dumps({"count":len(rows),"unexplained":sum(not x["candidate_reason"] for x in rows),"certified":False,"decision":"CASH"}))
if __name__=="__main__":main()
