"""Capture official source identities and missing evidence, without qualification.

Run after the collector so same-run company/list/statements are not requested
twice. Financial decisions and operating files are never modified here.
"""
import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from c3_balanced_financials import SnapshotCache, retry_network, digest
from dart_financial_screen import api_json, annual_receipt, latest_interim_filing
from c3_dart_document_evidence import download_document, inspect_archive


class DocumentCache:
    def __init__(self, root):
        self.root=Path(root)
        self.events=[]

    def seed(self, folder):
        """Import only hash-verified successful archives from a verified artifact."""
        manifest=Path(folder)/'document_evidence.json'
        if not manifest.is_file():return
        for company in json.loads(manifest.read_text()).get('companies',[]):
            for route in company.get('routes',[]):
                if not route.get('file'):continue
                binary=(Path(folder)/route['file']).read_bytes()
                if hashlib.sha256(binary).hexdigest()!=route['sha256']:
                    raise ValueError('DOCUMENT_SEED_HASH_MISMATCH')
                import io
                if not zipfile.is_zipfile(io.BytesIO(binary)):continue
                identity=dict(endpoint=route['endpoint'],receipt=company['receipt_no'],report=company['report_code'])
                stem=digest(identity);self.root.mkdir(parents=True,exist_ok=True)
                record=self.root/(stem+'.json')
                if record.exists():continue
                (self.root/(stem+'.zip')).write_bytes(binary)
                record.write_text(json.dumps(dict(identity=identity,sha256=route['sha256'],
                    observed_at=company['observed_at']),sort_keys=True))

    def get(self, endpoint, receipt, report, key, fetch=download_document):
        identity=dict(endpoint=endpoint,receipt=receipt,report=report)
        stem=digest(identity)
        record_path=self.root/(stem+'.json')
        binary_path=self.root/(stem+'.zip')
        if record_path.is_file():
            record=json.loads(record_path.read_text());binary=binary_path.read_bytes()
            if record['identity']!=identity or hashlib.sha256(binary).hexdigest()!=record['sha256']:
                raise ValueError('DOCUMENT_CACHE_INTEGRITY_ERROR')
            self.events.append(dict(identity=identity,state='HIT',sha256=record['sha256'],observed_at=record['observed_at']))
            return binary
        binary=retry_network(lambda:fetch(endpoint,receipt,report,key))
        sha=hashlib.sha256(binary).hexdigest()
        self.events.append(dict(identity=identity,state='FETCH',sha256=sha,observed_at=datetime.now(timezone.utc).isoformat()))
        # API errors (including 014) are observed, never permanent successful cache.
        import io
        if zipfile.is_zipfile(io.BytesIO(binary)):
            self.root.mkdir(parents=True,exist_ok=True)
            binary_path.write_bytes(binary)
            record_path.write_text(json.dumps(dict(identity=identity,sha256=sha,
                observed_at=self.events[-1]['observed_at']),sort_keys=True))
        return binary


def capture(financial, cache, out, key):
    out.mkdir(parents=True,exist_ok=True)
    raw=out/'raw';raw.mkdir(exist_ok=True)
    docs=DocumentCache(cache.root/'documents')
    asof=datetime.strptime(financial['asof'],'%Y%m%d').date()
    results=[]
    def save_json(kind, payload):
        name=kind+'_'+digest(payload)+'.json';(raw/name).write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True))
        return dict(file='raw/'+name,sha256=digest(payload),api_status=payload.get('status'))
    def get(endpoint, params, receipt=None):
        return cache.observed_or_request(endpoint,params,key,api_json,receipt)
    for row in financial.get('researched',[])+financial.get('excluded',[]):
        item=dict(ticker=row['ticker'],name=row.get('name'),corp_code=row.get('corp_code'),documents=[])
        results.append(item)
        try:
            corp=item['corp_code']
            if not corp:raise ValueError('CORPORATE_ID_NOT_AVAILABLE')
            info=get('company.json',dict(corp_code=corp));item['company']=save_json('company',info)
            pages=[];catalog=[];page=1
            while True:
                data=get('list.json',dict(corp_code=corp,bgn_de=f'{asof.year-3}0101',end_de=asof.strftime('%Y%m%d'),
                    pblntf_ty='A',last_reprt_at='N',page_count=100,page_no=page))
                pages.append(save_json('filings',data));catalog.extend(data.get('list',[]))
                if data.get('status')!='000' or page>=int(data.get('total_page',1)):break
                page+=1
                if page>10:raise ValueError('FILING_PAGINATION_BUDGET_EXCEEDED')
            item['catalogue_pages']=pages
            years=[(y,annual_receipt(dict(status='000',list=catalog),y,asof)) for y in (asof.year-1,asof.year-2)]
            year,selected=max((y,r) for y,r in years if r)
            day,receipt=selected
            item.update(selected_annual_receipt=receipt,selected_annual_filing_date=day.isoformat(),year=year,
                same_year_filings=[r for r in catalog if f'({year}.12)' in str(r.get('report_nm','')).replace(' ','')])
            major=get('fnlttSinglAcnt.json',dict(corp_code=corp,bsns_year=str(year),reprt_code='11011'))
            item['major_accounts']=save_json('major',major)
            division=row.get('statement_division') or row.get('statement_division_attempted') or 'CFS'
            payload=get('fnlttSinglAcntAll.json',dict(corp_code=corp,bsns_year=str(year),reprt_code='11011',fs_div=division),receipt)
            if payload.get('status') in ('013','014') and division=='CFS':
                division='OFS'
                payload=get('fnlttSinglAcntAll.json',dict(corp_code=corp,bsns_year=str(year),reprt_code='11011',fs_div=division),receipt)
            item.update(full_accounts=save_json('full',payload),division=division,
                returned_receipts=sorted({r.get('rcept_no') for r in payload.get('list',[]) if r.get('rcept_no')}))
            if row.get('financial_verdict')=='REJECTED_FINANCIAL_RISK':continue
            targets=[(receipt,'11011',year)]
            targets += [(r,'11011',year) for r in item['returned_receipts'] if r!=receipt and any(f.get('rcept_no')==r for f in catalog)]
            if row.get('sector_profile')=='FINANCIAL_SPECIAL_MODEL_REQUIRED':
                interim=latest_interim_filing(dict(status='000',list=catalog),asof)
                if interim:targets.append((interim['receipt_no'],interim['report_code'],interim['fiscal_year']))
            for actual,report,fy in targets:
                if actual[:8]>asof.strftime('%Y%m%d'):continue
                for endpoint in ('document.xml','fnlttXbrl.xml'):
                    source=dict(receipt_no=actual,report_code=report,division=division,endpoint=endpoint)
                    item['documents'].append(source)
                    try:
                        binary=docs.get(endpoint,actual,report,key)
                        import io
                        suffix='.zip' if zipfile.is_zipfile(io.BytesIO(binary)) else '.xml'
                        filename=actual+'_'+endpoint.split('.')[0]+suffix
                        (out/filename).write_bytes(binary)
                        source.update(file=filename,sha256=hashlib.sha256(binary).hexdigest(),bytes=len(binary))
                        references={'Assets':row.get('decision_basis',{}).get('annual_assets_krw'),
                            'Liabilities':row.get('liabilities_krw'),'Equity':row.get('equity_krw')}
                        checked=inspect_archive(binary,division,fy,corp,references)
                        source['inspection']=checked
                    except Exception as exc:
                        source.update(state='ERROR',error=type(exc).__name__)
        except Exception as exc:
            item.update(state='ERROR',error=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else type(exc).__name__)
    result=dict(asof=financial['asof'],scope='SOURCE_INVESTIGATION_NOT_QUALIFICATION',companies=results,
                document_cache_events=docs.events,observed_at=datetime.now(timezone.utc).isoformat())
    (out/'source_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_SOURCE_PROBE',json.dumps([dict(ticker=r['ticker'],selected=r.get('selected_annual_receipt'),
        returned=r.get('returned_receipts'),documents=len(r['documents']),error=r.get('error')) for r in results]))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--financial',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seed',type=Path,action='append',default=[])
    args=parser.parse_args()
    for folder in args.seed:DocumentCache(args.cache/'documents').seed(folder)
    capture(json.loads(args.financial.read_text()),SnapshotCache(args.cache),args.out,
        os.environ.get('DART_API_KEY') or os.environ.get('OPENDART_API_KEY') or os.environ.get('OPEN_DART_API_KEY'))
