#!/usr/bin/env python3
"""AI 브리핑 JSON(docs/ai/<날짜>_<슬롯>.json) 형식 검사·정리. 표준 라이브러리만 사용.

  python tools/validate_ai.py docs/ai/2026-11-17_am.json            # 검사 + 자동 정리 후 저장
  python tools/validate_ai.py docs/ai/2026-11-17_am.json --check    # 검사만

종료 코드 0 = 사용 가능(경고만 있을 수 있음), 1 = 필수 항목 누락으로 사용 불가.
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


def normalize(ai: dict, sectors: list[str] | None = None) -> tuple[dict, list[str], list[str]]:
    """(정리된 ai, 오류, 경고). 오류가 있으면 사용 불가."""
    errs, warns = [], []
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
    ai, errs, warns = normalize(ai, sectors)
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
