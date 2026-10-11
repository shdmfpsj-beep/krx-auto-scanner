#!/usr/bin/env python3
"""v5.6.2 research-only merger for v5.5 GitHub Actions market-data shards.

Reads local v5.5 outputs, and (when authenticated) recent GitHub Actions artifacts.
Fail-closed: only same session AND identical universe/shard layout are combined.
No BUY approval, no independent turnover or instrument-type verification.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

DATED = 'market_data_v54_dated.csv'
UNIVERSE = 'market_data_v52.csv'
AUDIT = 'market_data_v52_audit.json'
OUTPUT = 'market_data_v56_merged.csv'


def parse_csv(blob):
    return list(csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))))


def universe_key(rows):
    entries = sorted((r['ticker'], r['market']) for r in rows)
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def read_folder(folder):
    folder = Path(folder)
    audit = json.loads((folder / AUDIT).read_text(encoding='utf-8'))
    universe = parse_csv((folder / UNIVERSE).read_bytes())
    dated = parse_csv((folder / DATED).read_bytes())
    return audit, universe, dated


def read_artifact(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        def get(name):
            matches = [n for n in names if n == name or n.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError(f'artifact missing/ambiguous {name}')
            return z.read(matches[0])
        return json.loads(get(AUDIT)), parse_csv(get(UNIVERSE)), parse_csv(get(DATED))


def api_json(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                                               'Accept': 'application/vnd.github+json',
                                               'X-GitHub-Api-Version': '2022-11-28',
                                               'User-Agent': 'krx-v56-research'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def api_zip(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                                               'Accept': 'application/vnd.github+json',
                                               'X-GitHub-Api-Version': '2022-11-28',
                                               'User-Agent': 'krx-v56-research'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read(80_000_001)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='reports')
    p.add_argument('--max-runs', type=int, default=80)
    p.add_argument('--offline-artifacts', nargs='*', default=[], help='Local ZIPs for testing')
    a = p.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    result = {'version':'v5.6.2', 'research_only':True, 'status':'UNVERIFIED',
              'live_buy_approved':0, 'turnover_independently_reconciled':False,
              'verified_common_stocks':0, 'complete_market_dated':False,
              'source':'v5.5 dated OHLCV shards; same provider, not independent exchange evidence',
              'warnings':[], 'rejected_artifacts':Counter(), 'artifact_error_samples':[], 'artifact_error_types':Counter()}
    merged = {}
    try:
        current_audit, universe, current_rows = read_folder(out)
        expected_session = current_audit.get('batch_date')
        shard_count = int(current_audit['shard_count'])
        batch_size = int(current_audit['batch_size'])
        total = len(universe)
        digest = universe_key(universe)
        if not expected_session or shard_count != (total + batch_size - 1)//batch_size:
            raise ValueError('CURRENT_SHARD_METADATA_INCONSISTENT')
        universe_tickers = {(r['ticker'],r['market']) for r in universe}
        if len(universe_tickers) != total:
            raise ValueError('DUPLICATE_UNIVERSE')
        ordered = sorted(universe, key=lambda r: (0 if r['market']=='KOSPI' else 1,r['ticker']))
        shards = {}
        def ingest(audit, univ, rows, label):
            if audit.get('version') != 'v5.5' or audit.get('batch_date') != expected_session:
                result['rejected_artifacts']['wrong_version_or_date'] += 1
                return
            if universe_key(univ) != digest or int(audit.get('shard_count',-1)) != shard_count or int(audit.get('batch_size',-1)) != batch_size:
                result['rejected_artifacts']['universe_or_layout_mismatch'] += 1
                return
            idx = int(audit.get('shard_index',-1))
            if not 0 <= idx < shard_count:
                result['rejected_artifacts']['invalid_shard'] += 1
                return
            expected = {(r['ticker'],r['market']) for r in ordered[idx*batch_size:(idx+1)*batch_size]}
            if any((r['ticker'],r['market']) not in expected or r.get('snapshot_date') != expected_session or r.get('dated_ohlcv_valid','').lower() != 'true' for r in rows):
                result['rejected_artifacts']['invalid_dated_rows'] += 1
                return
            if len({(r['ticker'],r['market']) for r in rows}) != len(rows):
                result['rejected_artifacts']['duplicate_dated_rows'] += 1
                return
            # Prefer the latest valid artifact for each shard; current run takes precedence.
            if idx not in shards:
                shards[idx] = {'rows':rows,'label':label,'requested':len(expected)}
        ingest(current_audit, universe, current_rows, 'current_run')
        for path in a.offline_artifacts:
            try:
                ingest(*read_artifact(Path(path).read_bytes()), str(path))
            except Exception as exc:
                result['rejected_artifacts']['offline_read_error'] += 1
                result['warnings'].append(f'{Path(path).name}: {type(exc).__name__}')
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        repo = os.environ.get('GITHUB_REPOSITORY','')
        if token and '/' in repo:
            try:
                # Read only completed artifacts; current-run files are taken locally.
                base = f'https://api.github.com/repos/{repo}/actions/artifacts'
                checked = 0
                for page in range(1, min(6, (a.max_runs+99)//100 + 1)):
                    data = api_json(f'{base}?per_page=100&page={page}',token)
                    artifacts = data.get('artifacts',[])
                    if not artifacts: break
                    for artifact in artifacts:
                        if checked >= a.max_runs or len(shards) == shard_count: break
                        if artifact.get('expired') or artifact.get('name') != 'krx-scan-report': continue
                        checked += 1
                        try:
                            b = api_zip(artifact['archive_download_url'],token)
                            ingest(*read_artifact(b),f"run_artifact_{artifact['id']}")
                        except Exception as exc:
                            result['rejected_artifacts']['artifact_read_error'] += 1
                            kind = type(exc).__name__
                            message = str(exc)[:180]
                            result['artifact_error_types'][kind] += 1
                            if len(result['artifact_error_samples']) < 8:
                                result['artifact_error_samples'].append({'artifact_id':artifact.get('id'), 'run_id':artifact.get('workflow_run',{}).get('id'), 'error_type':kind, 'detail':message})
                    if checked >= a.max_runs or len(shards) == shard_count: break
                result['artifacts_examined'] = checked
            except Exception as exc:
                result['warnings'].append(f'GITHUB_API_UNAVAILABLE:{type(exc).__name__}:{str(exc)[:100]}')
        else:
            result['warnings'].append('GITHUB_API_NOT_CONFIGURED: current run only; set GH_TOKEN and GITHUB_REPOSITORY')
        for idx in sorted(shards):
            for row in shards[idx]['rows']:
                key = (row['ticker'],row['market'])
                if key in merged:
                    raise ValueError('OVERLAPPING_VALID_SHARDS')
                merged[key] = row
        fields = list(current_rows[0]) if current_rows else list(next((v['rows'][0] for v in shards.values() if v['rows']),{}))
        if fields:
            with (out / OUTPUT).open('w',newline='',encoding='utf-8-sig') as f:
                writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
                writer.writeheader()
                writer.writerows(merged.values())
        covered = sum(v['requested'] for v in shards.values())
        result.update(status='ALL_SHARDS_COLLECTED_WITH_FAILURES' if len(shards)==shard_count and len(merged)<total else ('ALL_SHARDS_COLLECTED_UNVERIFIED' if len(shards)==shard_count else 'PARTIAL_SHARDS_NO_BUY'),
                      batch_date=expected_session,universe_count=total,universe_sha256=digest,
                      shard_count=shard_count,shards_collected=len(shards),
                      missing_shards=[i for i in range(shard_count) if i not in shards],
                      attempted_tickers=covered,dated_valid_rows=len(merged),
                      failed_or_missing_tickers=total-len(merged),
                      complete_market_dated=len(shards)==shard_count and len(merged)==total,
                      shard_sources={str(k):v['label'] for k,v in shards.items()},
                      merged_csv=OUTPUT if fields else None)
        if len(shards)==shard_count and len(merged)==total:
            result['status']='ALL_SHARDS_COLLECTED_OHLCV_ONLY_NO_BUY'
        result['rejected_artifacts']=dict(result['rejected_artifacts'])
        result['artifact_error_types']=dict(result['artifact_error_types'])
    except Exception as exc:
        result['status']='MERGE_FAILED_NO_BUY'
        result['warnings'].append(f'{type(exc).__name__}:{str(exc)[:250]}')
        result['rejected_artifacts']=dict(result['rejected_artifacts'])
        result['artifact_error_types']=dict(result['artifact_error_types'])
    (out/'market_data_v56_merge_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result['status']=='MERGE_FAILED_NO_BUY' else 0

if __name__=='__main__':
    sys.exit(main())
