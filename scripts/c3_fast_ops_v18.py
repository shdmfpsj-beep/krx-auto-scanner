"""Price-supply orchestration, without changing selection or execution rules."""
import argparse,json,os,subprocess,time
from pathlib import Path
from c3_artifact_audit_v18 import write


def optional_scanner(run_id,outdir,ledger,fetch=None):
    from c3_runtime_v10 import scanner,download_scanner,quarantine
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    try:
        if not run_id:raise ValueError('NO_AUXILIARY_UPSTREAM_EVENT')
        audit=(fetch or scanner)(run_id);quarantine(download_scanner(audit,out/'operating'),ledger,out,audit)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        audit=dict(status='AUXILIARY_SCANNER_UNAVAILABLE',error_type=type(exc).__name__,
            required_price_supply_not_bypassed=True,run_id=str(run_id),prices_not_implicitly_certified=True)
        write(out/'provisional_status.json',dict(status='AUXILIARY_CLOSE_NOT_USED',used_for_selection=False,used_for_paper_fills=False))
    write(out/'upstream_validation.json',audit);return audit


def cached_current(report,expected,pipeline_hash,ledger,reader=None):
    """Reuse original registered source only after its hashes and bars pass again."""
    if not report or report.get('data_quality_state') not in ('OFFICIAL_VERIFIED','RESEARCH_VALIDATED') or report.get('source_price_asof')!=expected or report.get('errors') or report.get('source_hashes',{}).get('pipeline_code')!=pipeline_hash:return False
    from c3_forward_ledger_v8 import read_record
    from c3_runtime_v10 import quality
    base=Path(ledger)/'lanes/krx_unadjusted_v12';path=base/'markets'/(expected+'.json.gz')
    decision=base/'decisions'/(expected+'.json')
    if not path.exists() or not decision.exists():return False
    r=(reader or read_record)(path);d=(reader or read_record)(decision)
    if r['asof']!=expected or d['price_asof']!=expected or r['source'].get('price_basis')!='UNADJUSTED_AS_TRADED':return False
    rows=[dict(v,ticker=t,asof=expected) for t,v in r['rows'].items()]
    return not quality(rows,rows,expected)['errors']


def bounded_collect(day,previous,control,outdir,ledger,audit,budget=180,runner=subprocess.run):
    started=time.monotonic();status='COMPLETED'
    command=['python',str(Path(__file__).with_name('c3_supply_runtime_v12.py')),'--asof',day,'--previous-session',previous,
        '--control',str(control),'--outdir',str(outdir),'--ledger',str(ledger),'--audit',str(audit)]
    try:runner(command,check=True,timeout=budget)
    except subprocess.TimeoutExpired:
        status='PRICE_COLLECTION_BUDGET_EXCEEDED';raise ValueError(status)
    except subprocess.CalledProcessError:
        status='PRICE_COLLECTION_PROCESS_FAILED';raise ValueError(status)
    finally:
        write(str(audit)+'.timing.json',dict(asof=day,status=status,elapsed_seconds=time.monotonic()-started,
            budget_seconds=budget,price_supply_separate_from_auxiliary_data=True,unbounded_retries=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scanner',action='store_true');p.add_argument('--run-id',default='');p.add_argument('--outdir',required=True);p.add_argument('--ledger',default='');a=p.parse_args()
    if a.scanner:print(json.dumps(optional_scanner(a.run_id,a.outdir,a.ledger)))
    else:
        write(Path(a.outdir)/'upstream_validation.json',dict(status='PRICE_SUPPLY_PREFLIGHT',auxiliary_scanner_not_required=True,prices_not_implicitly_certified=True))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('run_id='+a.run_id+'\n')
