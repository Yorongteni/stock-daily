import pandas as pd, numpy as np, sys
c=pd.read_pickle(sys.argv[1]).ffill()
q=c["QQQ"]; stocks=[x for x in c.columns if x not in ("QQQ","SPY")]
ma200=c.rolling(200).mean(); ma50=c.rolling(50).mean()
COST=0.002
def run(N=5, look=(252,21), every=1, mkt=True, stop50=False, buffer=2, start="2015-06-01"):
    px=c[stocks]; mom=px.shift(look[1])/px.shift(look[0])-1
    days=c.index[c.index>=start]
    month_end=pd.Series(days,index=days).groupby([days.year,days.month]).last().values
    rebal=set(month_end[::every])
    hold={}; eq=1.0; curve=[]; cash=1.0; prev=None
    w={}
    for i,t in enumerate(days):
        if prev is not None:
            r=0
            for s,wt in list(w.items()):
                ret=c.at[t,s]/c.at[prev,s]-1
                if np.isnan(ret): ret=0
                w[s]=wt*(1+ret)
            eq=sum(w.values())+cash
            if stop50:
                for s in list(w):
                    if c.at[t,s]<ma50.at[t,s]:
                        cash+=w.pop(s)*(1-COST)
                eq=sum(w.values())+cash
        if t in rebal:
            tot=sum(w.values())+cash
            ok=(q[t]>ma200.at[t,"QQQ"]) if mkt else True
            target=[]
            if ok:
                m=mom.loc[t].dropna()
                m=m[(px.loc[t]>ma200.loc[t,stocks])[m.index]]
                rank=m.sort_values(ascending=False)
                keep=[s for s in w if s in rank.index[:N*buffer]]
                new=[s for s in rank.index if s not in keep][:max(0,N-len(keep))]
                target=(keep+new)[:N]
            # 리밸런스: 동일 비중
            turnover=0
            neww={}
            each=tot/N if target else 0
            for s in set(list(w)+target):
                cur=w.get(s,0); tgt=each if s in target else 0
                turnover+=abs(tgt-cur)
                if tgt>0: neww[s]=tgt
            tot-=turnover*COST
            each=tot/N if target else 0
            w={s:each for s in target}; cash=tot-each*len(target)
            eq=tot
        curve.append((t,eq)); prev=t
    e=pd.Series(dict(curve))
    return e
def stats(e,lab):
    yrs=(e.index[-1]-e.index[0]).days/365.25; cagr=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1
    dd=(e/e.cummax()-1).min()
    mret=e.resample("ME").last().pct_change().dropna()
    a=e[e.index<"2021-01-01"]; b=e[e.index>="2021-01-01"]
    ca=(a.iloc[-1]/a.iloc[0])**(1/((a.index[-1]-a.index[0]).days/365.25))-1
    cb=(b.iloc[-1]/b.iloc[0])**(1/((b.index[-1]-b.index[0]).days/365.25))-1
    yr=e.resample("YE").last().pct_change().dropna()
    print(f"{lab:46s} 연 {cagr*100:5.1f}% | 최대낙폭 {dd*100:5.1f}% | 월 승률 {(mret>0).mean()*100:3.0f}% | 2015~20 연 {ca*100:5.1f}% | 2021~ 연 {cb*100:5.1f}% | 최악 해 {yr.min()*100:5.1f}%",flush=True)
qq=c["QQQ"][c.index>="2015-06-01"]; stats(qq/qq.iloc[0],"비교: 나스닥100(QQQ) 그냥 보유")
sp=c["SPY"][c.index>="2015-06-01"]; stats(sp/sp.iloc[0],"비교: S&P500(SPY) 그냥 보유")
for args,lab in [
 (dict(N=5),"모멘텀 12-1개월 상위 5 · 매월 교체 · 시장필터"),
 (dict(N=5,mkt=False),"  └ 시장필터 없음"),
 (dict(N=5,every=2),"  └ 2개월마다 교체"),
 (dict(N=5,every=3),"  └ 3개월마다 교체"),
 (dict(N=5,stop50=True),"  └ 50일선 이탈 시 중간 매도"),
 (dict(N=5,look=(126,21)),"모멘텀 6-1개월 상위 5 · 매월"),
 (dict(N=3),"모멘텀 12-1 상위 3 · 매월"),
 (dict(N=8),"모멘텀 12-1 상위 8 · 매월"),
 (dict(N=5,buffer=1),"상위 5 · 버퍼 없음(순위 밖이면 바로 교체)"),
]:
    stats(run(**args),lab)
