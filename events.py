"""다가오는 시장 이벤트 후보 (앞으로 7일) — AI 가 이벤트 캘린더(upcoming_events)를 쓸 때 출발점.

프로그램이 확실히 아는 것만 넣는다 (지어내지 않음):
  1) 날짜가 규칙으로 정해진 일정: 국내 옵션 만기(매월 둘째 목요일, 3·6·9·12월은 선물·옵션 동시 만기),
     미국 월간 옵션 만기(셋째 금요일, 3·6·9·12월은 쿼드러플 위칭), 월초 수출입 동향(매월 1일)
  2) events.yaml 에 적어 둔 공식 일정 (연준 회의 등, 공식 발표로 확인한 것만)
  3) 뉴스에서 '예정·회담·발표 앞둬' 같은 앞으로의 일을 다룬 헤드라인 (news.py 의 event_queries)
정상회담·정책 발표·실적 발표처럼 날짜가 기사로만 알려지는 일은 AI 가 웹 검색으로 확인해 채운다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
WD = "월화수목금토일"


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _rule_events(start: date, end: date) -> list[dict]:
    out = []
    months = {(start.year, start.month), (end.year, end.month)}
    for y, m in sorted(months):
        kr = _nth_weekday(y, m, 3, 2)          # 둘째 목요일
        quarter = m in (3, 6, 9, 12)
        out.append({"date": kr.isoformat(), "time_kst": "15:20 전후 마감 영향", "scale": "중형" if quarter else "소형",
                    "title": "국내 선물·옵션 동시 만기일" if quarter else "국내 옵션 만기일",
                    "markets": "코스피200 대형주·프로그램 매매", "status": "확정(규칙)",
                    "note": "만기 당일 장 막판 프로그램 매물·환매로 대형주 변동이 커지기 쉽습니다.",
                    "scenarios": [{"if": "프로그램 매도 우위 (선물이 현물보다 싸짐)", "then": "장 막판 삼성전자·SK하이닉스 등 코스피200 대형주 매물 → 지수 하락 압력"},
                                  {"if": "프로그램 매수 우위", "then": "장 막판 대형주 매수 유입 → 지수 하단 지지. 만기 다음 날 되돌림 가능"}]})
        us = _nth_weekday(y, m, 4, 3)          # 셋째 금요일
        out.append({"date": (us + timedelta(days=1)).isoformat(), "time_kst": "미국 금요일 장 마감 = 한국 토요일 새벽",
                    "scale": "중형" if quarter else "소형",
                    "title": ("미국 쿼드러플 위칭(선물·옵션 동시 만기)" if quarter else "미국 월간 옵션 만기") + f" (미국 {us.month}/{us.day})",
                    "markets": "S&P 500·나스닥 대형 기술주", "status": "확정(규칙)",
                    "note": "만기 주간에는 옵션 포지션 정리로 지수 변동이 커지거나 특정 가격대에 묶이기 쉽습니다.",
                    "scenarios": [{"if": "만기 전", "then": "옵션이 많이 쌓인 가격대로 지수가 끌려가며 변동이 줄어들기 쉬움"},
                                  {"if": "만기 뒤", "then": "묶여 있던 포지션이 풀리며 다음 주 초 방향성이 커질 수 있음 (나스닥·대형 기술주)"}]})
        nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        out.append({"date": nxt.isoformat(), "time_kst": "09:00", "scale": "중형",
                    "title": f"{nxt.month - 1 if nxt.month > 1 else 12}월 수출입 동향 발표 (산업통상부)",
                    "markets": "반도체·자동차·조선 등 수출주, 원/달러", "status": "예정(매월 1일, 휴일이면 바뀔 수 있음)",
                    "note": "반도체 수출 증가율이 코스피 수출주 방향의 단서가 됩니다.",
                    "scenarios": [{"if": "반도체 수출 증가율이 예상보다 높음", "then": "삼성전자·SK하이닉스 등 반도체와 수출주 우호, 무역흑자로 원화 강세 요인"},
                                  {"if": "수출 둔화·감소", "then": "반도체·자동차·조선 등 수출주 부담, 경기 둔화 우려로 코스피 약세 요인"}]})
    return [e for e in out if start.isoformat() <= e["date"] <= end.isoformat()]


def _yaml_events(start: date, end: date) -> list[dict]:
    p = ROOT / "events.yaml"
    if not p.exists():
        return []
    import yaml
    rows = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    out = []
    far = (end + timedelta(days=7)).isoformat()          # 대형 이벤트는 2주 앞까지 미리 알림
    for r in rows:
        d = str(r.get("date", ""))
        if start.isoformat() <= d <= (far if r.get("scale") == "대형" else end.isoformat()):
            out.append({**r, "status": r.get("status", "확정(공식 일정)")})
    return out


def _gemini_events(gem: dict | None) -> list[dict]:
    """제미나이가 구글 검색으로 확인한 이벤트 (collect_gemini_research.py 가 날짜·기사 날짜 검사를 마친 것)."""
    if not gem or not gem.get("ok"):
        return []
    st = {"확정": "확정", "예정": "예정", "보도": "가능성(보도)"}
    return [{"date": e["date_kst"], "time_kst": e.get("time_kst", ""), "title": e["title"], "scale": e.get("scale", "중형"),
             "status": st.get(e.get("confirmed"), e.get("confirmed") or "예정"), "markets": ", ".join(e.get("sectors") or []),
             "note": e.get("why", ""), "source": f"제미나이 검색 · {e.get('source', '')} {e.get('source_date', '')}".strip(),
             "url": e.get("url", ""), "scenarios": [c for c in (e.get("scenarios") or []) if isinstance(c, dict) and c.get("if")]}
            for e in gem.get("events") or [] if e.get("date_kst")]


def collect(today: str, news: dict | None = None, days: int = 7, gemini: dict | None = None) -> dict:
    start = date.fromisoformat(today)
    end = start + timedelta(days=days)
    cal = _rule_events(start, end) + _yaml_events(start, end)
    have = {(e["date"], e["title"][:8]) for e in cal}
    cal += [e for e in _gemini_events(gemini) if (e["date"], e["title"][:8]) not in have]
    cal.sort(key=lambda e: e["date"])
    for e in cal:
        d = date.fromisoformat(e["date"])
        e["d_day"] = (d - start).days
        e["weekday"] = WD[d.weekday()]
    heads = [h for h in ((news or {}).get("events") or [])][:24]
    return {"from": start.isoformat(), "to": end.isoformat(), "calendar": cal, "headlines": heads,
            "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}


def brief_text(ev: dict) -> str:
    if not ev:
        return ""
    lines = [f"## 다가오는 이벤트 후보 ({ev['from']} ~ {ev['to']}, 프로그램 수집 — upcoming_events 의 출발점)",
             "### 일정 (규칙·공식 일정 + [제미나이 검색] 표시는 구글 검색으로 확인된 이벤트)"]
    for e in ev.get("calendar") or []:
        dd = "오늘" if e["d_day"] == 0 else "내일" if e["d_day"] == 1 else f"D-{e['d_day']}"
        lines.append(f"- {e['date']}({e['weekday']}, {dd}) {e.get('time_kst', '')} · {e['title']} · 규모 {e.get('scale', '')} · "
                     f"{e.get('status', '')} · 영향: {e.get('markets', '')} — {e.get('note', '')}"
                     + (f" [{e['source']}]" if e.get("source") else ""))
        for sc in e.get("scenarios") or []:
            lines.append(f"    · {sc.get('if', '')} → {sc.get('then', '')}")
    if not ev.get("calendar"):
        lines.append("- (없음)")
    lines.append("### 앞으로의 일을 다룬 뉴스 헤드라인 (예정·회담·발표 앞둠 등 — 날짜·사실은 원문으로 확인)")
    for h in ev.get("headlines") or []:
        t = f"[{h.get('time', '')} KST" + (f" · 미국 {h['time_et']} ET" if h.get("lang") == "en" and h.get("time_et") else "") + "]"
        lines.append(f"- {t} {h['title']} ({h.get('source', '')})")
    if not ev.get("headlines"):
        lines.append("- (수집 없음 — 웹 검색으로 직접 확인)")
    return "\n".join(lines)
