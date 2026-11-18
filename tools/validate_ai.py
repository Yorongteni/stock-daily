#!/usr/bin/env python3
"""AI 브리핑 JSON(docs/ai/<날짜>_<슬롯>.json) 형식 검사·정리. 표준 라이브러리만 사용.

  python tools/validate_ai.py docs/ai/2026-11-17_am.json            # 검사 + 자동 정리 후 저장
  python tools/validate_ai.py docs/ai/2026-11-17_am.json --check    # 검사만

종료 코드 0 = 사용 가능(경고만 있을 수 있음), 1 = 필수 항목 누락 또는 출처(sources) 부족으로 사용 불가.
출처: 원문 URL·게시일이 있는 기사 6개 이상, 그중 2개 이상은 브리핑 날짜 기준 이틀 안 (파일 이름의 날짜 기준).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOC_KEYS = ["kr_equity", "us_equity", "gold_commodities", "usd_cash", "krw_cash_bonds", "alternatives"]
ALLOC_NAMES = {"kr_equity": "국내 주식", "us_equity": "미국 주식", "gold_commodities": "금·원자재(현물)",
               "usd_cash": "달러 현금성", "krw_cash_bonds": "원화 현금·채권", "alternatives": "대체자산(비트코인 등)"}
REQUIRED = ["headline", "stance", "history_context", "macro", "social", "forecast",
            "opportunities", "risks", "sectors", "allocation", "action_plan", "script",
            "easy", "chains", "glossary"]
SCRIPT_KEYS = ["intro", "history", "macro", "social_forecast", "sectors", "opps_risks", "conclusion"]
STANCES = ["적극 매수 (주식 비중 늘리기)", "골라서 매수 (좋은 종목만 조금씩)", "관망 (지금 비중 유지)", "현금 확보·관망 (주식 비중 줄이기)"]
OLD_STANCES = {"공격적 비중확대": STANCES[0], "선별적 매수": STANCES[1], "중립·관망": STANCES[2], "방어적 비중축소": STANCES[3]}


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


_BP = re.compile(r"([+\-−]?)(\d+(?:\.\d+)?)\s?bp(?![A-Za-z])")


def fix_bp(s: str) -> str:
    """'+40bp' → '+0.40%p' (금리 변화는 항상 %p 로)"""
    return _BP.sub(lambda m: f"{'-' if m.group(1) in '-−' and m.group(1) else m.group(1)}{float(m.group(2)) / 100:.2f}%p", s)


def _walk(x):
    if isinstance(x, str):
        return fix_bp(x)
    if isinstance(x, list):
        return [_walk(v) for v in x]
    if isinstance(x, dict):
        return {k: _walk(v) for k, v in x.items()}
    return x


MIN_SOURCES = 6        # 출처 최소 개수
MIN_RECENT = 2         # 그중 브리핑 날짜 기준 RECENT_DAYS 안에 게시된 기사 최소 개수
RECENT_DAYS = 2
_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def check_sources(ai: dict, brief_date: str | None) -> tuple[list[str], list[str]]:
    """sources 검사 → (문제, 참고). 문제가 있으면 AI 가 푸시 전에 고쳐야 한다."""
    from datetime import date
    probs, notes = [], []
    src = ai.get("sources")
    if not isinstance(src, list) or not src:
        return [f"'sources'(확인한 기사 출처) 없음 — {MIN_SOURCES}개 이상 필요"], notes
    good, recent, seen = 0, 0, set()
    bd = date.fromisoformat(brief_date) if brief_date else None
    for i, x in enumerate(src, 1):
        if not isinstance(x, dict):
            probs.append(f"sources {i}번: 형식 오류")
            continue
        miss = [k for k in ("title", "url", "date") if not str(x.get(k) or "").strip()]
        url = str(x.get("url") or "").strip()
        if miss:
            probs.append(f"sources {i}번 '{str(x.get('title'))[:30]}': {', '.join(miss)} 없음")
            continue
        if not _URL.match(url) or "news.google" in url or "/search?" in url:
            probs.append(f"sources {i}번: 기사 원문 URL 이 아님 ({url[:60]})")
            continue
        if url in seen:
            probs.append(f"sources {i}번: 같은 URL 중복")
            continue
        seen.add(url)
        m = _DATE.match(str(x["date"]).strip())
        if not m:
            probs.append(f"sources {i}번: 날짜 형식은 YYYY-MM-DD ({x['date']})")
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            probs.append(f"sources {i}번: 없는 날짜 ({x['date']})")
            continue
        if bd and d > bd:
            probs.append(f"sources {i}번: 브리핑 날짜({bd})보다 뒤 날짜 ({d})")
            continue
        good += 1
        if bd and (bd - d).days <= RECENT_DAYS:
            recent += 1
    if good < MIN_SOURCES:
        probs.append(f"유효한 출처 {good}개 — {MIN_SOURCES}개 이상 필요")
    if bd and recent < MIN_RECENT:
        probs.append(f"최근 {RECENT_DAYS}일 안 기사 {recent}개 — {MIN_RECENT}개 이상 필요 (오늘 뉴스를 원문으로 확인)")
    notes.append(f"출처 {good}개 (최근 {RECENT_DAYS}일 안 {recent}개)")
    return probs, notes


def normalize(ai: dict, sectors: list[str] | None = None, brief_date: str | None = None,
              strict_sources: bool = False) -> tuple[dict, list[str], list[str]]:
    """(정리된 ai, 오류, 경고). 오류가 있으면 사용 불가.
    strict_sources=True(푸시 전 검사)면 출처 문제가 오류, 아니면(리포트 생성) 경고로만 남긴다 — 예전 파일도 리포트는 만들 수 있게."""
    errs, warns = [], []
    sp_probs, sp_notes = check_sources(ai, brief_date)
    (errs if strict_sources else warns).extend(sp_probs)
    warns.extend(sp_notes)
    ai = _walk(ai)
    for k in REQUIRED:
        if k not in ai or ai[k] in (None, "", [], {}):
            (errs if k in ("headline", "allocation", "forecast", "sectors") else warns).append(f"'{k}' 없음")

    st = ai.get("stance")
    if isinstance(st, str):
        ai["stance"] = st = {"label": st}
    if isinstance(st, dict) and st.get("label") in OLD_STANCES:
        st["label"] = OLD_STANCES[st["label"]]
    if isinstance(st, dict) and st.get("label") not in STANCES:
        warns.append(f"stance.label '{st.get('label')}' → 허용값 {STANCES}")
    if isinstance(st, dict) and _num(st.get("score")) is not None:
        sc = _num(st["score"])
        if not -2 <= sc <= 2:
            warns.append(f"stance.score {sc} → -2~+2 범위로 맞춤")
        st["score"] = max(-2.0, min(2.0, sc))

    al = ai.get("allocation")
    if isinstance(al, dict):
        vals = {k: _num(al.get(k)) or 0.0 for k in ALLOC_KEYS}
        total = sum(vals.values())
        if total <= 0:
            errs.append("allocation 비중 합계가 0")
        else:
            if abs(total - 100) > 0.5:
                warns.append(f"allocation 합계 {total:.1f}% → 100%로 맞춤")
                vals = {k: v * 100 / total for k, v in vals.items()}
            r = {k: round(v) for k, v in vals.items()}
            r[max(r, key=r.get)] += 100 - sum(r.values())
            al.update(r)
            neutral = al.get("neutral")
            if isinstance(neutral, dict):
                for k in ALLOC_KEYS:
                    neutral[k] = _num(neutral.get(k)) or 0
    fc = ai.get("forecast")
    if isinstance(fc, dict):
        for k in ("band_low", "band_high", "base_level", "prob_up"):
            if k in fc:
                fc[k] = _num(fc[k])
        if fc.get("band_low") and fc.get("band_high") and fc["band_low"] > fc["band_high"]:
            fc["band_low"], fc["band_high"] = fc["band_high"], fc["band_low"]
            warns.append("forecast 밴드 상·하단을 바로잡음")
        if not fc.get("scenarios"):
            warns.append("forecast.scenarios 없음")

    secs = ai.get("sectors")
    if isinstance(secs, list) and sectors:
        have = {s.get("name") for s in secs if isinstance(s, dict)}
        miss = [s for s in sectors if s not in have]
        if miss:
            warns.append(f"sectors 누락 {len(miss)}개: {', '.join(miss)}")
    sp = ai.get("spotlight")
    if sp is not None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from spotlight import BANNED, clean
            if not isinstance(sp, list):
                warns.append("spotlight 는 목록이어야 함 → 비움")
                ai["spotlight"] = []
            else:
                for x in sp:
                    for k in ("past_now", "market_link", "company_story", "why", "business", "risk"):
                        if isinstance(x, dict) and x.get(k) and BANNED.search(str(x[k])):
                            warns.append(f"spotlight '{x.get('company')}' {k}: 권유형 표현 문장 삭제")
                            x[k] = clean(x[k])
        except Exception as e:  # noqa: BLE001
            warns.append(f"spotlight 검사 실패: {e}")
    sc = ai.get("script")
    if isinstance(sc, dict):
        miss = [k for k in SCRIPT_KEYS if not sc.get(k)]
        if miss:
            warns.append(f"script 누락: {', '.join(miss)}")
    return ai, errs, warns


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1])
    try:
        ai = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"✗ JSON 읽기 실패: {e}")
        sys.exit(1)
    sectors = None
    try:  # 같은 슬롯의 데이터 묶음에서 분야 이름 확인
        data = p.parent.parent / "data" / (p.stem + ".json")
        if data.exists():
            d = json.loads(data.read_text(encoding="utf-8"))
            sectors = [c["name"] for c in (d.get("screens") or {}).get("categories", [])]
    except Exception:  # noqa: BLE001
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})_", p.stem)
    ai, errs, warns = normalize(ai, sectors, m.group(1) if m else None, strict_sources=True)
    for w in warns:
        print("  경고:", w)
    for e in errs:
        print("  오류:", e)
    if errs:
        print("✗ 사용 불가")
        sys.exit(1)
    if "--check" not in sys.argv:
        p.write_text(json.dumps(ai, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✓ 사용 가능")


if __name__ == "__main__":
    main()
