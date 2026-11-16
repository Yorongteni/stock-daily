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
    label = ("적극 매수 (주식 비중 늘리기)" if score >= 1 else "골라서 매수 (좋은 종목만 조금씩)" if score >= 0.25
             else "관망 (지금 비중 유지)" if score > -0.6 else "현금 확보·관망 (주식 비중 줄이기)")

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
    mk = "코스피" if slot == "am" else "S&P 500"
    if q and "error" not in q:
        d = q.get("expected_pct") or 0
        dirw = "상승" if d > 0.15 else "하락" if d < -0.15 else "보합"
        fc = {"market": q["target"], "base_level": q["base_close"], "band_low": q["band_low"],
              "band_high": q["band_high"], "direction": dirw, "prob_up": q.get("prob_up"),
              "open_view": f"밤사이 미국 시장 흐름({q['driver']})을 반영하면 {q['target']}는 어제보다 {d:+.1f}% 근처에서 출발할 가능성이 큽니다.",
              "intraday": "하루 동안은 위 예상 범위 안에서 오르내릴 가능성이 큽니다. 범위를 벗어나면 평소와 다른 큰 뉴스가 나왔다는 신호입니다.",
              "scenarios": []}

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
        why = "데이터가 부족합니다."
        if rs is not None:
            why = (f"최근 두 달 시장 평균보다 {abs(rs):.1f}%p {'더 올랐고' if rs >= 0 else '덜 올랐고(더 내렸고)'}, "
                   f"분야 안에서 오름세를 타는 종목이 {c.get('breadth', '–')}%입니다.")
        sectors.append({"name": c["name"], "stance": stance, "score": _clip(sc, -2, 2), "flow": flow or "중립",
                        "why": why, "vs_past": ""})
    regs = macro.get("regimes", [])

    # ── 초보자용 3단계 설명 (한 줄 결론 → 왜 그럴까 → 그래서 오늘은) ──
    kospi, t10, krw = _a(macro, "kospi"), _a(macro, "us10y"), _a(macro, "usdkrw")
    act = {"적": "주식을 조금 늘려도 좋은 흐름입니다.", "골": "좋은 분야만 골라 조금씩 나눠 사는 정도가 적당합니다.",
           "관": "새로 사거나 팔기보다 지금 비중을 유지하며 지켜보는 편이 좋습니다.",
           "현": "급하게 싸게 사려 하기보다 현금을 넉넉히 두고 지켜보는 편이 안전합니다."}[label[0]]
    cats = sorted([c for c in (screens or {}).get("categories", []) if c.get("rs_60d") is not None], key=lambda c: -c["rs_60d"])
    strong = ", ".join(c["name"] for c in cats[:3]) or "–"
    weak = ", ".join(c["name"] for c in cats[-3:][::-1]) or "–"
    rate_up = (t10.get("chg_3m") or 0) > 25
    easy = {
        "summary": [
            f"오늘 시장 판단은 '{label}'입니다.",
            (f"미국 금리가 최근 3개월 {t10['chg_3m'] / 100:+.2f}%p 움직여 지금 {t10['last']:.2f}%입니다. "
             + ("금리가 오르면 주식에는 부담입니다." if rate_up else "금리 부담은 크지 않은 편입니다.")) if t10 else "미국 금리 정보가 없습니다.",
            f"요즘 힘이 센 분야는 {strong}, 약한 분야는 {weak}입니다.",
        ],
        "history": {"one": (f"코스피는 1년 전보다 {kospi.get('yoy') or 0:+.0f}% 달라졌습니다." if kospi else "코스피 정보가 없습니다."),
                    "why": "금리·환율·세계 증시 흐름이 1년 사이 크게 바뀌었기 때문입니다. 위 그래프에서 최근 고점과 지금을 비교해 보세요.",
                    "do": act},
        "macro": {"one": " / ".join(f"{r['label']}: {r['value']}" for r in regs[:3]) or "주요 지표 정보가 없습니다.",
                  "why": "금리는 '돈의 가격', 환율은 '원화의 가격'입니다. 둘이 오르면 보통 주식에는 부담이 됩니다.",
                  "do": act},
        "forecast": {"one": (f"오늘 {fc.get('market', mk)}는 {fc['band_low']:,.0f}~{fc['band_high']:,.0f} 사이에서 움직일 가능성이 큽니다."
                             if fc else "오늘 예상 범위를 계산하지 못했습니다."),
                     "why": "밤사이 미국 시장에서 한국 관련 주식이 어떻게 움직였는지를 바탕으로 계산했습니다.",
                     "do": act},
        "sectors": {"one": f"힘센 분야는 {strong}, 약한 분야는 {weak}입니다.",
                    "why": "최근 두 달 동안 시장 평균보다 얼마나 잘 올랐는지와, 그 분야에서 오름세를 타는 종목 비율로 판단했습니다.",
                    "do": "강한 분야는 눌릴 때 조금씩, 약한 분야는 반등 신호가 보일 때까지 기다리는 것이 기본입니다."},
        "opps_risks": {"one": "가장 큰 위험은 금리가 더 오르는 것입니다." if rate_up else "급격한 위험 신호는 크지 않습니다.",
                       "why": "금리가 오르면 기업이 돈을 빌리기 어려워지고, 투자자는 주식보다 예금·채권을 찾게 됩니다.",
                       "do": act},
        "conclusion": {"one": f"오늘의 자세는 '{label}'입니다.",
                       "why": "주가 흐름, 공포지수, 금리, 달러, 원자재 흐름을 함께 계산한 결과입니다.",
                       "do": f"주식 {al['kr_equity'] + al['us_equity']}%, 금·원자재 {al['gold_commodities']}%, "
                             f"달러 {al['usd_cash']}%, 원화 현금·채권 {al['krw_cash_bonds']}% 정도로 나눠 두는 것을 참고하세요. {act}"},
    }
    return {
        "rule_based": True,
        "headline": f"{'모닝' if slot == 'am' else '나이트'} 브리핑 · 오늘의 자세: {label.split(' (')[0]}",
        "stance": {"label": label, "score": round(score, 2), "one_liner": easy["summary"][1] + " " + act},
        "history_context": {"summary": "", "same": [], "different": [], "analogs": []},
        "macro": {"summary": " / ".join(f"{r['label']}: {r['value']}" for r in regs), "assets": []},
        "social": {"summary": "", "themes": []},
        "forecast": fc,
        "opportunities": [], "risks": [],
        "sectors": sectors,
        "allocation": {**al, "neutral": dict(NEUTRAL),
                       "rationale": "주가 흐름·공포지수·금리·달러·원자재 흐름으로 계산한 기본 배분입니다.",
                       "hedges": ""},
        "action_plan": [act], "invalidation": [], "watch_events": [],
        "easy": easy, "chains": [], "glossary": [],
        "script": {},
    }


def stance_from_ai_or_rule(ai: dict | None, rule: dict) -> dict:
    """AI가 있으면 AI, 없으면 규칙 기반. 규칙 기반 결과는 참고용으로 항상 함께 둔다."""
    if ai:
        ai["quant_reference"] = {"stance": rule["stance"], "allocation": rule["allocation"]}
        return ai
    return rule
