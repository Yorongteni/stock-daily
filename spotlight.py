"""「데이터로 본 유망 3대 분야 & 대표 기업 스포트라이트」 — 리포트·영상 공통 칼럼.

13개 분야 표와 종목 스크리닝(3년 실적·밸류에이션)을 묶어 매일 3개 분야와 대표 기업 1곳씩 고른다.
  ① 장기 구조적 성장  : 3년 분야 수익률 + 매출 성장 중앙값이 가장 탄탄한 분야 → 성장 기대 목록의 대표 기업
  ② 추세 전환·수급 유입: 1년 전 대비 60일 상대강도 순위가 가장 크게 오른 분야 → 그 분야 핵심 기업
  ③ 저평가 실적 우량  : 3년 연속 흑자 + 이익 성장에도 PER이 업종 중앙값보다 낮은 기업이 있는 분야

설명 글은 AI 분석(view["spotlight"])을 먼저 쓰고, 없거나 권유형 표현이 섞이면 데이터 템플릿·기업 소개(company_profiles.yaml)로 채운다.
법적 안전장치: 매수·매도 권유, 추천, 목표주가 같은 표현이 든 문장은 지운다. 정보 제공용 기업 소개 어조만 남긴다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DISCLAIMER = ("본 스포트라이트 코너는 공개된 재무·시세 데이터를 바탕으로 산업과 기업을 알아보는 정보 제공 콘텐츠이며, "
              "특정 종목에 대한 매수나 매도 추천이 아닙니다.")

KINDS = {
    "growth": ("장기 구조적 성장 분야", "📈"),
    "trend": ("최근 추세 전환·수급 유입 분야", "🔄"),
    "value": ("저평가 실적 우량 분야", "💎"),
}

# 권유형 표현 (이 표현이 든 문장은 통째로 뺀다)
BANNED = re.compile(
    r"매수\s*하세요|매수하라|매수\s*추천|추천\s*종목|종목\s*추천|추천합니다|추천드|목표\s*주가|목표가|사야\s*할|사야\s*합니다|사\s*두세요|"
    r"담으세요|담아\s*두|매수\s*타이밍|매수\s*적기|매도\s*하세요|팔아야|투자하세요|비중을\s*늘리세요|강력\s*매수|저가\s*매수\s*기회|지금이\s*기회"
)

CAT_RISKS = {
    "반도체": "메모리 가격은 수요·공급에 따라 크게 출렁이고, AI 투자 속도가 꺾이면 실적 기대가 빠르게 바뀔 수 있습니다.",
    "IT하드웨어·AI인프라": "빅테크의 데이터센터 투자 계획에 실적이 크게 좌우되고, 부품 공급 차질이나 재고 조정에 민감합니다.",
    "소프트웨어·보안": "금리가 오르면 미래 이익을 크게 반영한 높은 주가 배수가 부담이 되고, 신규 고객 증가 속도가 둔화되는지 봐야 합니다.",
    "인터넷·플랫폼": "광고 경기와 규제(개인정보·독점) 이슈에 민감하고, AI 투자 비용이 이익률을 낮출 수 있습니다.",
    "2차전지·소재": "전기차 판매 속도, 리튬 같은 원료 가격, 각국 보조금 정책에 따라 실적이 크게 달라집니다.",
    "자동차·모빌리티": "관세·환율과 경기에 따라 판매가 흔들리고, 전기차 전환 비용이 이익을 줄일 수 있습니다.",
    "바이오·헬스케어": "임상 결과·허가 일정 같은 단일 이벤트에 가치가 크게 움직이고, 약가 정책 변화에 민감합니다.",
    "금융": "금리가 내려가면 이자 이익이 줄고, 경기가 나빠지면 대출 부실(연체) 비용이 늘어날 수 있습니다.",
    "조선·방산·기계": "수주가 실적으로 잡히기까지 시간이 걸리고, 원자재·인건비 상승과 지정학 이벤트 변화에 민감합니다.",
    "전력·에너지": "유가·전기요금 같은 정책·원자재 가격에 실적이 좌우되고, 설비 투자 사이클이 꺾이는지 봐야 합니다.",
    "소비재·유통": "경기 둔화로 소비가 줄거나 원가(원재료·인건비)가 오르면 이익률이 낮아질 수 있습니다.",
    "통신·미디어·게임": "요금 규제와 경쟁, 신작·콘텐츠 흥행 여부에 실적이 흔들릴 수 있습니다.",
    "지주·운송": "계열사 실적과 운임·물동량 같은 경기 변수에 따라 이익이 달라지고, 지주사는 할인 거래되는 경우가 많습니다.",
}


def _load_yaml(name: str) -> dict:
    try:
        import yaml
        return yaml.safe_load((ROOT / name).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def clean(text: str | None) -> str:
    """권유형 표현이 든 문장 제거."""
    if not text:
        return ""
    sents = re.split(r"(?<=[.!?。])\s+", str(text).strip())
    return " ".join(s for s in sents if s and not BANNED.search(s)).strip()


def _rank(cats: list, key: str, reverse=True) -> dict:
    xs = [c for c in cats if c.get(key) is not None]
    xs.sort(key=lambda c: c[key], reverse=reverse)
    return {c["name"]: i + 1 for i, c in enumerate(xs)}


def _f(v, fmt="+.1f", unit="%"):
    return "–" if v is None else f"{v:{fmt}}{unit}"


def _company_from_list(screens: dict, cat: str, lists=("growth", "value")) -> dict | None:
    best = None
    for k in lists:
        for r in screens.get(k) or []:
            if r.get("category") == cat and (best is None or (r.get("score") or 0) > (best.get("score") or 0)):
                best = {**r, "list": k}
    return best


def _company_from_cat(c: dict, tickers: dict) -> dict | None:
    for key, lab in (("growth_pick", ""), ("value_pick", ""), ("best", "최근 20일 주가")):
        v = c.get(key)
        if v and v[0]:
            nm = v[0]
            note = v[1] if isinstance(v[1], str) else f"20일 {v[1]:+.1f}%"
            return {"name": nm, "ticker": tickers.get(nm, ""), "category": c["name"], "metrics": {lab: note}, "reason": "", "list": key}
    return None


def select(screens: dict) -> list[dict]:
    """데이터로 3개 분야·대표 기업 선정 (설명 글 없이 수치만)."""
    cats = [c for c in (screens or {}).get("categories") or [] if c.get("name")]
    if len(cats) < 3:
        return []
    uni = _load_yaml("universe.yaml")
    tickers = {nm: t for m in uni.values() for t, nm in (m or {}).items()}
    val = (screens.get("valuation") or {})
    r3 = _rank(cats, "ret_3y")
    rg = _rank(cats, "rev_g")
    r60 = {c["name"]: c.get("rank_60d") for c in cats}
    r60_1y = {c["name"]: c.get("rank_60d_1y_ago") for c in cats}
    if not all(r60.values()):
        r60 = _rank(cats, "rs_60d")
    if not all(r60_1y.values()):
        r60_1y = _rank(cats, "rs_60d_1y_ago")
    used, out = set(), []

    def card(kind, c, comp, score_note):
        used.add(c["name"])
        return {"kind": kind, "kind_label": KINDS[kind][0], "icon": KINDS[kind][1], "category": c["name"],
                "cat": {k: c.get(k) for k in ("ret_1y", "ret_3y", "ret_60d", "rev_g", "pe_kr", "pe_us", "rs_60d", "rs_60d_1y_ago",
                                                "breadth", "flow")},
                "rank_3y": r3.get(c["name"]), "rank_rev": rg.get(c["name"]), "rank_now": r60.get(c["name"]),
                "rank_1y_ago": r60_1y.get(c["name"]), "n_cats": len(cats), "market_pe": {m: v.get("pe_median") for m, v in val.items()},
                "company": comp, "score_note": score_note}

    # ① 장기 구조적 성장: 3년 수익률 순위 + 매출 성장 순위 (성장 기대 목록 기업이 있으면 가산)
    def g_score(c):
        s = (len(cats) - r3.get(c["name"], len(cats))) + (len(cats) - rg.get(c["name"], len(cats)))
        return s + (2 if _company_from_list(screens, c["name"], ("growth",)) else 0)
    c1 = max(cats, key=g_score)
    comp = _company_from_list(screens, c1["name"], ("growth", "value")) or _company_from_cat(c1, tickers)
    out.append(card("growth", c1, comp, f"3년 수익률 {r3.get(c1['name'])}위 · 매출 성장 {rg.get(c1['name'])}위"))

    # ② 추세 전환: 1년 전 60일 순위 → 지금 순위 상승 폭
    rest = [c for c in cats if c["name"] not in used]
    c2 = max(rest, key=lambda c: ((r60_1y.get(c["name"]) or 0) - (r60.get(c["name"]) or 0), c.get("rs_60d") or -99))
    comp = _company_from_list(screens, c2["name"]) or _company_from_cat(c2, tickers)
    out.append(card("trend", c2, comp, f"60일 시장 대비 순위 {r60_1y.get(c2['name'])}위 → {r60.get(c2['name'])}위"))

    # ③ 저평가 실적 우량: 저평가 목록(3년 연속 흑자 + 업종보다 낮은 PER) 기업이 있는 분야 중 점수가 가장 높은 곳
    rest = [c for c in cats if c["name"] not in used]
    def pe_ratio(c):      # 분야 PER ÷ 시장 PER (1보다 작을수록 시장보다 싸게 거래)
        xs = [c.get(f"pe_{m}") / val[m]["pe_median"] for m in ("kr", "us")
              if c.get(f"pe_{m}") and (val.get(m) or {}).get("pe_median")]
        return sum(xs) / len(xs) if xs else 1.0
    byname = {c["name"]: c for c in rest}
    vals = [r for r in screens.get("value") or [] if r.get("category") in byname]
    if vals:
        r = max(vals, key=lambda x: (x.get("score") or 0) - 30 * (pe_ratio(byname[x["category"]]) - 1))
        c3 = next(c for c in rest if c["name"] == r["category"])
        comp = {**r, "list": "value"}
    else:   # 저평가 목록이 다른 분야뿐이면: 시장 PER 대비 분야 PER 이 가장 낮은 곳
        c3 = min(rest, key=pe_ratio)
        comp = _company_from_cat(c3, tickers)
    out.append(card("value", c3, comp, "3년 연속 흑자 · 업종 대비 낮은 PER"))
    return out


def _mv(v, unit="%", digits=0) -> str:
    """+305 → '305% 올라' / -12 → '12% 내려' (읽을 때 '퍼센트 상승 움직여' 같은 겹말 방지)"""
    if v is None:
        return "–"
    return f"{abs(v):.{digits}f}{unit} {'올라' if v >= 0 else '내려'}"


def _pct(v, digits=1) -> str:
    return "–" if v is None else f"{'마이너스 ' if v < 0 else ''}{abs(v):.{digits}f}%"


def _why(c: dict) -> str:
    k, s, nm = c["kind"], c["cat"], c["category"]
    if k == "growth":
        return (f"{nm} 분야 지수는 최근 3년 동안 {_mv(s.get('ret_3y'))} {c['n_cats']}개 분야 중 {c['rank_3y']}위이고, "
                f"분야 기업들의 매출 성장률 중앙값은 {_pct(s.get('rev_g'))}로 {c['rank_rev']}위입니다. "
                f"최근 1년 동안에도 {_mv(s.get('ret_1y'))} 주가와 실적이 함께 오래 받쳐 준 분야라는 점이 데이터에서 확인됩니다.")
    if k == "trend":
        return (f"1년 전에는 최근 60일 시장 대비 힘이 {c['n_cats']}개 분야 중 {c['rank_1y_ago']}위였지만 지금은 {c['rank_now']}위입니다. "
                f"지금은 시장 평균보다 {abs(s.get('rs_60d') or 0):.1f}%포인트 {'강하고' if (s.get('rs_60d') or 0) >= 0 else '약하고'}, "
                f"1년 전에는 {abs(s.get('rs_60d_1y_ago') or 0):.1f}%포인트 {'강했던' if (s.get('rs_60d_1y_ago') or 0) >= 0 else '약했던'} 것과 비교하면 흐름이 달라졌습니다. "
                f"최근 한 달 상승 흐름을 타는 종목 비율도 {s.get('breadth', '–')}%로, 시장의 관심과 자금이 이 분야로 옮겨 오는 모습입니다.")
    mp = c.get("market_pe") or {}
    mt = (c.get("company") or {}).get("metrics") or {}
    pe = " / ".join(f"{'국내' if m == 'kr' else '미국'} {s.get(f'pe_{m}')}배(전체 시장 {mp.get(m) or '–'}배)"
                    for m in ("kr", "us") if s.get(f"pe_{m}"))
    comp = (c.get("company") or {}).get("name", "")
    head = (f"{comp}의 PER(주가가 1년 이익의 몇 배인지)은 {mt['PER']}로 같은 업종 중앙값 {mt['업종 PER']}보다 낮습니다. "
            if mt.get("PER") and mt.get("업종 PER") else "")
    growth = (f"3년 순이익 성장률은 연 {mt['3년 순이익 성장'].lstrip('+').replace('/년', '')}입니다. "
              if mt.get("3년 순이익 성장") else "")
    return (f"{nm} 분야에는 3년 연속 흑자를 내며 이익이 늘었는데도 주가 배수가 낮게 형성된 기업이 있습니다. {head}{growth}"
            f"분야 PER 중앙값은 {pe or '–'}입니다. 이익과 주가 배수의 차이를 공부해 보는 차원에서 살펴봅니다.")


def _points(c: dict) -> list[str]:
    comp, s = c.get("company") or {}, c["cat"]
    pts = [f"{k} {v}".strip() for k, v in (comp.get("metrics") or {}).items()][:5]
    if c["kind"] == "trend":
        pts.append(f"분야 60일 순위 {c['rank_1y_ago']}위 → {c['rank_now']}위")
    elif c["kind"] == "growth":
        pts.append(f"분야 3년 {_f(s.get('ret_3y'), '+.0f')} · 매출 성장 중앙값 {_f(s.get('rev_g'))}")
    else:
        pts.append(f"분야 PER 중앙값 국내 {s.get('pe_kr') or '–'}배 / 미국 {s.get('pe_us') or '–'}배")
    return pts


def build(screens: dict, view: dict | None) -> dict:
    """리포트·영상에 넣을 완성본. AI 글이 있으면 그것을, 없으면 데이터 템플릿."""
    cards = select(screens or {})
    if not cards:
        return {}
    prof = _load_yaml("company_profiles.yaml")
    ai = {}
    for x in ((view or {}).get("spotlight") or []):
        if isinstance(x, dict) and x.get("category"):
            ai[x["category"]] = x
    for c in cards:
        comp = c.get("company") or {}
        a = ai.get(c["category"]) or {}
        same = not a.get("company") or comp.get("name", "") in a.get("company", "") or a.get("company", "") in comp.get("name", "")
        c["why"] = clean(a.get("why")) or _why(c)
        c["business"] = (clean(a.get("business")) if same else "") or prof.get(comp.get("name", ""), "") or \
            f"{comp.get('name', '')}은(는) {c['category']} 분야로 분류되는 상장 기업입니다."
        c["risk"] = clean(a.get("risk")) or CAT_RISKS.get(c["category"], "업황과 금리·환율 같은 거시 변수에 따라 실적 전망이 달라질 수 있습니다.")
        c["points"] = _points(c)
        c["ai"] = bool(a)
    return {"title": "데이터로 본 유망 3대 분야 & 대표 기업 스포트라이트", "cards": cards, "disclaimer": DISCLAIMER}


def brief_text(screens: dict) -> str:
    """AI 브리프에 넣을 오늘의 스포트라이트 대상 (설명 글은 AI가 쓴다)."""
    cards = select(screens or {})
    if not cards:
        return ""
    out = ["## 스포트라이트 대상 (프로그램이 데이터로 고름 — spotlight 에 이 3곳을 그대로 씀)"]
    for c in cards:
        comp = c.get("company") or {}
        mt = ", ".join(f"{k} {v}".strip() for k, v in (comp.get("metrics") or {}).items())
        out.append(f"- [{c['kind_label']}] 분야: {c['category']} ({c['score_note']}) · 대표 기업: {comp.get('name')}({comp.get('ticker')}) {mt}")
    return "\n".join(out)
