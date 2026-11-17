"""미국 주식 실전 단타 연습 (1~2거래일 보유) — 매일 18:00 KST.

하는 일 (순서대로):
  1) data/us_swing_portfolio.json 을 읽고, 간밤(들) 미국장 일봉으로 보유·예약 종목을 판정
       예약 매수(PENDING) → 장중 저가 ≤ 예약가면 체결(HOLDING), 아니면 미체결(MISSED)
       보유(HOLDING)      → 고가 ≥ 매도가면 익절, 저가 ≤ 손절가면 손절, 기한이면 종가 정리
  2) 남은 보유 종목의 '오늘 밤 대응 작전'(탈출 지정가 / 종가 정리 / 시초가 정리 / 1일 연장)
  3) 빈 슬롯만큼 오늘 밤 신규 타점 1~2개 (하루 변동폭 3.5% 이상 + 눌림목 반등형 / 모멘텀 돌파형)
  4) 50만 원 예산 → 정수 주식 수, 예약 매수가·목표가(+5%)·손절가(-3.5%)
  5) data/trade_history.json 누적 성적 + docs/swing/ 리포트

사용법:
  python swing.py                       # 오늘 날짜(KST)로 실행
  python swing.py --date 2026-11-17
  python swing.py --manual 매수추가 --ticker PLTR --price 25.4 --qty 4     # 내 실제 계좌 반영
  python swing.py --manual 매도완료 --ticker PLTR --price 26.7 [--qty 4]
  python swing.py --manual 수량·단가수정 --ticker PLTR --price 25.1 --qty 5
  python swing.py --manual 미체결삭제 --ticker PLTR

※ 연습용 가상 매매입니다. 수수료·세금·환전 비용은 계산에 넣지 않았습니다.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date as Date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from netretry import retry

KST = timezone(timedelta(hours=9))
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
import os  # noqa: E402
_DATA = Path(os.environ.get("SWING_DATA_DIR") or ROOT / "data")     # 시험할 때는 다른 폴더로
PORT_P = _DATA / "us_swing_portfolio.json"
HIST_P = _DATA / "trade_history.json"

# 뉴욕증권거래소 휴장일 (주말 제외)
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19", "2028-07-04", "2028-09-04",
    "2028-11-23", "2028-12-25",
}
# 반일장 (13:00 ET 마감)
NYSE_HALF = {"2026-11-27", "2026-12-24", "2027-11-26", "2028-07-03", "2028-11-24"}

RESULT_KO = {"WIN": "목표 달성 익절", "PROFIT": "약익절 탈출", "FLAT": "본전 탈출", "LOSS": "손실 정리",
             "STOP": "손절", "MISSED": "미체결 취소", "CANCEL": "주문 삭제"}

DEFAULTS = {
    "budget_krw": 500000, "target_pct": 5.0, "stop_pct": 3.5, "max_hold": 2, "max_slots": 3, "max_new": 2,
    "atr_min": 3.5, "min_price": 3.0, "min_dollar_vol": 1.0e8,
}


# ───────────────────────── 날짜·시간 ─────────────────────────
def is_trading_day(d: Date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in NYSE_HOLIDAYS


def prev_trading_day(d: Date) -> Date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d: Date) -> Date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def session_info(d: Date) -> dict:
    """오늘 밤(미국 날짜 d) 정규장 시간 (KST)."""
    op = datetime.combine(d, time(9, 30), ET)
    cl = datetime.combine(d, time(13 if d.isoformat() in NYSE_HALF else 16, 0), ET)
    dst = bool(op.dst())
    nxt = next_trading_day(d)
    ncl = datetime.combine(nxt, time(13 if nxt.isoformat() in NYSE_HALF else 16, 0), ET)
    return {
        "date": d.isoformat(), "trading": is_trading_day(d), "dst": dst,
        "open_kst": op.astimezone(KST).strftime("%H:%M"), "close_kst": cl.astimezone(KST).strftime("%H:%M"),
        "open_kst_full": op.astimezone(KST).strftime("%m/%d %H:%M"),
        "next_date": nxt.isoformat(), "next_close_kst": ncl.astimezone(KST).strftime("%m/%d %H:%M"),
        "half": d.isoformat() in NYSE_HALF,
        "next_open": datetime.combine(nxt, time(9, 30), ET).astimezone(KST).strftime("%m/%d %H:%M"),
    }


def current_session(now: datetime | None = None) -> Date:
    """지금 이미 열렸거나 끝난 가장 최근 정규장의 미국 날짜 (수동 입력 기준일)."""
    now = (now or datetime.now(KST)).astimezone(ET)
    d = now.date()
    if is_trading_day(d) and now.time() >= time(9, 30):
        return d
    return prev_trading_day(d)


# ───────────────────────── 파일 ─────────────────────────
def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def load_state() -> tuple[dict, list]:
    port = load_json(PORT_P, {})
    port.setdefault("start_date", datetime.now(KST).strftime("%Y-%m-%d"))
    port.setdefault("positions", [])
    hist = load_json(HIST_P, [])
    return port, hist


def r2(x) -> float:
    return round(float(x) + 1e-9, 2)


# ───────────────────────── 시세 ─────────────────────────
def download(tickers: list[str], period: str = "9mo") -> dict[str, pd.DataFrame]:
    import yfinance as yf
    tickers = sorted(set(tickers))
    raw = retry(yf.download, tickers, period=period, interval="1d", auto_adjust=False, group_by="ticker",
                progress=False, threads=True, tries=3, label="yfinance")
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            if len(df):
                out[t] = df
        except Exception:  # noqa: BLE001
            pass
    return out


def usdkrw() -> tuple[float, str]:
    try:
        import yfinance as yf
        s = retry(lambda: yf.Ticker("KRW=X").history(period="5d")["Close"].dropna(), tries=3, label="환율")
        return float(s.iloc[-1]), s.index[-1].strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass
    try:
        import FinanceDataReader as fdr
        s = fdr.DataReader("USD/KRW", (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"))["Close"].dropna()
        return float(s.iloc[-1]), s.index[-1].strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return 1400.0, "기본값"


# ───────────────────────── 지표 ─────────────────────────
def feats(df: pd.DataFrame) -> dict:
    from indicators import rsi
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ma5, ma20 = c.rolling(5).mean(), c.rolling(20).mean()
    vavg = v.shift(1).rolling(20).mean()
    last = df.iloc[-1]
    body = abs(last.Close - last.Open)
    lower = min(last.Open, last.Close) - last.Low
    rng = max(last.High - last.Low, 1e-9)
    return {
        "close": float(last.Close), "open": float(last.Open), "high": float(last.High), "low": float(last.Low),
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "chg1": float(c.iloc[-1] / c.iloc[-2] * 100 - 100) if len(c) > 1 else 0.0,
        "ret3": float(c.iloc[-1] / c.iloc[-4] * 100 - 100) if len(c) > 4 else 0.0,
        "atr": float(atr.iloc[-1]), "atr_pct": float(atr.iloc[-1] / c.iloc[-1] * 100),
        "ma5": float(ma5.iloc[-1]), "ma20": float(ma20.iloc[-1]),
        "ma20_up": bool(ma20.iloc[-1] > ma20.iloc[-6]) if len(ma20.dropna()) > 6 else False,
        "rsi": float(rsi(c).iloc[-1]),
        "vol_ratio": float(v.iloc[-1] / vavg.iloc[-1]) if vavg.iloc[-1] else 0.0,
        "dollar_vol": float((c * v).tail(20).mean()),
        "hi20_prev": float(h.iloc[-21:-1].max()) if len(h) > 21 else float(h.max()),
        "hammer": bool(last.Close >= last.Open and lower >= 1.5 * max(body, rng * 0.05) and lower / rng >= 0.4),
        "up_day": bool(last.Close > last.Open),
    }


# ───────────────────────── 1) 간밤 판정 ─────────────────────────
def _close_pos(pos: dict, price: float, d: str, reason: str, fx: float, hist: list, events: list, kind: str | None = None):
    ret = (price / pos["entry"] - 1) * 100
    pnl = (price - pos["entry"]) * pos["qty"]
    if kind is None:
        kind = "PROFIT" if ret >= 0.5 else "FLAT" if ret > -0.5 else "LOSS"
    rec = {
        "id": pos["id"], "ticker": pos["ticker"], "name": pos.get("name", pos["ticker"]), "source": pos.get("source", "auto"),
        "order_date": pos.get("order_date"), "entry_date": pos.get("entry_date"), "entry": r2(pos["entry"]),
        "exit_date": d, "exit": r2(price), "qty": pos["qty"], "ret_pct": round(ret, 2),
        "pnl_usd": r2(pnl), "pnl_krw": int(round(pnl * fx)), "fx": round(fx, 1), "held": pos.get("held", 0),
        "result": kind, "result_ko": RESULT_KO[kind], "reason": reason,
    }
    hist.append(rec)
    events.append({"type": "close", **rec})
    pos["status"] = "CLOSED"


def step(pos: dict, d: str, bar: pd.Series, fx: float, hist: list, events: list) -> None:
    """미국 일봉 하나로 포지션 하나를 판정 (같은 날 목표·손절 둘 다 닿으면 보수적으로 손절 먼저)."""
    o, h, l, c = float(bar.Open), float(bar.High), float(bar.Low), float(bar.Close)
    first = False
    if pos["status"] == "PENDING":
        if l <= pos["limit"]:
            fill = min(o, pos["limit"])
            pos.update(status="HOLDING", entry=r2(fill), entry_date=d, held=0)
            events.append({"type": "fill", "ticker": pos["ticker"], "name": pos.get("name"), "date": d, "price": r2(fill),
                           "qty": pos["qty"], "low": r2(l), "limit": pos["limit"]})
            first = True
        else:
            pos["status"] = "CLOSED"
            rec = {"id": pos["id"], "ticker": pos["ticker"], "name": pos.get("name"), "source": pos.get("source", "auto"),
                   "order_date": pos.get("order_date"), "exit_date": d, "limit": pos["limit"], "low": r2(l), "qty": pos["qty"],
                   "result": "MISSED", "result_ko": RESULT_KO["MISSED"],
                   "reason": f"장중 최저가 ${l:.2f}가 예약가 ${pos['limit']:.2f}까지 내려오지 않아 체결되지 않았어요."}
            hist.append(rec)
            events.append({"type": "missed", **rec})
            return

    pos["held"] = pos.get("held", 0) + 1
    pos["last"] = {"date": d, "open": r2(o), "high": r2(h), "low": r2(l), "close": r2(c)}
    if pos.pop("skip_first", False):        # 내가 직접 산 날: 장중 순서를 몰라 판정은 다음 날부터
        return
    plan = pos.get("plan") or {}
    mode = plan.get("mode", "target")
    sell = plan.get("price") or pos["target"]
    stop = pos["stop"]
    last_day = pos["held"] >= pos.get("max_hold", 2) and mode != "hold"
    tgt = sell >= pos["target"] - 1e-6

    if not first and mode == "open":
        _close_pos(pos, o, d, "작전대로 시초가에 전량 정리했어요.", fx, hist, events)
    elif not first and o >= sell:
        _close_pos(pos, o, d, f"시초가 ${o:.2f}가 매도가 ${sell:.2f} 위에서 열려 바로 팔렸어요.", fx, hist, events, "WIN" if tgt else None)
    elif not first and o <= stop:
        _close_pos(pos, o, d, f"시초가 ${o:.2f}가 손절가 ${stop:.2f} 아래에서 열려 바로 정리됐어요.", fx, hist, events, "STOP")
    elif l <= stop and not (first and pos["entry"] <= stop):
        both = " (같은 날 목표가에도 닿았지만 순서를 알 수 없어 보수적으로 손절로 계산)" if h >= sell else ""
        _close_pos(pos, stop, d, f"장중 ${l:.2f}까지 밀려 손절가 ${stop:.2f}에 정리됐어요.{both}", fx, hist, events,
                   "STOP" if stop < pos["entry"] else None)
    elif h >= sell:
        _close_pos(pos, sell, d, f"장중 고가 ${h:.2f}가 매도가 ${sell:.2f}에 닿아 팔렸어요.", fx, hist, events, "WIN" if tgt else None)
    elif last_day or mode == "loc":
        why = "작전대로 장 마감(LOC)에 전량 정리했어요." if mode == "loc" else             f"보유 기한({pos['held']}거래일{', 1일 연장 포함' if pos.get('ext_used') else ''})이 끝나 종가에 전량 정리했어요."
        _close_pos(pos, c, d, why, fx, hist, events)


def evaluate(port: dict, data: dict[str, pd.DataFrame], before: Date, fx: float, hist: list) -> list:
    """before(오늘 밤 세션 날짜) 이전의 완성된 일봉만 써서 판정. 같은 날 다시 돌려도 중복 판정하지 않음."""
    events = []
    for pos in port["positions"]:
        df = data.get(pos["ticker"])
        if df is None:
            events.append({"type": "nodata", "ticker": pos["ticker"], "name": pos.get("name")})
            continue
        start = pos.get("last_bar") or ""
        sess = pos.get("session_date") or ""
        for ts, bar in df.iterrows():
            d = ts.strftime("%Y-%m-%d")
            if d >= before.isoformat() or d <= start or d < sess:
                continue
            if pos["status"] == "CLOSED":
                break
            step(pos, d, bar, fx, hist, events)
            pos["last_bar"] = d
    port["positions"] = [p for p in port["positions"] if p["status"] != "CLOSED"]
    return events


# ───────────────────────── 2) 보유 종목 오늘 밤 작전 ─────────────────────────
def plan_holding(pos: dict, f: dict | None, cfg: dict, sess: dict) -> dict:
    e, c = pos["entry"], (pos.get("last") or {}).get("close") or (f or {}).get("close") or pos["entry"]
    ret = (c / e - 1) * 100
    day = pos.get("held", 0) + 1                    # 오늘 밤이 몇 일차인지
    last_day = day >= pos.get("max_hold", 2)
    ma5, ma20 = (f or {}).get("ma5") or c, (f or {}).get("ma20") or c
    rsi_v, vr = (f or {}).get("rsi") or 50, (f or {}).get("vol_ratio") or 1
    above5, above20 = c >= ma5, c >= ma20
    sup = f"5일 평균선 ${ma5:.2f}" + (" 위" if above5 else " 아래")
    tgt = pos["target"]
    if not last_day:
        return {"mode": "target", "price": tgt, "day": day,
                "action": f"목표가 ${tgt:.2f} 예약 매도 유지", "reason": f"아직 {day}일차라 목표가 매도를 그대로 둡니다. 손절가 ${pos['stop']:.2f}도 유지해요."}
    if pos.get("extended"):
        return {"mode": "target", "price": tgt, "day": day,
                "action": f"목표가 ${tgt:.2f} 예약 매도 + 안 되면 장 마감(LOC) 전량 정리",
                "reason": f"하루 연장한 마지막 날입니다. 손절가를 본전 ${pos['stop']:.2f}로 올려 두었어요."}
    # 마지막 날: 감정적 '비자발적 장기투자'를 막기 위한 냉정한 규칙
    if ret >= 2.0 and above5 and c > ma20 and rsi_v < 70 and vr >= 1.0 and not pos.get("ext_used"):
        pos["extended"] = pos["ext_used"] = True
        pos["max_hold"] = pos.get("max_hold", 2) + 1
        pos["stop"] = r2(max(pos["stop"], e * 1.002))
        return {"mode": "hold", "price": tgt, "day": day, "extend": True,
                "action": f"예외적 1일 연장: 목표가 ${tgt:.2f} 유지, 손절가를 본전 ${pos['stop']:.2f}로 올림",
                "reason": (f"수익 {ret:+.1f}%에 {sup}·20일선 위, 거래량도 평소의 {vr:.1f}배라 추세가 살아 있어요. "
                           "단, 본전 아래로 내려오면 바로 정리해 이익을 지킵니다.")}
    if ret >= 2.0:
        return {"mode": "target", "price": tgt, "day": day,
                "action": f"목표가 ${tgt:.2f} 예약 매도 + 안 되면 장 마감(LOC) 전량 정리",
                "reason": f"이미 {ret:+.1f}% 수익 중이라 목표가를 노리되, 마감까지 안 닿으면 수익을 확정합니다."}
    if ret <= -2.5 and not above5 and not above20:
        return {"mode": "open", "price": None, "day": day,
                "action": "오늘 밤 시초가에 전량 정리 (교체 매매)",
                "reason": (f"{ret:+.1f}% 손실에 {sup}, 20일 평균선 ${ma20:.2f}까지 깨져 반등 근거가 약해요. "
                           "기다리면 손절가까지 밀릴 가능성이 커 빨리 정리하고 다음 기회를 봅니다.")}
    if above5 and ret > -2.0:
        px = r2(e * 1.02)
        return {"mode": "limit", "price": px, "day": day,
                "action": f"${px:.2f} 약익절 예약 매도 (+2%) + 안 되면 장 마감(LOC) 전량 정리",
                "reason": f"종가가 {sup}에서 버티고 있어 작은 반등은 기대할 수 있어요. 목표 +5% 대신 +2%에서 가볍게 탈출합니다."}
    px = r2(e * 1.003)
    return {"mode": "limit", "price": px, "day": day,
            "action": f"${px:.2f} 본전 탈출 예약 매도 + 안 되면 장 마감(LOC) 전량 정리",
            "reason": (f"{ret:+.1f}%로 {sup}에서 힘이 약해요. 본전(수수료 감안 +0.3%)에 닿으면 바로 나오고, "
                       "못 닿으면 마감에 정리해 손실이 커지기 전에 끊습니다.")}


# ───────────────────────── 3) 신규 타점 ─────────────────────────
def screen(data: dict[str, pd.DataFrame], names: dict, cfg: dict, fx: float, held: set) -> tuple[list, list]:
    picks, near = [], []
    budget_usd = cfg["budget_krw"] / fx
    for t, df in data.items():
        if t not in names or t in held or len(df) < 40:
            continue
        f = feats(df)
        f["ticker"], f["name"] = t, names[t]
        if f["close"] < cfg["min_price"] or f["dollar_vol"] < cfg["min_dollar_vol"] or f["close"] * 0.99 > budget_usd:
            continue
        if not (f["atr_pct"] >= cfg["atr_min"]) or math.isnan(f["rsi"]) or not f["ma20"] == f["ma20"]:
            continue        # 변동폭 부족 또는 시세 이상(NaN)
        a_trend = f["close"] >= f["ma20"] * 0.98 and f["ma20_up"]
        a_dip = f["ret3"] <= -3.0 and 30 <= f["rsi"] <= 45
        a_sign = f["hammer"] or f["vol_ratio"] >= 1.2
        b_vol = f["vol_ratio"] >= 1.5
        b_brk = f["close"] > f["hi20_prev"] and f["up_day"]
        kind, score = None, 0.0
        if a_trend and a_dip and a_sign:
            kind = "pullback"
            score = (45 - f["rsi"]) / 15 + (0.8 if f["hammer"] else 0) + min(f["vol_ratio"], 3) * 0.4 + f["atr_pct"] / 10
        elif b_vol and b_brk and f["rsi"] < 80:
            kind = "breakout"
            score = min(f["vol_ratio"], 4) * 0.5 + (f["close"] / f["hi20_prev"] - 1) * 20 + f["atr_pct"] / 10
        f["checks"] = {"추세(20일선 위·상승)": a_trend, "2~3일 급락·RSI 30~45": a_dip, "아래꼬리 양봉/거래량 유입": a_sign,
                       "거래량 1.5배": b_vol, "20일 고점 돌파": b_brk}
        if kind:
            f["kind"], f["score"] = kind, round(score, 2)
            picks.append(f)
        else:
            f["score"] = round(sum(f["checks"].values()) + f["atr_pct"] / 10, 2)
            near.append(f)
    picks.sort(key=lambda x: -x["score"])
    near.sort(key=lambda x: -x["score"])
    return picks, near[:3]


def make_order(f: dict, cfg: dict, fx: float, sess: dict) -> dict:
    if f["kind"] == "pullback":
        dip = min(2.0, max(0.8, 0.35 * f["atr_pct"]))
        why = f"전일 종가 대비 -{dip:.1f}% 눌림 (하루 평균 변동폭의 약 1/3 아래)"
    else:
        dip = min(1.5, max(0.5, 0.25 * f["atr_pct"]))
        why = f"전일 종가 대비 -{dip:.1f}% (돌파 직후 시초가 흔들림을 기다리는 자리)"
    limit = r2(f["close"] * (1 - dip / 100))
    qty = max(0, math.floor(cfg["budget_krw"] / (limit * fx)))
    target = r2(limit * (1 + cfg["target_pct"] / 100))
    stop = r2(limit * (1 - cfg["stop_pct"] / 100))
    return {
        "limit": limit, "dip_pct": round(dip, 1), "limit_why": why, "qty": qty,
        "cost_usd": r2(limit * qty), "cost_krw": int(round(limit * qty * fx)),
        "target": target, "stop": stop,
        "gain_krw": int(round((target - limit) * qty * fx)), "loss_krw": int(round((stop - limit) * qty * fx)),
        "deadline": f"{sess['next_date'][5:].replace('-', '/')} 미국장 마감 (한국 {sess['next_close_kst']})",
    }


def pick_story(f: dict, o: dict, news: list) -> list[str]:
    """초보자용 3줄 요약 (차트 타점 + 뉴스 재료 + 변동성)."""
    if f["kind"] == "pullback":
        a = (f"오르던 주식이 최근 3일 {f['ret3']:.1f}% 쉬어 가면서 과열이 식었어요 (RSI {f['rsi']:.0f}, 30 근처면 '많이 눌림'). "
             "20일 평균선 위라 큰 흐름은 아직 오름세예요.")
        b = ("어제 아래꼬리 양봉(장중에 밀렸다가 다시 올라와 마감)이 나와 저가 매수세가 들어온 신호예요."
             if f["hammer"] else f"어제 거래량이 평소의 {f['vol_ratio']:.1f}배로 늘어 저가에 사려는 사람이 들어왔어요.")
    else:
        a = (f"어제 최근 20일 최고가(${f['hi20_prev']:.2f})를 넘어 ${f['close']:.2f}에 마감했어요. "
             "막혀 있던 가격을 뚫으면 추가 상승이 이어지기 쉬워요.")
        b = f"거래량이 평소의 {f['vol_ratio']:.1f}배로 터져, 돌파에 힘이 실렸다는 뜻이에요."
    if news:
        b += f" 관련 뉴스: “{news[0]['title'][:70]}”"
    c = (f"하루 평균 {f['atr_pct']:.1f}%씩 움직이는 종목이라 +5%는 하루~이틀이면 닿을 수 있는 거리예요. "
         f"대신 ${o['stop']:.2f}(-3.5%) 아래로 밀리면 미련 없이 정리합니다.")
    return [a, b, c]


def ticker_news(t: str, name: str, n: int = 3) -> list:
    """종목 뉴스: 제목에 그 회사(영문 이름 첫 단어 또는 티커)가 나오는 기사만. 시세 안내 페이지는 제외."""
    import re
    import yfinance as yf
    junk = re.compile(r"stock price|quote|historical|\bchart\b", re.I)
    eng = ""
    try:
        eng = (yf.Ticker(t).info or {}).get("shortName") or ""
    except Exception:  # noqa: BLE001
        pass
    key = re.sub(r"[^A-Za-z0-9&\- ]", " ", eng).split()
    key = key[0] if key and len(key[0]) >= 3 else ""
    pat = re.compile(rf"\b({re.escape(t)}{'|' + re.escape(key) if key else ''})\b", re.I if key else 0)
    out = []

    def add(title, src, link):
        if (title and pat.search(title) and not junk.search(title)
                and title not in [x["title"] for x in out] and len(out) < n):
            out.append({"title": title, "source": src or "", "link": link or ""})
    try:
        for it in (yf.Ticker(t).news or [])[:15]:
            c = it.get("content") or it
            add(c.get("title"), (c.get("provider") or {}).get("displayName") or c.get("publisher"),
                (c.get("canonicalUrl") or {}).get("url") or c.get("link"))
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {t} 야후 뉴스: {e}")
    if len(out) < n:
        try:
            import news as nw
            feed = nw._fetch(nw._gnews(f'"{key or t}" stock', "en"))
            for e in feed.entries[:20]:
                title, src = nw._clean_title(e.get("title", ""))
                add(title, src, e.get("link", ""))
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {t} 구글 뉴스: {e}")
    return out


# ───────────────────────── 4) 성적 ─────────────────────────
def track(hist: list, start: str) -> dict:
    tr = [h for h in hist if h.get("result") not in ("MISSED", "CANCEL")]
    tr.sort(key=lambda h: (h.get("exit_date") or "", h.get("id") or ""))
    wins = [h for h in tr if h["pnl_krw"] > 0]
    cum, curve = 0, []
    for h in tr:
        cum += h["pnl_krw"]
        curve.append({"date": h["exit_date"], "cum_krw": cum, "ticker": h["ticker"]})
    return {
        "since": start, "trades": len(tr), "wins": len(wins), "losses": len(tr) - len(wins),
        "winrate": round(len(wins) / len(tr) * 100, 1) if tr else None,
        "pnl_krw": cum, "pnl_usd": r2(sum(h["pnl_usd"] for h in tr)),
        "avg_ret": round(sum(h["ret_pct"] for h in tr) / len(tr), 2) if tr else None,
        "best": max(tr, key=lambda h: h["ret_pct"]) if tr else None,
        "worst": min(tr, key=lambda h: h["ret_pct"]) if tr else None,
        "targets": sum(1 for h in tr if h["result"] == "WIN"),
        "missed": sum(1 for h in hist if h.get("result") == "MISSED"),
        "curve": curve, "recent": list(reversed(tr[-8:])),
    }


# ───────────────────────── 실행 ─────────────────────────
def spark(df: pd.DataFrame, n: int = 40) -> dict:
    t = df.tail(n + 20).copy()
    t["ma20"] = t["Close"].rolling(20).mean()
    t = t.tail(n)
    return {"dates": [d.strftime("%m/%d") for d in t.index], "close": [r2(x) for x in t["Close"]],
            "ma20": [None if pd.isna(x) else r2(x) for x in t["ma20"]],
            "high": [r2(x) for x in t["High"]], "low": [r2(x) for x in t["Low"]]}


def run(today: str, cfg_all: dict, out: Path) -> dict:
    cfg = {**DEFAULTS, **(cfg_all.get("swing") or {})}
    names = {str(k): v for k, v in (cfg.get("universe") or {}).items()}
    tonight = Date.fromisoformat(today)
    sess = session_info(tonight)
    port, hist = load_state()
    print(f"[1/5] 환율·시세 ({len(names)}종목 + 보유 {len(port['positions'])}개)")
    fx, fx_date = usdkrw()
    tick = list(names) + [p["ticker"] for p in port["positions"]] + ["QQQ", "^VIX"]
    data = download(tick)
    print(f"  ✓ 시세 {len(data)}개, 원/달러 {fx:,.1f} ({fx_date})")
    # 시간 기준: 오늘 밤 세션 전까지 완성된 일봉만
    data = {t: df[df.index < pd.Timestamp(tonight)] for t, df in data.items()}
    last_bar = max((df.index[-1] for df in data.values() if len(df)), default=None)

    # 같은 날 다시 돌리면 오늘 만든 자동 예약은 지우고 새로 계산 (중복 방지, 수동 입력 반영)
    port["positions"] = [p for p in port["positions"]
                         if not (p["status"] == "PENDING" and p.get("order_date") == today and p.get("source") == "auto")]
    print("[2/5] 간밤 판정")
    events = evaluate(port, data, tonight, fx, hist)
    # 같은 날 다시 만들 때(수동 입력 후 재작성 등)도 간밤 판정 결과가 리포트에 남도록 저장
    prev = port.get("last_events") or {}
    if prev.get("date") == today:
        events = prev.get("events", []) + events
    port["last_events"] = {"date": today, "events": events}
    for e in events:
        print(f"  · {e['type']}: {e.get('ticker')} {e.get('result_ko', '')} {e.get('reason', '')[:50]}")

    print("[3/5] 보유 종목 오늘 밤 작전")
    holdings = []
    for p in port["positions"]:
        if p["status"] != "HOLDING":
            continue
        df = data.get(p["ticker"])
        f = feats(df) if df is not None and len(df) > 25 else None
        if (p.get("plan") or {}).get("made") == today:
            pass        # 같은 날 다시 만들 때는 이미 정한 작전(연장 판정 포함)을 그대로
        else:
            p["plan"] = {**(plan_holding(p, f, cfg, sess) if sess["trading"] else (p.get("plan") or {"mode": "target", "price": p["target"],
                                                                                              "action": "오늘 밤 휴장 — 기존 주문 유지", "reason": "미국장이 쉬는 날입니다."})), "made": today}
        c = (p.get("last") or {}).get("close") or (f or {}).get("close") or p["entry"]
        holdings.append({**p, "now": r2(c), "ret_pct": round((c / p["entry"] - 1) * 100, 2),
                         "pnl_usd": r2((c - p["entry"]) * p["qty"]), "pnl_krw": int(round((c - p["entry"]) * p["qty"] * fx)),
                         "feats": f, "spark": spark(df) if df is not None else None})
        print(f"  · {p['ticker']} {p['plan']['action']}")

    used = len(port["positions"])
    free = max(0, cfg["max_slots"] - used)
    n_new = min(cfg["max_new"], free)
    print(f"[4/5] 신규 타점 (슬롯 {used}/{cfg['max_slots']}, 신규 최대 {n_new})")
    vix = float(data["^VIX"]["Close"].iloc[-1]) if "^VIX" in data and len(data["^VIX"]) else None
    qqq = feats(data["QQQ"]) if "QQQ" in data and len(data["QQQ"]) > 25 else None
    if vix and vix >= 30:
        n_new = min(n_new, 1)      # 공포 지수가 높으면 하루 1종목만
    if not sess["trading"]:
        n_new = 0
    cands, near = screen(data, names, cfg, fx, {p["ticker"] for p in port["positions"]})
    picks, block = [], ""
    if not sess["trading"]:
        block = "오늘 밤은 미국 증시 휴장일이라 신규 매수를 쉬어 갑니다."
    elif n_new == 0:
        block = f"보유 슬롯 {cfg['max_slots']}개가 모두 찼어요. 오늘 밤은 신규 매수를 보류하고 기존 종목 탈출에 집중합니다."
    elif not cands:
        block = "오늘은 조건(하루 변동폭 3.5% 이상 + 눌림목 반등/거래량 돌파)을 모두 만족한 종목이 없어요. 억지로 사지 않고 쉬어 갑니다."
    for f in cands[:n_new]:
        o = make_order(f, cfg, fx, sess)
        if o["qty"] < 1:
            continue
        nws = ticker_news(f["ticker"], f["name"])
        f["news"], f["order"], f["story"] = nws, o, pick_story(f, o, nws)
        f["spark"] = spark(data[f["ticker"]])
        picks.append(f)
        port["positions"].append({
            "id": f"{today}-{f['ticker']}", "ticker": f["ticker"], "name": f["name"], "source": "auto",
            "status": "PENDING", "order_date": today, "session_date": sess["date"], "kind": f["kind"],
            "limit": o["limit"], "qty": o["qty"], "target": o["target"], "stop": o["stop"],
            "max_hold": cfg["max_hold"], "fx_at_order": round(fx, 1), "last_bar": f["date"],
        })
        print(f"  ✓ {f['ticker']} {f['kind']} 예약 ${o['limit']} × {o['qty']}주")

    print("[5/5] 성적·저장")
    port.update(updated_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M"), last_run=today,
                rules={k: cfg[k] for k in DEFAULTS})
    save_json(PORT_P, port)
    save_json(HIST_P, hist)
    rec = track(hist, port["start_date"])
    payload = {
        "date": today, "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "session": sess,
        "data_date": last_bar.strftime("%Y-%m-%d") if last_bar is not None else None,
        "fx": round(fx, 1), "fx_date": fx_date, "vix": round(vix, 2) if vix else None,
        "qqq": {"close": r2(qqq["close"]), "chg1": round(qqq["chg1"], 2), "above20": qqq["close"] >= qqq["ma20"]} if qqq else None,
        "rules": {k: cfg[k] for k in DEFAULTS}, "events": events, "holdings": holdings,
        "pending_other": [p for p in port["positions"] if p["status"] == "PENDING" and p.get("order_date") != today],
        "picks": picks, "near": near, "block": block,
        "slots": {"max": cfg["max_slots"], "used_before": used, "after": len(port["positions"])},
        "record": rec,
    }
    (out / "swing" / "data").mkdir(parents=True, exist_ok=True)
    save_json(out / "swing" / "data" / f"{today}.json", payload)
    import swing_report
    path = swing_report.write(payload, out)
    print(f"리포트: {path}")
    return payload


# ───────────────────────── 수동 입력 (스마트폰 GitHub Actions) ─────────────────────────
ACTIONS = {"매수추가": "add", "수량·단가수정": "edit", "수량단가수정": "edit", "매도완료": "sell", "미체결삭제": "delete",
           "add": "add", "edit": "edit", "sell": "sell", "delete": "delete"}


def manual(action: str, ticker: str, price: float | None, qty: int | None, cfg_all: dict, note: str = "") -> str:
    act = ACTIONS.get(action.strip())
    if not act:
        raise SystemExit(f"알 수 없는 작업: {action} (매수추가 / 수량·단가수정 / 매도완료 / 미체결삭제)")
    cfg = {**DEFAULTS, **(cfg_all.get("swing") or {})}
    names = {str(k): v for k, v in (cfg.get("universe") or {}).items()}
    t = ticker.strip().upper()
    port, hist = load_state()
    now = datetime.now(KST)
    sess = current_session(now).isoformat()
    mine = [p for p in port["positions"] if p["ticker"] == t]
    fx, _ = usdkrw()
    tag = f"수동 입력 {now:%m/%d %H:%M}" + (f" · {note}" if note else "")

    def need(v, what):
        if v is None or (isinstance(v, (int, float)) and v <= 0):
            raise SystemExit(f"{what} 값을 넣어 주세요.")
        return v

    if act in ("add", "edit"):
        price, qty = need(price, "가격(price)"), need(qty, "수량(qty)")
        target, stop = r2(price * (1 + cfg["target_pct"] / 100)), r2(price * (1 - cfg["stop_pct"] / 100))
        p = next((x for x in mine if x["status"] == "PENDING"), None) or next((x for x in mine if x["status"] == "HOLDING"), None)
        if act == "edit" and p is None:
            raise SystemExit(f"{t} 보유·예약 종목이 없어요. 새로 산 거라면 '매수추가'를 쓰세요.")
        if p is None or act == "add" and p["status"] == "HOLDING":
            p = {"id": f"{sess}-{t}-m{now:%H%M}", "ticker": t, "name": names.get(t, t), "order_date": sess,
                 "max_hold": cfg["max_hold"]}
            port["positions"].append(p)
            fresh = True
        else:
            fresh = p["status"] == "PENDING"
        p.update(source="manual", qty=int(qty), entry=r2(price), target=target, stop=stop, note=tag)
        p.pop("plan", None)
        if fresh:      # 새로 체결된 것으로 보고, 그날 일봉부터 보유 일수를 셈
            p.update(status="HOLDING", entry_date=sess, session_date=sess, held=0, skip_first=True,
                     last_bar=prev_trading_day(Date.fromisoformat(sess)).isoformat())
        msg = f"{t} {int(qty)}주 @ ${price:.2f} 반영 (목표 ${target:.2f} / 손절 ${stop:.2f})"
    elif act == "sell":
        p = next((x for x in mine if x["status"] == "HOLDING"), None)
        if p is None:
            raise SystemExit(f"{t} 보유 종목이 없어요.")
        price = need(price, "매도가(price)")
        q = int(qty) if qty else p["qty"]
        if q < p["qty"]:      # 일부 매도
            part = {**p, "qty": q}
            _close_pos(part, price, sess, f"내 계좌 실제 매도 ({tag})", fx, hist, [],
                       "WIN" if price >= p["target"] - 1e-6 else None)
            p["qty"] -= q
        else:
            _close_pos(p, price, sess, f"내 계좌 실제 매도 ({tag})", fx, hist, [],
                       "WIN" if price >= p["target"] - 1e-6 else None)
            port["positions"].remove(p)
        hist[-1]["source"] = "manual"
        msg = f"{t} {q}주 @ ${price:.2f} 매도 기록 ({hist[-1]['ret_pct']:+.2f}%, {hist[-1]['pnl_krw']:+,}원)"
    else:
        p = next((x for x in mine if x["status"] == "PENDING"), None) or (mine[0] if mine else None)
        if p is None:
            raise SystemExit(f"{t} 예약·보유 종목이 없어요.")
        port["positions"].remove(p)
        hist.append({"id": p["id"], "ticker": t, "name": p.get("name"), "source": "manual", "order_date": p.get("order_date"),
                     "exit_date": sess, "qty": p.get("qty"), "result": "CANCEL", "result_ko": RESULT_KO["CANCEL"],
                     "reason": f"직접 삭제 ({tag})"})
        msg = f"{t} 주문/보유 기록 삭제"
    port["updated_at"] = now.strftime("%Y-%m-%d %H:%M")
    save_json(PORT_P, port)
    save_json(HIST_P, hist)
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--date", help="오늘 날짜 KST (기본: 지금)")
    ap.add_argument("--out", default=str(ROOT / "docs"))
    ap.add_argument("--manual", help="매수추가 / 수량·단가수정 / 매도완료 / 미체결삭제")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--price", type=float)
    ap.add_argument("--qty", type=int)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    if a.manual:
        print(manual(a.manual, a.ticker, a.price, a.qty, cfg, a.note))
        return
    run(a.date or datetime.now(KST).strftime("%Y-%m-%d"), cfg, Path(a.out))


if __name__ == "__main__":
    main()
