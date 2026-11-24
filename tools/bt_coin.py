"""코인 3배 단타 방법 비교 백테스트 — "물어본 그 순간 시장가 진입" 기준.

여러 트레이더 원칙(추세 눌림 · 유동성 스윕+구조 전환 · 돌파 모멘텀 · 과열 되돌림 · 비트코인 방향 모멘텀)과
지금 쓰는 원픽 방식(현재 방식)을 같은 조건으로 OKX 과거 시세에 돌려 비교한다.

  python3 tools/bt_coin.py <tools/bt_fetch.py 로 받은 폴더> [결과 JSON 경로]

규칙
- 결정 시각: 4시간마다 (UTC 0·4·8·12·16·20시). 그 시각까지 끝난 봉만 본다 (미래 정보 없음).
- 진입: 결정 시각의 15분봉 시가에 시장가 + 슬리피지 0.05%. 수수료 테이커 0.055% × 2.
- 청산: 15분봉으로 SL·TP 판정, 같은 봉에서 둘 다 닿으면 손절로 (보수적). 24시간 안에 안 나면 그 시각 종가.
- 방법마다 결정 시각당 1개(점수 1위)만 = 원픽. 기간 앞 60%(학습)와 뒤 40%(검증)를 따로 집계.
- 한계: 지금 거래대금 상위 코인만 써서 생존 편향이 있고, 미결제약정·펀딩비 과거값은 없어 그 조건은 빠진다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.055 * 2 / 100          # 왕복 테이커
SLIP = 0.05 / 100              # 진입·청산 각각
LEV = 3
HOLD = pd.Timedelta(hours=24)


def load(folder: Path):
    insts = json.load(open(folder / "universe.json"))
    h1, m15 = {}, {}
    for inst in insts:
        try:
            a = json.load(open(folder / f"{inst}_1H.json"))
            b = json.load(open(folder / f"{inst}_15m.json"))
        except FileNotFoundError:
            continue
        if len(a) < 500 or len(b) < 2000:
            continue
        for src, dst in ((a, h1), (b, m15)):
            df = pd.DataFrame(src, columns=["t", "Open", "High", "Low", "Close", "Volume"])
            df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
            dst[inst.replace("-USDT-SWAP", "")] = df.set_index("t").sort_index()
    return h1, m15


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def feats_1h(df: pd.DataFrame) -> pd.DataFrame:
    """1시간봉 지표. 인덱스 = 봉 시작 시각, 값은 그 봉이 끝난 뒤(시작+1h) 알 수 있는 것."""
    f = pd.DataFrame(index=df.index)
    c = df.Close
    f["close"], f["open"], f["high"], f["low"] = c, df.Open, df.High, df.Low
    f["ema20"] = ema(c, 20)
    f["rsi"] = rsi(c)
    tr = pd.concat([df.High - df.Low, (df.High - c.shift()).abs(), (df.Low - c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = tr.rolling(14).mean()
    f["atr_pct"] = f["atr"] / c * 100
    f["dist"] = (c / f["ema20"] - 1) * 100
    f["chg24"] = (c / c.shift(24) - 1) * 100
    f["chg4"] = (c / c.shift(4) - 1) * 100
    f["hi24"] = df.High.rolling(24).max()
    f["lo24"] = df.Low.rolling(24).min()
    f["hi24_prev"] = df.High.shift(1).rolling(24).max()
    f["lo24_prev"] = df.Low.shift(1).rolling(24).min()
    f["range24"] = (f["hi24"] - f["lo24"]) / c * 100
    v = df.Volume
    f["vol_ratio"] = v.rolling(3).mean() / v.shift(3).rolling(24).mean()
    f["vol1"] = v / v.shift(1).rolling(24).mean()
    rng = (df.High - df.Low).replace(0, np.nan)
    f["bull"] = c > df.Open
    f["bear"] = c < df.Open
    f["lower_wick"] = (np.minimum(df.Open, c) - df.Low) / rng
    f["upper_wick"] = (df.High - np.maximum(df.Open, c)) / rng
    f["close_pos"] = (c - df.Low) / rng
    f["swing_lo6"] = df.Low.rolling(6).min()
    f["swing_hi6"] = df.High.rolling(6).max()
    # 4시간봉 (끝난 4시간봉 값만 1시간봉에 붙임)
    h4 = df.resample("4h", label="left", closed="left").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    e20, e50 = ema(h4.Close, 20), ema(h4.Close, 50)
    t4 = pd.DataFrame({"c4": h4.Close, "e20_4": e20, "e50_4": e50, "rsi4": rsi(h4.Close)})
    t4.index = t4.index + pd.Timedelta(hours=4) - pd.Timedelta(hours=1)   # 4시간봉이 끝나는 1시간봉 위치에
    f = f.join(t4, how="left")
    f[["c4", "e20_4", "e50_4", "rsi4"]] = f[["c4", "e20_4", "e50_4", "rsi4"]].ffill()
    f["trend4"] = np.where((f.c4 > f.e50_4) & (f.e20_4 > f.e50_4), 1, np.where((f.c4 < f.e50_4) & (f.e20_4 < f.e50_4), -1, 0))
    return f


# ───────────── 방법들: (row, btc_row, m15 최근 봉들) → [(side, sl, tp, score)] ─────────────
def _sl_tp(entry, side, sl, rr):
    risk = abs(entry - sl)
    tp = entry + rr * risk if side == "LONG" else entry - rr * risk
    return sl, tp


def m_current(r, b, m, entry):
    """지금 원픽 방식 근사 (미결제약정·펀딩비 조건 제외 → 6개 중 5개 이상)."""
    out = []
    for side in ("LONG", "SHORT"):
        L = side == "LONG"
        rel = r.chg24 - b.chg24
        chk = [r.trend4 == (1 if L else -1),
               (-1.8 <= r.dist <= 0.8 and 36 <= r.rsi <= 58) if L else (-0.8 <= r.dist <= 1.8 and 42 <= r.rsi <= 64),
               (r.bull or r.lower_wick >= 0.45) if L else (r.bear or r.upper_wick >= 0.45),
               r.vol_ratio >= 1.1, rel >= 0 if L else rel <= 0, r.range24 >= 3.0]
        near = (r.close <= r.lo24 * 1.005 and r.close < r.e20_4) if L else (r.close >= r.hi24 * 0.995 and r.close > r.e20_4)
        chase = (r.rsi >= 72 and r.dist >= 3.5) if L else (r.rsi <= 28 and r.dist <= -3.5)
        if not (chk[0] and chk[4] and chk[5]) or near or chase or sum(chk) < 5:
            continue
        lvl = r.swing_lo6 * (1 - 0.002) if L else r.swing_hi6 * (1 + 0.002)
        d = min(max(abs(entry - lvl) / entry * 100, 1.2), 1.8)
        sl = entry * (1 - d / 100) if L else entry * (1 + d / 100)
        tp = entry * (1 + 0.0245) if L else entry * (1 - 0.0245)
        out.append((side, sl, tp, sum(chk) + min(r.vol_ratio, 3) * 0.3))
    return out


def m_pullback(r, b, m, entry):
    """추세 눌림: 4시간 추세 방향 + 1시간 20선까지 되돌림 후 다시 추세 방향 마감 + 15분봉 방향 확인. SL 직전 스윙 밖, TP 2R."""
    out = []
    for side in ("LONG", "SHORT"):
        L = side == "LONG"
        if r.trend4 != (1 if L else -1):
            continue
        touched = (r.low <= r.ema20 * 1.002 and r.close > r.ema20) if L else (r.high >= r.ema20 * 0.998 and r.close < r.ema20)
        if not touched or not ((40 <= r.rsi <= 60) if L else (40 <= r.rsi <= 60)):
            continue
        last = m.iloc[-1]
        if not ((last.Close > last.Open) if L else (last.Close < last.Open)):
            continue
        sl = r.swing_lo6 - 0.1 * r.atr if L else r.swing_hi6 + 0.1 * r.atr
        d = abs(entry - sl) / entry * 100
        if not 0.5 <= d <= 3.0 or (L and sl >= entry) or (not L and sl <= entry):
            continue
        out.append((side, *_sl_tp(entry, side, sl, 2.0), r.vol_ratio))
    return out


def m_sweep(r, b, m, entry, htf=True):
    """유동성 스윕 + 구조 전환 (15분봉): 최근 2시간 안에 24시간 저점(고점)을 찔렀다가 되돌아오고,
    스윕 뒤 작은 고점(저점)을 마감으로 넘김. SL 스윕 끝 밖, TP 2R. htf=True 면 4시간 추세가 반대가 아닐 때만."""
    out = []
    if len(m) < 104:
        return out
    base, recent = m.iloc[-104:-8], m.iloc[-8:]
    for side in ("LONG", "SHORT"):
        L = side == "LONG"
        if htf and r.trend4 == (-1 if L else 1):
            continue
        lvl = base.Low.min() if L else base.High.max()
        ext = recent.Low.values if L else recent.High.values
        s = int(np.argmin(ext)) if L else int(np.argmax(ext))
        if s >= len(recent) - 1:
            continue
        swept = ext[s] < lvl if L else ext[s] > lvl
        last = recent.iloc[-1]
        back = last.Close > lvl if L else last.Close < lvl
        mid = recent.iloc[s:-1]
        mss = last.Close > mid.High.max() if L else last.Close < mid.Low.min()
        if not (swept and back and mss):
            continue
        sl = ext[s] * (1 - 0.0005) if L else ext[s] * (1 + 0.0005)
        d = abs(entry - sl) / entry * 100
        if not 0.4 <= d <= 3.0:
            continue
        out.append((side, *_sl_tp(entry, side, sl, 2.0), abs(last.Close - lvl) / lvl * 100))
    return out


def m_sweep_any(r, b, m, entry):
    return m_sweep(r, b, m, entry, htf=False)


def m_breakout(r, b, m, entry):
    """돌파 모멘텀: 1시간봉이 24시간 고점(저점)을 거래량 1.5배 이상으로 뚫고 봉 위(아래)쪽에서 마감. SL 1.5 ATR, TP 2R."""
    out = []
    for side in ("LONG", "SHORT"):
        L = side == "LONG"
        brk = (r.close > r.hi24_prev and r.close_pos >= 0.75) if L else (r.close < r.lo24_prev and r.close_pos <= 0.25)
        if not brk or r.vol1 < 1.5:
            continue
        sl = entry - 1.5 * r.atr if L else entry + 1.5 * r.atr
        out.append((side, *_sl_tp(entry, side, sl, 2.0), r.vol1))
    return out


def m_fade(r, b, m, entry):
    """과열 되돌림: 4시간에 1시간 평균 변동폭의 3배 넘게 한쪽으로 가고 1시간 RSI 극단(25/75) → 반대로. SL 극단 밖, TP 1.5R."""
    out = []
    for side in ("LONG", "SHORT"):
        L = side == "LONG"
        ok = (r.chg4 <= -3 * r.atr_pct and r.rsi < 25) if L else (r.chg4 >= 3 * r.atr_pct and r.rsi > 75)
        if not ok:
            continue
        sl = (r.swing_lo6 - 0.2 * r.atr) if L else (r.swing_hi6 + 0.2 * r.atr)
        d = abs(entry - sl) / entry * 100
        if not 0.4 <= d <= 4.0:
            continue
        out.append((side, *_sl_tp(entry, side, sl, 1.5), abs(r.chg4)))
    return out


def m_btc_mom(r, b, m, entry):
    """비트코인 방향 모멘텀: 비트코인이 4시간 20선 위 + 24시간 상승이면 비트코인보다 강한 코인 롱 (반대면 약한 코인 숏).
    코인도 1시간 20선 위(아래). SL 1.5 ATR, TP 2R."""
    out = []
    up = b.close > b.e20_4 and b.chg24 > 0
    dn = b.close < b.e20_4 and b.chg24 < 0
    rel = r.chg24 - b.chg24
    if up and rel > 0 and r.close > r.ema20 and r.rsi < 70:
        out.append(("LONG", *_sl_tp(entry, "LONG", entry - 1.5 * r.atr, 2.0), rel))
    if dn and rel < 0 and r.close < r.ema20 and r.rsi > 30:
        out.append(("SHORT", *_sl_tp(entry, "SHORT", entry + 1.5 * r.atr, 2.0), -rel))
    return out


_RNG = np.random.default_rng(7)


def m_random(r, b, m, entry):
    """기준선: 아무 근거 없이 무작위 방향 (점수도 무작위) — SL 1.5 ATR, TP 2R. 이보다 못하면 방법이 의미 없음."""
    side = "LONG" if _RNG.random() < 0.5 else "SHORT"
    sl = entry - 1.5 * r.atr if side == "LONG" else entry + 1.5 * r.atr
    return [(side, *_sl_tp(entry, side, sl, 2.0), _RNG.random())]


METHODS = {
    "무작위 (기준선)": m_random,
    "현재 방식 (참고: OI·펀딩 제외 근사)": m_current,
    "추세 눌림 (4h 추세 + 1h 20선 되돌림, 2R)": m_pullback,
    "유동성 스윕+구조 전환 (15m, 4h 역추세 제외, 2R)": m_sweep,
    "유동성 스윕+구조 전환 (15m, 추세 무관, 2R)": m_sweep_any,
    "돌파 모멘텀 (24h 고저 돌파 + 거래량, 2R)": m_breakout,
    "과열 되돌림 (4h 급변 + RSI 극단, 1.5R)": m_fade,
    "비트코인 방향 모멘텀 (상대강도, 2R)": m_btc_mom,
}


def simulate(m15: pd.DataFrame, t0, side, entry, sl, tp):
    """15분봉으로 결과. 반환: (가격 수익률 %, 결과)."""
    L = side == "LONG"
    w = m15.loc[t0: t0 + HOLD - pd.Timedelta(minutes=15)]
    for _, k in w.iterrows():
        if (k.Low <= sl) if L else (k.High >= sl):
            px, res = sl, "LOSS"
            break
        if (k.High >= tp) if L else (k.Low <= tp):
            px, res = tp, "WIN"
            break
    else:
        if w.empty:
            return None
        px, res = w.Close.iloc[-1], "TIME"
    exit_px = px * (1 - SLIP) if L else px * (1 + SLIP)
    g = (exit_px / entry - 1) * 100 if L else (1 - exit_px / entry) * 100
    return g - FEE * 100, res


def run(folder: Path):
    h1, m15 = load(folder)
    F = {k: feats_1h(v) for k, v in h1.items()}
    btc = F["BTC"]
    start = max(v.index[0] for v in m15.values()) + pd.Timedelta(days=2)
    end = min(v.index[-1] for v in m15.values()) - HOLD
    times = pd.date_range(start.ceil("4h"), end, freq="4h", tz="UTC")
    trades = {k: [] for k in METHODS}
    allsig = {k: [] for k in METHODS}
    for T in times:
        tb = T - pd.Timedelta(hours=1)          # 마지막으로 끝난 1시간봉 (시작 시각)
        if tb not in btc.index:
            continue
        b = btc.loc[tb]
        cands = {k: [] for k in METHODS}
        for sym, f in F.items():
            if tb not in f.index or sym not in m15:
                continue
            r = f.loc[tb]
            if r.isna()[["ema20", "rsi", "atr", "e50_4", "vol_ratio", "hi24_prev"]].any():
                continue
            mm = m15[sym]
            past = mm.loc[: T - pd.Timedelta(minutes=15)].tail(120)
            if T not in mm.index or len(past) < 20:
                continue
            o = mm.loc[T, "Open"]
            for name, fn in METHODS.items():
                for side, sl, tp, sc in fn(r, b, past, o):
                    entry = o * (1 + SLIP) if side == "LONG" else o * (1 - SLIP)
                    cands[name].append((sc, sym, side, entry, sl, tp))
        for name, cs in cands.items():
            if not cs:
                continue
            for sc, sym, side, entry, sl, tp in cs:          # 1위만이 아니라 신호 전체 (표본 늘리기)
                res_a = simulate(m15[sym], T, side, entry, sl, tp)
                if res_a:
                    allsig[name].append({"t": T.isoformat(), "side": side, "ret": round(res_a[0], 3), "sym": sym, "res": res_a[1]})
            sc, sym, side, entry, sl, tp = max(cs, key=lambda x: x[0])
            res = simulate(m15[sym], T, side, entry, sl, tp)
            if res:
                risk = abs(entry - sl) / entry * 100
                trades[name].append({"t": T.isoformat(), "sym": sym, "side": side, "ret": round(res[0], 3), "res": res[1],
                                     "risk": round(risk, 3), "R": round(res[0] / risk, 3) if risk else None,
                                     "n_cands": len(cs)})
    return trades, times, allsig


def summarize(ts: list[dict]) -> dict:
    if not ts:
        return {"n": 0}
    r = np.array([t["ret"] for t in ts])
    wins = r[r > 0]
    loss = r[r <= 0]
    streak = mx = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    eq = np.cumsum(r * LEV)
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    return {"n": len(r), "win_rate": round(len(wins) / len(r) * 100, 1),
            "avg_ret_pct": round(float(r.mean()), 3), "avg_roe3": round(float(r.mean()) * LEV, 2),
            "pf": round(float(wins.sum() / -loss.sum()), 2) if loss.sum() < 0 else None,
            "sum_roe3": round(float(r.sum()) * LEV, 1), "max_loss_streak": mx, "max_dd_roe3": round(dd, 1),
            "long_n": sum(1 for t in ts if t["side"] == "LONG"),
            "long_avg_roe3": round(float(np.mean([t["ret"] for t in ts if t["side"] == "LONG"] or [0])) * LEV, 2),
            "short_n": sum(1 for t in ts if t["side"] == "SHORT"),
            "short_avg_roe3": round(float(np.mean([t["ret"] for t in ts if t["side"] == "SHORT"] or [0])) * LEV, 2)}


def main():
    folder = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    trades, times, allsig = run(folder)
    cut = times[int(len(times) * 0.6)]
    res = {"period": [times[0].isoformat(), times[-1].isoformat()], "split": cut.isoformat(),
           "decisions": len(times), "methods": {}}
    for name, ts in trades.items():
        tr = [t for t in ts if t["t"] < cut.isoformat()]
        te = [t for t in ts if t["t"] >= cut.isoformat()]
        sa = allsig[name]
        res["methods"][name] = {"all": summarize(ts), "train": summarize(tr), "test": summarize(te),
                                "signals_all": summarize(sa),
                                "signals_test": summarize([t for t in sa if t["t"] >= cut.isoformat()]), "trades": ts}
        a, b_, c = summarize(ts), summarize(tr), summarize(te)
        print(f"{name}\n  원픽 전체 {a}\n  원픽 학습 {b_}\n  원픽 검증 {c}\n  신호 전체 {summarize(sa)}")
    if out:
        json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
