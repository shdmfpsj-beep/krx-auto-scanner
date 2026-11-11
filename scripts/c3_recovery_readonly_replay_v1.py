"""Actual immutable-price/MA/ledger rehearsal. No broker or Telegram token."""
import argparse,copy,json,os
from datetime import datetime,timezone
from pathlib import Path
from c3_telegram_inputs import GitHub,ROOT,RESEARCH,canonical,digest,report_pair,frozen_live_bars,warmup_from_owner
from c3_telegram_notify import report_error
from c3_classic_theme import create_cards


class ReadOnlyGitHub(GitHub):
    def api(self,path,method='GET',payload=None,missing_ok=False):
        if method!='GET' or payload is not None:raise ValueError('RECOVERY_REPLAY_MUTATION_FORBIDDEN')
        return super().api(path,method,payload,missing_ok)
    def create(self,*a,**kw):raise ValueError('RECOVERY_REPLAY_MUTATION_FORBIDDEN')


def protected(gh,ref,prefix):
    tree=gh.api('git/trees/'+ref+'?recursive=1')
    if tree.get('truncated'):raise ValueError('INCOMPLETE_LEDGER_TREE')
    return {r['path']:r['sha'] for r in tree['tree'] if r['type']=='blob' and any(r['path'].startswith(p) for p in prefix)}


def run(outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True);gh=ReadOnlyGitHub(os.environ.get('GH_TOKEN',''))
    r,s,ref=report_pair(gh);main=gh.head('main');delivery=gh.head('delivery/c3-top2-telegram')
    prefix=(ROOT+'/lanes/',ROOT+'/key_envelopes/',ROOT+'/bootstrap/')
    original=protected(gh,ref,prefix);receipts=protected(gh,delivery,('receipts/',))
    before=canonical(r);frozen=frozen_live_bars(gh,copy.deepcopy(r),ref)
    original_candidates=copy.deepcopy(frozen['research_top2'])
    display=warmup_from_owner(gh,frozen,ref)
    for old,new in zip(original_candidates,display['research_top2']):
        if {k:v for k,v in old.items() if k!='chart_bars'}!={k:v for k,v in new.items() if k not in ('chart_bars','chart_warmup_audit')}:
            raise ValueError('DISPLAY_WARMUP_CHANGED_SELECTION_OR_PLAN')
    display['example_only']=True;display['historical_test_only']=True
    files=create_cards(display,out/'historical_ma60_replay')
    diagnostics=json.loads((out/'historical_ma60_replay/render_diagnostics.json').read_text())
    if any(c['visible_rows']!=60 or c['source_labels']['ma60_visible_points']!=60 for c in diagnostics['cards']):
        raise ValueError('ACTUAL_FULL_WINDOW_MA60_TEST_FAILED')
    current_research=gh.head(RESEARCH);end=protected(gh,current_research,prefix)
    current_delivery=gh.head('delivery/c3-top2-telegram');end_receipts=protected(gh,current_delivery,('receipts/',))
    unchanged=all(end.get(p)==v for p,v in original.items())
    same_receipts=all(end_receipts.get(p)==v for p,v in receipts.items())
    if not unchanged or not same_receipts or canonical(r)!=before:raise ValueError('PROTECTED_LEDGER_CHANGED_DURING_REPLAY')
    audit={'schema':'C3_RECOVERY_READONLY_REPLAY_V1','checked_at':datetime.now(timezone.utc).isoformat(),
        'source_price_asof':r['source_price_asof'],'source_run_id':r['source_run_id'],'research_ref':ref,
        'main_ref':main,'current_source_gate':report_error(r,s,datetime.now(timezone.utc)),
        'decision_payload_sha256':display['input_provenance']['decision_payload_sha256'],
        'source_report_sha256':digest(before),'historical_only':True,'not_a_new_20261111_result':True,
        'candidate_count':len(display['research_top2']),'historical_png_count':len(files),
        'warmup':[dict(ticker=x['ticker'],**x['chart_warmup_audit']) for x in display['research_top2']],
        'protected_blobs':len(original),'protected_tree_sha256':digest(canonical(original)),
        'protected_original_blobs_unchanged':unchanged,'receipt_original_blobs_unchanged':same_receipts,
        'receipt_ref':current_delivery,'source_scope_certified_by_warmup':False,
        'paper_performance':r.get('performance'),'paper_observations':r.get('observations'),
        'new_signals_registered':0,'ledger_write_requests':0,'telegram_send_attempts':0,'orders_enabled':False}
    (out/'recovery_replay.json').write_bytes(canonical(audit)+b'\n')
    print(json.dumps({k:audit[k] for k in ('source_price_asof','historical_png_count','protected_original_blobs_unchanged','telegram_send_attempts')}))
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();run(a.outdir)
