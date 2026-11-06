"""Field-level source checks, not selection rules or trading permissions."""
import math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

KST=ZoneInfo('Asia/Seoul')
KRX_TABLE='https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT015'


def classify_bar(row):
    fields=('open','high','low','close','volume','turnover_krw')
    try:
        if any(isinstance(row[k],bool) for k in fields):return 'INVALID_NUMBER'
        o,h,l,c,v,a=(float(row[k]) for k in fields)
    except (ValueError,TypeError,KeyError):return 'MISSING_OR_INVALID_FIELD'
    if not all(math.isfinite(x) and x>=0 for x in (o,h,l,c,v,a)) or c<=0:return 'INVALID_NUMBER'
    if not v.is_integer():return 'FRACTIONAL_SHARE_VOLUME'
    if v==0:
        if a!=0:return 'ZERO_VOLUME_WITH_POSITIVE_TURNOVER'
        if (o,h,l)==(0,0,0) or o==h==l==c:return 'NO_TRADES_OBSERVED'
        return 'INVALID_NO_TRADE_OHLC'
    if a<=0:return 'POSITIVE_VOLUME_WITHOUT_TURNOVER'
    if not 0<l<=min(o,c)<=max(o,c)<=h:return 'OHLC_FIELD_OR_SESSION_CONFLICT'
    return 'VALID_TRADED_BAR'


def regular_contract(provider,trade_day,collected_at):
    """A dated file and post-close clock do not certify regular-only fields."""
    stamp=datetime.fromisoformat(collected_at.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('SOURCE_RECEIPT_TIMEZONE_REQUIRED')
    capture_day=stamp.astimezone(KST).date().isoformat()
    if trade_day>capture_day:raise ValueError('FUTURE_SOURCE_DAY')
    if provider=='FINANCEDATA_KRX_CACHE':
        price=('CURRENT_DAY_CLOSE_MAY_INCLUDE_AFTERMARKET' if trade_day==capture_day else 'HISTORICAL_QUERY_REGULAR_OHLC_PER_KRX_DOCUMENT')
        flow='ALL_TRADING_SESSIONS_PER_KRX_DOCUMENT'
        blockers=['VOLUME_AND_TURNOVER_NOT_REGULAR_ONLY']
        if trade_day==capture_day:blockers.append('CURRENT_DAY_CLOSE_NOT_REGULAR_ONLY')
        return {'provider':provider,'source_table':'MDCSTAT01501','documentation':KRX_TABLE,
                'original_trade_day':trade_day,'collected_at':collected_at,'capture_day_kst':capture_day,
                'ohlc_scope':price,'volume_scope':flow,'turnover_scope':flow,
                'volume_unit':'SHARES','turnover_unit':'KRW','units_from_upstream_query':{'share':'1','money':'1'},
                'regular_input_allowed':False,'blockers':blockers,
                'historical_is_based_on_original_query_time_not_later_download_time':True}
    return {'provider':provider,'original_trade_day':trade_day,'collected_at':collected_at,
            'ohlc_scope':'SOURCE_CONTRACT_NOT_ATTESTED','volume_scope':'SOURCE_CONTRACT_NOT_ATTESTED',
            'turnover_scope':'SOURCE_CONTRACT_NOT_ATTESTED','regular_input_allowed':False,
            'blockers':['EXPLICIT_REGULAR_ONLY_FIELD_CONTRACT_REQUIRED']}


def latest_observed_session(now,sessions):
    if now.tzinfo is None:raise ValueError('AWARE_CLOCK_REQUIRED')
    local=now.astimezone(KST);today=local.date().isoformat()
    eligible=[d for d in sessions if d<today or d==today and local.hour*60+local.minute>=930]
    return max(eligible) if eligible else None
