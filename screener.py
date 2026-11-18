"""3년 실적 + 밸류에이션 + 가격 추세로 종목을 스크리닝.

- 저평가: 업종 대비 낮은 PER·PBR, 3년 연속 흑자, 순이익 성장, ROE
- 성장 기대: 3년 매출 성장률, 최근 매출·이익 성장, 이익 전망 개선, 6개월 주가 모멘텀
- 고평가 위험: 업종 대비 과도한 PER·PSR, 200일선 대비 과열, 높은 RSI, 성장 둔화

실적(재무제표)은 분기마다 바뀌므로 일주일에 한 번만 새로 받아 cache/에 저장하고,
주가는 매일 새로 받습니다.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from indicators import rsi
from netretry import retry

SECTOR_KO = {"Technology": "기술", "Financial Services": "금융", "Healthcare": "헬스케어",
             "Industrials": "산업재", "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재",
             "Energy": "에너지", "Utilities": "유틸리티", "Basic Materials": "소재",
             "Communication Services": "커뮤니케이션", "Real Estate": "부동산"}
CACHE = Path("cache/fundamentals.json")
INFO_KEYS = ["trailingPE", "forwardPE", "priceToBook", "priceToSalesTrailing12Months",
             "returnOnEquity", "revenueGrowth", "earningsGrowth", "profitMargins",
             "marketCap", "sector", "industry", "currency", "currentPrice", "regularMarketPrice"]


# ───────────────────────── 데이터 수집 ─────────────────────────
def _annual(stmt: pd.DataFrame, names, n_last: int = 4) -> list:
    """재무제표에서 최근 n_last 개 기간 값 (오래된 → 최근).
    연간은 4개(= 3년 전 → 올해, 3년 성장률 계산용). 예전에는 3개만 받아 '3년 성장'이 실제로는 2년 성장이었다."""
    for n in names:
        if stmt is not None and n in stmt.index:
            vals = stmt.loc[n].dropna()
            vals = vals.sort_index().tail(n_last)
            return [float(v) for v in vals.values]
    return []


def _fetch_one(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    out = {k: info.get(k) for k in INFO_KEYS}
    stmt = t.income_stmt
    out["revenue"] = _annual(stmt, ["Total Revenue", "Operating Revenue"])
    out["op_income"] = _annual(stmt, ["Operating Income"])
    out["net_income"] = _annual(stmt, ["Net Income", "Net Income Common Stockholders"])
    # 분기 재무제표 (최근 5개 분기) — 야후 요약값(revenueGrowth·earningsGrowth)을 직접 계산한 전년 동기 대비로 검증
    try:
        q = t.quarterly_income_stmt
        out["q_revenue"] = _annual(q, ["Total Revenue", "Operating Revenue"], 5)
        out["q_net_income"] = _annual(q, ["Net Income", "Net Income Common Stockholders"], 5)
    except Exception:  # noqa: BLE001
        out["q_revenue"], out["q_net_income"] = [], []
    out["fetched"] = datetime.now().strftime("%Y-%m-%d")
    return out


def load_fundamentals(universe: dict, refresh_days: int = 7, demo=False) -> dict:
    if demo:
        return _fake_fundamentals(universe)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    limit = (datetime.now() - timedelta(days=refresh_days)).strftime("%Y-%m-%d")
    # 분기 재무제표(q_revenue)가 없는 예전 캐시(연간 3개 값만 저장)는 다시 받는다 — 3년 성장률을 제대로 계산하기 위해
    todo = [t for t in universe if cache.get(t, {}).get("fetched", "") < limit or "q_revenue" not in cache.get(t, {})]
    if todo:
        print(f"  … 실적 데이터 수집 {len(todo)}종목 (주 1회, 몇 분 걸릴 수 있음)")
    for i, t in enumerate(todo, 1):
        try:
            cache[t] = retry(_fetch_one, t, tries=2, base=2, label=t)
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ {t} 실적 수집 실패: {e}")
        if i % 20 == 0:
            print(f"    {i}/{len(todo)}")
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.4)  # 야후 서버 차단 방지
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {t: cache[t] for t in universe if t in cache}


def load_prices(tickers: list, demo=False, period="5y") -> tuple[dict, dict]:
    """종가와 거래대금(종가×거래량) 시계열."""
    if demo:
        p = _fake_prices(tickers)
        return p, {t: s * 1e6 for t, s in p.items()}
    import yfinance as yf
    df = retry(yf.download, tickers, period=period, auto_adjust=True, group_by="ticker",
               threads=True, progress=False, label="종목 주가")
    out, val = {}, {}
    for t in tickers:
        try:
            d = df[t] if len(tickers) > 1 else df
            s = d["Close"].dropna()
            if len(s) > 60:
                if getattr(s.index, "tz", None) is not None:
                    s.index = s.index.tz_localize(None)
                out[t] = s
                if "Volume" in d:
                    v = (d["Close"] * d["Volume"]).dropna()
                    if getattr(v.index, "tz", None) is not None:
                        v.index = v.index.tz_localize(None)
                    val[t] = v
        except KeyError:
            pass
    return out, val


# ───────────────────────── 지표 계산 ─────────────────────────
def _cagr(vals, years: int = 3):
    """연평균 성장률 = (최신 / years년 전) ** (1/years) − 1. years+1 개 값이 없으면 계산하지 않는다
    (예전 캐시처럼 3개 값뿐이면 2년 성장률을 '3년'이라 부르게 되므로)."""
    vals = list(vals or [])[-(years + 1):]
    if len(vals) < years + 1 or vals[0] <= 0 or vals[-1] <= 0:
        return None
    return (vals[-1] / vals[0]) ** (1 / years) - 1


def _yoy_q(vals):
    """최근 분기 전년 동기 대비 (5개 분기: 4분기 전 → 최근). 분모가 0 이하면 계산하지 않는다."""
    vals = list(vals or [])
    if len(vals) < 5 or vals[-5] <= 0:
        return None
    return vals[-1] / vals[-5] - 1


def _checked_growth(reported, computed, label: str, ticker: str):
    """야후 요약 성장률을 분기 재무제표로 직접 계산한 값과 대조. 직접 계산값이 있으면 그것을 쓴다."""
    if computed is None:
        return reported
    if reported is not None and abs(reported - computed) > 0.2:
        print(f"    ⚠ {ticker} {label}: 야후 요약 {reported * 100:+.0f}% ↔ 분기 재무제표 계산 {computed * 100:+.0f}% → 계산값 사용")
    return computed


def build_table(universe: dict, fund: dict, prices: dict) -> pd.DataFrame:
    rows = []
    for t, (name, market, cat) in universe.items():
        f = fund.get(t)
        if not f:
            continue
        rev, ni = f.get("revenue") or [], f.get("net_income") or []
        # 매출·순이익이 뒤바뀐 데이터 방지: 순이익이 매출보다 크면 그 기간 재무는 쓰지 않는다
        if rev and ni and len(rev) == len(ni) and any(n > r > 0 for r, n in zip(rev, ni)):
            print(f"    ⚠ {t} 순이익이 매출보다 큼 → 재무 성장률 계산 제외")
            rev, ni = [], []
        p = prices.get(t)
        # 실적은 주 1회 받으므로, 받은 날 이후 주가 변화만큼 PER·PBR·PSR을 보정
        px0 = f.get("currentPrice") or f.get("regularMarketPrice")
        adj = float(p.iloc[-1]) / px0 if p is not None and px0 else 1.0
        if not 0.2 < adj < 5:
            adj = 1.0

        def mult(k, f=f, adj=adj):
            return None if f.get(k) is None else f.get(k) * adj
        row = {
            "ticker": t, "name": name, "market": market, "category": cat,
            "sector": SECTOR_KO.get(f.get("sector"), f.get("sector") or "기타"), "industry": f.get("industry") or "",
            "pe": mult("trailingPE"), "fpe": mult("forwardPE"),
            "pb": mult("priceToBook"), "ps": mult("priceToSalesTrailing12Months"),
            "roe": f.get("returnOnEquity"),
            "rev_g": _checked_growth(f.get("revenueGrowth"), _yoy_q(f.get("q_revenue")), "최근 분기 매출 성장", t),
            "eps_g": _checked_growth(f.get("earningsGrowth"), _yoy_q(f.get("q_net_income")), "최근 분기 이익 성장", t),
            "margin": f.get("profitMargins"),
            "rev_cagr": _cagr(rev), "ni_cagr": _cagr(ni),
            "ni_all_pos": bool(ni) and len(ni) >= 2 and all(v > 0 for v in ni[-3:]),   # 최근 3개 회계연도 연속 흑자
            "ni_last": ni[-1] if ni else None,
            "years": len(rev),
        }
        # 국내 종목은 야후가 PER·PBR을 비워 두는 경우가 많아 시가총액/순이익, PER×ROE로 보완
        mc = mult("marketCap")
        if row["pe"] is None and mc and ni and ni[-1] > 0:
            row["pe"] = mc / ni[-1]
        # 일회성 손익에 덜 흔들리는 PER: 최근 3년 평균 순이익 기준 (고평가 판정 교차 확인용)
        pos = [v for v in ni[-3:] if v > 0]
        if mc and len(pos) == len(ni[-3:]) and pos:
            row["pe_avg3"] = mc / (sum(pos) / len(pos))
        if row["pb"] is None and row["pe"] and row["roe"] and row["roe"] > 0:
            row["pb"] = row["pe"] * row["roe"]
        if p is not None and len(p) > 25:
            row["ret_1d"] = p.iloc[-1] / p.iloc[-2] - 1
            row["ret_5d"] = p.iloc[-1] / p.iloc[-6] - 1
            row["ret_20d"] = p.iloc[-1] / p.iloc[-21] - 1
            row["above_ma20"] = bool(p.iloc[-1] > p.tail(20).mean())
        if p is not None and len(p) > 130:
            row["ret_6m"] = p.iloc[-1] / p.iloc[-127] - 1
            row["rsi"] = float(rsi(p).iloc[-1])
            ma200 = p.rolling(min(200, len(p) - 1)).mean().iloc[-1]
            row["vs_ma200"] = p.iloc[-1] / ma200 - 1
        rows.append(row)
    df = pd.DataFrame(rows)
    num = ["pe", "pe_avg3", "fpe", "pb", "ps", "roe", "rev_g", "eps_g", "margin",
           "rev_cagr", "ni_cagr", "ret_6m", "rsi", "vs_ma200", "ret_1d", "ret_5d", "ret_20d"]
    for c in num:
        if c not in df:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.loc[df.pe <= 0, "pe"] = np.nan

    # 비교 기준 PER: 같은 시장·같은 분야(3개 이상) → 같은 시장·야후 업종 → 시장 전체
    def med(keys):
        g = df.groupby(keys)["pe"]
        m = g.median()
        return m[g.count() >= 3]
    by_cat, by_sec, by_mkt = med(["market", "category"]), med(["market", "sector"]), df.groupby("market")["pe"].median()
    df["pe_med"] = [by_cat.get((m, c), by_sec.get((m, s), by_mkt.get(m)))
                    for m, c, s in zip(df.market, df.category, df.sector)]
    df["pe_rel"] = df.pe / df.pe_med
    df["fpe_rel"] = df.fpe / df.pe_med
    df["pe_avg3_rel"] = df.pe_avg3 / df.pe_med
    df["fwd_up"] = df.pe / df.fpe - 1  # +면 내년 이익 증가 예상
    return df


def _pct(s: pd.Series, higher_better=True):
    """시장별 백분위 (0~1). 값이 없으면 중간값 0.5."""
    r = s.rank(pct=True)
    return (r if higher_better else 1 - r).fillna(0.5)


def _by_market(df, col, higher_better=True):
    return df.groupby("market")[col].transform(lambda s: _pct(s, higher_better))


def _metrics(d: dict) -> dict:
    """값이 없는 항목('–')은 빼서, 리포트·해설에 '최근 이익 성장 –'처럼 빈 칸이 찍히지 않게 한다."""
    return {k: v for k, v in d.items() if v and not str(v).startswith("–")}


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return {"x": f"{v:.1f}배", "p": f"{v * 100:+.0f}%", "pp": f"{v * 100:.0f}%", "n": f"{v:.0f}"}[kind]


# ───────────────────────── 스크리닝 ─────────────────────────
def screen(df: pd.DataFrame, top_n=5, cap=1, hist: dict | None = None) -> dict:
    out = {}

    # 1) 저평가: 3년 흑자 + PER 있음 + ROE 양수
    v = df[df.ni_all_pos & df.pe.notna() & (df.roe > 0)].copy()
    if len(v):
        v["score"] = (_by_market(v, "pe_rel", False) * 0.35 + _by_market(v, "pb", False) * 0.2
                      + _by_market(v, "roe") * 0.2 + _by_market(v, "ni_cagr") * 0.25)
        v = v[(v.pe_rel < 1) & (v.ni_cagr.fillna(0) > -0.05)]
        out["value"] = [{
            **_base(r),
            "metrics": _metrics({"PER": _fmt(r.pe, "x"), "업종 PER": _fmt(r.pe_med, "x"),
                                 "PBR": _fmt(r.pb, "x"), "ROE": _fmt(r.roe, "pp"),
                                 "3년 순이익 성장": _fmt(r.ni_cagr, "p") + "/년"}),
            "reason": f"PER이 업종 중앙값의 {r.pe_rel * 100:.0f}% 수준이고 3년 연속 흑자"
                      + (f", 순이익 연 {r.ni_cagr * 100:+.0f}% 성장" if pd.notna(r.ni_cagr) else ""),
        } for r in _diverse(v, top_n, cap).itertuples()]

    # 2) 성장 기대: 매출 성장 + 이익 전망 개선 + 모멘텀
    g = df[(df.rev_cagr > 0.05) | (df.rev_g > 0.1)].copy()
    if len(g):
        g["score"] = (_by_market(g, "rev_cagr") * 0.3 + _by_market(g, "rev_g") * 0.25
                      + _by_market(g, "eps_g") * 0.2 + _by_market(g, "fwd_up") * 0.2
                      + _by_market(g, "ret_6m") * 0.05)
        out["growth"] = [{
            **_base(r),
            "metrics": _metrics({"3년 매출 성장": _fmt(r.rev_cagr, "p") + "/년", "최근 매출 성장": _fmt(r.rev_g, "p"),
                                 "최근 이익 성장": _fmt(r.eps_g, "p"), "6개월 주가": _fmt(r.ret_6m, "p"),
                                 "PER→선행PER": f"{_fmt(r.pe, 'x')}→{_fmt(r.fpe, 'x')}"}),
            "reason": f"{r.industry or r.sector} 업종"
                      + (f", 매출이 3년간 연 {_fmt(r.rev_cagr, 'p')} 늘었고" if pd.notna(r.rev_cagr) else "")
                      + (f" 최근 분기 매출(전년 같은 분기 대비) {_fmt(r.rev_g, 'p')}" if pd.notna(r.rev_g) else "")
                      + (f", 최근 분기 이익 {_fmt(r.eps_g, 'p')}" if pd.notna(r.eps_g) else ""),
        } for r in _diverse(g, top_n, cap).itertuples()]

    # 3) 고평가 위험: 업종 대비 PER 과다 또는 적자인데 PSR 높음 + 가격 과열
    # 과거 12개월 PER만 높고 선행 PER·3년 평균 이익 PER은 업종 수준이면 일회성 비용으로 이익이 줄어든 것 → 고평가로 보지 않는다
    # (예: SK텔레콤 과거 PER 43배 ↔ 선행 12.5배·3년 평균 이익 기준 19배)
    one_off = (df.pe_rel > 1.8) & ((df.fpe_rel <= 1.2) | (df.pe_avg3_rel <= 1.2))
    o = df[((df.pe_rel > 1.8) & ~one_off) | (df.pe.isna() & (df.ps > 8))].copy()
    if len(o):
        o["pe_rel_f"] = o.pe_rel.fillna(o.pe_rel.median() if o.pe_rel.notna().any() else 3)
        o["score"] = (_by_market(o, "pe_rel_f") * 0.3 + _by_market(o, "ps") * 0.2
                      + _by_market(o, "vs_ma200") * 0.2 + _by_market(o, "rsi") * 0.15
                      + _by_market(o, "rev_g", False) * 0.15)
        out["overvalued"] = [{
            **_base(r),
            "metrics": _metrics({"PER": _fmt(r.pe, "x") if pd.notna(r.pe) else "적자",
                                 "선행 PER": _fmt(r.fpe, "x"), "업종 PER": _fmt(r.pe_med, "x"), "PSR": _fmt(r.ps, "x"),
                                 "200일선 대비": _fmt(r.vs_ma200, "p"), "RSI": _fmt(r.rsi, "n")}),
            "reason": (f"PER이 업종 중앙값의 {r.pe_rel * 100:.0f}%" if pd.notna(r.pe_rel)
                       else f"최근 이익 적자인데 PSR {_fmt(r.ps, 'x')}")
                      + (f", 주가가 200일선보다 {_fmt(r.vs_ma200, 'p')} 위" if pd.notna(r.vs_ma200) and r.vs_ma200 > 0.15 else ""),
        } for r in _diverse(o, top_n, cap).itertuples()]

    out["categories"] = categories(df, out, hist or {})
    out["universe_size"] = int(len(df))
    out["valuation"] = valuation(df)
    out["leadership"] = (hist or {}).get("_leadership", {})
    return out


def _f(v):
    return None if v is None or pd.isna(v) else round(float(v) * 100, 2)


def categories(df: pd.DataFrame, lists: dict, hist: dict) -> list:
    """분야별 등락·추세 폭·실적·대표 종목 요약 (20일 수익률 높은 순)."""
    flagged = {k: {r["ticker"] for r in lists.get(k, [])} for k in ("value", "growth", "overvalued")}
    out = []
    for cat, g in df.groupby("category", sort=False):
        mv = g.dropna(subset=["ret_5d"]).sort_values("ret_5d")
        pe = {m: g[g.market == m].pe.median() for m in ("kr", "us")}
        item = {
            "name": cat, "n": int(len(g)),
            "ret_1d": _f(g.ret_1d.mean()), "ret_5d": _f(g.ret_5d.mean()), "ret_20d": _f(g.ret_20d.mean()),
            "breadth": round(float(g.above_ma20.fillna(False).astype(bool).mean()) * 100) if "above_ma20" in g else None,
            "rev_g": _f(g.rev_g.median()),
            "pe_kr": None if pd.isna(pe["kr"]) else round(float(pe["kr"]), 1),
            "pe_us": None if pd.isna(pe["us"]) else round(float(pe["us"]), 1),
            "best": [mv.iloc[-1]["name"], _f(mv.iloc[-1].ret_5d)] if len(mv) else None,
            "worst": [mv.iloc[0]["name"], _f(mv.iloc[0].ret_5d)] if len(mv) > 1 else None,
        }
        # 분야 안에서 실적 기준 대표 종목 (전체 목록과 별개로 분야마다 하나씩)
        v = g[g.ni_all_pos & g.pe_rel.notna()]
        if len(v):
            r = v.assign(s=v.pe_rel.rank() - v.roe.rank() - v.ni_cagr.rank()).sort_values("s").iloc[0]
            item["value_pick"] = [r["name"], f"PER {r.pe:.1f}배"]
        gr = g[g.rev_g.notna()]
        if len(gr):
            r = gr.assign(s=gr.rev_g.rank() + gr.rev_cagr.rank()).sort_values("s").iloc[-1]
            item["growth_pick"] = [r["name"], f"최근 매출 {r.rev_g * 100:+.0f}%"]
        item["risk_names"] = [n for t, n in zip(g.ticker, g.name) if t in flagged["overvalued"]]
        item.update(hist.get(cat, {}))
        out.append(item)
    out.sort(key=lambda x: (x["ret_20d"] is None, -(x["ret_20d"] or 0)))
    return out


def _diverse(d: pd.DataFrame, n: int, cap: int) -> pd.DataFrame:
    """점수 순으로 고르되 같은 분야는 cap개까지만."""
    picked, count = [], {}
    for idx, r in d.sort_values("score", ascending=False).iterrows():
        if count.get(r.category, 0) < cap:
            picked.append(idx)
            count[r.category] = count.get(r.category, 0) + 1
        if len(picked) == n:
            break
    return d.loc[picked]


def _base(r):
    return {"ticker": r.ticker, "name": r.name, "market": r.market, "category": r.category,
            "sector": r.sector, "score": round(float(r.score) * 100)}


def run(cfg: dict, demo=False) -> dict:
    import yaml
    uni_raw = yaml.safe_load(open(cfg.get("universe_file", "universe.yaml"), encoding="utf-8"))
    universe = {}
    for cat, items in uni_raw.items():
        for t, n in (items or {}).items():
            t = str(t)
            universe[t] = (n, "kr" if t.endswith((".KS", ".KQ")) else "us", cat)
    fund = load_fundamentals(universe, cfg.get("refresh_days", 7), demo)
    prices, values = load_prices(list(universe), demo, cfg.get("price_period", "5y"))
    df = build_table(universe, fund, prices)
    try:
        hist = sector_history(universe, prices, values)
    except Exception as e:  # noqa: BLE001
        print(f"    ✗ 분야 장기 비교 실패: {e}")
        hist = {}
    return screen(df, cfg.get("top_n", 5), cfg.get("max_per_category", 1), hist)


# ───────────────────────── 분야 장기 비교 ─────────────────────────
def sector_history(universe: dict, prices: dict, values: dict) -> dict:
    """분야별 동일가중 지수로 60일·1년·3년 수익률, 시장 대비 상대강도와 1년 전 대비 변화,
    상대강도의 3년 백분위, 거래대금 증감(자금 유입·유출 대용)을 계산."""
    rets = {}
    for t, s in prices.items():
        if len(s) < 260:
            continue
        rets[t] = s.pct_change().clip(-0.3, 0.3)
    if not rets:
        return {}
    R = pd.DataFrame(rets).sort_index()
    mkt = R.mean(axis=1, skipna=True).fillna(0)
    mkt_idx = (1 + mkt).cumprod()
    cats: dict[str, list] = {}
    for t, (_, _, c) in universe.items():
        if t in R:
            cats.setdefault(c, []).append(t)

    def ret(idx, n, lag=0):
        if len(idx) <= n + lag:
            return None
        return float(idx.iloc[-1 - lag] / idx.iloc[-1 - lag - n] - 1)

    out, rank_now, rank_ago = {}, {}, {}
    for c, ts in cats.items():
        sr = R[ts].mean(axis=1, skipna=True).fillna(0)
        idx = (1 + sr).cumprod()
        rel = idx / mkt_idx
        r60, r60_ago = ret(idx, 60), ret(idx, 60, 252)
        m60, m60_ago = ret(mkt_idx, 60), ret(mkt_idx, 60, 252)
        rel3 = rel.tail(756)
        # 거래대금: 최근 5일 평균 / 60일 평균 (종목별 비율의 중앙값)
        ratios = []
        for t in ts:
            v = values.get(t)
            if v is not None and len(v) > 70:
                a, b = v.tail(5).mean(), v.tail(60).mean()
                if b > 0:
                    ratios.append(a / b)
        vr = float(np.median(ratios)) if ratios else None
        r5 = ret(idx, 5)
        flow = None
        if vr is not None and r5 is not None:
            if r5 > 0.01 and vr >= 1.0:
                flow = "유입"
            elif r5 < -0.01 and vr >= 1.0:
                flow = "유출"
            elif vr < 0.85:
                flow = "관심 감소"
            else:
                flow = "중립"
        weekly = idx.resample("W-FRI").last().tail(157)
        if len(weekly):
            weekly = weekly / weekly.iloc[0] * 100
        out[c] = {
            "ret_60d": _f(r60), "ret_1y": _f(ret(idx, 252)), "ret_3y": _f(ret(idx, 756)),
            "rs_60d": _f(None if r60 is None or m60 is None else r60 - m60),
            "rs_60d_1y_ago": _f(None if r60_ago is None or m60_ago is None else r60_ago - m60_ago),
            "rs_pct_3y": round(float((rel3 < rel3.iloc[-1]).mean() * 100)) if len(rel3) > 100 else None,
            "turnover_ratio": None if vr is None else round(vr, 2), "flow": flow,
            "spark": [[d.strftime("%Y-%m-%d"), round(float(v), 1)] for d, v in weekly.items()],
        }
        if r60 is not None:
            rank_now[c] = r60
        if r60_ago is not None:
            rank_ago[c] = r60_ago
    order_now = [c for c, _ in sorted(rank_now.items(), key=lambda x: -x[1])]
    order_ago = [c for c, _ in sorted(rank_ago.items(), key=lambda x: -x[1])]
    for c in out:
        out[c]["rank_60d"] = order_now.index(c) + 1 if c in order_now else None
        out[c]["rank_60d_1y_ago"] = order_ago.index(c) + 1 if c in order_ago else None
    out["_leadership"] = {"now": order_now[:3], "year_ago": order_ago[:3],
                          "laggards_now": order_now[-3:][::-1]}
    return out


def valuation(df: pd.DataFrame) -> dict:
    """시장별 PER·PBR 중앙값과 이익수익률(1/PER). 매일 history에 쌓아 장기 비교에 사용."""
    out = {}
    for m in ("kr", "us"):
        g = df[df.market == m]
        pe, pb = g.pe.median(), g.pb.median()
        out[m] = {"pe_median": None if pd.isna(pe) else round(float(pe), 2),
                  "pb_median": None if pd.isna(pb) else round(float(pb), 2),
                  "earnings_yield": None if pd.isna(pe) or pe <= 0 else round(100 / float(pe), 2),
                  "n": int(g.pe.notna().sum())}
    return out



# ───────────────────────── 데모용 가짜 데이터 ─────────────────────────
def _fake_fundamentals(universe):
    import zlib
    out = {}
    for t, (n, m, c) in universe.items():
        rng = np.random.default_rng(zlib.crc32(t.encode()))
        base = rng.uniform(1e9, 5e10)
        g = rng.normal(0.08, 0.15)
        rev = [base * (1 + g) ** i for i in range(4)]
        ni = [r * rng.uniform(-0.05, 0.2) for r in rev]
        out[t] = {"trailingPE": float(rng.lognormal(2.8, 0.6)) if ni[-1] > 0 else None,
                  "forwardPE": float(rng.lognormal(2.7, 0.5)), "priceToBook": float(rng.lognormal(0.6, 0.7)),
                  "priceToSalesTrailing12Months": float(rng.lognormal(1, 0.9)),
                  "returnOnEquity": float(rng.normal(0.12, 0.08)), "revenueGrowth": float(rng.normal(0.08, 0.15)),
                  "earningsGrowth": float(rng.normal(0.1, 0.3)), "profitMargins": 0.1,
                  "sector": rng.choice(["Technology", "Financial Services", "Healthcare", "Industrials"]),
                  "industry": "", "revenue": rev, "net_income": ni}
    return out


def _fake_prices(tickers):
    import zlib
    idx = pd.bdate_range(end=datetime.now(), periods=250)
    out = {}
    for t in tickers:
        rng = np.random.default_rng(zlib.crc32(t.encode()) + 1)
        out[t] = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 250))), index=idx)
    return out
