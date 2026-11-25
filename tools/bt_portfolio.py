"""자산 배분 포트폴리오 백테스트 (달러 기준, 월말 리밸런싱, 비용 0.2%/편도). python3 tools/bt_portfolio.py <etf.pkl>"""
import sys, numpy as np, pandas as pd
c = pd.read_pickle(sys.argv[1]).ffill()
c = c[c.index >= "2014-06-01"]
r = c.pct_change().fillna(0)
ma = c.rolling(200).mean()
CASH = (1.03) ** (1 / 252) - 1
me = set(c.resample("ME").last().index.map(lambda d: c.index[c.index <= d][-1]))
def run(weights, trend=False, start="2015-06-01"):
    days = c.index[c.index >= start]; w = {}; eq = 1.0; cash = 0.0; out = []; prev = None
    for t in days:
        if prev is not None:
            for k in w: w[k] *= 1 + r.at[t, k]
            cash *= 1 + CASH
            eq = sum(w.values()) + cash
        if prev is None or t in me:
            tgt = {}
            for k, v in weights.items():
                if trend and k != "CASH" and c.at[t, k] < ma.at[t, k]:
                    tgt["CASH"] = tgt.get("CASH", 0) + v
                else:
                    tgt[k] = tgt.get(k, 0) + v
            new = {k: eq * v for k, v in tgt.items() if k != "CASH"}
            turn = sum(abs(new.get(k, 0) - w.get(k, 0)) for k in set(new) | set(w))
            eq -= turn * 0.002
            w = {k: eq * v for k, v in tgt.items() if k != "CASH"}; cash = eq * tgt.get("CASH", 0)
        out.append((t, eq)); prev = t
    return pd.Series(dict(out))
def stats(e, lab):
    yrs = (e.index[-1] - e.index[0]).days / 365.25; cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = (e / e.cummax() - 1).min(); yr = e.resample("YE").last().pct_change().dropna()
    vol = e.pct_change().std() * np.sqrt(252)
    y22 = e[(e.index >= "2022-01-01") & (e.index <= "2022-12-31")]; y22 = y22.iloc[-1] / y22.iloc[0] - 1
    print(f"{lab:40s} 연 {cagr*100:5.1f}% | 변동성 {vol*100:4.1f}% | 최대낙폭 {dd*100:6.1f}% | 최악 해 {yr.min()*100:6.1f}% | 2022년 {y22*100:6.1f}%")
P = {
 "주식 100% (SPY)": {"SPY": 1},
 "나스닥 100% (QQQ)": {"QQQ": 1},
 "주식 60 / 채권 40": {"SPY": .6, "IEF": .4},
 "올웨더형 (주식30·장기채40·중기채15·금15)": {"SPY": .3, "TLT": .4, "IEF": .15, "GLD": .15},
 "성장 균형 (QQQ35·SPY25·금15·중기채15·현금10)": {"QQQ": .35, "SPY": .25, "GLD": .15, "IEF": .15, "CASH": .10},
 "4등분 (QQQ·SPY·금·중기채)": {"QQQ": .25, "SPY": .25, "GLD": .25, "IEF": .25},
}
for k, v in P.items():
    stats(run(v), k)
print("--- 각 자산이 200일선 아래면 그 몫은 현금 (월 1회 판단) ---")
for k in ("주식 60 / 채권 40", "성장 균형 (QQQ35·SPY25·금15·중기채15·현금10)", "4등분 (QQQ·SPY·금·중기채)"):
    stats(run(P[k], trend=True), k + " + 추세")
