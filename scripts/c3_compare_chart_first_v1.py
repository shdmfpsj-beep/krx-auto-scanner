"""Compare baseline vs chart-first on identical diagnostic cohort (research only)."""
import argparse,json
from pathlib import Path
from c3_chart_first_turnaround_v1 import classify,geometry
def compare(doc):
 rows=doc['rows'];day=doc['asof']
 baseline={r['ticker'] for r in rows if r['entry_window'].get('quality_momentum_liquidity_eligible')}
 baseline_entry={r['ticker'] for r in rows if r['entry_window'].get('research_fit_eligible')}
 ranked=[geometry(r,classify(r,day)) for r in rows]
 new={r['ticker'] for r in ranked if r['status'] in ('CHART_FIRST_WATCH','V4_ENTRY_RESEARCH_REVIEW','GEOMETRY_RESEARCH_READY')}
 ready={r['ticker'] for r in ranked if r['status']=='GEOMETRY_RESEARCH_READY'}
 return dict(asof=day,technical_candidates=len(rows),baseline_quality_count=len(baseline),
  chart_first_watch_count=len(new),overlap_count=len(baseline&new),
  new_only_count=len(new-baseline),baseline_only_count=len(baseline-new),
  baseline_entry_fit_count=len(baseline_entry),chart_first_geometry_ready_count=len(ready),
  loss_improving_watch_count=sum(r.get('turnaround_loss_making',False) for r in ranked if r['ticker'] in new),
  research_only=True,buy_approved=False,
  warning='WATCH is not entry. No 5/10/20-day forward returns or audit/listing risk certification.',
  top10=[dict(name=r['name'],ticker=r['ticker'],close=r['close'],score=r['combined_score'],baseline_entry_status=r['baseline_entry_status']) for r in sorted((r for r in ranked if r['ticker'] in new),key=lambda r:(-r['combined_score'],r['ticker']))[:10]])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 result=compare(json.loads(Path(a.input).read_text()));Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
