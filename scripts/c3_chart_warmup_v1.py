"""Display-only MA warm-up from the already locked original price panel.

The engine's 90 bars, ranks, plans and ledgers are never rewritten. Every
overlap is compared before a prefix is attached to a temporary presentation.
This validates price continuity, not the original provider's session scope.
"""
import copy,csv,gzip,hashlib,io,json,math,zipfile
from datetime import date
from pathlib import Path

PANEL_ARTIFACT_ID=13367962976
PANEL_ZIP_SHA256='2f241cfc112c721a2dbb187bd4874423d5958fa46fe66151356cbcbe09d39738'
FIELDS=('open','high','low','close','volume','turnover_krw')
REQUIRED_ROWS=119


def digest(body):return hashlib.sha256(body).hexdigest()


def load_locked_panel(path,tickers):
    raw=Path(path).read_bytes()
    if digest(raw)!=PANEL_ZIP_SHA256:raise ValueError('LOCKED_CHART_ARCHIVE_HASH_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        audit=json.loads(archive.read('quality_audit.json'))
        panel=archive.read('official_panel.csv.gz')
        if digest(panel)!=audit.get('panel_sha256'):raise ValueError('LOCKED_CHART_PANEL_HASH_MISMATCH')
        rows=[];sessions=set()
        with gzip.open(io.BytesIO(panel),'rt') as f:
            for row in csv.DictReader(f):
                sessions.add(row['date'])
                if row['ticker'] in tickers:rows.append(row)
    return rows,sorted(sessions),audit


def extend_bars(row,panel_rows,sessions,audit):
    frozen=copy.deepcopy(row.get('chart_bars') or [])
    if len(frozen)<60:raise ValueError('FROZEN_CHART_HISTORY_INSUFFICIENT')
    days=[b['date'] for b in frozen]
    if days!=sorted(set(days)):raise ValueError('FROZEN_CHART_DATE_ORDER_MISMATCH')
    by={b['date']:b for b in panel_rows if b['ticker']==row['ticker']}
    overlap=[b for b in frozen if b['date'] in by]
    # Without overlap, two independently sourced price segments cannot be joined.
    if len(overlap)<20:raise ValueError('CHART_WARMUP_OVERLAP_INSUFFICIENT')
    for b in overlap:
        old=by[b['date']]
        if old['name']!=row['name'] or any(float(old[k])!=float(b[k]) for k in FIELDS):
            raise ValueError('CHART_WARMUP_FROZEN_OVERLAP_MISMATCH')
    prefix=[dict({k:float(b[k]) for k in FIELDS},date=b['date'],name=b['name'],segment=0)
            for b in panel_rows if b['ticker']==row['ticker'] and b['date']<days[0]]
    bars=(sorted(prefix,key=lambda b:b['date'])+frozen)[-REQUIRED_ROWS:]
    if len(bars)<REQUIRED_ROWS:raise ValueError('FULL_WINDOW_MA60_HISTORY_INSUFFICIENT')
    grid=sorted(set(sessions)|set(days));positions={d:i for i,d in enumerate(grid)}
    events={e['date'] for e in audit.get('reference_rebase_candidates',[]) if e['ticker']==row['ticker']}
    previous=None
    for b in bars:
        date.fromisoformat(b['date']);v={k:float(b[k]) for k in FIELDS}
        if (not all(math.isfinite(x) for x in v.values()) or
            not 0<v['low']<=min(v['open'],v['close'])<=max(v['open'],v['close'])<=v['high'] or
            v['volume']<=0 or v['volume']!=int(v['volume']) or v['turnover_krw']<=0):
            raise ValueError('CHART_WARMUP_INVALID_PRICE_OR_HALT')
        if (b.get('name',row['name'])!=row['name'] or b.get('action_boundary') or
            b.get('corporate_action_unresolved') or b['date'] in events):
            raise ValueError('CHART_WARMUP_ACTION_OR_IDENTITY_BOUNDARY')
        if previous and (positions[b['date']]!=positions[previous['date']]+1 or
                         abs(v['close']/float(previous['close'])-1)>.35):
            raise ValueError('CHART_WARMUP_SESSION_OR_PRICE_GAP')
        previous=b
    # All original bars remain the authoritative suffix; only earlier bars added.
    if bars[-len(frozen):]!=frozen:raise ValueError('CHART_WARMUP_CHANGED_FROZEN_BARS')
    return bars,dict(original_rows=len(frozen),display_input_rows=len(bars),
        added_prefix_rows=len(bars)-len(frozen),matched_overlap_rows=len(overlap),
        ma60_visible_points=60,selection_input_changed=False,
        original_bars_sha256=digest(json.dumps(frozen,sort_keys=True,separators=(',',':')).encode()),
        source_scope_certified_by_warmup=False)


def attach_locked_warmup(report,path):
    out=copy.deepcopy(report);picks=out.get('research_top2') or []
    if not picks:return out
    rows,sessions,audit=load_locked_panel(path,{r['ticker'] for r in picks})
    for row in picks:row['chart_bars'],row['chart_warmup_audit']=extend_bars(row,rows,sessions,audit)
    out.setdefault('input_provenance',{})['display_warmup']={
        'artifact_id':PANEL_ARTIFACT_ID,'archive_sha256':PANEL_ZIP_SHA256,
        'panel_sha256':audit['panel_sha256'],'original_selection_and_plans_unchanged':True}
    return out
