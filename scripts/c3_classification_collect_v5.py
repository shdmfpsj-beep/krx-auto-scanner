"""Public KIND company industries/products + Naver industry corroboration.

Save a NEW dated snapshot; never overwrite an earlier decision's classifications.
Only industry and KRX tradability metadata are kept from Naver, never its prices
or NXT fields. No credentials are used by this collector.
"""
import argparse,concurrent.futures,csv,hashlib,io,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from c3_selection_scope_v5 import write_csv

KIND="https://kind.krx.co.kr/corpgeneral/corpList.do"
DIRECTORY="https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/industries?sortType=changeRate&sortDirection=desc&period=daily&size=100"
HEADERS={"User-Agent":"Mozilla/5.0","Referer":"https://stock.naver.com/market/stock/kr/industry"}


def fetch(url):
    headers=dict(HEADERS)
    if url.startswith(KIND):headers["Referer"]="https://kind.krx.co.kr/"
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15) as r:body=r.read(12_000_001)
    if len(body)>12_000_000:raise ValueError("SOURCE_TOO_LARGE")
    return body,dict(url=url,received_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(body).hexdigest())


def kind_rows(body,market):
    import pandas as pd
    tables=pd.read_html(io.BytesIO(body),encoding="euc-kr",converters={"종목코드":str})
    frame=next((x for x in tables if {"종목코드","업종","주요제품","상장일","회사명"}.issubset(x.columns)),None)
    if frame is None:raise ValueError("KIND_SCHEMA_CHANGED")
    rows=[]
    for item in frame.to_dict("records"):
        row={k:"" if pd.isna(v) else str(v).strip() for k,v in item.items()};ticker=row["종목코드"]
        if not re.fullmatch(r"[0-9A-Z]{6}",ticker):raise ValueError("KIND_SECURITY_CODE_CHANGED")
        rows.append(dict(ticker=ticker,market=market,name=row["회사명"],industry=row["업종"],products=row["주요제품"],listed_date=row["상장일"]))
    return rows


def sector_rows(sector,fetcher=fetch):
    rows=[];receipts=[];cursor=None
    for page in range(8):
        q=dict(sortType="tradingValue",sortDirection="desc",size=100)
        if cursor:q["cursor"]=cursor
        url="https://stock.naver.com/api/domestic/market/upjong/"+sector["code"]+"/stocklist?"+urllib.parse.urlencode(q)
        body,receipt=fetcher(url);j=json.loads(body);receipts.append(receipt)
        if not isinstance(j.get("items"),list):raise ValueError("SECONDARY_SCHEMA_CHANGED")
        for r in j["items"]:
            t=r["itemCode"];t=t[1:] if re.fullmatch(r"A[0-9]{6}",t) else t
            if not re.fullmatch(r"[0-9A-Z]{6}",t):raise ValueError("SECONDARY_SECURITY_CODE_CHANGED")
            rows.append(dict(ticker=t,name=r["itemName"],market=r["marketType"],sector=sector["name"],sector_id=sector["code"],
                krx_tradable_status=(r.get("krx") or {}).get("tradableStatus","")))
        if not j["hasNext"]:return rows,receipts
        if not j.get("cursor") or j["cursor"]==cursor:raise ValueError("CURSOR_NOT_ADVANCING")
        cursor=j["cursor"]
    raise ValueError("PAGINATION_LIMIT_UNCONFIRMED_CATEGORY")


def collect(outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=False);kind=[];receipts=[]
    for market,source in (("KOSPI","stockMkt"),("KOSDAQ","kosdaqMkt")):
        url=KIND+"?"+urllib.parse.urlencode(dict(method="download",marketType=source,searchType="13",currentPageSize="5000",pageIndex="1"))
        body,receipt=fetch(url);kind+=kind_rows(body,market);receipts.append(receipt)
    body,receipt=fetch(DIRECTORY);receipts.append(receipt);directory=json.loads(body)
    if directory["hasNext"] or not 1<=len(directory["items"])<=100:raise ValueError("INDUSTRY_DIRECTORY_INCOMPLETE")
    secondary=[];failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures={ex.submit(sector_rows,s):s for s in directory["items"]}
        for f in concurrent.futures.as_completed(futures):
            s=futures[f]
            try:
                rows,rs=f.result();secondary+=rows;receipts+=rs
            except Exception as e:failures.append(dict(sector=s["name"],sector_id=s["code"],error=type(e).__name__))
    write_csv(root/"kind_companies.csv",sorted(kind,key=lambda r:r["ticker"]))
    write_csv(root/"secondary_industries.csv",sorted(secondary,key=lambda r:(r["ticker"],r["sector_id"])))
    meta=dict(schema="C3_CLASSIFICATION_SOURCES_V5",frozen_at=datetime.now(timezone.utc).isoformat(),kind_rows=len(kind),secondary_rows=len(secondary),
        industries=len(directory["items"]),secondary_failed_categories=failures,
        file_sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ("kind_companies.csv","secondary_industries.csv")},
        receipts=sorted(receipts,key=lambda r:r["url"]),historical_pit_verified=False,quote_fields_used=False,nxt_fields_used=False)
    (root/"classification_sources.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n")
    return meta


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--outdir",required=True);a=p.parse_args();m=collect(a.outdir)
    print(json.dumps({k:m[k] for k in ("kind_rows","secondary_rows","secondary_failed_categories")},ensure_ascii=False))
