"""AI 브리핑 불러오기 + AI가 없을 때 쓰는 규칙 기반(정량) 결론.

AI 결과(docs/ai/<날짜>_<슬롯>.json)가 있으면 검사·정리해서 쓰고, 없거나 형식이 깨졌으면
지표만으로 같은 모양의 결론(자세·자산 배분·예측 밴드·섹터 판단)을 만들어 리포트와 영상이 항상
같은 순서로 나오게 합니다. 규칙 기반 결과는 "rule_based": true 로 표시됩니다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from validate_ai import ALLOC_KEYS, ALLOC_NAMES, normalize  # noqa: E402,F401

NEUTRAL = {"kr_equity": 25, "us_equity": 30, "gold_commodities": 10, "usd_cash": 15,
           "krw_cash_bonds": 15, "alternatives": 5}


def load_ai(path: Path, sectors: list[str]) -> dict | None:
    if not path.exists():
        return None
    try:
        ai = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ AI 파일 읽기 실패: {e}")
        return None
    ai, errs, warns = normalize(ai, sectors)
    for w in warns:
        print("    경고:", w)
    if errs:
        print("  ✗ AI 파일 사용 불가:", "; ".join(errs))
        return None
    ai.setdefault("allocation", {}).setdefault("neutral", dict(NEUTRAL))
    return ai


def _a(macro: dict, key: str) -> dict:
    for a in macro.get("assets", []):
        if a["key"] == key and "error" not in a:
            return a
    return {}


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def rule_based(results: dict, macro: dict, screens: dict, slot: str) -> dict:
    """지표만으로 만든 결론. 점수 = 추세(지수) + 변동성 + 금리 + 달러 + 위험선호."""
    ev, score = [], 0.0
    idx = [r for c, r in results.items() if c in ("KS11", "US500", "IXIC", "KQ11") and "error" not in r]
    if idx:
        t = sum(r["score"] for r in idx) / len(idx) / 6           # -1 ~ +1
        score += t * 1.2
        ev.append(f"주요 지수 평균 추세 점수 {t * 6:+.1f}/6")
    vix = _a(macro, "vix")
    if vix:
        v = vix["last"]
        adj = 0.4 if v < 15 else 0.1 if v < 20 else -0.4 if v < 30 else -0.9
        score += adj
        ev.append(f"VIX {v:.1f}")
    t10 = _a(macro, "us10y")
    if t10 and t10.get("chg_3m") is not None:
        adj = _clip(-t10["chg_3m"] / 100, -0.5, 0.5)
        score += adj
        ev.append(f"미국 10년물 3개월 {t10['chg_3m']:+.0f}bp")
    dxy = _a(macro, "dxy")
    if dxy and dxy.get("chg_1m") is not None:
        score += _clip(-dxy["chg_1m"] / 4, -0.3, 0.3)
        ev.append(f"달러 인덱스 1개월 {dxy['chg_1m']:+.1f}%")
    cu, au = _a(macro, "copper"), _a(macro, "gold")
    if cu.get("chg_3m") is not None and au.get("chg_3m") is not None:
        score += _clip((cu["chg_3m"] - au["chg_3m"]) / 20, -0.3, 0.3)
    score = _clip(score, -2, 2)
    label = ("공격적 비중확대" if score >= 1 else "선별적 매수" if score >= 0.25
             else "중립·관망" if score > -0.6 else "방어적 비중축소")

    al = dict(NEUTRAL)
    eq = round(score * 6)                         # 주식 비중 가감 (±12%p)
    ks = next((r for c, r in results.items() if c == "KS11" and "error" not in r), None)
    us = next((r for c, r in results.items() if c == "US500" and "error" not in r), None)
    tilt = 0
    if ks and us:
        tilt = _clip(round((ks["score"] - us["score"]) / 2), -4, 4)
    al["kr_equity"] += eq // 2 + tilt
    al["us_equity"] += eq - eq // 2 - tilt
    al["gold_commodities"] += -eq // 4 + (2 if (vix.get("last") or 0) >= 25 else 0)
    al["usd_cash"] += -(eq - (-eq // 4)) // 2
    rest = 100 - sum(al.values())
    al["krw_cash_bonds"] += rest
    al = {k: max(0, v) for k, v in al.items()}
    s = sum(al.values())
    al["krw_cash_bonds"] += 100 - s

    q = macro.get("quant") or {}
    fc = {}
    if q and "error" not in q:
        d = q.get("expected_pct") or 0
        fc = {"market": q["target"], "base_level": q["base_close"], "band_low": q["band_low"],
              "band_high": q["band_high"], "direction": "상승" if d > 0.15 else "하락" if d < -0.15 else "보합",
              "prob_up": q.get("prob_up"), "open_view": f"{q['driver']} 기준 예상 {d:+.2f}%",
              "intraday": "정량 기준선만 제시합니다(AI 해설 없음).", "scenarios": []}

    sectors = []
    for c in (screens or {}).get("categories", []):
        rs, flow = c.get("rs_60d"), c.get("flow")
        sc = 0
        if rs is not None:
            sc += 1 if rs > 3 else -1 if rs < -3 else 0
        if (c.get("breadth") or 0) >= 60:
            sc += 1
        elif (c.get("breadth") or 100) <= 30:
            sc -= 1
        if flow == "유입":
            sc += 1
        elif flow == "유출":
            sc -= 1
        stance = "비중확대" if sc >= 2 else "비중축소" if sc <= -2 else "중립"
        sectors.append({"name": c["name"], "stance": stance, "score": _clip(sc, -2, 2), "flow": flow or "중립",
                        "why": f"시장 대비 60일 {rs:+.1f}%p, 20일선 위 {c.get('breadth', '–')}%, 거래대금 {c.get('turnover_ratio') or '–'}배"
                        if rs is not None else "데이터 부족", "vs_past": ""})
    regs = macro.get("regimes", [])
    return {
        "rule_based": True,
        "headline": f"{'모닝' if slot == 'am' else '나이트'} 브리핑 · 정량 판단 '{label}'",
        "stance": {"label": label, "score": round(score, 2), "one_liner": " · ".join(ev)},
        "history_context": {"summary": "", "same": [], "different": [], "analogs": []},
        "macro": {"summary": " / ".join(f"{r['label']}: {r['value']}" for r in regs), "assets": []},
        "social": {"summary": "", "themes": []},
        "forecast": fc,
        "opportunities": [], "risks": [],
        "sectors": sectors,
        "allocation": {**al, "neutral": dict(NEUTRAL),
                       "rationale": "추세 점수·VIX·금리·달러·구리/금 비율로 계산한 규칙 기반 배분입니다.",
                       "hedges": ""},
        "action_plan": [], "invalidation": [], "watch_events": [],
        "script": {},
    }


def stance_from_ai_or_rule(ai: dict | None, rule: dict) -> dict:
    """AI가 있으면 AI, 없으면 규칙 기반. 규칙 기반 결과는 참고용으로 항상 함께 둔다."""
    if ai:
        ai["quant_reference"] = {"stance": rule["stance"], "allocation": rule["allocation"]}
        return ai
    return rule
