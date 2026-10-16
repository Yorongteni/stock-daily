"""기술적 지표 계산과 추세 점수/신호 판정."""
import math
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast=12, slow=26, sig=9):
    line = ema(close, fast) - ema(close, slow)
    signal = ema(line, sig)
    return line, signal, line - signal


def tsi(close: pd.Series, r=25, s=13, sig=7):
    """True Strength Index (모멘텀 반전 확인용)."""
    d = close.diff()
    num = ema(ema(d, r), s)
    den = ema(ema(d.abs(), r), s)
    line = 100 * num / den.replace(0, float("nan"))
    return line, ema(line, sig)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["Close"]
    for n in (20, 60, 120):
        df[f"SMA{n}"] = c.rolling(n).mean()
    df["RSI"] = rsi(c)
    df["MACD"], df["MACD_SIG"], df["MACD_HIST"] = macd(c)
    df["TSI"], df["TSI_SIG"] = tsi(c)
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    df["BB_UP"], df["BB_LO"] = mid + 2 * sd, mid - 2 * sd
    return df


def _pct(a, b):
    try:
        return round((a / b - 1) * 100, 2)
    except ZeroDivisionError:
        return None


def _crossed(a: pd.Series, b: pd.Series, lookback=3):
    """최근 lookback 거래일 안에 a가 b를 상향(+1)/하향(-1) 돌파했는지."""
    diff = (a - b).dropna().tail(lookback + 1)
    if len(diff) < 2:
        return 0
    sign = diff.apply(lambda x: 1 if x > 0 else -1)
    if sign.iloc[0] != sign.iloc[-1]:
        return int(sign.iloc[-1])
    return 0


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def analyze(df: pd.DataFrame, chart_days: int = 180) -> dict:
    df = add_indicators(df)
    last, prev = df.iloc[-1], df.iloc[-2]
    c = df["Close"]

    # ── 추세 점수 (각 항목 ±1, 합계 -6 ~ +6) ──
    checks = [
        ("종가 > 20일선", last.Close > last.SMA20 if pd.notna(last.SMA20) else None),
        ("20일선 > 60일선", last.SMA20 > last.SMA60 if pd.notna(last.SMA60) else None),
        ("60일선 > 120일선", last.SMA60 > last.SMA120 if pd.notna(last.SMA120) else None),
        ("MACD 히스토그램 양수", last.MACD_HIST > 0),
        ("TSI > 시그널", last.TSI > last.TSI_SIG if pd.notna(last.TSI) else None),
        ("RSI > 50", last.RSI > 50),
    ]
    score = sum((1 if ok else -1) for _, ok in checks if ok is not None)
    label = "강세" if score >= 3 else "약세" if score <= -3 else "중립"

    # ── 이벤트 신호 ──
    signals = []
    gc = _crossed(df["SMA20"], df["SMA60"])
    if gc == 1:
        signals.append(("bull", "20/60일선 골든크로스"))
    elif gc == -1:
        signals.append(("bear", "20/60일선 데드크로스"))
    tc = _crossed(df["TSI"], df["TSI_SIG"], 2)
    if tc == 1:
        signals.append(("bull", f"TSI 시그널 상향 돌파 (TSI {last.TSI:.1f})"))
    elif tc == -1:
        signals.append(("bear", f"TSI 시그널 하향 돌파 (TSI {last.TSI:.1f})"))
    mc = _crossed(df["MACD"], df["MACD_SIG"], 2)
    if mc == 1:
        signals.append(("bull", "MACD 매수 신호 전환"))
    elif mc == -1:
        signals.append(("bear", "MACD 매도 신호 전환"))
    if last.RSI >= 70:
        signals.append(("warn", f"RSI {last.RSI:.0f} 과열권"))
    elif last.RSI <= 30:
        signals.append(("warn", f"RSI {last.RSI:.0f} 과매도권"))
    if pd.notna(last.BB_UP) and last.Close > last.BB_UP:
        signals.append(("warn", "볼린저밴드 상단 이탈"))
    elif pd.notna(last.BB_LO) and last.Close < last.BB_LO:
        signals.append(("warn", "볼린저밴드 하단 이탈"))

    yr = c.tail(252)
    hi, lo = yr.max(), yr.min()
    if last.Close >= hi * 0.98:
        signals.append(("bull", "52주 신고가 근접"))
    elif last.Close <= lo * 1.02:
        signals.append(("bear", "52주 신저가 근접"))

    def back(n):
        return _pct(last.Close, c.iloc[-n - 1]) if len(c) > n else None

    tail = df.tail(chart_days)
    series = {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        **{k: [_clean(v) for v in tail[col]] for k, col in [
            ("close", "Close"), ("sma20", "SMA20"), ("sma60", "SMA60"),
            ("sma120", "SMA120"), ("rsi", "RSI"), ("tsi", "TSI"), ("tsi_sig", "TSI_SIG")]},
    }

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": _clean(last.Close),
        "chg_1d": _pct(last.Close, prev.Close),
        "chg_5d": back(5),
        "chg_20d": back(20),
        "pos_52w": round((last.Close - lo) / (hi - lo) * 100, 1) if hi > lo else None,
        "rsi": _clean(last.RSI),
        "tsi": _clean(last.TSI),
        "macd_hist": _clean(last.MACD_HIST),
        "score": int(score),
        "label": label,
        "checks": [(n, bool(ok)) for n, ok in checks if ok is not None],
        "signals": signals,
        "series": series,
    }
