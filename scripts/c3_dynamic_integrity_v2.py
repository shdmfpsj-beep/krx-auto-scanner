"""Read-only before/after proof for immutable signals, receipts and main."""
import argparse,json,os
from pathlib import Path
from c3_telegram_inputs import GitHub,canonical,digest
from c3_morning_final_v1 import protected_snapshot


def capture(gh):
    protected,refs=protected_snapshot(gh)
    return dict(protected=protected,protected_sha256=digest(canonical(protected)),refs=refs,
                main=gh.head('main'),counts={b:len(v) for b,v in protected.items()},telegram_requests=0,ledger_writes=0)


def run(phase,out):
    out.mkdir(parents=True,exist_ok=True);report=capture(GitHub(os.environ['GH_TOKEN']))
    if phase=='after':
        before=json.loads((out/'before.json').read_text())
        if report['protected']!=before['protected']:raise ValueError('PROTECTED_ORIGINAL_BLOB_CHANGED_DURING_RESEARCH')
        if report['main']!=before['main']:raise ValueError('PRODUCTION_MAIN_CHANGED_DURING_RESEARCH')
        report['originals_and_receipts_unchanged']=True;report['production_main_unchanged']=True
    (out/(phase+'.json')).write_bytes(canonical(report)+b'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('protected',)},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=('before','after'),required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.phase,a.out)
