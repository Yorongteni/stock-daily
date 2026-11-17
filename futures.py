"""바이낸스 USDT 무기한 선물 3배 롱/숏 원픽 연습 (24시간 이내) — 매일 18:00 KST, swing.py 가 함께 부른다.

하는 일:
  1) data/binance_futures_log.json 의 대기·보유 포지션을 '추천 이후 1시간봉'으로 판정
       예약가 도달 → 진입(OPEN) → 목표가(+2.45%) 먼저 닿으면 WIN(+7%), 손절가(-1.50%) 먼저면 LOSS(-4.5%)
       24시간이 지나면 TIME_EXIT(그 시각 종가로 정리), 끝내 예약가에 안 닿으면 NO_FILL(미체결)
  2) 아직 시간이 남은 보유 포지션(내가 직접 넣은 것 등)은 오늘 밤 탈출·대응 지정가
  3) 비트코인·나스닥 선물로 오늘의 방향(롱 우위/숏 우위)을 먼저 정하고,
     거래대금 상위 30개 코인 중 4시간봉 추세 + 1시간봉 눌림/반등 + 거래량·미결제약정이 가장 뚜렷한 1개
  4) 격리 3배 · 증거금 360 USDT · 진입가 · 목표가 · 손절가 · 수량 · 청산가(참고)

데이터: 바이낸스 공개 선물 API(fapi.binance.com, 인증 키 불필요).
  GitHub 서버(미국)에서는 바이낸스가 접속을 막는 경우가 많아, 막히면 OKX 무기한 선물 공개 API →
  바이낸스 현물 공개 미러(data-api.binance.vision, 펀딩비·미결제약정 없음) 순서로 대신 씁니다.
  리포트에 실제로 쓴 데이터 출처를 적습니다.

수동 입력:
  python futures.py --manual BUY   --ticker SOLUSDT --direction LONG --price 142.3 [--qty 360 | --qty 7.6개]
  python futures.py --manual CLOSE --ticker SOLUSDT --price 145.1
  python futures.py --manual CANCEL --ticker SOLUSDT

※ 연습용 가상 매매입니다. 실제 계좌·주문과 연결되어 있지 않습니다.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from netretry import retry

KST = timezone(timedelta(hours=9))
UTC = timezone.utc
ROOT = Path(__file__).resolve().parent
_DATA = Path(os.environ.get("SWING_DATA_DIR") or ROOT / "data")
LOG_P = _DATA / "binance_futures_log.json"
UA = {"User-Agent": "stock-daily-practice/1.0"}

DEFAULTS = {
    "leverage": 3, "margin_usdt": 360.0, "tp_pct": 2.45, "sl_pct": 1.50, "win_roe": 7.0, "loss_roe": 4.5,
    "fee_roe": 0.3, "hold_hours": 24, "top_n": 30, "max_open": 2, "min_range24": 3.0, "mmr": 0.5,
}
STABLE = {"USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDE", "USDP", "PYUSD", "USD1", "EUR", "XUSD", "BFUSD", "RLUSD"}
MAJORS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "SUI", "AVAX", "LINK", "ADA", "TRX", "LTC", "DOT", "TON", "BCH"]
NAMES = {"BTC": "비트코인", "ETH": "이더리움", "SOL": "솔라나", "BNB": "BNB", "XRP": "리플", "DOGE": "도지코인",
         "SUI": "수이", "AVAX": "아발란체", "LINK": "체인링크", "ADA": "에이다", "TRX": "트론", "LTC": "라이트코인",
         "DOT": "폴카닷", "TON": "톤코인", "BCH": "비트코인캐시", "NEAR": "니어", "APT": "앱토스", "ARB": "아비트럼",
         "OP": "옵티미즘", "PEPE": "페페", "1000PEPE": "페페", "WIF": "도그위프햇", "SHIB": "시바이누", "1000SHIB": "시바이누",
         "ENA": "에테나", "TIA": "셀레스티아", "SEI": "세이", "INJ": "인젝티브", "FIL": "파일코인", "AAVE": "에이브",
         "UNI": "유니스왑", "ETC": "이더리움클래식", "HBAR": "헤데라", "WLD": "월드코인", "ONDO": "온도", "HYPE": "하이퍼리퀴드",
         "TAO": "비텐서", "XLM": "스텔라루멘", "BONK": "봉크", "1000BONK": "봉크", "FET": "페치에이아이", "RENDER": "렌더",
         "TRUMP": "트럼프", "VIRTUAL": "버추얼", "PENGU": "펏지펭귄", "KAITO": "카이토", "ZEC": "지캐시", "ASTER": "애스터"}
RESULT_KO = {"WIN": "목표 달성 익절 (+7%)", "LOSS": "손절 (-4.5%)", "TIME_EXIT": "24시간 경과 정리", "NO_FILL": "미체결 취소",
             "CLOSE": "직접 청산", "CANCEL": "주문 삭제"}


def coin(sym: str) -> str:
    return sym[:-4] if sym.endswith("USDT") else sym


def coin_name(sym: str) -> str:
    c = coin(sym)
    return NAMES.get(c, c)


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(t: str) -> datetime:
    return datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def kst(t: datetime | str, fmt: str = "%m/%d %H:%M") -> str:
    if isinstance(t, str):
        t = parse(t)
    return t.astimezone(KST).strftime(fmt)


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def load_log() -> dict:
    log = load_json(LOG_P, {})
    log.setdefault("start_date", datetime.now(KST).strftime("%Y-%m-%d"))
    log.setdefault("positions", [])
    log.setdefault("history", [])
    return log


# ───────────────────────── 가격 반올림 ─────────────────────────
def tick_of(price: float) -> float:
    """가격 크기에 맞춘 호가 단위 (거래소 tickSize 를 모를 때)."""
    if price <= 0:
        return 0.0001
    return 10 ** (math.floor(math.log10(price)) - 5)


def rp(price: float, tick: float | None = None) -> float:
    t = tick or tick_of(price)
    dec = max(0, -int(math.floor(math.log10(t) + 1e-9)))
    return round(round(price / t) * t, dec)


def fmt_px(v: float | None) -> str:
    if v is None:
        return "–"
    t = tick_of(v)
    dec = max(0, -int(math.floor(math.log10(t) + 1e-9)))
    return f"{v:,.{min(dec, 8)}f}"


def qty_for(notional: float, price: float) -> float:
    raw = notional / price
    dec = 0 if raw >= 1000 else 1 if raw >= 10 else 2 if raw >= 1 else 3 if raw >= 0.1 else 4
    f = 10 ** dec
    return math.floor(raw * f) / f


# ───────────────────────── 데이터 출처 ─────────────────────────
def _get(url: str, params: dict | None = None, timeout: int = 15):
    import requests
    r = requests.get(url, params=params or {}, headers=UA, timeout=timeout)
    if r.status_code in (403, 451):
        raise PermissionError(f"{r.status_code} 접속 제한 ({url.split('/')[2]})")
    r.raise_for_status()
    return r.json()


def _df(rows: list, cols=("t", "Open", "High", "Low", "Close", "Volume")) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(cols)).astype({"Open": float, "High": float, "Low": float, "Close": float, "Volume": float})
    df["t"] = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)
    return df.set_index("t").sort_index()


class Binance:
    name, label = "binance", "바이낸스 USDT 무기한 선물 (fapi.binance.com)"
    B = "https://fapi.binance.com"

    def __init__(self):
        self._tick = {}

    def tickers(self) -> list[dict]:
        rows = retry(_get, f"{self.B}/fapi/v1/ticker/24hr", tries=2, label="바이낸스 선물")
        try:
            info = retry(_get, f"{self.B}/fapi/v1/exchangeInfo", tries=2, label="바이낸스 종목 정보")
            ok = set()
            for s in info.get("symbols", []):
                if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
                    ok.add(s["symbol"])
                    for f in s.get("filters", []):
                        if f.get("filterType") == "PRICE_FILTER":
                            self._tick[s["symbol"]] = float(f["tickSize"])
        except Exception:  # noqa: BLE001
            ok = None
        out = []
        for r in rows:
            s = r["symbol"]
            if not s.endswith("USDT") or (ok is not None and s not in ok):
                continue
            out.append({"symbol": s, "last": float(r["lastPrice"]), "qv": float(r["quoteVolume"]), "chg24": float(r["priceChangePercent"])})
        return out

    def klines(self, sym: str, interval: str, limit: int = 200) -> pd.DataFrame:
        rows = retry(_get, f"{self.B}/fapi/v1/klines", {"symbol": sym, "interval": interval, "limit": limit}, tries=3, label=sym)
        return _df([r[:6] for r in rows])

    def funding(self, sym: str) -> float | None:
        r = retry(_get, f"{self.B}/fapi/v1/premiumIndex", {"symbol": sym}, tries=2, label=f"{sym} 펀딩비")
        return float(r["lastFundingRate"]) * 100

    def oi_change(self, sym: str) -> float | None:
        rows = retry(_get, f"{self.B}/futures/data/openInterestHist", {"symbol": sym, "period": "1h", "limit": 25}, tries=2, label=f"{sym} 미결제약정")
        v = [float(r["sumOpenInterestValue"]) for r in rows]
        return (v[-1] / v[0] - 1) * 100 if len(v) >= 2 and v[0] else None

    def tick(self, sym: str) -> float | None:
        return self._tick.get(sym)


class OKX:
    name, label = "okx", "OKX USDT 무기한 선물 (바이낸스 선물 API 접속 제한으로 대체)"
    B = "https://www.okx.com"

    def __init__(self):
        self._tick = {}

    @staticmethod
    def inst(sym: str) -> str:
        return f"{coin(sym)}-USDT-SWAP"

    def _data(self, path, params=None):
        j = retry(_get, f"{self.B}{path}", params, tries=3, label="OKX")
        if str(j.get("code")) != "0":
            raise RuntimeError(f"OKX 오류: {j.get('msg')}")
        return j["data"]

    def tickers(self) -> list[dict]:
        try:
            for s in self._data("/api/v5/public/instruments", {"instType": "SWAP"}):
                self._tick[s["instId"].replace("-USDT-SWAP", "USDT")] = float(s["tickSz"])
        except Exception:  # noqa: BLE001
            pass
        out = []
        for r in self._data("/api/v5/market/tickers", {"instType": "SWAP"}):
            if not r["instId"].endswith("-USDT-SWAP"):
                continue
            last, o24 = float(r["last"] or 0), float(r.get("open24h") or 0)
            out.append({"symbol": r["instId"].replace("-USDT-SWAP", "USDT"), "last": last,
                        "qv": float(r.get("volCcy24h") or 0) * last, "chg24": (last / o24 - 1) * 100 if o24 else 0.0})
        return out

    def klines(self, sym: str, interval: str, limit: int = 200) -> pd.DataFrame:
        bar = {"1h": "1H", "4h": "4H"}[interval]
        rows = self._data("/api/v5/market/candles", {"instId": self.inst(sym), "bar": bar, "limit": min(limit, 300)})
        return _df([r[:6] for r in rows])

    def funding(self, sym: str) -> float | None:
        d = self._data("/api/v5/public/funding-rate", {"instId": self.inst(sym)})
        return float(d[0]["fundingRate"]) * 100 if d else None

    def oi_change(self, sym: str) -> float | None:
        d = self._data("/api/v5/rubik/stat/contracts/open-interest-history", {"instId": self.inst(sym), "period": "1H", "limit": 25})
        v = [float(r[3]) for r in sorted(d, key=lambda r: int(r[0]))]
        return (v[-1] / v[0] - 1) * 100 if len(v) >= 2 and v[0] else None

    def tick(self, sym: str) -> float | None:
        return self._tick.get(sym)


class BinanceSpot(Binance):
    name, label = "binance_spot", "바이낸스 현물 공개 미러 (선물 API 접속 제한으로 대체 · 펀딩비·미결제약정 없음)"
    B = "https://data-api.binance.vision"

    def tickers(self) -> list[dict]:
        rows = retry(_get, f"{self.B}/api/v3/ticker/24hr", tries=3, label="바이낸스 현물")
        return [{"symbol": r["symbol"], "last": float(r["lastPrice"]), "qv": float(r["quoteVolume"]),
                 "chg24": float(r["priceChangePercent"])} for r in rows if r["symbol"].endswith("USDT")]

    def klines(self, sym: str, interval: str, limit: int = 200) -> pd.DataFrame:
        rows = retry(_get, f"{self.B}/api/v3/klines", {"symbol": sym, "interval": interval, "limit": limit}, tries=3, label=sym)
        return _df([r[:6] for r in rows])

    def funding(self, sym):
        return None

    def oi_change(self, sym):
        return None


def pick_source(force: str | None = None):
    """접속되는 첫 데이터 출처와 거래대금 목록을 돌려준다."""
    order = [Binance, OKX, BinanceSpot]
    if force:
        order = [c for c in order if c.name == force] + [c for c in order if c.name != force]
    errs = []
    for cls in order:
        src = cls()
        try:
            tk = src.tickers()
            if len(tk) >= 10:
                print(f"  ✓ 코인 데이터: {src.label} ({len(tk)}종목)")
                return src, tk, errs
            errs.append(f"{cls.name}: 종목 {len(tk)}개")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{cls.name}: {type(e).__name__} {str(e)[:80]}")
            print(f"  ✗ {cls.name}: {e}")
    raise RuntimeError("코인 데이터 출처에 모두 접속하지 못했습니다: " + " / ".join(errs))


# ───────────────────────── 지표 ─────────────────────────
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(c: pd.Series, n: int = 14) -> float:
    from indicators import rsi as _rsi
    return float(_rsi(c, n).iloc[-1])


def atr_pct(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1] / c.iloc[-1] * 100)


def closed(df: pd.DataFrame, hours: int, now: datetime) -> pd.DataFrame:
    """지금 시각 기준 이미 끝난 봉만."""
    return df[df.index + pd.Timedelta(hours=hours) <= pd.Timestamp(now)]


def coin_feats(src, sym: str, now: datetime) -> dict | None:
    h1 = closed(src.klines(sym, "1h", 200), 1, now)
    h4 = closed(src.klines(sym, "4h", 200), 4, now)
    if len(h1) < 60 or len(h4) < 60:
        return None
    c1, c4 = h1["Close"], h4["Close"]
    e20_4, e50_4 = ema(c4, 20), ema(c4, 50)
    e20_1 = ema(c1, 20)
    last = h1.iloc[-1]
    c = float(last.Close)
    rng = max(float(last.High - last.Low), 1e-12)
    body_lo, body_hi = min(last.Open, last.Close), max(last.Open, last.Close)
    t24 = h1.tail(24)
    v = h1["Volume"]
    trend4 = (1 if c4.iloc[-1] > e50_4.iloc[-1] and e20_4.iloc[-1] > e50_4.iloc[-1] else
              -1 if c4.iloc[-1] < e50_4.iloc[-1] and e20_4.iloc[-1] < e50_4.iloc[-1] else 0)
    f = {
        "symbol": sym, "coin": coin(sym), "name": coin_name(sym), "close": c, "bar_time": iso(h1.index[-1].to_pydatetime() + timedelta(hours=1)),
        "chg24": float(c / c1.iloc[-25] * 100 - 100), "chg4h": float(c / c1.iloc[-5] * 100 - 100),
        "range24": float((t24["High"].max() - t24["Low"].min()) / c * 100),
        "atr1h": atr_pct(h1), "atr4h": atr_pct(h4), "rsi1h": rsi(c1), "rsi4h": rsi(c4),
        "ema20_1h": float(e20_1.iloc[-1]), "ema20_4h": float(e20_4.iloc[-1]), "ema50_4h": float(e50_4.iloc[-1]),
        "dist1h": float((c / e20_1.iloc[-1] - 1) * 100), "trend4": trend4,
        "vol_ratio": float(v.tail(3).mean() / v.iloc[-27:-3].mean()) if v.iloc[-27:-3].mean() else 1.0,
        "bull": bool(last.Close > last.Open), "bear": bool(last.Close < last.Open),
        "lower_wick": float((body_lo - last.Low) / rng), "upper_wick": float((last.High - body_hi) / rng),
        "hi24": float(t24["High"].max()), "lo24": float(t24["Low"].min()),
    }
    try:
        f["funding"] = src.funding(sym)
    except Exception:  # noqa: BLE001
        f["funding"] = None
    try:
        f["oi_chg24"] = src.oi_change(sym)
    except Exception:  # noqa: BLE001
        f["oi_chg24"] = None
    tail = h1.tail(72)
    f["spark"] = {"t": [kst(x.to_pydatetime(), "%d일 %H시") for x in tail.index], "close": [float(x) for x in tail["Close"]],
                  "ema20": [float(x) for x in e20_1.tail(72)]}
    return f


def setup(f: dict, side: str, cfg: dict) -> dict:
    """한 방향(LONG/SHORT)의 타점 점검표와 점수."""
    L = side == "LONG"
    fr, oi = f.get("funding"), f.get("oi_chg24")
    chk = {
        "4시간봉 추세": f["trend4"] == (1 if L else -1),
        "1시간봉 눌림" if L else "1시간봉 반등": (-1.8 <= f["dist1h"] <= 0.8 and 36 <= f["rsi1h"] <= 58) if L
        else (-0.8 <= f["dist1h"] <= 1.8 and 42 <= f["rsi1h"] <= 64),
        "반등 캔들" if L else "꺾임 캔들": (f["bull"] or f["lower_wick"] >= 0.45) if L else (f["bear"] or f["upper_wick"] >= 0.45),
        "거래량 증가": f["vol_ratio"] >= 1.1,
        "미결제약정 증가": oi is not None and oi > 0 and (f["chg24"] >= -2 if L else f["chg24"] <= 2),
        "펀딩비 과열 아님": fr is None or (fr <= 0.03 if L else fr >= -0.03),
        "변동폭 충분": f["range24"] >= cfg["min_range24"],
    }
    s = sum(chk.values())
    score = (s + (0.6 if chk["거래량 증가"] else 0) + min(f["vol_ratio"], 3) * 0.3
             + (min(abs(oi or 0), 10) / 10 if chk["미결제약정 증가"] else 0)
             + (abs(f["chg4h"]) * -0.15 if (f["chg4h"] < 0) == L else 0))
    ok = chk["4시간봉 추세"] and chk["변동폭 충분"] and s >= 5
    return {"side": side, "checks": chk, "passed": s, "score": round(score, 2), "ok": ok}


# ───────────────────────── 시장 방향 ─────────────────────────
def nasdaq_futures() -> dict | None:
    try:
        import yfinance as yf
        df = retry(lambda: yf.Ticker("NQ=F").history(period="3mo", interval="1d")[["Close"]].dropna(), tries=3, label="나스닥 선물")
        c = df["Close"]
        h = retry(lambda: yf.Ticker("NQ=F").history(period="5d", interval="1h")[["Close"]].dropna(), tries=2, label="나스닥 선물 1h")
        hc = h["Close"]
        chg24 = float(hc.iloc[-1] / hc.iloc[-24] * 100 - 100) if len(hc) > 24 else float(c.iloc[-1] / c.iloc[-2] * 100 - 100)
        ma20 = float(c.rolling(20).mean().iloc[-1])
        last = float(hc.iloc[-1]) if len(hc) else float(c.iloc[-1])
        return {"close": round(last, 2), "chg24": round(chg24, 2), "ma20": round(ma20, 2), "above20": last >= ma20,
                "time": kst(hc.index[-1].to_pydatetime()) if len(hc) else None}
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ 나스닥 선물: {e}")
        return None


def market_bias(btc: dict, nq: dict | None) -> dict:
    s_btc = (1.0 if btc["close"] > btc["ema50_4h"] else -1.0) + (0.5 if btc["ema20_4h"] > btc["ema50_4h"] else -0.5)
    s_btc += 0.5 if btc["chg24"] > 1 else -0.5 if btc["chg24"] < -1 else 0
    s_nq = 0.0
    if nq:
        s_nq = (0.5 if nq["chg24"] > 0 else -0.5) + (0.5 if nq["above20"] else -0.5)
    total = round(s_btc + 0.6 * s_nq, 2)
    side = "LONG" if total >= 0.75 else "SHORT" if total <= -0.75 else "NEUTRAL"
    why = [f"비트코인 {btc['close']:,.0f}달러, 24시간 {btc['chg24']:+.1f}% · 4시간봉 50선 {'위' if btc['close'] > btc['ema50_4h'] else '아래'}"
           f"({'상승' if btc['ema20_4h'] > btc['ema50_4h'] else '하락'} 배열)"]
    if nq:
        why.append(f"나스닥100 선물 24시간 {nq['chg24']:+.1f}% · 20일 평균선 {'위' if nq['above20'] else '아래'}")
    ko = {"LONG": "🟢 롱 우위", "SHORT": "🔴 숏 우위", "NEUTRAL": "⚪ 중립 (양방향 모두 신중)"}[side]
    return {"side": side, "score": total, "btc_score": s_btc, "nq_score": s_nq, "label": ko, "why": why}


# ───────────────────────── 1) 판정 ─────────────────────────
def roe_of(pos: dict, price: float, cfg: dict) -> float:
    mv = (price / pos["entry"] - 1) * 100 * (1 if pos["direction"] == "LONG" else -1)
    return round(mv * pos.get("leverage", cfg["leverage"]) - cfg["fee_roe"], 2)


def _finish(pos: dict, kind: str, price: float | None, at: datetime, reason: str, cfg: dict, fx: float, log: dict, events: list):
    if kind == "WIN":
        roe = cfg["win_roe"]
    elif kind == "LOSS":
        roe = -cfg["loss_roe"]
    elif kind in ("NO_FILL", "CANCEL"):
        roe = 0.0
    else:
        roe = roe_of(pos, price, cfg)
    margin = pos.get("margin", cfg["margin_usdt"])
    pnl = round(margin * roe / 100, 2)
    rec = {k: pos.get(k) for k in ("id", "symbol", "name", "direction", "source", "pick_time", "limit", "entry", "entry_time",
                                   "tp", "sl", "qty", "margin", "leverage")}
    rec.update(exit=price, exit_time=iso(at), result=kind, result_ko=RESULT_KO[kind], roe=roe, pnl_usdt=pnl,
               pnl_krw=int(round(pnl * fx)), fx=round(fx, 1), reason=reason)
    log["history"].append(rec)
    events.append({"type": "close" if kind not in ("NO_FILL", "CANCEL") else "missed", **rec})
    pos["status"] = "CLOSED"


def evaluate(src, log: dict, now: datetime, cfg: dict, fx: float) -> list:
    events = []
    for pos in log["positions"]:
        if pos["status"] == "CLOSED":
            continue
        start = parse(pos.get("entry_time") if pos["status"] == "OPEN" and pos.get("source") == "manual" else pos["pick_time"])
        end = start + timedelta(hours=pos.get("hold_hours", cfg["hold_hours"]))
        try:
            df = closed(src.klines(pos["symbol"], "1h", 200), 1, now)
        except Exception as e:  # noqa: BLE001
            events.append({"type": "nodata", "symbol": pos["symbol"], "name": pos.get("name"), "reason": str(e)[:80]})
            continue
        checked = parse(pos["checked_to"]) if pos.get("checked_to") else None
        L = pos["direction"] == "LONG"
        for ts, bar in df.iterrows():
            t0 = ts.to_pydatetime()
            t1 = t0 + timedelta(hours=1)
            if t0 < start.replace(minute=0, second=0) + (timedelta(hours=1) if start.minute or start.second else timedelta(0)):
                continue            # 추천(진입) 시각 이전 봉은 보지 않음 (미래 정보 차단)
            if checked and t1 <= checked:
                continue
            if t1 > end:
                break
            h, l, c = float(bar.High), float(bar.Low), float(bar.Close)
            pos["checked_to"] = iso(t1)
            first = False
            if pos["status"] == "PENDING":
                if (l <= pos["limit"]) if L else (h >= pos["limit"]):
                    pos.update(status="OPEN", entry=pos["limit"], entry_time=iso(t0))
                    events.append({"type": "fill", "symbol": pos["symbol"], "name": pos.get("name"), "direction": pos["direction"],
                                   "price": pos["limit"], "time": iso(t0)})
                    first = True
                else:
                    continue
            hit_sl = (l <= pos["sl"]) if L else (h >= pos["sl"])
            hit_tp = (h >= pos["tp"]) if L else (l <= pos["tp"])
            if hit_sl:
                both = " (같은 1시간 안에 목표가에도 닿았지만 순서를 알 수 없어 보수적으로 손절로 계산)" if hit_tp else ""
                _finish(pos, "LOSS", pos["sl"], t1, f"{kst(t0)} 봉에서 손절가 {fmt_px(pos['sl'])}에 닿았어요.{both}", cfg, fx, log, events)
                break
            if hit_tp and not first:
                _finish(pos, "WIN", pos["tp"], t1, f"{kst(t0)} 봉에서 목표가 {fmt_px(pos['tp'])}에 닿아 익절했어요.", cfg, fx, log, events)
                break
            pos["last"] = {"time": iso(t1), "close": c}
        if pos["status"] == "CLOSED":
            continue
        if now >= end:
            if pos["status"] == "PENDING":
                _finish(pos, "NO_FILL", None, end, f"24시간 동안 예약가 {fmt_px(pos['limit'])}에 닿지 않아 체결되지 않았어요.", cfg, fx, log, events)
            else:
                px = (pos.get("last") or {}).get("close") or pos["entry"]
                _finish(pos, "TIME_EXIT", px, end, f"24시간이 지나 {kst(end)} 종가 {fmt_px(px)}에 정리했어요.", cfg, fx, log, events)
    log["positions"] = [p for p in log["positions"] if p["status"] != "CLOSED"]
    return events


# ───────────────────────── 2) 보유 포지션 대응 ─────────────────────────
def plan_open(pos: dict, price: float, now: datetime, cfg: dict) -> dict:
    L = pos["direction"] == "LONG"
    sign = 1 if L else -1
    mv = (price / pos["entry"] - 1) * 100 * sign
    start = parse(pos.get("entry_time") if pos.get("source") == "manual" else pos["pick_time"])
    end = start + timedelta(hours=pos.get("hold_hours", cfg["hold_hours"]))
    left = max(0, int((end - now).total_seconds() // 3600))
    if pos["status"] == "PENDING":
        return {"action": f"예약 {'매수' if L else '매도'} {fmt_px(pos['limit'])} 유지 · {kst(end)}까지 안 닿으면 취소",
                "price": pos["limit"], "kind": "wait", "left": left, "move": round(mv, 2),
                "reason": "아직 진입가에 닿지 않았어요. 추격 진입은 하지 않습니다."}
    if mv >= 1.2:
        be = rp(pos["entry"] * (1 + 0.1 / 100 * sign))
        pos["sl"] = be
        return {"action": f"손절가를 본전 {fmt_px(be)}로 옮기고 목표가 {fmt_px(pos['tp'])} 유지", "price": pos["tp"], "kind": "good",
                "left": left, "move": round(mv, 2),
                "reason": f"가격 기준 {mv:+.2f}%(수익률 {mv * pos['leverage']:+.1f}%) 앞서 있어 이익을 지키는 쪽으로 손절선을 올립니다."}
    if mv <= -0.9:
        ex = rp(pos["entry"] * (1 + 0.15 / 100 * sign))
        return {"action": f"탈출 지정가 {fmt_px(ex)}(본전 근처) + 손절가 {fmt_px(pos['sl'])} 유지", "price": ex, "kind": "risk",
                "left": left, "move": round(mv, 2),
                "reason": f"가격 기준 {mv:+.2f}%(수익률 {mv * pos['leverage']:+.1f}%) 밀려 있어요. 본전에 돌아오면 바로 빠지고, 손절가는 절대 넓히지 않습니다."}
    return {"action": f"목표가 {fmt_px(pos['tp'])} · 손절가 {fmt_px(pos['sl'])} 그대로 · {kst(end)}에 시간 정리", "price": pos["tp"],
            "kind": "wait", "left": left, "move": round(mv, 2), "reason": "진입가 근처에서 움직이고 있어 처음 계획을 그대로 지킵니다."}


# ───────────────────────── 3) 원픽 ─────────────────────────
def make_order(f: dict, side: str, cfg: dict, tick: float | None) -> dict:
    L = side == "LONG"
    c = f["close"]
    off = min(0.8, max(0.15, 0.3 * f["atr1h"]))          # 1시간 평균 변동폭의 약 30% 유리한 자리
    entry = rp(c * (1 - off / 100) if L else c * (1 + off / 100), tick)
    tp = rp(entry * (1 + cfg["tp_pct"] / 100) if L else entry * (1 - cfg["tp_pct"] / 100), tick)
    sl = rp(entry * (1 - cfg["sl_pct"] / 100) if L else entry * (1 + cfg["sl_pct"] / 100), tick)
    lev, mg = cfg["leverage"], cfg["margin_usdt"]
    liq = rp(entry * (1 - 1 / lev + cfg["mmr"] / 100) if L else entry * (1 + 1 / lev - cfg["mmr"] / 100), tick)
    return {"entry": entry, "off_pct": round(off, 2), "tp": tp, "sl": sl, "liq": liq, "leverage": lev, "margin": mg,
            "notional": round(mg * lev, 2), "qty": qty_for(mg * lev, entry),
            "win_usdt": round(mg * cfg["win_roe"] / 100, 2), "loss_usdt": round(-mg * cfg["loss_roe"] / 100, 2)}


def story(f: dict, side: str, o: dict, bias: dict) -> list[str]:
    L = side == "LONG"
    a = (f"4시간봉이 50봉 평균선 {'위에서 오르는' if L else '아래에서 내리는'} 흐름이에요 "
         f"(24시간 {f['chg24']:+.1f}%). 오늘 시장 방향은 {bias['label'].split(' ', 1)[1]}입니다.")
    if L:
        b = (f"1시간봉이 20봉 평균선 근처({f['dist1h']:+.1f}%)까지 쉬어 가며 과열이 식었고(RSI {f['rsi1h']:.0f}), "
             f"{'마지막 봉이 양봉으로 반등' if f['bull'] else '아래꼬리로 저가 매수세가 확인'}됐어요.")
    else:
        b = (f"1시간봉이 20봉 평균선 근처({f['dist1h']:+.1f}%)까지 되돌림 반등했다가(RSI {f['rsi1h']:.0f}) "
             f"{'마지막 봉이 음봉으로 꺾였어요' if f['bear'] else '위꼬리로 매도 압력이 확인됐어요'}.")
    extra = []
    if f.get("oi_chg24") is not None:
        extra.append(f"미결제약정 24시간 {f['oi_chg24']:+.1f}%")
    if f.get("funding") is not None:
        extra.append(f"펀딩비 {f['funding']:+.4f}%")
    extra.append(f"최근 3시간 거래량 평소의 {f['vol_ratio']:.1f}배")
    c = (f"{' · '.join(extra)}. 진입가 {fmt_px(o['entry'])}에서 {'+' if L else '-'}2.45%면 목표, "
         f"{'-' if L else '+'}1.50%면 미련 없이 손절합니다.")
    return [a, b, c]


def run(today: str, cfg_all: dict, fx: float, now: datetime | None = None, force_source: str | None = None) -> dict:
    cfg = {**DEFAULTS, **(cfg_all.get("futures") or {})}
    now = now or now_utc()
    log = load_log()
    print("[B1] 코인 데이터 출처")
    src, tk, src_errs = pick_source(force_source)
    tick = getattr(src, "tick", lambda s: None)

    # 같은 날 다시 돌리면 오늘 만든 자동 추천은 지우고 새로 (수동 입력 반영)
    log["positions"] = [p for p in log["positions"]
                        if not (p["status"] == "PENDING" and p.get("pick_date") == today and p.get("source") == "auto")]
    print("[B2] 지난 추천·보유 판정")
    events = evaluate(src, log, now, cfg, fx)
    prev = log.get("last_events") or {}
    if prev.get("date") == today:
        events = prev.get("events", []) + events
    log["last_events"] = {"date": today, "events": events}
    for e in events:
        print(f"  · {e['type']}: {e.get('symbol')} {e.get('result_ko', '')} {e.get('roe', '')}")

    print("[B3] 시장 방향 (비트코인 + 나스닥 선물)")
    cand = [t for t in tk if coin(t["symbol"]) not in STABLE and t["qv"] > 0]
    cand.sort(key=lambda t: -t["qv"])
    syms = [t["symbol"] for t in cand[:cfg["top_n"]]]
    have = {t["symbol"] for t in cand}
    for m in MAJORS:
        s = f"{m}USDT"
        if s in have and s not in syms and len(syms) < cfg["top_n"] + 5:
            syms.append(s)
    if "BTCUSDT" not in syms:
        syms.insert(0, "BTCUSDT")
    feats = {}
    for s in syms:
        try:
            f = coin_feats(src, s, now)
            if f:
                f["qv"] = next((t["qv"] for t in cand if t["symbol"] == s), 0)
                feats[s] = f
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {s}: {e}")
    if "BTCUSDT" not in feats:
        raise RuntimeError("비트코인 시세를 받지 못했습니다.")
    btc = feats["BTCUSDT"]
    nq = nasdaq_futures()
    bias = market_bias(btc, nq)
    print(f"  ✓ {bias['label']} (점수 {bias['score']}) · 분석 {len(feats)}종목")

    print("[B4] 보유 포지션 대응")
    holdings = []
    for p in log["positions"]:
        f = feats.get(p["symbol"])
        price = (f or {}).get("close") or (p.get("last") or {}).get("close") or p.get("entry") or p.get("limit")
        if f is None:
            try:
                price = float(closed(src.klines(p["symbol"], "1h", 3), 1, now)["Close"].iloc[-1])
            except Exception:  # noqa: BLE001
                pass
        plan = plan_open(p, price, now, cfg)
        p["plan"] = plan
        unreal = roe_of(p, price, cfg) if p["status"] == "OPEN" else None
        holdings.append({**p, "now": price, "roe_now": unreal,
                         "pnl_now": round(p.get("margin", cfg["margin_usdt"]) * unreal / 100, 2) if unreal is not None else None})
        print(f"  · {p['symbol']} {p['status']} → {plan['action']}")

    print("[B5] 오늘의 원픽")
    rows = []
    open_syms = {p["symbol"] for p in log["positions"]}
    for s, f in feats.items():
        for side in ("LONG", "SHORT"):
            st = setup(f, side, cfg)
            align = 1.5 if side == bias["side"] else -1.5 if bias["side"] != "NEUTRAL" else 0
            rows.append({"symbol": s, "name": f["name"], "side": side, "score": round(st["score"] + align, 2), "ok": st["ok"],
                         "passed": st["passed"], "checks": st["checks"], "close": f["close"], "chg24": round(f["chg24"], 2),
                         "rsi1h": round(f["rsi1h"], 1), "funding": f.get("funding"), "oi_chg24": f.get("oi_chg24"),
                         "vol_ratio": round(f["vol_ratio"], 2), "range24": round(f["range24"], 1)})
    allowed = (lambda r: r["side"] == bias["side"]) if bias["side"] != "NEUTRAL" else (lambda r: True)
    ok = sorted([r for r in rows if r["ok"] and allowed(r) and r["symbol"] not in open_syms], key=lambda r: -r["score"])
    ranked = sorted(rows, key=lambda r: -r["score"])
    pick, block = None, ""
    if len(log["positions"]) >= cfg["max_open"]:
        block = f"이미 대기·보유 포지션이 {len(log['positions'])}개라 오늘은 새 원픽을 쉬고 기존 포지션 관리에 집중합니다."
    elif not ok:
        side_ko = {"LONG": "롱", "SHORT": "숏", "NEUTRAL": "롱·숏"}[bias["side"]]
        block = (f"오늘은 시장 방향({bias['label'].split(' ', 1)[1]})에 맞는 {side_ko} 조건(4시간봉 추세 + 1시간봉 타점 + 거래량·미결제약정)을 "
                 "충분히 갖춘 코인이 없어요. 억지로 진입하지 않고 쉬어 갑니다.")
    else:
        r = ok[0]
        f = feats[r["symbol"]]
        o = make_order(f, r["side"], cfg, tick(r["symbol"]))
        pick = {**{k: v for k, v in f.items() if k != "spark"}, "side": r["side"], "score": r["score"], "checks": r["checks"],
                "order": o, "story": story(f, r["side"], o, bias), "spark": f["spark"]}
        end = now + timedelta(hours=cfg["hold_hours"])
        pick["valid_until"] = iso(end)
        log["positions"].append({
            "id": f"{today}-{r['symbol']}", "symbol": r["symbol"], "name": f["name"], "direction": r["side"], "source": "auto",
            "status": "PENDING", "pick_date": today, "pick_time": iso(now), "limit": o["entry"], "tp": o["tp"], "sl": o["sl"],
            "qty": o["qty"], "margin": o["margin"], "leverage": o["leverage"], "hold_hours": cfg["hold_hours"], "liq": o["liq"],
        })
        print(f"  ✓ {r['symbol']} {r['side']} 진입 {o['entry']} / TP {o['tp']} / SL {o['sl']}")
    near = [r for r in ranked if not (pick and r["symbol"] == pick["symbol"] and r["side"] == pick["side"])][:4]

    log.update(updated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M"), last_run=today, rules={k: cfg[k] for k in DEFAULTS},
               source=src.name)
    save_json(LOG_P, log)
    return {
        "source": src.name, "source_label": src.label, "source_errors": src_errs, "generated_at": kst(now, "%Y-%m-%d %H:%M"),
        "data_time": kst(btc["bar_time"]), "bias": bias, "btc": {k: btc[k] for k in ("close", "chg24", "ema20_4h", "ema50_4h", "rsi4h", "funding", "oi_chg24")},
        "nq": nq, "events": events, "holdings": holdings, "pick": pick, "near": near, "block": block,
        "universe": len(feats), "rules": {k: cfg[k] for k in DEFAULTS}, "record": track(log, fx),
    }


# ───────────────────────── 4) 성적 ─────────────────────────
def track(log: dict, fx: float) -> dict:
    tr = [h for h in log["history"] if h.get("result") not in ("NO_FILL", "CANCEL")]
    tr.sort(key=lambda h: h.get("exit_time") or "")
    wins = [h for h in tr if h["pnl_usdt"] > 0]
    cum, curve = 0.0, []
    for h in tr:
        cum += h["pnl_usdt"]
        curve.append({"date": kst(h["exit_time"], "%m/%d"), "cum_usdt": round(cum, 2), "symbol": h["symbol"]})
    return {
        "since": log["start_date"], "trades": len(tr), "wins": len(wins), "losses": len(tr) - len(wins),
        "winrate": round(len(wins) / len(tr) * 100, 1) if tr else None,
        "pnl_usdt": round(cum, 2), "pnl_krw": int(round(sum(h.get("pnl_krw", 0) for h in tr))),
        "avg_roe": round(sum(h["roe"] for h in tr) / len(tr), 2) if tr else None,
        "tp_hits": sum(1 for h in tr if h["result"] == "WIN"), "sl_hits": sum(1 for h in tr if h["result"] == "LOSS"),
        "no_fill": sum(1 for h in log["history"] if h.get("result") == "NO_FILL"),
        "curve": curve, "recent": list(reversed(tr[-8:])),
    }


# ───────────────────────── 수동 입력 ─────────────────────────
def parse_qty(q: str | None, price: float, cfg: dict) -> tuple[float, float]:
    """(증거금 USDT, 코인 수량). 숫자만 → 증거금 USDT, '7.6개'·'7.6coin' → 코인 수량."""
    lev = cfg["leverage"]
    if not q:
        m = cfg["margin_usdt"]
        return m, qty_for(m * lev, price)
    s = str(q).strip().replace(",", "").upper()
    for suf in ("개", "COIN", "COINS", "EA"):
        if s.endswith(suf):
            n = float(s[: -len(suf)])
            return round(n * price / lev, 2), n
    n = float(s.replace("USDT", "").replace("U", "").strip())
    return n, qty_for(n * lev, price)


def manual(action: str, sym: str, direction: str, price: float | None, qty: str | None, cfg_all: dict, fx: float) -> str:
    cfg = {**DEFAULTS, **(cfg_all.get("futures") or {})}
    act = action.strip().split()[0].upper()
    sym = sym.strip().upper().replace("-", "").replace("/", "")
    if not sym.endswith("USDT"):
        sym += "USDT"
    log = load_log()
    now = now_utc()
    mine = [p for p in log["positions"] if p["symbol"] == sym]
    if act == "BUY":
        if not price or price <= 0:
            raise SystemExit("price(내 실제 진입가)를 넣어 주세요.")
        d = (direction or "LONG").strip().split()[0].upper()
        if d not in ("LONG", "SHORT"):
            raise SystemExit("direction 은 LONG 또는 SHORT")
        margin, q = parse_qty(qty, price, cfg)
        L = d == "LONG"
        p = next((x for x in mine if x["direction"] == d), None)
        if p is None:
            p = {"id": f"{datetime.now(KST):%Y-%m-%d}-{sym}-m{datetime.now(KST):%H%M}", "symbol": sym, "name": coin_name(sym),
                 "direction": d, "pick_date": datetime.now(KST).strftime("%Y-%m-%d"), "pick_time": iso(now), "hold_hours": cfg["hold_hours"]}
            log["positions"].append(p)
        p.update(source="manual", status="OPEN", entry=price, entry_time=iso(now), limit=price, margin=margin, qty=q,
                 leverage=cfg["leverage"], checked_to=None,
                 tp=rp(price * (1 + cfg["tp_pct"] / 100) if L else price * (1 - cfg["tp_pct"] / 100)),
                 sl=rp(price * (1 - cfg["sl_pct"] / 100) if L else price * (1 + cfg["sl_pct"] / 100)),
                 liq=rp(price * (1 - 1 / cfg["leverage"] + cfg["mmr"] / 100) if L else price * (1 + 1 / cfg["leverage"] - cfg["mmr"] / 100)))
        p.pop("plan", None)
        msg = (f"{sym} {('🟢 LONG' if L else '🔴 SHORT')} {fmt_px(price)} 진입 반영 · 증거금 {margin:,.2f} USDT · 수량 {q} "
               f"(목표 {fmt_px(p['tp'])} / 손절 {fmt_px(p['sl'])} / {kst(now + timedelta(hours=cfg['hold_hours']))} 시간 정리)")
    elif act == "CLOSE":
        p = next((x for x in mine if x["status"] == "OPEN"), None) or (mine[0] if mine else None)
        if p is None:
            raise SystemExit(f"{sym} 보유 포지션이 없어요.")
        if not price or price <= 0:
            raise SystemExit("price(내 실제 청산가)를 넣어 주세요.")
        if p["status"] == "PENDING":
            p.update(entry=p["limit"], entry_time=p["pick_time"], status="OPEN")
        p["source"] = "manual"
        _finish(p, "CLOSE", price, now, f"내 계좌 실제 청산 (수동 입력 {datetime.now(KST):%m/%d %H:%M})", cfg, fx, log, [])
        log["positions"].remove(p)
        h = log["history"][-1]
        msg = f"{sym} {fmt_px(price)} 청산 기록 (수익률 {h['roe']:+.2f}%, {h['pnl_usdt']:+,.2f} USDT ≈ {h['pnl_krw']:+,}원)"
    elif act == "CANCEL":
        p = next((x for x in mine if x["status"] == "PENDING"), None) or (mine[0] if mine else None)
        if p is None:
            raise SystemExit(f"{sym} 대기·보유 포지션이 없어요.")
        p["source"] = "manual"
        _finish(p, "CANCEL", None, now, f"직접 삭제 (수동 입력 {datetime.now(KST):%m/%d %H:%M})", cfg, fx, log, [])
        log["positions"].remove(p)
        msg = f"{sym} 주문/포지션 기록 삭제"
    else:
        raise SystemExit(f"알 수 없는 작업: {action} (BUY / CLOSE / CANCEL)")
    log["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    save_json(LOG_P, log)
    return msg


def main():
    import yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--manual", required=True, help="BUY / CLOSE / CANCEL")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--direction", default="LONG")
    ap.add_argument("--price", type=float)
    ap.add_argument("--qty", default="")
    ap.add_argument("--fx", type=float)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    fx = a.fx
    if not fx:
        from swing import usdkrw
        fx, _ = usdkrw()
    print(manual(a.manual, a.ticker, a.direction, a.price, a.qty, cfg, fx))


if __name__ == "__main__":
    main()
