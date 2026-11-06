"""Portrait charts of frozen paper plans and sourced bars, not new TOP2 picks."""
import argparse
import csv
from pathlib import Path
from c3_price_concordance_v1 import read_rows


def render(plans,prices,outdir,preview_dir=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    matplotlib.rcParams["svg.fonttype"]="none"
    matplotlib.rcParams["svg.hashsalt"]="c3-frozen-plan-v1"
    outputs=[]
    for plan in plans:
        series=sorted((day,bar) for (code,day),bar in prices.items() if code==plan["ticker"])
        if len(series)<30:
            raise ValueError("INSUFFICIENT_REAL_BARS_FOR_CHART")
        show=series[-50:]
        fig,(ax,vol)=plt.subplots(2,1,figsize=(7.2,10),sharex=True,
                                 gridspec_kw=dict(height_ratios=[4,1]),layout="constrained")
        fig.set_facecolor("#f7f8fb")
        ax.set_title(f"{plan['ticker']} | frozen C3 plan\nResearch only - CASH / no new buy approval",loc="left",fontsize=14)
        for i,(day,b) in enumerate(show):
            color="#df4b51" if b["close"]>=b["open"] else "#387de0"
            ax.plot([i,i],[b["low"],b["high"]],color=color,linewidth=1)
            ax.add_patch(Rectangle((i-.3,min(b["open"],b["close"])),.6,
                                  max(abs(b["close"]-b["open"]),b["close"]*.0003),facecolor=color,edgecolor=color))
            vol.bar(i,b["volume"],color=color,width=.6)
        for n,color in ((5,"#e6a21c"),(20,"#794ac2"),(60,"#009b8d")):
            values=[]
            for day,_ in show:
                prior=[b["close"] for d,b in series if d<=day]
                values.append(sum(prior[-n:])/n if len(prior)>=n else float('nan'))
            ax.plot(range(len(show)),values,label=f"MA{n}",color=color,linewidth=1.2)
        low,high=(float(plan[k]) for k in ("watch_low","watch_high"))
        ax.axhspan(low,high,color="#21a366",alpha=.12,label="Frozen watch band")
        for key,label,color in (("structure_stop","Structural stop","#cf2c3c"),
                                ("target1","Frozen T1 (resistance unverified)","#9b7200"),
                                ("target2","Frozen T2 (resistance unverified)","#8b6f38")):
            value=float(plan[key]);ax.axhline(value,color=color,ls="--",lw=1,label=f"{label}: {value:,.0f}")
        ax.set_ylabel("KRW | adjusted research prices")
        ax.ticklabel_format(style="plain",axis="y",useOffset=False)
        ax.grid(alpha=.15);ax.legend(loc="upper left",fontsize=7.3)
        vol.set_ylabel("Volume\nscope unknown",fontsize=8)
        ticks=list(range(0,len(show),10))+[len(show)-1]
        vol.set_xticks(ticks,[show[i][0][5:] for i in ticks],rotation=35)
        fig.supxlabel(f"Actual bars through {show[-1][0]} | pykrx adjusted / session scope uncertified\nPlan: {plan['plan_id']} | registration: {plan['registered_day']}\nT1/T2 are immutable plan levels; not verified current resistance.",fontsize=8)
        path=root/(plan["ticker"]+"_frozen_plan.svg")
        fig.savefig(path,format="svg",metadata={"Date":None})
        if preview_dir:
            preview=Path(preview_dir);preview.mkdir(parents=True,exist_ok=True)
            fig.savefig(preview/(plan["ticker"]+"_frozen_plan.png"),dpi=100)
        plt.close(fig)
        outputs.append(str(path))
    return outputs


def main():
    p=argparse.ArgumentParser();p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True);p.add_argument("--outdir",required=True)
    p.add_argument("--preview-dir")
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    print("\n".join(render(plans,read_rows(a.prices),a.outdir,a.preview_dir)))


if __name__=="__main__":
    main()
