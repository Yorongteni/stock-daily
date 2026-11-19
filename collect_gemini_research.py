"""[1단계] 제미나이(Gemini) + 구글 검색(Google Search Grounding) 리서치.

실시간 구글 검색으로 확인한 ① 앞으로 7일 이벤트 ② 오늘 시장을 움직인 핵심 뉴스·테마 배경을 JSON 으로 모은다.
[2단계] 클로드 분석(brief)이 이 결과를 최우선 근거로 읽는다 (commentary.py 의 _gemini_text).

  GEMINI_API_KEY=... python collect_gemini_research.py --date 2026-11-19 --slot pm
  → data/gemini_research.json (최신) · docs/data/<날짜>_<슬롯>_gemini.json (날짜별 보관)

안전장치: 키가 없거나, 호출이 실패하거나(할당량 초과 포함), 답이 JSON 이 아니면 {"ok": false, "error": ...} 를 돌려주고
파이프라인은 기존 RSS 수집만으로 계속 간다. 이 모듈은 절대 예외를 밖으로 던지지 않는다 (run()).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
# 앞에서부터 시도. 모델이 없어졌거나(404) 이 키로 못 쓰면 다음 모델로 넘어간다.
# (2026-11: gemini-2.5-flash 는 새 사용자에게 제공 중단 — 구글 안내에 따라 gemini-3.8-flash 로 넘어감)
MODELS = [m.strip() for m in os.environ.get("GEMINI_MODEL", "gemini-2.5-flash,gemini-3.8-flash").split(",") if m.strip()]
MODEL = MODELS[0]
LATEST = ROOT / "data" / "gemini_research.json"
SCALES = {"대형", "중형", "소형"}

PROMPT = """당신은 한국 개인투자자용 시장 브리핑의 **리서치·팩트체크 담당**입니다. 반드시 구글 검색으로 확인한 사실만 씁니다.

[기준 시각] 지금은 한국 시간 {now_kst} (미국 동부 {now_et}) 입니다. 브리핑: {date} {slot_name}.
[시차 규칙] 미국 정규장 = 한국 {open_kst} ~ 다음 날 {close_kst}. **미국 X일 장 마감 후 발표 = 한국 X+1일 {close_kst} 이후 아침**.
기사 속 'today·tonight·내일'은 그 기사가 나온 날짜 기준이므로, 기사 게시일을 확인해 한국 날짜(KST)로 바꿔 적습니다.

[할 일 1] 오늘({date})부터 7일 뒤({end})까지 한국·미국 증시에 영향을 줄 **예정 이벤트**를 찾으세요:
국내외 정상회담·외교 일정, 정부 정책·규제 발표(한한령·관세·수출 규제 등), 미국 연준·한국은행 회의와 주요 인사 연설,
빅테크·대형 기업 실적 발표, 주요 경제지표(물가·고용·수출입·GDP), 대형 상장·지수 변경·만기.
기대감이나 우려로 **이미 관련 주가가 움직이고 있는 이벤트**는 꼭 포함하고, 그 움직임을 why 에 적으세요.

[할 일 2] 최근 1~2거래일 한국·미국 증시에서 **크게 오르거나 내린 섹터·테마 3~5개**와 그 구체적인 뉴스 원인을 찾으세요
(예: 엔터·게임, 반도체, 방산, 2차전지). 등락 수치는 기사에 나온 값만 쓰고, 없으면 비워 두세요.

[팩트체크 규칙]
- 확인되지 않은 루머, 날짜가 불분명한 기사, 게시일이 7일보다 오래된 기사만 근거인 내용은 **빼세요**.
- 일정이 공식 발표됐으면 "확정", 날짜는 나왔지만 내용이 불확실하면 "예정", 보도·관측 단계면 "보도"로 정직하게 적으세요.
- 날짜는 모두 한국 시간(KST) YYYY-MM-DD. 미국 일정은 time_kst 에 "미국 11/20 16:00 ET = 한국 11/21 06:00" 처럼 둘 다 적으세요.
- 매수·매도 권유, 목표주가는 쓰지 마세요.

[출력] 아래 JSON 한 덩어리만 출력하세요. 앞뒤 설명·마크다운 금지.
{{
  "events": [{{"date_kst": "YYYY-MM-DD", "time_kst": "HH:MM 또는 미정", "title": "이벤트 이름", "scale": "대형|중형|소형",
              "confirmed": "확정|예정|보도", "sectors": ["영향 섹터"], "why": "시장이 주목하는 이유와 이미 반영된 움직임 (1~2문장)",
              "source": "언론사·기관", "source_date": "기사 게시일 YYYY-MM-DD", "url": "기사 주소(알면)"}}],
  "movers": [{{"sector": "섹터·테마", "direction": "급등|급락|강세|약세", "date_kst": "YYYY-MM-DD", "move": "기사에 나온 등락 (없으면 빈칸)",
              "cause": "구체적인 뉴스 원인 (1~2문장)", "names": ["대표 종목"], "source": "언론사", "source_date": "YYYY-MM-DD", "url": "기사 주소(알면)"}}],
  "excluded": ["확인이 안 돼서 뺀 소문·내용 (있으면)"]
}}
events 5~12개(대형 먼저), movers 3~5개."""


def _anchor(day: str) -> dict:
    from zoneinfo import ZoneInfo
    now = datetime.now(KST)
    et = now.astimezone(ZoneInfo("America/New_York"))
    dst = bool(et.dst())
    end = (date.fromisoformat(day) + timedelta(days=7)).isoformat()
    return {"now_kst": now.strftime("%Y-%m-%d %H:%M"), "now_et": et.strftime("%Y-%m-%d %H:%M"), "end": end,
            "open_kst": "22:30" if dst else "23:30", "close_kst": "05:00" if dst else "06:00"}


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("JSON 을 찾지 못함")
        t = t[a:b + 1]
    return json.loads(t)


def _grounding(resp) -> tuple[list[dict], list[str]]:
    """구글 검색 근거(검색어·웹 출처) — 제미나이가 실제로 검색했는지의 증거."""
    links, queries = [], []
    try:
        gm = resp.candidates[0].grounding_metadata
        queries = list(gm.web_search_queries or [])
        for ch in gm.grounding_chunks or []:
            w = getattr(ch, "web", None)
            if w and getattr(w, "uri", None):
                links.append({"title": getattr(w, "title", "") or "", "uri": w.uri})
    except Exception:  # noqa: BLE001
        pass
    return links, queries


def _d(s) -> date | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def clean(raw: dict, day: str) -> tuple[dict, list[str]]:
    """형식·날짜 검사: 날짜 없는 이벤트, 7일 창 밖 일정, 7일보다 오래된 기사 근거, 미래 날짜 기사는 뺀다."""
    d0 = date.fromisoformat(day)
    end = d0 + timedelta(days=7)
    drops, events, movers = [], [], []
    for e in raw.get("events") or []:
        if not isinstance(e, dict) or not e.get("title"):
            continue
        dk, sd = _d(e.get("date_kst")), _d(e.get("source_date"))
        why = None
        if not dk:
            why = "날짜 불분명"
        elif not (d0 <= dk <= end + timedelta(days=7)):     # 대형 이벤트는 2주까지 허용
            why = f"기간 밖 ({dk})"
        elif sd and (sd > d0 + timedelta(days=1) or (d0 - sd).days > 7):
            why = f"기사 날짜 이상 ({sd})"
        if why:
            drops.append(f"이벤트 '{e.get('title')}': {why}")
            continue
        e["scale"] = e.get("scale") if e.get("scale") in SCALES else "중형"
        e["date_kst"] = dk.isoformat()
        events.append(e)
    for m in raw.get("movers") or []:
        if not isinstance(m, dict) or not m.get("sector") or not m.get("cause"):
            continue
        sd = _d(m.get("source_date")) or _d(m.get("date_kst"))
        if sd and ((d0 - sd).days > 3 or sd > d0 + timedelta(days=1)):
            drops.append(f"테마 '{m.get('sector')}': 오래되거나 날짜 이상 ({sd})")
            continue
        movers.append(m)
    events.sort(key=lambda e: ({"대형": 0, "중형": 1, "소형": 2}.get(e["scale"], 3), e["date_kst"]))
    return {"events": events, "movers": movers, "excluded": raw.get("excluded") or []}, drops


def run(day: str, slot: str = "am", save: bool = True, out_docs: Path | None = None) -> dict:
    """제미나이 리서치. 실패해도 예외를 던지지 않고 {"ok": False, "error": ...} 를 돌려준다."""
    base = {"date": day, "slot": slot, "model": MODEL, "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "ok": False}
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return {**base, "error": "GEMINI_API_KEY 없음 — 제미나이 단계 건너뜀 (RSS 수집만 사용)"}
    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # noqa: BLE001
        return {**base, "error": f"google-genai 설치 안 됨: {e}"}
    a = _anchor(day)
    prompt = PROMPT.format(date=day, slot_name="모닝 브리핑(07:00)" if slot == "am" else "나이트 브리핑(22:00)", **a)
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=180_000))
    cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.2)
    last, res, tried = None, None, []
    models = list(MODELS)
    model = models.pop(0)
    attempt = 0
    while attempt < 3:
        attempt += 1
        try:
            tried.append(model)
            resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
            raw = _parse_json(resp.text)
            links, queries = _grounding(resp)
            data, drops = clean(raw, day)
            res = {**base, "ok": True, "model": model, **data, "dropped": drops, "search_queries": queries,
                   "grounding": links[:40], "anchor": a}
            if not queries and not links:
                res["warning"] = "구글 검색 근거(grounding)가 비어 있음 — 검색 없이 답했을 수 있어 참고만"
            break
        except Exception as e:  # noqa: BLE001  (할당량 초과 429·일시 오류·JSON 형식 오류 모두)
            last = f"{type(e).__name__}: {str(e)[:1500]}"   # 할당량 오류는 뒤쪽에 원인(quotaMetric)이 있어 길게 남김
            print(f"  ✗ 제미나이 {model} {attempt}차 실패: {last[:160]}")
            if ("404" in last or "NOT_FOUND" in last) and models:      # 모델 없음 → 다음 모델로 (시도 횟수는 새로)
                model, attempt = models.pop(0), 0
                print(f"    → 다음 모델로: {model}")
                continue
            if "429" in last or "RESOURCE_EXHAUSTED" in last or "quota" in last.lower():
                if attempt >= 2:
                    break
                time.sleep(30)
            else:
                time.sleep(5 * attempt)
    if res is None or not res.get("ok"):
        res = {**base, "error": last or "알 수 없는 오류", "tried": tried}
    if save:
        try:
            LATEST.parent.mkdir(parents=True, exist_ok=True)
            LATEST.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            if out_docs is not None:
                (out_docs / "data").mkdir(parents=True, exist_ok=True)
                (out_docs / "data" / f"{day}_{slot}_gemini.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ 제미나이 결과 저장 실패: {e}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--slot", choices=["am", "pm"], default="am" if datetime.now(KST).hour < 12 else "pm")
    ap.add_argument("--out", default="", help="날짜별 사본을 저장할 docs 폴더 (비우면 data/gemini_research.json 만)")
    a = ap.parse_args()
    r = run(a.date, a.slot, out_docs=Path(a.out) if a.out else None)
    if r.get("ok"):
        print(f"✓ 제미나이 리서치: 이벤트 {len(r['events'])}개 · 테마 {len(r['movers'])}개 · 검색어 {len(r['search_queries'])}개 · "
              f"근거 링크 {len(r['grounding'])}개 · 제외 {len(r['dropped'])}건")
    else:
        print(f"✗ 제미나이 리서치 실패 (RSS 로 계속): {r.get('error')}")


if __name__ == "__main__":
    main()
