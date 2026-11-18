"""「데이터로 본 유망 3대 분야 & 대표 기업 스포트라이트」 — 리포트·영상 공통 칼럼.

선정: 13개 분야를 4가지 차원으로 교차 평가한 뒤 3개 분야·대표 기업 1곳씩 고른다.
  ① 3~5년 장기 산업 궤적  : 3년 분야 수익률, 3년 상대강도 백분위, 1년 수익률
  ② 3년 재무·실적 뒷받침  : 분야 매출 성장 중앙값 + 대표 기업의 3년 매출·순이익 성장(스크리닝)
  ③ 현재 매크로와의 궁합   : 금리·환율·유가·공포지수 상태 × 분야별 민감도(sector_narratives.yaml)
  ④ 사회·정책 흐름(뉴스)   : 최근 뉴스 제목 중 분야의 구조적 키워드(수출·정책·수주·규제 등)와 맞물린 기사
  슬롯별 주 기준: 장기 구조적 성장(①②) / 추세 전환·수급 유입(60일 순위 상승 폭) / 저평가 실적 우량(3년 흑자 + 낮은 PER)

해설: 4단계 서사 (산업의 어제와 오늘 → 시장·사회 흐름과의 연결 → 대표 기업과 3년 실적 검증 → 균형 잡힌 체크 포인트).
  AI 분석(view["spotlight"])이 있으면 그 글을, 없으면 sector_narratives.yaml + company_profiles.yaml + 데이터로 같은 구조를 만든다.
법적 안전장치: 매수·매도 권유, 추천, 목표주가 같은 표현이 든 문장은 지운다. 정보 제공용 산업·기업 소개 어조만 남긴다.
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
STAGES = [("past_now", "① 산업의 어제와 오늘"), ("market_link", "② 시장 상황·사회적 흐름과의 연결"),
          ("company_story", "③ 대표 기업과 3년 실적 검증"), ("risk", "④ 균형 잡힌 체크 포인트")]
DIMS = [("traj", "장기 궤적"), ("fin", "3년 실적"), ("macro", "매크로 궁합"), ("news", "뉴스 흐름")]

# 권유형 표현 (이 표현이 든 문장은 통째로 뺀다)
BANNED = re.compile(
    r"매수\s*하세요|매수하라|매수\s*추천|추천\s*종목|종목\s*추천|추천합니다|추천드|목표\s*주가|목표가|사야\s*할|사야\s*합니다|사\s*두세요|"
    r"담으세요|담아\s*두|매수\s*타이밍|매수\s*적기|매도\s*하세요|팔아야|투자하세요|비중을\s*늘리세요|강력\s*매수|저가\s*매수\s*기회|지금이\s*기회|매수\s*기회"
)
# 뉴스 제목 중 주가 등락·시세 안내성 기사 (구조적 흐름 근거로 쓰지 않음)
NEWS_JUNK = re.compile(r"주식 움직였습니다|By Investing|주가 전망|주가가 오늘|특징주|급등|급락|상한가|하한가|52주|주가 상승 중|주가 하락 중|"
                       r"\(\w+\) 주식|목표주가|목표가|매수|매도|수급포착|껑충|털썩|\?$|주가[^,]*\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?%[^,]*주가")

MACRO_WORDS = {
    "rate_up": ("금리 상승기", "금리 하락기"), "usd_up": ("원화 약세", "원화 강세"),
    "oil_up": ("유가 상승기", "유가 하락기"), "dxy_up": ("달러 강세", "달러 약세"), "risk_off": ("시장 불안 국면", "시장 안정 국면"),
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


def _mv(v, unit="%", digits=0) -> str:
    """+305 → '305% 올라' / -12 → '12% 내려' (읽을 때 '퍼센트 상승 움직여' 같은 겹말 방지)"""
    if v is None:
        return "–"
    return f"{abs(v):.{digits}f}{unit} {'올라' if v >= 0 else '내려'}"


def _pct(v, digits=1) -> str:
    return "–" if v is None else f"{'마이너스 ' if v < 0 else ''}{abs(v):.{digits}f}%"


def _josa(word: str, pair=("은", "는")) -> str:
    ch = (word or " ")[-1]
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[0] if ch.isdigit() and ch in "013678" else pair[1]


# ───────────────────────── ③ 매크로 상태 ─────────────────────────
def macro_state(macro: dict | None) -> dict:
    """지금 매크로 상태: +1 / 0 / -1 과 근거 문구."""
    a = {x.get("key"): x for x in ((macro or {}).get("assets") or []) if isinstance(x, dict)}
    st, ev = {}, {}
    r = a.get("us10y") or {}
    c3, lv = r.get("chg_3m"), r.get("last")
    st["rate_up"] = 1 if (c3 or 0) >= 15 or (r.get("pct_5y") or 0) >= 85 else -1 if (c3 or 0) <= -15 else 0
    ev["rate_up"] = f"미국 10년 금리 {lv:.2f}%, 3개월 {c3 / 100:+.2f}%p" if lv is not None and c3 is not None else ""
    k = a.get("usdkrw") or {}
    kc = k.get("chg_3m")
    st["usd_up"] = 1 if (kc or 0) >= 2 else -1 if (kc or 0) <= -2 else 0
    ev["usd_up"] = f"원/달러 {k.get('last'):,.0f}원, 3개월 {kc:+.1f}%" if k.get("last") and kc is not None else ""
    d = a.get("dxy") or {}
    dc = d.get("chg_3m")
    st["dxy_up"] = 1 if (dc or 0) >= 2 else -1 if (dc or 0) <= -2 else 0
    ev["dxy_up"] = f"달러 인덱스 {d.get('last'):.1f}, 3개월 {dc:+.1f}%" if d.get("last") and dc is not None else ""
    o = a.get("wti") or {}
    oc, oy = o.get("chg_3m"), o.get("yoy")
    st["oil_up"] = 1 if (oc or 0) >= 5 or ((oc or 0) > -5 and (oy or 0) >= 25) else -1 if (oc or 0) <= -5 else 0
    ev["oil_up"] = f"WTI 원유 {o.get('last'):.1f}달러, 1년 {oy:+.0f}%" if o.get("last") and oy is not None else ""
    v = a.get("vix") or {}
    st["risk_off"] = 1 if (v.get("last") or 0) >= 22 else -1 if (v.get("last") or 99) <= 15 else 0
    ev["risk_off"] = f"공포지수(VIX) {v.get('last'):.1f}" if v.get("last") else ""
    return {"state": st, "evidence": ev}


US_DOLLAR_WHY = "해외 매출 비중이 큰 미국 기업은 달러가 강하면 해외에서 번 돈을 달러로 바꿀 때 이익이 줄어듭니다."


def market_of(comp: dict | None) -> str:
    """대표 기업의 시장: 한국 종목(.KS/.KQ)이면 'kr', 그 밖은 'us'."""
    comp = comp or {}
    if comp.get("market") in ("kr", "us"):
        return comp["market"]
    t = str(comp.get("ticker") or "")
    return "kr" if t.endswith((".KS", ".KQ")) or t.isdigit() else "us"


def macro_fit(cat: str, ms: dict, narr: dict, market: str = "kr") -> tuple[float, list[str], list[str]]:
    """(궁합 점수 -4~+4, 유리한 이유 문장들, 불리한 이유 문장들).
    환율: 한국 기업이면 원/달러(원화 약세 = 수출 이익 증가), 미국 기업이면 달러 인덱스(강달러 = 해외 이익 감소)."""
    n = narr.get(cat) or {}
    sens, why = dict(n.get("macro") or {}), dict(n.get("macro_why") or {})
    states = dict(ms.get("state") or {})
    if market == "us":
        # 원/달러 문구는 빼고, 수출·해외 매출에 민감한 분야면 강달러를 불리하게 본다
        exp = sens.pop("usd_up", 0)
        why.pop("usd_up", None)
        states.pop("usd_up", None)
        if exp:
            sens["dxy_up"], why["dxy_up"] = -1, US_DOLLAR_WHY
    else:
        states.pop("dxy_up", None)
    score, good, bad = 0.0, [], []
    for k, s in states.items():
        e = (sens.get(k) or 0) * s
        if not e or not why.get(k):
            continue
        score += e
        state_word = MACRO_WORDS[k][0 if s > 0 else 1]
        evid = (ms.get("evidence") or {}).get(k)
        head = f"지금은 {state_word}입니다{f'({evid})' if evid else ''}."
        if s > 0:        # 설명 문장이 지금 상태를 그대로 말함
            line = f"{head} {why[k]}"
        else:            # 설명은 반대 상황 기준 → 지금은 거꾸로 작용
            line = f"{head} {why[k]} 지금은 그 반대여서 {'우호적인' if e > 0 else '부담이 되는'} 요인입니다."
        (good if e > 0 else bad).append(line)
        continue
    return score, good, bad


# ───────────────────────── ④ 뉴스 ─────────────────────────
def news_match(cat: str, news: dict | None, narr: dict, n: int = 2) -> tuple[int, list[str]]:
    """분야의 구조적 키워드와 맞물린 최근 뉴스 (주가 등락성 기사는 제외)."""
    kws = [k for k in ((narr.get(cat) or {}).get("keywords") or []) if k]
    if not kws or not news:
        return 0, []
    pool = list((news.get("by_sector") or {}).get(cat) or []) + list(news.get("items") or [])
    seen, hits = set(), []
    for it in pool:
        t = (it.get("title") or "").strip()
        if not t or t in seen or NEWS_JUNK.search(t) or BANNED.search(t):
            continue
        seen.add(t)
        if any(k.lower() in t.lower() for k in kws):
            hits.append((0 if it.get("lang") == "ko" else 1, t))
    hits.sort(key=lambda x: x[0])
    return len(hits), [t for _, t in hits[:n]]


# ───────────────────────── 선정 ─────────────────────────
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
            note = v[1] if isinstance(v[1], str) else f"{v[1]:+.1f}%"
            return {"name": nm, "ticker": tickers.get(nm, ""), "category": c["name"], "metrics": {lab: note}, "reason": "", "list": key}
    return None


def evaluate(screens: dict, macro: dict | None = None, news: dict | None = None) -> dict:
    """13개 분야 × 4차원 점수 (0~1)."""
    cats = [c for c in (screens or {}).get("categories") or [] if c.get("name")]
    narr = _load_yaml("sector_narratives.yaml")
    ms = macro_state(macro)
    n = max(len(cats), 1)
    r3, rp, r1, rg = (_rank(cats, k) for k in ("ret_3y", "rs_pct_3y", "ret_1y", "rev_g"))
    out = {}
    for c in cats:
        nm = c["name"]
        traj = 1 - ((r3.get(nm, n) - 1) * 0.5 + (rp.get(nm, n) - 1) * 0.3 + (r1.get(nm, n) - 1) * 0.2) / max(n - 1, 1)
        comp = _company_from_list(screens, nm)
        fin = 1 - (rg.get(nm, n) - 1) / max(n - 1, 1)
        fin = min(1.0, fin * 0.75 + (0.25 if comp else 0))
        mscore, good, bad = macro_fit(nm, ms, narr, market_of(comp))
        hits, heads = news_match(nm, news, narr)
        out[nm] = {"traj": round(traj, 2), "fin": round(fin, 2), "macro": round((mscore + 4) / 8, 2), "news": round(min(hits, 4) / 4, 2),
                   "macro_raw": mscore, "macro_good": good, "macro_bad": bad, "news_hits": hits, "headlines": heads,
                   "rank_3y": r3.get(nm), "rank_rev": rg.get(nm), "rank_pct3y": rp.get(nm)}
    return {"cats": cats, "ev": out, "macro": ms, "narr": narr}


FIN_MIN = 0.25          # 3년 실적 점수 최소 기준 (이보다 낮으면 대표 기업 3년 성장이 뚜렷할 때만 후보)
STRONG_GROWTH = 15.0    # 대표 기업 3년 매출·순이익 연평균 성장률(%) 이 이 이상이면 '실적 성장이 뚜렷'


def _strong_growth(comp: dict | None) -> bool:
    for k in ("3년 매출 성장", "3년 순이익 성장"):
        v = ((comp or {}).get("metrics") or {}).get(k)
        m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", str(v or ""))
        if m and float(m.group(1)) >= STRONG_GROWTH:
            return True
    return False


def select(screens: dict, macro: dict | None = None, news: dict | None = None) -> list[dict]:
    """다차원 종합 평가로 3개 분야·대표 기업 선정 (설명 글 없이 수치·근거만)."""
    E = evaluate(screens, macro, news)
    cats, ev = E["cats"], E["ev"]
    if len(cats) < 3:
        return []
    uni = _load_yaml("universe.yaml")
    tickers = {nm: t for m in uni.values() for t, nm in (m or {}).items()}
    val = (screens.get("valuation") or {})
    n = len(cats)
    r60 = {c["name"]: c.get("rank_60d") for c in cats}
    r60_1y = {c["name"]: c.get("rank_60d_1y_ago") for c in cats}
    if not all(r60.values()):
        r60 = _rank(cats, "rs_60d")
    if not all(r60_1y.values()):
        r60_1y = _rank(cats, "rs_60d_1y_ago")
    used, out = set(), []
    ok = {c["name"] for c in cats if ev[c["name"]]["fin"] >= FIN_MIN or _strong_growth(_company_from_list(screens, c["name"]))}
    if len(ok) < 3:        # 기준을 넘는 분야가 너무 적으면 실적 점수 상위 3개는 남긴다
        ok |= {c["name"] for c in sorted(cats, key=lambda c: -ev[c["name"]]["fin"])[:3]}
    cats = [c for c in cats if c["name"] in ok]

    def card(kind, c, comp, score, note):
        used.add(c["name"])
        e = dict(ev[c["name"]])
        _, e["macro_good"], e["macro_bad"] = macro_fit(c["name"], E["macro"], E["narr"], market_of(comp))
        return {"kind": kind, "kind_label": KINDS[kind][0], "icon": KINDS[kind][1], "category": c["name"],
                "cat": {k: c.get(k) for k in ("ret_1y", "ret_3y", "ret_60d", "rev_g", "pe_kr", "pe_us", "rs_60d", "rs_60d_1y_ago",
                                                "rs_pct_3y", "breadth", "flow")},
                "rank_3y": e["rank_3y"], "rank_rev": e["rank_rev"], "rank_now": r60.get(c["name"]), "rank_1y_ago": r60_1y.get(c["name"]),
                "n_cats": n, "market_pe": {m: v.get("pe_median") for m, v in val.items()}, "company": comp,
                "score": round(score, 2), "score_note": note,
                "eval": {k: e[k] for k, _ in DIMS}, "macro_good": e["macro_good"], "macro_bad": e["macro_bad"],
                "headlines": e["headlines"], "news_hits": e["news_hits"]}

    def common(nm, w):           # 4차원 가중 합
        e = ev[nm]
        return sum(e[k] * w[k] for k in w)

    # ① 장기 구조적 성장: 장기 궤적·3년 실적 중심 + 매크로·뉴스 교차 검증
    c1 = max(cats, key=lambda c: common(c["name"], {"traj": .35, "fin": .35, "macro": .15, "news": .15}))
    comp = _company_from_list(screens, c1["name"], ("growth", "value")) or _company_from_cat(c1, tickers)
    out.append(card("growth", c1, comp, common(c1["name"], {"traj": .35, "fin": .35, "macro": .15, "news": .15}),
                    f"3년 수익률 {ev[c1['name']]['rank_3y']}위 · 매출 성장 {ev[c1['name']]['rank_rev']}위"))

    # ② 추세 전환·수급 유입: 1년 전 → 지금 60일 순위 상승 폭 + 실적·매크로·뉴스
    rest = [c for c in cats if c["name"] not in used]

    def t_score(c):
        jump = ((r60_1y.get(c["name"]) or n) - (r60.get(c["name"]) or n)) / max(n - 1, 1)
        return 0.45 * max(jump, 0) + common(c["name"], {"fin": .15, "macro": .2, "news": .2})
    c2 = max(rest, key=t_score)
    comp = _company_from_list(screens, c2["name"]) or _company_from_cat(c2, tickers)
    out.append(card("trend", c2, comp, t_score(c2), f"60일 시장 대비 순위 {r60_1y.get(c2['name'])}위 → {r60.get(c2['name'])}위"))

    # ③ 저평가 실적 우량: 3년 흑자 + 업종보다 낮은 PER 기업(저평가 목록) + 분야 PER + 실적·매크로·뉴스
    rest = [c for c in cats if c["name"] not in used]

    def pe_ratio(c):      # 분야 PER ÷ 시장 PER (1보다 작을수록 시장보다 싸게 거래)
        xs = [c.get(f"pe_{m}") / val[m]["pe_median"] for m in ("kr", "us")
              if c.get(f"pe_{m}") and (val.get(m) or {}).get("pe_median")]
        return sum(xs) / len(xs) if xs else 1.0
    byname = {c["name"]: c for c in rest}
    vals = [r for r in screens.get("value") or [] if r.get("category") in byname]

    def v_score(r):
        return ((r.get("score") or 0) / 100 * 0.4 - 0.3 * (pe_ratio(byname[r["category"]]) - 1)
                + common(r["category"], {"fin": .2, "macro": .2, "news": .2}))
    if vals:
        r = max(vals, key=v_score)
        c3, comp, sc = byname[r["category"]], {**r, "list": "value"}, v_score(r)
    else:
        c3 = min(rest, key=lambda c: pe_ratio(c) - common(c["name"], {"fin": .2, "macro": .2, "news": .2}))
        comp, sc = _company_from_cat(c3, tickers), 0
    out.append(card("value", c3, comp, sc, "3년 연속 흑자 · 업종 대비 낮은 PER"))
    return out


# ───────────────────────── 해설 (폴백 서사) ─────────────────────────
def _company_proof(c: dict) -> str:
    comp = c.get("company") or {}
    mt = comp.get("metrics") or {}
    nm = comp.get("name", "")
    grow = []
    for k, lab in (("3년 매출 성장", "3년 매출은 연평균 {}"), ("3년 순이익 성장", "3년 순이익은 연평균 {}"),
                   ("최근 매출 성장", "최근 분기 매출은 {}"), ("최근 이익 성장", "최근 분기 이익은 {}")):
        v = mt.get(k)
        if v and not v.startswith(("-", "–")):
            grow.append(lab.format(v.replace("/년", "").lstrip("+")))
    sents = []
    if grow:
        sents.append(f"데이터로 보면 {nm}의 " + ", ".join(grow) + " 늘었습니다.")
    if mt.get("PER") and mt.get("업종 PER"):
        sents.append(f"PER(주가가 1년 이익의 몇 배인지)은 {mt['PER']}로 같은 업종 중앙값 {mt['업종 PER']}보다 낮은 수준입니다.")
    elif mt.get("PER→선행PER"):
        a_, b_ = mt["PER→선행PER"].split("→")
        sents.append(f"PER은 지금 {a_}이지만 내년 예상 이익 기준으로는 {b_}로, 이익이 늘어날수록 주가 배수가 낮아지는 구조입니다.")
    for k, v in mt.items():
        if not k and v:
            sents.append(f"최근 실적은 '{v}'로 분야 안에서 두드러집니다.")
    if mt.get("ROE"):
        sents.append(f"자기자본이익률(ROE)은 {mt['ROE']}입니다.")
    why_this = {"growth": "분야 성장 기대 후보 중 3년 실적 점수가 가장 높은 기업이라 대표로 살펴봅니다.",
                "value": "3년 연속 흑자를 내면서도 주가 배수가 업종보다 낮은 기업이라 대표로 살펴봅니다.",
                "best": "최근 분야 안에서 주가 흐름이 가장 강한 기업이라 대표로 살펴봅니다.",
                "growth_pick": "분야 안에서 최근 매출 성장이 가장 두드러진 기업이라 대표로 살펴봅니다.",
                "value_pick": "분야 안에서 주가 배수가 가장 낮은 편인 기업이라 대표로 살펴봅니다."}.get(comp.get("list"), "")
    return " ".join([why_this] + sents).strip()


def _fallback(c: dict, narr: dict, prof: dict) -> dict:
    n = narr.get(c["category"]) or {}
    s = c["cat"]
    comp = c.get("company") or {}
    nm = comp.get("name", "")
    # 1. 어제와 오늘
    data1 = (f"숫자로 보면 분야 지수는 최근 3년 동안 {_mv(s.get('ret_3y'))} {c['n_cats']}개 분야 중 {c['rank_3y']}위이고, "
             f"최근 1년 동안에는 {_mv(s.get('ret_1y'))}습니다.").replace("올라습", "올랐습").replace("내려습", "내렸습")
    if c["kind"] == "trend":
        data1 += (f" 1년 전에는 최근 60일 시장 대비 힘이 {c['rank_1y_ago']}위였지만 지금은 {c['rank_now']}위로 올라섰습니다.")
    past_now = " ".join(x for x in (n.get("past"), n.get("now"), data1) if x)
    # 2. 시장·사회 흐름
    link = list(c.get("macro_good") or [])[:2] + list(c.get("macro_bad") or [])[:1]
    if c.get("headlines"):
        link.append("최근 뉴스에서도 " + ", ".join(f"‘{h[:48]}’" for h in c["headlines"][:2]) + " 같은 소식이 이 흐름과 맞물려 있습니다.")
    if not link:
        link.append(f"지금의 금리·환율 환경에서 이 분야는 {'·'.join(n.get('drivers') or []) or '고유한 성장 동력'}에 따라 움직이는 모습입니다.")
    if c["kind"] == "value":
        mp = c.get("market_pe") or {}
        link.append(f"분야 PER 중앙값은 국내 {s.get('pe_kr') or '–'}배(전체 시장 {mp.get('kr') or '–'}배), "
                    f"미국 {s.get('pe_us') or '–'}배(전체 시장 {mp.get('us') or '–'}배)입니다.")
    # 3. 기업과 3년 실적
    biz = prof.get(nm, "") or f"{c['category']} 분야로 분류되는 상장 기업입니다."
    company_story = f"{nm}{_josa(nm)} {biz} {_company_proof(c)}".strip()
    # 4. 체크 포인트
    risk = " ".join(x for x in (n.get("watch"), *(c.get("macro_bad") or [])[1:2]) if x)
    return {"past_now": past_now, "market_link": " ".join(link), "company_story": company_story,
            "risk": risk or "업황과 금리·환율 같은 거시 변수에 따라 실적 전망이 달라질 수 있습니다.", "business": biz}


def _points(c: dict) -> list[str]:
    comp, s = c.get("company") or {}, c["cat"]
    pts = [f"{k} {v}".strip() for k, v in (comp.get("metrics") or {}).items()][:5]
    if c["kind"] == "trend":
        pts.append(f"분야 60일 순위 {c['rank_1y_ago']}위 → {c['rank_now']}위")
    pts.append(f"분야 3년 {s.get('ret_3y'):+.0f}% · 매출 성장 중앙값 {s.get('rev_g'):+.1f}%" if s.get("ret_3y") is not None and s.get("rev_g") is not None else "")
    if c["kind"] == "value":
        pts.append(f"분야 PER 중앙값 국내 {s.get('pe_kr') or '–'}배 / 미국 {s.get('pe_us') or '–'}배")
    return [p for p in pts if p]


def build(screens: dict, view: dict | None, macro: dict | None = None, news: dict | None = None) -> dict:
    """리포트·영상에 넣을 완성본. AI 글이 있으면 그것을, 없으면 서사형 템플릿."""
    cards = select(screens or {}, macro, news)
    if not cards:
        return {}
    prof = _load_yaml("company_profiles.yaml")
    narr = _load_yaml("sector_narratives.yaml")
    ai = {x["category"]: x for x in ((view or {}).get("spotlight") or []) if isinstance(x, dict) and x.get("category")}
    for c in cards:
        comp = c.get("company") or {}
        fb = _fallback(c, narr, prof)
        a = ai.get(c["category"]) or {}
        same = not a.get("company") or comp.get("name", "") in a.get("company", "") or a.get("company", "") in comp.get("name", "")
        txt = {
            "past_now": clean(a.get("past_now")) or fb["past_now"],
            "market_link": clean(a.get("market_link")) or fb["market_link"],
            "company_story": (clean(a.get("company_story") or (f"{comp.get('name', '')}{_josa(comp.get('name', ''))} " + a["business"] if a.get("business") else ""))
                              if same else "") or fb["company_story"],
            "risk": clean(a.get("risk")) or fb["risk"],
        }
        c["stages"] = [{"key": k, "title": t, "text": txt[k]} for k, t in STAGES]
        c["business"] = (clean(a.get("business")) if same else "") or fb["business"]
        c["why"] = txt["past_now"]
        c["risk"] = txt["risk"]
        c["points"] = _points(c)
        c["eval_view"] = [{"label": lab, "value": c["eval"][k]} for k, lab in DIMS]
        c["ai"] = bool(a)
    return {"title": "데이터로 본 유망 3대 분야 & 대표 기업 스포트라이트", "cards": cards, "disclaimer": DISCLAIMER}


def brief_text(screens: dict, macro: dict | None = None, news: dict | None = None) -> str:
    """AI 브리프에 넣을 오늘의 스포트라이트 대상과 4차원 근거 (설명 글은 AI가 4단계 서사로 쓴다)."""
    cards = select(screens or {}, macro, news)
    if not cards:
        return ""
    narr = _load_yaml("sector_narratives.yaml")
    out = ["## 스포트라이트 대상 (프로그램이 4차원 교차 평가로 고름 — spotlight 에 이 3곳을 순서·이름 그대로 씀)"]
    for c in cards:
        comp, s, e = c.get("company") or {}, c["cat"], c["eval"]
        n = narr.get(c["category"]) or {}
        mt = ", ".join(f"{k} {v}".strip() for k, v in (comp.get("metrics") or {}).items())
        out += [f"### [{c['kind_label']}] {c['category']} — 대표 기업 {comp.get('name')}({comp.get('ticker')})",
                f"- 선정 근거: {c['score_note']} · 4차원 점수(0~1) 장기 궤적 {e['traj']} / 3년 실적 {e['fin']} / 매크로 궁합 {e['macro']} / 뉴스 흐름 {e['news']}",
                f"- ① 장기 궤적: 3년 {s.get('ret_3y')}% ({c['rank_3y']}위), 1년 {s.get('ret_1y')}%, 3년 상대강도 백분위 {s.get('rs_pct_3y')}, "
                f"60일 순위 {c['rank_1y_ago']}위(1년 전) → {c['rank_now']}위",
                f"- ② 3년 실적: 분야 매출 성장 중앙값 {s.get('rev_g')}% ({c['rank_rev']}위) · 기업 {mt or '–'}",
                f"- ③ 매크로 궁합: 유리 — {' / '.join(c['macro_good']) or '없음'} · 불리 — {' / '.join(c['macro_bad']) or '없음'}",
                f"- ④ 관련 뉴스: {' / '.join(c['headlines']) or '구조적 키워드와 맞는 기사 없음 (웹 검색으로 확인)'}",
                f"- 참고 배경(기본 해설): {n.get('past', '')} {n.get('now', '')}"]
    return "\n".join(out)
