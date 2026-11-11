#!/usr/bin/env python3
"""Fail-closed research-only OpenDART original receipt probe.
Supports exact 14 previously time-joined financial filing receipts AND the
8 prior corporate/halt title events. Never claims KIND exchange notice is an
OpenDART original if the API returns an error or unrelated XML.
Records SHA256 of original ZIP/SGML bytes; does not publish raw documents or
promote accounting numbers without separate period/FS/GAAP validation.
"""
import argparse,csv,datetime as dt,hashlib,io,json,os,re,time,urllib.parse,urllib.request,urllib.error,zipfile
from collections import Counter
from pathlib import Path

URL="https://opendart.fss.or.kr/api/document.xml"
MAX_RAW=25*1024*1024
MAX_UNCOMP=50*1024*1024

def sha(b):return hashlib.sha256(b).hexdigest()
def analyze_document(raw):
    result={"zip_authenticated":False,"original_archive_sha256":sha(raw),
      "original_primary_document_numeric_PIT_verified":False,
      "actual_corporate_action_effective_price_verified":False,
      "file_count":0,"uncompressed_bytes":0,"status":"BLOCKED_NOT_ZIP"}
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        m=re.search(rb"<status>\s*(\d+)\s*</status>",raw[:5000])
        result["status"]="OPEN_DART_STATUS_"+(m.group(1).decode() if m else "UNKNOWN_NONZIP")
        return result
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if len(infos)>30 or sum(i.file_size for i in infos)>MAX_UNCOMP:
            result["status"]="BLOCKED_ZIP_BOMB_OR_TOO_MANY_FILES";return result
        if not infos or any(i.is_dir() or ".." in Path(i.filename).parts for i in infos):
            result["status"]="BLOCKED_EMPTY_OR_INVALID_FILE";return result
        digests=[]
        for i in infos:
            b=z.read(i)
            digests.append({"name_sha256":sha(i.filename.encode()),"byte_count":len(b),
                "sha256":sha(b)})
        result.update(zip_authenticated=True,status="ORIGINAL_DOC_ARCHIVE_RETRIEVED_NUMERIC_UNVERIFIED",
            file_count=len(infos),uncompressed_bytes=sum(i.file_size for i in infos),
            file_evidence=digests)
    return result

def exact_receipts(financial_join,dart_titles):
    receipts={}
    for ev in financial_join["events"]:
        f=ev.get("financial") or {}
        no=str(f.get("receipt_no") or "")
        if re.fullmatch(r"\d{14}",no):
            receipts.setdefault(no,{"kind":"FINANCIAL_PROVISIONAL_DATE_LINK",
                "ticker":ev["ticker"],"filing_date":f.get("filing_date")})
    for ev in dart_titles["events"]:
        if ev["label"]=="NO_MATCHING_PRIOR_TITLE_IN_SNAPSHOT":continue
        for r in ev.get("prior_30_day_titles",[]):
            no=str(r.get("receipt_no") or "")
            if re.fullmatch(r"\d{14}",no) and (
                    "무상증자결정" in str(r.get("report_name") or "") or
                    "권리락" in str(r.get("report_name") or "") or
                    "주권매매거래정지" in str(r.get("report_name") or "")):
                receipts.setdefault(no,{"kind":"CORPORATE_OR_RIGHTS_DART_TITLE_ONLY",
                    "ticker":ev["ticker"],"filing_date":r["receipt_date"]})
    return receipts

def fetch_one(receipt,key):
    if not key or len(key)<30:return {"status":"BLOCKED_OPENDART_KEY_UNAVAILABLE"}
    qs=urllib.parse.urlencode({"crtfc_key":key,"rcept_no":receipt})
    try:
        req=urllib.request.Request(URL+"?"+qs,headers={"User-Agent":"C3-Research-PIT/1.2"})
        with urllib.request.urlopen(req,timeout=30) as r:
            if int(getattr(r,"status",200))!=200:return {"status":"BLOCKED_HTTP"}
            raw=r.read(MAX_RAW+1)
        if len(raw)>MAX_RAW:return {"status":"BLOCKED_DOC_TOO_LARGE"}
        return analyze_document(raw)
    except urllib.error.HTTPError as e:return {"status":f"BLOCKED_HTTP_{e.code}"}
    except (urllib.error.URLError,OSError,TimeoutError) as e:return {"status":"BLOCKED_ORIGINAL_ENDPOINT_UNAVAILABLE"}

def audit(financial_join,dart_titles,key):
    wanted=exact_receipts(financial_join,dart_titles)
    entries=[];statuses=Counter()
    for no,metadata in sorted(wanted.items()):
        data=fetch_one(no,key)
        statuses[data["status"]]+=1
        entries.append({"receipt_no":no,**metadata,**data})
        time.sleep(.12)
    return {
        "schema":"C3_V12_ORIGINAL_RECEIPT_EVIDENCE_AUDIT",
        "requested_receipts":len(wanted),
        "file_status_counts":dict(statuses),
        "financial_original_numeric_verification_count":0,
        "rights_reference_price_verified_from_open_dart_original_count":0,
        "rights_ex_date_verified_from_original_count":0,
        "original_regulatory_filings_not_ex_rights_KRX_execution_certification":True,
        "document_original_bytes_not_redistributed":True,
        "new_stock_selection_predictions_or_real_fills_claimed":False,
        "operating_code_modified":False,"decision":"CASH",
        "receipts":entries
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--join",required=True,type=Path)
    p.add_argument("--dart-titles",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    financial=json.loads(a.join.read_text())
    titles=json.loads(a.dart_titles.read_text())
    if financial.get("event_count")!=129 or titles.get("total_adjacent_anomalies")!=73:
        raise ValueError("FROZEN_PARENT_EVIDENCE_NOT_MATCHED")
    report=audit(financial,titles,os.environ.get("OPENDART_API_KEY",""))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C3_V12_ORIGINAL_RECEIPT",json.dumps({k:v for k,v in report.items() if k!="receipts"},ensure_ascii=False))
if __name__=="__main__":main()
