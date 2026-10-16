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

SECTOR_KO = {"Technology": "기술", "Financial Services": "금융", "Healthcare": "헬스케어",
             "Industrials": "산업재", "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재",
             "Energy": "에너지", "Utilities": "유틸리티", "Basic Materials": "소재",
             "Communication Services": "커뮤니케이션", "Real Estate": "부동산"}
CACHE = Path("cache/fundamentals.json")
INFO_KEYS = ["trailingPE", "forwardPE", "priceToBook", "priceToSalesTrailing12Months",
             "returnOnEquity", "revenueGrowth", "earningsGrowth", "profitMargins",
             "marketCap", "sector", "industry", "currency"]


# ───────────────────────── 데이터 수집 ─────────────────────────
def _annual(stmt: pd.DataFrame, names) -> list:
    """재무제표에서 최근 3개 회계연도 값 (오래된 → 최근)."""
    for n in names:
        if stmt is not None and n in stmt.index:
            vals = stmt.loc[n].dropna()
            vals = vals.sort_index().tail(3)
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
    out["fetched"] = datetime.now().strftime("%Y-%m-%d")
    return out


def load_fundamentals(universe: dict, refresh_days: int = 7, demo=False) -> dict:
    if demo:
        return _fake_fundamentals(universe)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    limit = (datetime.now() - timedelta(days=refresh_days)).strftime("%Y-%m-%d")
    todo = [t for t in universe if cache.get(t, {}).get("fetched", "") < limit]
    if todo:
        print(f"  … 실적 데이터 수집 {len(todo)}종목 (주 1회, 몇 분 걸릴 수 있음)")
    for i, t in enumerate(todo, 1):
        try:
            cache[t] = _fetch_one(t)
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


def load_prices(tickers: list, demo=False) -> dict:
    if demo:
        return _fake_prices(tickers)
    import yfinance as yf
    df = yf.download(tickers, period="1y", auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            s = df[t]["Close"].dropna() if len(tickers) > 1 else df["Close"].dropna()
            if len(s) > 60:
                out[t] = s
        except KeyError:
            pass
    return out


# ───────────────────────── 지표 계산 ─────────────────────────
def _cagr(vals):
    if len(vals) < 2 or vals[0] <= 0 or vals[-1] <= 0:
        return None
    return (vals[-1] / vals[0]) ** (1 / (len(vals) - 1)) - 1


def build_table(universe: dict, fund: dict, prices: dict) -> pd.DataFrame:
    rows = []
    for t, (name, market) in universe.items():
        f = fund.get(t)
        if not f:
            continue
        rev, ni = f.get("revenue") or [], f.get("net_income") or []
        row = {
            "ticker": t, "name": name, "market": market,
            "sector": SECTOR_KO.get(f.get("sector"), f.get("sector") or "기타"), "industry": f.get("industry") or "",
            "pe": f.get("trailingPE"), "fpe": f.get("forwardPE"),
            "pb": f.get("priceToBook"), "ps": f.get("priceToSalesTrailing12Months"),
            "roe": f.get("returnOnEquity"), "rev_g": f.get("revenueGrowth"),
            "eps_g": f.get("earningsGrowth"), "margin": f.get("profitMargins"),
            "rev_cagr": _cagr(rev), "ni_cagr": _cagr(ni),
            "ni_all_pos": bool(ni) and len(ni) >= 2 and all(v > 0 for v in ni),
            "ni_last": ni[-1] if ni else None,
            "years": len(rev),
        }
        p = prices.get(t)
        if p is not None and len(p) > 130:
            row["ret_6m"] = p.iloc[-1] / p.iloc[-127] - 1
            row["rsi"] = float(rsi(p).iloc[-1])
            ma200 = p.rolling(min(200, len(p) - 1)).mean().iloc[-1]
            row["vs_ma200"] = p.iloc[-1] / ma200 - 1
        rows.append(row)
    df = pd.DataFrame(rows)
    num = ["pe", "fpe", "pb", "ps", "roe", "rev_g", "eps_g", "margin",
           "rev_cagr", "ni_cagr", "ret_6m", "rsi", "vs_ma200"]
    for c in num:
        if c not in df:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.loc[df.pe <= 0, "pe"] = np.nan

    # 업종 내 PER 중앙값 (같은 시장·업종 3개 이상일 때, 아니면 시장 전체 중앙값)
    def sector_median(g):
        return g["pe"].median() if g["pe"].notna().sum() >= 3 else np.nan
    sec = df.groupby(["market", "sector"]).apply(sector_median, include_groups=False)
    mkt = df.groupby("market")["pe"].median()
    df["pe_med"] = [sec.get((m, s), np.nan) if pd.notna(sec.get((m, s), np.nan)) else mkt.get(m)
                    for m, s in zip(df.market, df.sector)]
    df["pe_rel"] = df.pe / df.pe_med
    df["fwd_up"] = df.pe / df.fpe - 1  # +면 내년 이익 증가 예상
    return df


def _pct(s: pd.Series, higher_better=True):
    """시장별 백분위 (0~1). 값이 없으면 중간값 0.5."""
    r = s.rank(pct=True)
    return (r if higher_better else 1 - r).fillna(0.5)


def _by_market(df, col, higher_better=True):
    return df.groupby("market")[col].transform(lambda s: _pct(s, higher_better))


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return {"x": f"{v:.1f}배", "p": f"{v * 100:+.0f}%", "pp": f"{v * 100:.0f}%", "n": f"{v:.0f}"}[kind]


# ───────────────────────── 스크리닝 ─────────────────────────
def screen(df: pd.DataFrame, top_n=5) -> dict:
    out = {}

    # 1) 저평가: 3년 흑자 + PER 있음 + ROE 양수
    v = df[df.ni_all_pos & df.pe.notna() & (df.roe > 0)].copy()
    if len(v):
        v["score"] = (_by_market(v, "pe_rel", False) * 0.35 + _by_market(v, "pb", False) * 0.2
                      + _by_market(v, "roe") * 0.2 + _by_market(v, "ni_cagr") * 0.25)
        v = v[(v.pe_rel < 1) & (v.ni_cagr.fillna(0) > -0.05)]
        out["value"] = [{
            **_base(r),
            "metrics": {"PER": _fmt(r.pe, "x"), "업종 PER": _fmt(r.pe_med, "x"),
                        "PBR": _fmt(r.pb, "x"), "ROE": _fmt(r.roe, "pp"),
                        "3년 순이익 성장": _fmt(r.ni_cagr, "p") + "/년"},
            "reason": f"PER이 업종 중앙값의 {r.pe_rel * 100:.0f}% 수준이고 3년 연속 흑자"
                      + (f", 순이익 연 {r.ni_cagr * 100:+.0f}% 성장" if pd.notna(r.ni_cagr) else ""),
        } for r in v.nlargest(top_n, "score").itertuples()]

    # 2) 성장 기대: 매출 성장 + 이익 전망 개선 + 모멘텀
    g = df[(df.rev_cagr > 0.05) | (df.rev_g > 0.1)].copy()
    if len(g):
        g["score"] = (_by_market(g, "rev_cagr") * 0.25 + _by_market(g, "rev_g") * 0.25
                      + _by_market(g, "eps_g") * 0.2 + _by_market(g, "fwd_up") * 0.15
                      + _by_market(g, "ret_6m") * 0.15)
        out["growth"] = [{
            **_base(r),
            "metrics": {"3년 매출 성장": _fmt(r.rev_cagr, "p") + "/년", "최근 매출 성장": _fmt(r.rev_g, "p"),
                        "최근 이익 성장": _fmt(r.eps_g, "p"), "6개월 주가": _fmt(r.ret_6m, "p"),
                        "PER→선행PER": f"{_fmt(r.pe, 'x')}→{_fmt(r.fpe, 'x')}"},
            "reason": f"{r.industry or r.sector} 업종, 매출이 3년간 연 {_fmt(r.rev_cagr, 'p')} 늘었고 "
                      f"최근 분기 매출 {_fmt(r.rev_g, 'p')}",
        } for r in g.nlargest(top_n, "score").itertuples()]

    # 3) 고평가 위험: 업종 대비 PER 과다 또는 적자인데 PSR 높음 + 가격 과열
    o = df[(df.pe_rel > 1.8) | (df.pe.isna() & (df.ps > 8))].copy()
    if len(o):
        o["pe_rel_f"] = o.pe_rel.fillna(o.pe_rel.median() if o.pe_rel.notna().any() else 3)
        o["score"] = (_by_market(o, "pe_rel_f") * 0.3 + _by_market(o, "ps") * 0.2
                      + _by_market(o, "vs_ma200") * 0.2 + _by_market(o, "rsi") * 0.15
                      + _by_market(o, "rev_g", False) * 0.15)
        out["overvalued"] = [{
            **_base(r),
            "metrics": {"PER": _fmt(r.pe, "x") if pd.notna(r.pe) else "적자",
                        "업종 PER": _fmt(r.pe_med, "x"), "PSR": _fmt(r.ps, "x"),
                        "200일선 대비": _fmt(r.vs_ma200, "p"), "RSI": _fmt(r.rsi, "n")},
            "reason": (f"PER이 업종 중앙값의 {r.pe_rel * 100:.0f}%" if pd.notna(r.pe_rel)
                       else f"최근 이익 적자인데 PSR {_fmt(r.ps, 'x')}")
                      + (f", 주가가 200일선보다 {_fmt(r.vs_ma200, 'p')} 위" if pd.notna(r.vs_ma200) and r.vs_ma200 > 0.15 else ""),
        } for r in o.nlargest(top_n, "score").itertuples()]

    out["universe_size"] = int(len(df))
    return out


def _base(r):
    return {"ticker": r.ticker, "name": r.name, "market": r.market,
            "sector": r.sector, "score": round(float(r.score) * 100)}


def run(cfg: dict, demo=False) -> dict:
    import yaml
    uni_raw = yaml.safe_load(open(cfg.get("universe_file", "universe.yaml"), encoding="utf-8"))
    universe = {str(t): (n, m) for m, items in uni_raw.items() for t, n in items.items()}
    fund = load_fundamentals(universe, cfg.get("refresh_days", 7), demo)
    prices = load_prices(list(universe), demo)
    df = build_table(universe, fund, prices)
    return screen(df, cfg.get("top_n", 5))


# ───────────────────────── 데모용 가짜 데이터 ─────────────────────────
def _fake_fundamentals(universe):
    import zlib
    out = {}
    for t, (n, m) in universe.items():
        rng = np.random.default_rng(zlib.crc32(t.encode()))
        base = rng.uniform(1e9, 5e10)
        g = rng.normal(0.08, 0.15)
        rev = [base * (1 + g) ** i for i in range(3)]
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
