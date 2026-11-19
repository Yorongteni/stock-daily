"""단타 브리핑의 「앞으로 1주일 대응 플랜」 — 보유 포지션(실제 매매)과 이번 추천 타점마다 날짜별로 무엇을 할지.

프로그램이 규칙(목표·손절·본전 방어·최대 보유일·연장 조건)과 다가오는 일정(events.py)으로 기본 플랜을 만든다.
Claude 에게 단타 브리핑을 요청하면 이 기본 플랜과 시세를 읽고 상황에 맞는 AI 플랜을
docs/swing/ai/<날짜>.json 에 써서 푸시한다 (.claude/skills/swing-brief) → 리포트 맨 위에 AI 플랜이 함께 보인다.
"""
from __future__ import annotations

from datetime import date as Date, timedelta

WD = "월화수목금토일"
US_KEYS = ("미국", "FOMC", "CPI", "고용", "옵션 만기", "쿼드러플", "연준", "Fed")


def _md(d: Date) -> str:
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def _events_by_day(today: str, days: int = 7) -> dict[str, list[str]]:
    try:
        import events
        cal = events.collect(today, {}, days)["calendar"]
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[str]] = {}
    for e in cal:
        if any(k in e["title"] for k in US_KEYS):
            out.setdefault(e["date"], []).append(f"{e['title']} ({e.get('scale', '')}, {e.get('time_kst', '')})")
    return out


def _us_days(start: Date, n: int = 5) -> list[Date]:
    from swing import is_trading_day, next_trading_day
    d = start if is_trading_day(start) else next_trading_day(start)
    out = [d]
    while len(out) < n:
        out.append(next_trading_day(out[-1]))
    return out


def _stock_plan(name: str, held: int, max_hold: int, levels: dict, sess_date: str, ev: dict, pending: bool) -> list[dict]:
    """미국 주식 1~2거래일 단타: 날짜(미국 거래일)별 행동."""
    T, S, L = levels.get("target"), levels.get("stop"), levels.get("limit")
    bt, bp = levels.get("be_trigger"), levels.get("be_price")
    rows = []
    days = _us_days(Date.fromisoformat(sess_date), 5)
    for i, d in enumerate(days):
        k = (i + 1) if pending else (held + 1 + i)      # 이 미국장이 보유 몇 일차인지 (추천은 첫날 체결 가정)
        if pending and i == 0:
            act = (f"예약 매수 ${L:.2f} — 체결되면 바로 목표 ${T:.2f} 예약 매도·손절 ${S:.2f} 설정(1일차). "
                   f"체결 안 되면 주문을 지우고 다음 날 새 브리핑으로 다시 판단")
        elif k < max_hold:
            act = f"{k}일차: 목표 ${T:.2f} 예약 매도 유지 · 손절 ${S:.2f}" + (
                f" · 장중 ${bt:.2f} 닿으면 다음 날부터 손절을 본전 ${bp:.2f}로" if bt else "")
        elif k == max_hold:
            act = (f"{k}일차(마지막 날): +2% 이상이면 목표가 두고 안 되면 장 마감 정리 / 5일선 지지면 +2% 약익절 / "
                   f"힘이 약하면 본전 탈출 / 20일선까지 깨지면 시초가 정리")
        elif k == max_hold + 1:
            act = ("예외 연장일: 전날 수익 +2% 이상·5일·20일선 위·거래량 유지·RSI 70 미만이었을 때만 보유 (손절은 본전). "
                   "아니면 이미 정리된 상태")
        else:
            act = "포지션 정리 완료 — 같은 종목 재진입은 새 브리핑 타점이 나올 때만"
        note = " / ".join(ev.get((d + timedelta(days=1)).isoformat(), []) + ev.get(d.isoformat(), []))
        rows.append({"date": d.isoformat(), "label": f"미국 {_md(d)} 장 (한국 {_md(d + timedelta(days=1))} 새벽 마감)", "action": act,
                     "watch": f"⚠ 이 날 일정: {note} — 발표 전후 변동이 커질 수 있어 목표·손절 주문을 꼭 걸어 두세요" if note else ""})
        if k > max_hold + 1:
            break
    return rows


def _coin_plan(sym: str, side: str, levels: dict, today: str, ev: dict, open_: bool, hold_h: int, order_h: int) -> list[dict]:
    L = side == "LONG"
    tp, sl, en = levels.get("tp"), levels.get("sl"), levels.get("entry")
    bt, bp = levels.get("be_trigger"), levels.get("be_price")
    d0 = Date.fromisoformat(today)
    rows = [{"date": today, "label": f"{_md(d0)} 지금 ~ {hold_h}시간",
             "action": ((f"보유 중: TP {tp} / SL {sl} 유지" if open_ else
                         f"지정가 {en} {'롱' if L else '숏'} 예약 ({order_h}시간 유효) — 체결되면 TP {tp} / SL {sl} 동시 설정")
                        + (f" · 가격이 {bt}에 닿으면 SL 을 본전 {bp}로 이동" if bt else "")
                        + f" · 체결 뒤 {hold_h}시간 안에 TP·SL 이 안 나면 시장가 정리"),
             "watch": ""}]
    for i in range(1, 7):
        d = d0 + timedelta(days=i)
        note = " / ".join(ev.get(d.isoformat(), []))
        rows.append({"date": d.isoformat(), "label": _md(d),
                     "action": "이 포지션은 24시간 규칙으로 이미 정리된 상태 — 새로 들어갈지는 그날 새 브리핑(원픽·방향)으로 판단",
                     "watch": f"⚠ {note} — 미국 지표 발표 전후 비트코인·코인 변동성 확대, 레버리지 진입은 발표 뒤로" if note else ""})
    return rows


def build(d: dict) -> list[dict]:
    """swing.run 의 payload → 포지션·추천마다 1주일 플랜 목록."""
    today = d["date"]
    sess = d.get("session") or {}
    ev = _events_by_day(today, 8)
    out = []
    for h in d.get("holdings") or []:
        out.append({"kind": "보유 (실제 매매)", "market": "미국 주식", "name": f"{h.get('name')} ({h['ticker']})",
                    "summary": f"{h['qty']}주 · 진입 ${h['entry']:.2f} · 지금 ${h.get('now', h['entry']):.2f} ({h.get('ret_pct', 0):+.1f}%)",
                    "days": _stock_plan(h["ticker"], h.get("held", 0), h.get("max_hold", 2),
                                        {"target": h["target"], "stop": h["stop"], "be_trigger": h.get("be_trigger"), "be_price": h.get("be_price")},
                                        sess.get("date", today), ev, pending=False)})
    for p in d.get("picks") or []:
        o = p["order"]
        out.append({"kind": "이번 추천 타점 (기록 안 함)", "market": "미국 주식", "name": f"{p['name']} ({p['ticker']})",
                    "summary": f"예약 매수 ${o['limit']:.2f} × {o['qty']}주 · 목표 ${o['target']:.2f} · 손절 ${o['stop']:.2f}",
                    "days": _stock_plan(p["ticker"], 0, d.get("rules", {}).get("max_hold", 2),
                                        {"target": o["target"], "stop": o["stop"], "limit": o["limit"],
                                         "be_trigger": o.get("be_trigger"), "be_price": o.get("be_price")},
                                        sess.get("date", today), ev, pending=True)})
    fu = d.get("futures") or {}
    rules = fu.get("rules") or {}
    for h in fu.get("holdings") or []:
        out.append({"kind": "보유 (실제 매매)", "market": "바이낸스 3배", "name": f"{h.get('name')} ({h['symbol']}) {h['direction']}",
                    "summary": f"{h['status']} · 진입 {h.get('entry') or h.get('limit')} · 지금 {h.get('now')}",
                    "days": _coin_plan(h["symbol"], h["direction"], {"tp": h.get("tp"), "sl": h.get("sl"), "entry": h.get("entry") or h.get("limit"),
                                                                    "be_trigger": h.get("be_trigger"), "be_price": h.get("be_price")},
                                       today, ev, h["status"] == "OPEN", rules.get("hold_hours", 24), rules.get("order_valid_hours", 6))})
    pk = fu.get("pick")
    if pk:
        o = pk["order"]
        out.append({"kind": "이번 추천 원픽 (기록 안 함)", "market": "바이낸스 3배", "name": f"{pk.get('name')} ({pk['symbol']}) {pk['side']}",
                    "summary": f"진입 {o['entry']} · TP {o['tp']} · SL {o['sl']} · 증거금 {o['margin']:.0f} USDT",
                    "days": _coin_plan(pk["symbol"], pk["side"], {"tp": o["tp"], "sl": o["sl"], "entry": o["entry"],
                                                                 "be_trigger": o.get("be_trigger"), "be_price": o.get("be_price")},
                                       today, ev, False, pk.get("hold_hours", 24), pk.get("order_hours", 6))})
    return out
