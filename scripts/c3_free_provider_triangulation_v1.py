"""Summarize experimental free-provider agreement without granting certification."""
import argparse
import json
from pathlib import Path

def summarize(naver,yahoo):
    def counts(d):
        if d.get("comparison_count",0)<1:
            raise ValueError("EMPTY_COMPARISON")
        r=d.get("result_counts",{})
        n=d["comparison_count"]
        m=r.get("MATCH",0)
        x=r.get("MISMATCH",0)
        if any(type(v) is not int or v<0 for v in (n,m,x)) or m+x!=n:
            raise ValueError("INVALID_CONCORDANCE_COUNTS")
        return dict(rows=n,matches=m,mismatches=x)
    n=counts(naver)
    y=counts(yahoo)
    return dict(schema="C3_FREE_PROVIDER_TRIANGULATION_V1",
                naver_vs_pykrx=n,yahoo_vs_pykrx=y,
                observed_naver_agreement=n["mismatches"]==0,
                naver_source_independence_verified=False,
                naver_may_share_pykrx_adjusted_upstream=True,
                matching_rows_are_not_independent_validation=True,
                yahoo_adjustment_basis_verified=False,
                official_exchange_ohlcv_verified=False,
                regular_only_certified=False,
                trade_approved=False,orders_enabled=False,
                next_step="VERIFY_KRX_OFFICIAL_SOURCE_AND_YAHOO_ADJUSTMENT_BASIS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--naver",required=True)
    p.add_argument("--yahoo",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--markdown",required=True)
    a=p.parse_args()
    result=summarize(json.loads(Path(a.naver).read_text(encoding="utf-8")),
                     json.loads(Path(a.yahoo).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    n=result["naver_vs_pykrx"]
    y=result["yahoo_vs_pykrx"]
    md=("### 무료 3경로 가격 교차비교 (인증 아님)\n"
        "| 비교 | 일치 | 불일치 | 전체 |\n|---|---:|---:|---:|\n"
        f"| NAVER ↔ pykrx | {n['matches']} | {n['mismatches']} | {n['rows']} |\n"
        f"| Yahoo ↔ pykrx | {y['matches']} | {y['mismatches']} | {y['rows']} |\n\n"
        "> pykrx 수정주가 조회는 NAVER로 연결될 수 있으므로 이 일치는 독립 검증이 아닙니다. Yahoo 수정주가·세션 범위 미확인. 실전 매매 차단.\n")
    Path(a.markdown).write_text(md,encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":
    main()
