"""원픽 복기 일지 — 실제로 샀든 안 샀든, 단타 브리핑이 고른 코인 원픽을 모두 남기고 실제 시세로 결과를 매긴다.

목적: 실제 매매 몇 건만으로는 규칙을 다듬기 어렵다. 모든 원픽을 같은 규칙(지정가 진입·TP·SL·본전 이동·24시간 정리)으로
1시간봉에 대 보고, 어떤 조건(확실도·1시간 RSI·평균선 거리·비트코인 4시간 RSI·미결제약정 등)에서 이기고 지는지 통계를 쌓는다.
실제 매매 기록(data/binance_futures_log.json)과는 완전히 따로다 — 성적·누적 손익에 섞이지 않는다.

  data/pick_journal.json : {"picks": [...]}  (같은 원픽을 여러 번 돌려도 진입·TP·SL 이 같으면 1건)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_DATA = Path(os.environ.get("SWING_DATA_DIR") or ROOT / "data")
P = _DATA / "pick_journal.json"
UTC = timezone.utc
KST = timezone(timedelta(hours=9))

FEATS = ("close", "chg24", "chg4h", "rsi1h", "dist1h", "oi_chg24", "vol_ratio", "funding", "range24", "hi24", "lo24")


def load() -> dict:
    try:
        return json.loads(P.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"picks": []}


def save(j: dict) -> None:
    P.parent.mkdir(parents=True, exist_ok=True)
    P.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")


def add(j: dict, pick: dict, fu_ctx: dict, gen_iso: str) -> None:
    """원픽 1건 추가 (진입·TP·SL 이 같은 기존 건이 있으면 건너뜀)."""
    o = pick["order"]
    key = f"{pick['symbol']}|{pick['side']}|{o['entry']}|{o['tp']}|{o['sl']}"
    if any(x.get("key") == key for x in j["picks"]):
        return
    b = fu_ctx.get("btc") or {}
    j["picks"].append({
        "key": key, "symbol": pick["symbol"], "name": pick.get("name"), "side": pick["side"],
        "picked_at": gen_iso, "valid_until": pick.get("valid_until"), "hold_hours": pick.get("hold_hours", 24),
        "entry": o["entry"], "tp": o["tp"], "sl": o["sl"], "be_trigger": o.get("be_trigger"), "be_price": o.get("be_price"),
        "grade": pick.get("grade"), "score": pick.get("score"), "passed": pick.get("passed"), "aligned": pick.get("aligned"),
        "missing": [k for k, v in (pick.get("checks") or {}).items() if not v],
        "feats": {k: pick.get(k) for k in FEATS},
        "btc": {"rsi4h": b.get("rsi4h"), "chg24": b.get("chg24"), "above_ema20_4h": (b.get("close") or 0) > (b.get("ema20_4h") or 9e18)},
        "bias": (fu_ctx.get("bias") or {}).get("score"),
        # 스윕 엔진 (2026-11-23~): 복기용 맥락 — 비트코인 4시간 추세·미결제약정 구간·신호 깊이·무효 기준선
        "engine": pick.get("engine", "score"), "cancel_level": pick.get("cancel_level"),
        "sweep_score": pick.get("score") if pick.get("engine") == "sweep" else None,
        "btc_ctx": {k: (fu_ctx.get("panel") or {}).get(k) for k in ("price", "chg24", "oi_chg24", "oi_chg4h", "funding", "ls_ratio")}
                   | {"trend4": b.get("trend4"), "covering": fu_ctx.get("covering")},
        "status": "pending",
    })


def _t(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s) if "T" in s else datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST)


def judge(x: dict, df) -> None:
    """1시간봉으로 결과 매기기 (같은 봉에서 TP·SL 이 다 닿으면 손절로 — 보수적). df: index=UTC 시각, High/Low/Close."""
    L = x["side"] == "LONG"
    t0, tv = _t(x["picked_at"]), _t(x["valid_until"])
    hold = timedelta(hours=x.get("hold_hours", 24))
    fill = None
    stop, be = x["sl"], False
    for ts, r in df.iterrows():
        t = ts.to_pydatetime()
        if t < t0:          # 원픽 시각보다 먼저 시작한 봉은 보지 않음 (그 봉의 고가·저가에 원픽 전 움직임이 섞여 있음)
            continue
        h, l, c = float(r.High), float(r.Low), float(r.Close)
        if fill is None:
            if t > tv:
                x.update(status="done", result="NO_FILL", result_ko="미체결")
                return
            cl = x.get("cancel_level")
            if cl and ((c > cl) if not L else (c < cl)) and not ((h >= x["entry"]) if not L else (l <= x["entry"])):
                x.update(status="done", result="INVALID", result_ko="체결 전 신호 무효")
                return
            if (h >= x["entry"]) if not L else (l <= x["entry"]):
                fill = t
                x["filled_at"] = t.isoformat()
            else:
                continue
        if (h >= stop) if not L else (l <= stop):
            x.update(status="done", result="BE" if be else "LOSS", result_ko="본전 정리" if be else "손절", exit=stop, exit_at=t.isoformat())
            break
        if (l <= x["tp"]) if not L else (h >= x["tp"]):
            x.update(status="done", result="WIN", result_ko="익절", exit=x["tp"], exit_at=t.isoformat())
            break
        if not be and x.get("be_trigger") and ((l <= x["be_trigger"]) if not L else (h >= x["be_trigger"])):
            be, stop = True, x["be_price"]
        if t - fill >= hold:
            x.update(status="done", result="TIME", result_ko="24시간 정리", exit=c, exit_at=t.isoformat())
            break
    if x.get("exit") is not None:
        m = (x["entry"] - x["exit"]) / x["entry"] * 100 if not L else (x["exit"] - x["entry"]) / x["entry"] * 100
        x["move_pct"] = round(m, 2)
        x["roe3"] = round(m * 3 - 0.3, 2)          # 3배, 수수료 감안 대략


def evaluate(j: dict, src, now: datetime) -> None:
    for x in j["picks"]:
        if x.get("status") == "done":
            continue
        try:
            df = src.klines(x["symbol"], "1h", 200)
            df = df[df.index + timedelta(hours=1) <= now]          # 끝난 봉만
            judge(x, df)
        except Exception as e:  # noqa: BLE001
            x["error"] = str(e)[:80]


def _bucket(v, edges, labels):
    if v is None:
        return "없음"
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


def _oi_regime(c: dict) -> str:
    if c.get("oi_chg24") is None or c.get("chg24") is None:
        return "없음"
    up_p, up_o = c["chg24"] > 0, c["oi_chg24"] > 0
    return "가격↑OI↑" if up_p and up_o else "가격↑OI↓(숏커버)" if up_p else "가격↓OI↑" if up_o else "가격↓OI↓(롱청산)"


def stats(j: dict) -> dict:
    done = [x for x in j["picks"] if x.get("status") == "done" and x.get("result") not in ("NO_FILL", "INVALID")]
    def agg(rows):
        n = len(rows)
        w = sum(1 for x in rows if x["result"] == "WIN")
        return {"n": n, "win": w, "rate": round(w / n * 100) if n else None,
                "avg_roe3": round(sum(x.get("roe3", 0) for x in rows) / n, 2) if n else None}
    groups = {
        "확실도": lambda x: x.get("grade") or "없음(등급 전)",
        "1시간 평균선 거리(진입 방향 기준)": lambda x: _bucket((x["feats"].get("dist1h") or 0) * (1 if x["side"] == "SHORT" else -1),
                                                    [-3, 0, 2], ["-3% 미만 (추격)", "-3~0%", "0~2% (평균선 근처)", "+2% 이상 (반등 끝)"]),
        "1시간 RSI": lambda x: _bucket(x["feats"].get("rsi1h"), [30, 45, 60], ["30 미만", "30~45", "45~60", "60 이상"]),
        "비트코인 4시간 RSI": lambda x: _bucket(x["btc"].get("rsi4h"), [30, 45, 60], ["30 미만", "30~45", "45~60", "60 이상"]),
        "미결제약정 24시간": lambda x: _bucket(x["feats"].get("oi_chg24"), [1, 3], ["+1% 미만", "+1~3%", "+3% 이상"]),
        "엔진": lambda x: x.get("engine") or "score",
        "비트코인 미결제약정 구간": lambda x: _oi_regime(x.get("btc_ctx") or {}),
    }
    out = {"total": agg(done), "picks": len(j["picks"]),
           "no_fill": sum(1 for x in j["picks"] if x.get("result") == "NO_FILL"),
           "pending": sum(1 for x in j["picks"] if x.get("status") != "done"), "by": {}}
    for name, fn in groups.items():
        b: dict[str, list] = {}
        for x in done:
            b.setdefault(fn(x), []).append(x)
        out["by"][name] = {k: agg(v) for k, v in sorted(b.items())}
    out["recent"] = [{k: x.get(k) for k in ("picked_at", "name", "symbol", "side", "grade", "entry", "result_ko", "roe3")}
                     for x in j["picks"][-12:]][::-1]
    return out
