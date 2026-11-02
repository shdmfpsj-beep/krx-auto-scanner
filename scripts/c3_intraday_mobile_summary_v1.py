"""Mobile summary for read-only intraday C3 research; no live orders."""
import argparse,json
from pathlib import Path
def render(quotes,watch):
    status=quotes.get("status","UNKNOWN")
    lines=["# C3 TOP2 장중 관찰 (연구용)","","**실제 주문 없음 · 검증된 시세가 없으면 매수 판단 보류**","",
           f"시세 수집 상태: {status}",f"점검 시각: {quotes.get('checked_at','미확인')}","","| 종목 | 장중 판정 | 관찰 가격 |","|---|---|---:|"]
    rows=watch.get("alerts",[])
    if not rows:lines.append("| 대상 없음 | 관찰 불가 | - |")
    for item in rows:
        price=item.get("observed_price")
        label=item.get("status","NO_VERIFIED_QUOTE")
        lines.append(f"| {str(item.get('name') or item.get('ticker') or '미확인').replace('|','/')} | {label} | {f'{price:,.0f}원' if isinstance(price,(int,float)) else '-'} |")
    if status=="PENDING_PROVIDER_CREDENTIALS":
        lines.extend(["","**다음 필수 조치:** KIS_APP_KEY 및 KIS_APP_SECRET 인증정보 연결 전에는 장중 시세 수집이 불가능합니다.",
                      "현재 연결된 키움 REST API는 이 KIS 수집기의 대체 인증정보가 아닙니다."])
    lines.extend(["","장중 구조손절선 이탈은 종가 손절 확정이 아닙니다.",
                  "시세 공급원·거래소 구분·시간이 검증되지 않은 경우 가상 매수를 기록하지 않습니다.",""])
    return "\n".join(lines)
def main():
    p=argparse.ArgumentParser();p.add_argument("--quotes",required=True);p.add_argument("--watch",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    q=json.loads(Path(a.quotes).read_text(encoding="utf-8"))
    w=json.loads(Path(a.watch).read_text(encoding="utf-8"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(render(q,w),encoding="utf-8")
    print("C3_INTRADAY_MOBILE_SUMMARY_WRITTEN",out)
if __name__=="__main__":main()
