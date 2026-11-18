"""거시경제·다중 자산 데이터 수집과 '과거 5년 vs 현재' 비교.

- 자산마다 출처를 순서대로 시도 (yfinance → FinanceDataReader → FRED CSV). 하나라도 성공하면 사용,
  모두 실패하면 그 자산만 {"error": ...} 로 남기고 나머지는 계속 진행합니다.
- 비교 지표: 1일/1주/1개월/3개월 변화, 작년 동기 대비(YoY), 1·3·5년 평균 대비, 3·5년 백분위,
  200일선 추세, 5년 주간 차트.
- 레짐 판정(금리·달러·원화·변동성·커브·위험선호)과, 과거 5년 중 지금과 가장 비슷했던 국면(유사 국면) 탐색.
- 정량 예측 기준선: 모닝은 EWY(미국 상장 한국 ETF) 간밤 등락 → 코스피, 나이트는 S&P500 선물 → S&P500.
"""
from __future__ import annotations

import io
import math
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from netretry import retry

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (stock-daily briefing bot)"}


# ───────────────────────── 수집 ─────────────────────────
def _clean(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    s.index = pd.DatetimeIndex(s.index).normalize()
    s = s[~s.index.duplicated(keep="last")]
    # 하루짜리 잘못된 체결값(스파이크) 제거: 앞뒤 7일 중앙값에서 25% 넘게 벗어난 점
    if len(s) > 10:
        med = s.rolling(7, center=True, min_periods=3).median()
        dev = (s / med - 1).abs()
        s = s[(dev < 0.25) | med.isna() | (s <= 0)]
    return s


def _yf_batch(symbols: list[str], start: str) -> dict[str, pd.Series]:
    if not symbols:
        return {}
    import yfinance as yf
    df = yf.download(symbols, start=start, auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    out = {}
    for sym in symbols:
        try:
            s = df[sym]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
            s = _clean(s)
            if len(s) > 20:
                out[sym] = s
        except Exception:  # noqa: BLE001
            pass
    return out


def _fdr(code: str, start: str) -> pd.Series:
    import FinanceDataReader as fdr
    df = fdr.DataReader(code, start)
    return _clean(df["Close"])


def _fred(series_id: str, start: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        df = pd.read_csv(io.BytesIO(r.read()))
    date_col = df.columns[0]
    s = pd.Series(pd.to_numeric(df[series_id], errors="coerce").values,
                  index=pd.to_datetime(df[date_col]))
    return _clean(s)


def fetch_all(assets: list[dict], years: int = 5) -> tuple[dict[str, pd.Series], dict[str, str]]:
    """자산별 일간 시계열과, 실제로 쓰인 출처(또는 오류)를 돌려준다."""
    start = (datetime.now(KST) - timedelta(days=int(365.25 * years) + 30)).strftime("%Y-%m-%d")
    series, used = {}, {}
    yf_first = [a["sources"][0][1] for a in assets if a["sources"] and a["sources"][0][0] == "yf"]
    try:
        yf_data = retry(_yf_batch, yf_first, start, label="야후 일괄")
    except Exception as e:  # noqa: BLE001
        print(f"    ✗ 야후 일괄 수집 실패: {e}")
        yf_data = {}
    today = pd.Timestamp(datetime.now(KST).date())
    for a in assets:
        errs, best = [], None
        for src, code in a["sources"]:
            try:
                if src == "yf":
                    s = yf_data.get(code)
                    if s is None:
                        s = retry(_yf_batch, [code], start, tries=2, label=code).get(code)
                    if s is None:
                        raise ValueError("빈 데이터")
                elif src == "fdr":
                    s = retry(_fdr, code, start, tries=2, label=code)
                elif src == "fred":
                    s = retry(_fred, code, start, tries=3, label=code)
                else:
                    raise ValueError(f"알 수 없는 출처 {src}")
                if len(s) < 20:
                    raise ValueError(f"{len(s)}일뿐")
                if a.get("kind") == "rate" and s.median() > 20:   # 일부 출처는 금리×10
                    s = s / 10
                if best is None or s.index[-1] > best[0].index[-1]:
                    best = (s, f"{src}:{code}")
                # 최신 데이터면 확정. 3일 넘게 묵은 값이면(출처 갱신 지연) 다음 출처도 확인해 더 최신 것을 쓴다
                if (today - best[0].index[-1]).days <= 3:
                    break
            except Exception as e:  # noqa: BLE001
                errs.append(f"{src}:{code} {type(e).__name__}")
        if best is not None:
            series[a["key"]], used[a["key"]] = best
        else:
            used[a["key"]] = "실패 — " + "; ".join(errs)
    # 장단기 금리차는 표에 보이는 10년·2년 금리로 직접 계산한다 (FRED T10Y2Y 는 날짜·출처가 달라
    # '5.10% − 4.83%'와 금리차 숫자가 맞지 않던 문제). 날짜가 어긋나면 각자 마지막 값을 이어 붙여 뺀다.
    if "us10y" in series and "us2y" in series:
        both = pd.concat([series["us10y"].rename("a"), series["us2y"].rename("b")], axis=1, sort=True).sort_index().ffill().dropna()
        if len(both) >= 20:
            series["curve"] = (both["a"] - both["b"]).round(4)
            used["curve"] = f"계산: 10년({used.get('us10y')}) − 2년({used.get('us2y')})"
    return series, used


# ───────────────────────── 지표 ─────────────────────────
def _r(v, n=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), n)


def _asof(s: pd.Series, when: pd.Timestamp):
    sub = s[s.index <= when]
    return None if sub.empty else float(sub.iloc[-1])


def _chg(now, past, rate: bool):
    if now is None or past is None:
        return None
    if rate:
        return _r((now - past) * 100, 0)          # bp
    return None if past == 0 else _r((now / past - 1) * 100)


def metrics(s: pd.Series, kind: str = "price") -> dict:
    rate = kind == "rate"
    last_d, last = s.index[-1], float(s.iloc[-1])
    ago = lambda days: _asof(s, last_d - pd.Timedelta(days=days))  # noqa: E731
    w = lambda yrs: s[s.index > last_d - pd.Timedelta(days=int(365.25 * yrs))]  # noqa: E731
    s1, s3, s5 = w(1), w(3), w(5)
    yoy_val = ago(365)
    ma200 = s.tail(200).mean() if len(s) >= 150 else None
    weekly = s.resample("W-FRI").last().dropna().tail(270)
    if len(weekly):                               # 그래프의 '지금' 점 = 가장 최근 거래일 종가 (날짜도 실제 거래일로)
        weekly = weekly.iloc[:-1]
        weekly.loc[last_d] = last
    out = {
        "kind": kind, "date": last_d.strftime("%Y-%m-%d"), "last": _r(last, 4 if abs(last) < 10 else 2),
        "chg_1d": _chg(last, float(s.iloc[-2]) if len(s) > 1 else None, rate),
        "chg_1w": _chg(last, ago(7), rate), "chg_1m": _chg(last, ago(30), rate),
        "chg_3m": _chg(last, ago(91), rate), "yoy": _chg(last, yoy_val, rate),
        "year_ago": _r(yoy_val, 4 if yoy_val is not None and abs(yoy_val) < 10 else 2),
        "avg_1y": _r(s1.mean()), "avg_3y": _r(s3.mean()), "avg_5y": _r(s5.mean()),
        "vs_avg_3y": _chg(last, float(s3.mean()), rate), "vs_avg_5y": _chg(last, float(s5.mean()), rate),
        "pct_3y": _r((s3 < last).mean() * 100, 0), "pct_5y": _r((s5 < last).mean() * 100, 0),
        "min_5y": _r(s5.min()), "max_5y": _r(s5.max()),
        "trend": None if ma200 is None else ("상승" if last > ma200 else "하락"),
        "years": _r((last_d - s.index[0]).days / 365.25, 1),
        "spark": [[d.strftime("%Y-%m-%d"), _r(v, 4)] for d, v in weekly.items()],
    }
    if len(s1) > 30 and s1.std() > 0:
        out["z_1y"] = _r((last - s1.mean()) / s1.std())
    return out


def rank5(p) -> str:
    """5년 백분위 → '최근 5년 중 상위 15%' 같은 일상 표현."""
    if p is None:
        return "5년 위치 정보 없음"
    return f"최근 5년 중 상위 {max(1, round(100 - p))}%" if p >= 50 else f"최근 5년 중 하위 {max(1, round(p))}%"


def regimes(m: dict) -> list[dict]:
    """금리·달러·원화·변동성·커브·위험선호 레짐을 판정. 근거 수치 포함."""
    out = []

    def add(key, label, value, evidence):
        out.append({"key": key, "label": label, "value": value, "evidence": evidence})

    t = m.get("us10y")
    if t and "error" not in t:
        d3, yoy = t.get("chg_3m") or 0, t.get("yoy") or 0
        v = "금리 상승기" if d3 > 25 else "금리 하락기" if d3 < -25 else "금리 고원(횡보)"
        add("rate", "미국 금리", v, f"10년 금리 {t['last']:.2f}%, 3개월 {d3 / 100:+.2f}%p, 1년 {yoy / 100:+.2f}%p, {rank5(t['pct_5y'])}")
    d = m.get("dxy")
    if d and "error" not in d:
        v = "강달러" if (d["pct_5y"] or 0) >= 65 else "약달러" if (d["pct_5y"] or 0) <= 35 else "달러 중립"
        add("dollar", "달러", v + (" · 상승 추세" if d.get("trend") == "상승" else " · 하락 추세"),
            f"달러 인덱스 {d['last']:.1f}, {rank5(d['pct_5y'])}, 1년 {d.get('yoy') or 0:+.1f}%")
    k = m.get("usdkrw")
    if k and "error" not in k:
        p = k["pct_5y"] or 0
        v = "원화 약세(고환율)" if p >= 70 else "원화 강세(저환율)" if p <= 30 else "환율 중립"
        add("krw", "원화", v, f"원/달러 {k['last']:,.0f}원, {rank5(p)}, 3년 평균 대비 {k.get('vs_avg_3y') or 0:+.1f}%")
    x = m.get("vix")
    if x and "error" not in x:
        lv = x["last"]
        v = "저변동(낙관)" if lv < 15 else "보통" if lv < 20 else "경계" if lv < 30 else "공포"
        add("vol", "변동성(공포지수)", v, f"VIX {lv:.1f} (20 아래 평온, 30 위 공포), {rank5(x['pct_5y'])}")
    c = m.get("curve")
    if c and "error" not in c:
        lv = c["last"]
        v = "역전(경기 침체 경고)" if lv < 0 else "확대(경기 회복 기대)" if (c.get("yoy") or 0) > 0 else "축소(경기 둔화 신호)"
        add("curve", "장단기 금리차", v, f"10년−2년 금리 {lv:+.2f}%p, 1년 변화 {(c.get('yoy') or 0) / 100:+.2f}%p")
    cu, au = m.get("copper"), m.get("gold")
    if cu and au and "error" not in cu and "error" not in au and cu.get("chg_3m") is not None and au.get("chg_3m") is not None:
        diff = cu["chg_3m"] - au["chg_3m"]
        v = "위험선호(경기 기대)" if diff > 3 else "안전선호(경기 우려)" if diff < -3 else "중립"
        add("risk", "구리/금", v, f"3개월 구리 {cu['chg_3m']:+.1f}% vs 금 {au['chg_3m']:+.1f}%")
    return out


# ───────────────────────── 유사 국면 ─────────────────────────
# 비교 항목: (원자료, 계산 방식, 보고서에 보일 이름, 표시 방식)
FEATURES = {
    "kospi_dd": ("kospi", "dd52", "코스피 1년 고점 대비", "pct"),
    "kospi_6m": ("kospi", "ret26", "코스피 6개월 수익률", "pct"),
    "spx_6m": ("spx", "ret26", "S&P500 6개월 수익률", "pct"),
    "us10y": ("us10y", "level", "미국 10년 금리", "rate"),
    "us10y_6m": ("us10y", "diff26", "미국 10년 금리 6개월 변화", "pp"),
    "usdkrw": ("usdkrw", "level", "원/달러 환율", "num"),
    "vix": ("vix", "level", "공포지수(VIX)", "num"),
    "cuau_6m": ("cuau", "ret26", "구리/금 6개월 변화", "pct"),
}
WEIGHTS = {"kospi_dd": 1.5, "kospi_6m": 1.3, "spx_6m": 1.0, "us10y": 0.8, "us10y_6m": 1.0,
           "usdkrw": 0.6, "vix": 1.0, "cuau_6m": 0.6}


def _fmt_feat(v, how):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return {"pct": _r(v * 100, 1), "rate": _r(v, 2), "pp": _r(v, 2), "num": _r(v, 1)}[how]


def analogs(series: dict[str, pd.Series], top: int = 3, min_gap_days: int = 365) -> dict:
    """지금과 가장 비슷했던 과거 시점(최대 20여 년 전까지)을 찾고, 그때 전후 코스피·S&P500 흐름을 붙인다.

    비슷함의 기준: 코스피가 1년 고점에서 얼마나 내려왔는지, 6개월 수익률, 미국 금리 수준·변화, 환율, VIX, 구리/금.
    각 사례마다 '그 시점 1년 전 → 이후 6개월' 주간 경로(시점=100)를 함께 저장해 그래프로 겹쳐 볼 수 있게 한다.
    """
    w = {k: s.resample("W-FRI").last() for k, s in series.items()}
    if "copper" in w and "gold" in w:
        w["cuau"] = w["copper"] / w["gold"]
    cols = {}
    for name, (key, how, _, _) in FEATURES.items():
        s = w.get(key)
        if s is None:
            continue
        cols[name] = {"ret26": s / s.shift(26) - 1, "diff26": s - s.shift(26), "level": s,
                      "dd52": s / s.rolling(52, min_periods=40).max() - 1}[how]
    if len(cols) < 4 or "kospi" not in w or "spx" not in w:
        return {}
    # 일부 자산만 최신 주 값이 비어도(휴장·출처 지연) 마지막 주가 통째로 빠지지 않게 앞 값으로 최대 3주 채움.
    # 주간 마지막 칸은 가장 최근 거래일 종가이므로, '지금' 값은 일간 최신 종가와 같다.
    f = pd.DataFrame(cols).ffill(limit=3).dropna()
    if len(f) < 150:
        return {}
    z = (f - f.mean()) / f.std(ddof=0).replace(0, np.nan)
    z = z.dropna(axis=1)
    wts = pd.Series({c: WEIGHTS.get(c, 1.0) for c in z.columns})
    cur = z.iloc[-1]
    hist = z.iloc[:-52]                       # 최근 1년은 제외 (같은 흐름의 연장선이므로)
    hist = hist[hist.index <= z.index[-1] - pd.Timedelta(weeks=26 + 52)]  # 이후 6개월 결과가 있는 시점만
    dist = np.sqrt((((hist - cur) ** 2) * wts).sum(axis=1) / wts.sum()).sort_values()
    picked = []
    for d, v in dist.items():
        if all(abs((d - p).days) > min_gap_days for p, _ in picked):
            picked.append((d, v))
        if len(picked) == top:
            break

    def path(key, d, before=52, after=26):
        s = w[key].dropna()
        base = _asof(s, d)
        if not base:
            return []
        out = []
        for k in range(-before, after + 1, 2):
            v = _asof(s, d + pd.Timedelta(weeks=k))
            if v is not None and (k <= 0 or d + pd.Timedelta(weeks=k) <= s.index[-1]):
                out.append([k, _r(v / base * 100, 1)])
        return out

    def state(d):
        return {k: _fmt_feat(f.loc[d, k], FEATURES[k][3]) for k in f.columns}

    out = []
    for d, v in picked:
        row = {"date": d.strftime("%Y-%m-%d"), "similarity": _r(100 / (1 + v * 2), 0), "state": state(d),
               "path_kospi": path("kospi", d), "path_spx": path("spx", d)}
        for key in ("kospi", "spx"):
            s = w[key].dropna()
            base = _asof(s, d)
            for wk in (4, 13, 26):
                fut = _asof(s, d + pd.Timedelta(weeks=wk))
                row[f"{key}_{wk}w"] = None if base in (None, 0) or fut is None else _r((fut / base - 1) * 100, 1)
        out.append(row)
    d0 = f.index[-1]
    return {"features": {k: [FEATURES[k][2], FEATURES[k][3]] for k in f.columns},
            "now": state(d0), "now_path_kospi": path("kospi", d0, after=0), "now_path_spx": path("spx", d0, after=0),
            "since": f.index[0].strftime("%Y-%m-%d"), "matches": out}


# ───────────────────────── 정량 예측 기준선 ─────────────────────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def quant_forecast(series: dict[str, pd.Series], slot: str) -> dict:
    """am: EWY 간밤 수익률 → 코스피 당일 / pm: S&P500 선물 → S&P500 당일. 1σ(68%) 밴드."""
    try:
        if slot == "am":
            tgt, drv = series["kospi"], series["ewy"]
            tr, dr = tgt.pct_change().dropna(), drv.pct_change().dropna()
            # 코스피 d일 수익률 ↔ 그 전날까지 마감한 EWY 수익률
            pos = dr.index.searchsorted(tr.index, side="left") - 1
            ok = pos >= 0
            x = pd.Series(dr.values[pos[ok]], index=tr.index[ok]).tail(250)
            y = tr[ok].tail(250)
            beta = float(np.cov(x, y)[0, 1] / np.var(x, ddof=1))
            alpha = float(y.mean() - beta * x.mean())
            resid = y - (alpha + beta * x)
            sig = float(resid.std())
            r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
            new = dr[dr.index > tgt.index[-1]]
            drv_ret = float((1 + new).prod() - 1) if len(new) else 0.0
            exp = alpha + beta * drv_ret
            base = float(tgt.iloc[-1])
            name, driver = "코스피", f"밤사이 미국 시장의 한국 ETF(EWY) {drv_ret * 100:+.2f}%"
            model = f"EWY 회귀 베타 {beta:.2f}, 설명력 {r2 * 100:.0f}%"
        else:
            tgt, drv = series["spx"], series["es"]
            sig = float(tgt.pct_change().dropna().tail(60).std())
            if drv.index[-1] > tgt.index[-1]:
                drv_ret = float(drv.iloc[-1] / drv[drv.index <= tgt.index[-1]].iloc[-1] - 1)
            else:
                drv_ret = 0.0
            exp, base, beta, r2 = drv_ret, float(tgt.iloc[-1]), 1.0, None
            name, driver = "S&P 500", f"S&P500 선물 {drv_ret * 100:+.2f}% (어제 종가 대비)"
            model = "선물 등락 + 60일 변동성"
        mid = base * (1 + exp)
        return {
            "target": name, "base_close": _r(base), "expected_pct": _r(exp * 100),
            "expected": _r(mid), "band_low": _r(mid * (1 - sig)), "band_high": _r(mid * (1 + sig)),
            "sigma_pct": _r(sig * 100), "prob_up": _r(_norm_cdf(exp / sig) * 100, 0) if sig > 0 else None,
            "driver": driver, "model": model, "method": "일반적인 예상 등락 범위 (대략 3번 중 2번 이 안에서 끝남)",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"정량 예측 계산 실패: {type(e).__name__}: {e}"}


# ───────────────────────── 실행 ─────────────────────────
def run(cfg: dict, slot: str, demo: bool = False) -> tuple[dict, dict[str, pd.Series]]:
    assets = cfg.get("assets", [])
    if demo:
        series, used = _fake(assets, max(cfg.get("years", 5), cfg.get("analog_years", 20))), {a["key"]: "demo" for a in assets}
    else:
        series, used = fetch_all(assets, max(cfg.get("years", 5), cfg.get("analog_years", 20)))
    out = {"assets": [], "sources": used}
    m = {}
    for a in assets:
        k = a["key"]
        item = {"key": k, "name": a["name"], "group": a["group"]}
        if k in series:
            try:
                item.update(metrics(series[k], a.get("kind", "price")))
                m[k] = item
            except Exception as e:  # noqa: BLE001
                item["error"] = f"지표 계산 실패: {e}"
        else:
            item["error"] = used.get(k, "데이터 없음")
        out["assets"].append(item)
    out["regimes"] = regimes(m)
    try:
        out["analogs"] = analogs(series)
    except Exception as e:  # noqa: BLE001
        out["analogs"] = {}
        print(f"    ✗ 유사 국면 계산 실패: {e}")
    out["quant"] = quant_forecast(series, slot)
    out["ok"] = sum(1 for a in out["assets"] if "error" not in a)
    return out, series


def _fake(assets, years):
    import zlib
    idx = pd.bdate_range(end=datetime.now(KST).date(), periods=int(252 * years))
    out = {}
    for a in assets:
        rng = np.random.default_rng(zlib.crc32(a["key"].encode()))
        if a.get("kind") == "rate":
            out[a["key"]] = pd.Series(np.clip(3 + np.cumsum(rng.normal(0, 0.04, len(idx))), -1, 8), index=idx)
        else:
            out[a["key"]] = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx)))), index=idx)
    return out
