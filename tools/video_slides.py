"""영상 전용 16:9 슬라이드 (1920×1080).

리포트(세로로 긴 웹 페이지)를 축소 캡처하지 않고, 영상용 화면을 따로 그립니다.
  - 1슬라이드 1메시지: 핵심 차트 1개 + 요약 3줄 이내, 글씨 40px(≈30pt) 이상
  - 상태 배지: 🟢 기회 / 🟡 관망 / 🔴 위험
  - 아래 170px 는 자막 바 자리 (ffmpeg 가 아나운서 문장을 이 위치에 입힘)
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CHART_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
SLOT_NAME = {"am": "모닝 브리핑", "pm": "나이트 브리핑"}
BADGE = {"good": ("🟢", "기회", "#1E8E3E", "#E6F4EA"), "wait": ("🟡", "관망", "#B06000", "#FEF3E0"),
         "risk": ("🔴", "위험", "#C5221F", "#FCE8E6"), "info": ("🔵", "참고", "#1F5FBF", "#E3ECFA")}


@dataclass
class Slide:
    section: str
    title: str
    narration: str
    lines: list[str] = field(default_factory=list)
    badge: tuple[str, str] | None = None          # (종류 good/wait/risk/info, 문구)
    chart: dict | None = None                       # Chart.js 설정
    body_html: str = ""                             # 차트 대신 넣을 큰 카드 등
    center: bool = False


# ───────────────────────── 문장 도우미 ─────────────────────────
def _sents(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!])\s+", re.sub(r"\s+", " ", (text or "").strip())) if s]


def split_text(text: str, n: int) -> list[str]:
    """대본을 n 개 슬라이드에 문장 단위로 고르게 나눈다."""
    ss = _sents(text)
    if n <= 1 or len(ss) <= 1:
        return [" ".join(ss)] + [""] * (n - 1)
    total = sum(len(s) for s in ss)
    out, cur, acc, k = [], [], 0, 1
    for s in ss:
        cur.append(s)
        acc += len(s)
        if acc >= total * k / n and k < n:
            out.append(" ".join(cur))
            cur, k = [], k + 1
    out.append(" ".join(cur))
    return out + [""] * (n - len(out))


def cap(text: str, limit: int) -> str:
    """대본 길이 상한: 문장 단위로만 자른다 (문장 중간에서 자르지 않음)."""
    ss = _sents(text)
    out = ""
    for s in ss:
        if out and len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out


def first(text: str) -> str:
    """화면 카드용: 첫 문장을 통째로 (글자 수로 자르지 않음)."""
    ss = _sents(text)
    return ss[0] if ss else (text or "")


def stance_kind(label: str) -> str:
    if re.search(r"늘리기|적극|골라서|매수", label or "") and "현금" not in (label or ""):
        return "good"
    if re.search(r"줄이기|현금|방어|축소", label or ""):
        return "risk"
    return "wait"


def _jong(ch: str) -> int:
    """한글 끝 글자의 받침 번호 (0 = 받침 없음, 8 = ㄹ). 한글이 아니면 -1."""
    return (ord(ch) - 0xAC00) % 28 if ch and "가" <= ch <= "힣" else -1


def ro(word: str) -> str:
    """'로/으로' 고르기: 받침 없거나 ㄹ 받침이면 '로'."""
    w = (word or "").strip()
    j = _jong(w[-1:]) if w else 0
    return "로" if j in (0, 8) or j == -1 and not w[-1:].isdigit() else "으로" if j > 0 else "로"


def eun(word: str) -> str:
    w = (word or "").strip()
    return "은" if _jong(w[-1:]) > 0 else "는"


def to_clause(np_: str) -> str:
    """화면용 명사구 → 이어 말하기용 절. '비용이 커짐' → '비용이 커지고', '가치가 줄어듦' → '가치가 줄어들고', '수요 증가' → '수요가 증가하고'"""
    s = (np_ or "").strip().rstrip(".")
    if not s:
        return s
    last = s[-1]
    j = _jong(last)
    if last == "움" and len(s) >= 2 and _jong(s[-2]) == 0:      # 쉬움 → 쉽고, 어려움 → 어렵고 (ㅂ 불규칙)
        return s[:-2] + chr(ord(s[-2]) + 17) + "고"
    if s.endswith(("우려", "부담", "불안", "기대")):
        return s + ("이" if _jong(last) > 0 else "가") + " 커지고"
    if j == 16:                                     # ㅁ 받침: 커짐 → 커지고, 하락함 → 하락하고
        return s[:-1] + chr(ord(last) - 16) + "고"
    if j == 10:                                     # ㄻ 받침: 줄어듦 → 줄어들고
        return s[:-1] + chr(ord(last) - 10 + 8) + "고"
    BECOME = ("약화", "강화", "둔화", "악화", "확대", "축소", "개선", "위축", "지연", "부각", "고조", "심화", "완화", "반영", "집중")
    DO = ("증가", "감소", "하락", "상승", "급락", "급등", "반등", "이동", "확보", "매도", "매수", "유입", "유출", "이탈", "회피",
          "선호", "전환", "축적", "회복", "투자", "철수", "조정", "인상", "인하", "상향", "하향")
    if re.search(r"[고며]$", s) and not s.endswith(("확보", "고조")):
        return s
    OBJ = ("확보", "매도", "매수", "회피", "선호", "축적", "투자", "인상", "인하", "상향", "하향", "조정")   # 을/를 받는 말
    words = s.split()
    w = words[-1] if words else s
    if len(words) >= 2 and (w in BECOME or w in DO):
        pre = " ".join(words[:-1])
        noun_end = pre.endswith(("주가", "물가", "단가", "원가", "유가", "시가", "종가", "평가", "국가", "차이", "금리 차이"))
        if noun_end or not re.search(r"(로|를|을|에|서|와|과|이|가|은|는|도|의)$", pre):     # 이미 조사가 붙어 있으면 그대로
            j2 = _jong(pre[-1:]) > 0
            pre += ("을" if j2 else "를") if w in OBJ else ("이" if j2 else "가")
        s = f"{pre} {w}"
    if s.endswith(BECOME):
        return s + "되고"
    if s.endswith(DO):
        return s + "하고"
    if s.endswith(("압력", "부담", "리스크", "변동성")):
        return s + ("이" if _jong(last) > 0 else "가") + " 커지고"
    if s.endswith(("약세", "강세", "역전", "현상", "흐름", "분위기")):
        return s + ("이" if _jong(last) > 0 else "가") + " 나타나고"
    if re.search(r"[다요고며]$", s):        # 이미 서술어로 끝남 (팔고, 줄이며 …)
        return s if s.endswith(("고", "며")) else s
    return s + ("이" if _jong(last) > 0 else "가") + " 나타나고"


def after_moves(m: dict, subject="코스피는") -> str:
    """유사 국면 이후 1·3·6개월을 한 문장으로.
    같은 방향: '그 뒤 코스피는 1개월 뒤 10.5%, 3개월 뒤 8.2%, 6개월 뒤에는 15.0% 상승했습니다.'
    방향이 바뀌면: '그 뒤 코스피는 1개월 뒤 1.1% 올랐다가, 3개월 뒤 26.8%, 6개월 뒤에는 24.9% 하락했습니다.'"""
    xs = [(lab, m.get(k)) for lab, k in (("1개월 뒤", "kospi_4w"), ("3개월 뒤", "kospi_13w"), ("6개월 뒤에는", "kospi_26w"))
          if m.get(k) is not None]
    if not xs:
        return ""
    sign = lambda v: 1 if v >= 0.05 else -1 if v <= -0.05 else 0
    out = []
    for i, (lab, v) in enumerate(xs):
        last = i == len(xs) - 1
        nxt = None if last else sign(xs[i + 1][1])
        if sign(v) == 0:
            piece = f"{lab} 거의 변하지 않았{'습니다' if last else '고'}"
        elif last:
            piece = f"{lab} {abs(v):.1f}% {'상승' if v > 0 else '하락'}했습니다"
        elif nxt != sign(v):
            piece = f"{lab} {abs(v):.1f}% {'올랐다가' if v > 0 else '내렸다가'}"
        else:
            piece = f"{lab} {abs(v):.1f}%"
        out.append(piece)
    return f"그 뒤 {subject} " + ", ".join(out) + "."


def drop_restated(text: str) -> str:
    """AI 교훈 문장에서 1·3·6개월 수치를 되풀이한 문장은 뺀다 (after_moves 가 이미 읽음)."""
    sents = re.split(r"(?<=[.?!])\s+", (text or "").strip())
    keep = [x for x in sents if x and not (re.search(r"\d+\s*개월", x) and re.search(r"[+-]?\d+(?:\.\d+)?\s*%", x))]
    return " ".join(keep)


def moved(v, subject="코스피는") -> str:
    """부호에 맞는 서술어: -24.9 → '코스피는 24.9% 하락했습니다'"""
    if v is None:
        return f"{subject} 결과를 확인할 수 없습니다."
    if abs(v) < 0.05:
        return f"{subject} 거의 변하지 않았습니다."
    return f"{subject} {abs(v):.1f}% {'상승' if v > 0 else '하락'}했습니다."


def chg_word(v, unit="%") -> str:
    if v is None:
        return "–"
    return f"{v:+.1f}{unit}"


def fmt_level(a: dict, v=None) -> str:
    v = a.get("last") if v is None else v
    if v is None:
        return "–"
    if a.get("kind") == "rate":
        return f"{v:.2f}%"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def rank5(p) -> str:
    if p is None:
        return "–"
    return f"최근 5년 중 상위 {max(1, round(100 - p))}%" if p >= 50 else f"최근 5년 중 하위 {max(1, round(p))}%"


# ───────────────────────── 슬라이드 구성 ─────────────────────────
def build(data: dict, slot: str, date: str) -> list[Slide]:
    V = data.get("view") or {}
    RB = bool(V.get("rule_based"))
    sc = {} if RB else (V.get("script") or {})
    ez = V.get("easy") or {}
    M = data.get("macro") or {}
    A = {a["key"]: a for a in M.get("assets", []) if "error" not in a}
    SC = data.get("screens") or {}
    cats = SC.get("categories") or []
    st, fc, al = V.get("stance") or {}, V.get("forecast") or {}, V.get("allocation") or {}
    md = f"{int(date[5:7])}월 {int(date[8:10])}일"
    sname = SLOT_NAME.get(slot, "시장 브리핑")
    S: list[Slide] = []

    def e3(key):          # 3단계 해설 → 화면 3줄
        x = ez.get(key)
        if isinstance(x, dict):
            return [v for v in (x.get("one"), x.get("why"), x.get("do")) if v]
        return _sents(x)[:3] if isinstance(x, str) else []

    def e3text(key):
        return " ".join(e3(key))

    # 1. 오프닝
    S.append(Slide("오프닝", V.get("headline") or f"{md} {sname}", center=True,
                   narration=cap(sc.get("intro") or f"{md} {sname}입니다. 경제를 잘 몰라도 이해할 수 있게 오늘 시장을 정리해 드리겠습니다.", 240),
                   badge=(stance_kind(st.get("label", "")), f"오늘의 자세: {st.get('label', '관망')}")))

    # 2. 오늘 이것만
    summ = [x for x in (ez.get("summary") or []) if x][:3]
    if summ:
        nums = ["첫째", "둘째", "셋째"]
        S.append(Slide("핵심 요약", "오늘 시장, 이것만 알면 됩니다", lines=summ,
                       narration="오늘 시장, 이것만 기억하세요. " + " ".join(f"{nums[i]}, {s}" for i, s in enumerate(summ))))

    # 3. 오늘의 결론 (자산 배분 도넛)
    alloc_keys = [("kr_equity", "국내 주식", "#D0342C"), ("us_equity", "미국 주식", "#1F5FBF"), ("gold_commodities", "금·원자재", "#B7791F"),
                  ("usd_cash", "달러 현금", "#0D5C6B"), ("krw_cash_bonds", "원화 현금·채권", "#6B7A88"), ("alternatives", "대체자산", "#7B4FA0")]
    lines = []
    if fc.get("band_low"):
        lines.append(f"{fc.get('market', '지수')} 예상 범위 {fc['band_low']:,.0f} ~ {fc['band_high']:,.0f}")
    if al:
        lines.append(f"주식 {(al.get('kr_equity') or 0) + (al.get('us_equity') or 0)}% · 금·원자재 {al.get('gold_commodities', 0)}% · 현금·채권 {(al.get('usd_cash') or 0) + (al.get('krw_cash_bonds') or 0)}%")
    conc_e = e3("conclusion")
    if conc_e:
        lines.append(first(conc_e[-1]))
    S.append(Slide("오늘의 결론", "결론부터: " + (st.get("label") or "관망"), lines=lines[:3],
                   badge=(stance_kind(st.get("label", "")), st.get("label", "관망").split(" (")[0]),
                   chart=_donut([(n, al.get(k) or 0, c) for k, n, c in alloc_keys]) if al else None,
                   narration=cap("결론부터 말씀드리겠습니다. 오늘의 자세는 " + (st.get("label") or "관망") + "입니다. " + " ".join(lines), 300)))

    # 4. 과거 대비 — 자산별 슬라이드 (코스피 / 미국 금리 / 환율)
    hist_keys = [k for k in ("kospi", "us10y", "usdkrw") if k in A]
    hist_parts = split_text(sc.get("history") or e3text("history"), max(1, len(hist_keys)))
    for i, k in enumerate(hist_keys):
        a = A[k]
        sp = a.get("spark") or []
        mo = list({p[0][:7]: p for p in sp}.values())
        hi = max(sp, key=lambda p: p[1]) if sp else None
        rate = a.get("kind") == "rate"
        dd = None if not hi else ((a["last"] - hi[1]) * 100 if rate else (a["last"] / hi[1] - 1) * 100)
        kind = "risk" if dd is not None and dd <= (-50 if rate else -15) else "good" if (a.get("chg_3m") or 0) > (30 if rate else 5) else "wait"
        if rate:      # 금리는 오를수록 주식에 부담 → 색 의미를 반대로
            kind = "risk" if (a.get("chg_3m") or 0) > 25 else "good" if (a.get("chg_3m") or 0) < -25 else "wait"
        state = ("최근 고점에서 크게 하락" if dd is not None and dd <= (-50 if rate else -15) else
                 "최근 3개월 상승" if (a.get("chg_3m") or 0) > (25 if rate else 5) else
                 "최근 3개월 하락" if (a.get("chg_3m") or 0) < -(25 if rate else 5) else "큰 변화 없음")
        ln = [f"최근 고점 {fmt_level(a, hi[1])}({hi[0][2:4]}.{hi[0][5:7]}) → 지금 {fmt_level(a)}  ({(f'{dd / 100:+.2f}%p' if rate else f'{dd:+.1f}%') if dd is not None else '–'})",
              f"1년 전 {fmt_level(a, a.get('year_ago'))} → 지금 {fmt_level(a)}  ({(f'{(a.get('yoy') or 0) / 100:+.2f}%p' if rate else chg_word(a.get('yoy')))})",
              f"5년 전체로 보면 {rank5(a.get('pct_5y'))}"]
        nar = hist_parts[i] or (f"{a['name']}{eun(a['name'])} 최근 고점보다 {abs(dd):.0f}% 낮고, " + moved(a.get('yoy'), "1년 전보다는") if dd is not None and not rate else ln[1])
        if i == 0 and not hist_parts[0]:
            nar = "작년, 그리고 최근 5년과 비교해 지금이 어디쯤인지 보겠습니다. " + nar
        S.append(Slide("① 과거와 비교", f"{a['name']}: {state}", lines=ln, badge=(kind, state),
                       chart=_line_hist(a, mo), narration=cap(nar, 420)))

    # 5. 과거 사례
    AN = M.get("analogs") or {}
    if AN.get("matches"):
        aia = ((V.get("history_context") or {}).get("analogs") or [])
        names, parts = [], []
        for i, m in enumerate(AN["matches"][:3]):
            x = next((q for q in aia if q.get("date") == m["date"]), aia[i] if i < len(aia) else {})
            nm = x.get("period") or f"{m['date'][:4]}년 {int(m['date'][5:7])}월"
            names.append(f"{nm}: 그 뒤 6개월 코스피 {chg_word(m.get('kospi_26w'))}")
            parts.append(f"{nm}. " + (x.get("what_happened", "") + " " if x.get("what_happened") else "")
                         + after_moves(m) + " " + drop_restated(x.get("lesson") or ""))
        S.append(Slide("① 과거와 비교", "지금과 비슷했던 과거 사례", lines=names, badge=("info", "역사는 참고용"),
                       chart=_overlay(AN), narration=cap("지금과 비슷했던 과거를 겹쳐 보겠습니다. 검은 선이 지금입니다. " + " ".join(parts), 620)))

    # 6. 매크로 (상태 카드 3개)
    regs = M.get("regimes") or []
    if regs:
        cards = "".join(_reg_card(r) for r in regs[:3])
        S.append(Slide("② 금리·환율·원자재", "돈의 흐름: 금리·달러·공포지수", body_html=f"<div class='cards3'>{cards}</div>",
                       narration=cap(sc.get("macro") or e3text("macro") or " ".join(f"{r['label']}는 {r['value']}." for r in regs), 560)))

    # 7. 연결고리 (한 장에 2개)
    chains = [c for c in (V.get("chains") or []) if isinstance(c, dict) and c.get("from")]
    for j in range(0, min(len(chains), 4), 2):
        grp = chains[j:j + 2]
        body = "".join(_chain_html(c) for c in grp)
        def say_chain(c):
            frm = re.sub(r"\s*\([^)]*\)", "", c.get("from", "")).strip()          # 괄호 설명은 말하지 않음
            so = re.sub(r"\s*\([^)]*\)", "", (c.get("so") or "")).strip().rstrip(".")
            cl = [to_clause(re.sub(r"\s*\([^)]*\)", "", s)) for s in (c.get("steps") or []) if s]
            if cl:   # 마지막 고리는 '~며,'로 끊고 '이는 결국 ~로 이어집니다'로 맺음 → '이어지고' 반복 없음
                cl[-1] = re.sub(r"고$", "며,", cl[-1])
            body = " ".join(cl)
            return (f"{frm}{'이' if _jong(frm[-1:]) > 0 else '가'} 나타나면 {body} 이는 결국 {so}{ro(so)} 이어집니다." if body
                    else f"{frm}{'이' if _jong(frm[-1:]) > 0 else '가'} 나타나면 결국 {so}{ro(so)} 이어집니다.")
        nar = " ".join(say_chain(c) for c in grp)
        S.append(Slide("③ 오늘의 연결고리", "무엇이 무엇을 움직이나" + (" (계속)" if j else ""), body_html=f"<div class='chains'>{body}</div>",
                       narration=cap(("오늘 시장이 왜 이렇게 움직이는지 연결고리로 보겠습니다. " if j == 0 else "") + nar, 520)))

    # 8. 오늘 예측
    if fc.get("band_low"):
        dirw = fc.get("direction", "보합")
        kind = "good" if "상승" in dirw else "risk" if "하락" in dirw else "wait"
        sc3 = [s for s in (fc.get("scenarios") or []) if isinstance(s, dict)][:3]
        body = _gauge(fc, (M.get("quant") or {})) + ("<div class='scen'>" + "".join(
            f"<div class='sc {('good' if s.get('name') == '강세' else 'risk' if s.get('name') == '약세' else 'wait')}'><b>{html.escape(str(s.get('name', '')))} {s.get('prob', '')}%</b>"
            f"<span>{html.escape(first(str(s.get('trigger', ''))))}</span></div>" for s in sc3) + "</div>" if sc3 else "")
        S.append(Slide("③ 오늘 시장 예상", f"{'오늘' if slot == 'am' else '오늘 밤'} {fc.get('market', '지수')}: {dirw} 예상", badge=(kind, f"상승 확률 {round(fc.get('prob_up') or 50)}%"),
                       body_html=body, narration=cap(sc.get("social_forecast") or e3text("forecast"), 700)))

    # 9. 13개 분야 (막대그래프 + 강·약 카드)
    if cats:
        srt = sorted([c for c in cats if c.get("rs_60d") is not None], key=lambda c: -c["rs_60d"])
        sec_parts = split_text(sc.get("sectors") or e3text("sectors"), 2)
        S.append(Slide("④ 13개 분야", "분야별 힘: 시장 평균보다 잘 오른 분야는?", chart=_bars(srt),
                       lines=["막대가 오른쪽(초록)일수록 최근 두 달 시장 평균보다 잘 오른 분야"],
                       narration=cap(sec_parts[0] or "13개 분야를 시장 평균과 비교해 보겠습니다.", 420)))
        aisec = {s.get("name"): s for s in (V.get("sectors") or [])}
        top, bot = srt[:3], srt[-3:][::-1]
        body = "<div class='two'><div><h3 class='g'>🟢 힘센 분야</h3>" + "".join(_sec_card(c, aisec.get(c["name"], {})) for c in top) + \
               "</div><div><h3 class='r'>🔴 약한 분야</h3>" + "".join(_sec_card(c, aisec.get(c["name"], {})) for c in bot) + "</div></div>"
        S.append(Slide("④ 13개 분야", "주목할 분야 vs 조심할 분야", body_html=body,
                       narration=cap(sec_parts[1] or f"힘센 분야는 {', '.join(c['name'] for c in top)}, 약한 분야는 {', '.join(c['name'] for c in bot)}입니다.", 420)))

    # 10. 기회 / 리스크
    ops, rks = (V.get("opportunities") or [])[:2], (V.get("risks") or [])[:2]
    or_parts = split_text(sc.get("opps_risks") or e3text("opps_risks"), 2)
    if ops:
        S.append(Slide("⑤ 기회와 위험", "지금 기회가 있는 곳", badge=("good", "기회"),
                       lines=[f"{o.get('title', '')}: {first(o.get('how', ''))}" for o in ops],
                       narration=cap(or_parts[0] or " ".join(f"{o.get('title', '')}. {o.get('why', '')}" for o in ops), 380)))
    if rks:
        S.append(Slide("⑤ 기회와 위험", "조심해야 할 것", badge=("risk", "위험"),
                       lines=[f"{r.get('title', '')}: {first(r.get('signal', ''))}" for r in rks],
                       narration=cap(or_parts[1] or " ".join(f"{r.get('title', '')}. {r.get('why', '')}" for r in rks), 380)))
    if not ops and not rks and e3("opps_risks"):
        S.append(Slide("⑤ 기회와 위험", "기회와 위험", lines=e3("opps_risks"), badge=("wait", "점검"), narration=e3text("opps_risks")))

    # 11. 종합 총론
    plan = [p for p in (V.get("action_plan") or []) if p][:3]
    S.append(Slide("⑥ 종합 전략", "그래서 오늘은 이렇게", lines=[first(p) for p in plan] or conc_e[:3],
                   badge=(stance_kind(st.get("label", "")), st.get("label", "관망").split(" (")[0]),
                   chart=_donut([(n, al.get(k) or 0, c) for k, n, c in alloc_keys]) if al else None,
                   narration=cap(sc.get("conclusion") or e3text("conclusion"), 620)))

    # 12. 스포트라이트 칼럼 (정보 제공용 산업·기업 소개)
    sp_slide = spotlight_slide(data, V)
    if sp_slide:
        S.append(sp_slide)

    S.append(Slide("마무리", "오늘 브리핑은 여기까지입니다", center=True,
                   lines=["자세한 내용은 설명란의 리포트·PDF에서"],
                   narration="자세한 분석은 설명란의 리포트와 PDF에서 확인하세요. 이 영상은 투자 권유가 아닌 정보 제공 목적입니다."))
    return [s for s in S if s.narration.strip()]


SPOT_CSS = """<style>
.spw{display:flex;flex-direction:column;gap:14px;height:100%}
.sp3{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;flex:1;min-height:0}
.sp3 .c{background:#fff;border-radius:22px;border-top:12px solid #0D5C6B;padding:22px 28px;display:flex;flex-direction:column;gap:10px}
.sp3 .k{font-size:26px;font-weight:800;color:#0D5C6B}.sp3 .cat{font-size:44px;font-weight:900;line-height:1.1}
.sp3 .co{font-size:34px;font-weight:800;margin-top:6px}.sp3 .co span{font-size:22px;color:#5C6875;font-weight:600}
.sp3 .biz{font-size:25px;line-height:1.38;color:#3A4652}
.sp3 .pt{font-size:24px;font-weight:700;background:#F0F3F6;border-radius:12px;padding:8px 14px}
.spd{font-size:23px;color:#3A4652;background:#FFF6E5;border-radius:12px;padding:10px 18px;text-align:center}
</style>"""


def spotlight_slide(data: dict, V: dict):
    """「오늘의 유망 3대 분야 & 기업 스포트라이트」 와이드 슬라이드 (약 1분, 정보 제공 어조 + 안내 멘트)."""
    import html as _h
    sp = data.get("spotlight")
    if not sp:
        try:
            import spotlight as _sp
            sp = _sp.build(data.get("screens") or {}, V)
        except Exception:  # noqa: BLE001
            sp = None
    cards = (sp or {}).get("cards") or []
    if len(cards) < 3:
        return None
    order = ["첫째", "둘째", "셋째"]
    cols, says = [], []
    for i, c in enumerate(cards[:3]):
        co = c.get("company") or {}
        nm = co.get("name", "")
        pts = (c.get("points") or [])[:2]
        ev = c.get("eval_view") or []
        if ev:      # 4차원 평가를 별 5개로 (장기 궤적·3년 실적·매크로 궁합·뉴스 흐름)
            pts = pts[:1] + [" · ".join(f"{e['label']} {'★' * max(1, round((e['value'] or 0) * 5))}" for e in ev[:2]),
                             " · ".join(f"{e['label']} {'★' * max(1, round((e['value'] or 0) * 5))}" for e in ev[2:])]
        cols.append(f"<div class='c'><div class='k'>{_h.escape(c.get('icon', ''))} {_h.escape(c['kind_label'])}</div>"
                    f"<div class='cat'>{_h.escape(c['category'])}</div>"
                    f"<div class='co'>{_h.escape(nm)} <span>{_h.escape(co.get('ticker', ''))}</span></div>"
                    f"<div class='biz'>{_h.escape(c.get('business', ''))}</div>"
                    + "".join(f"<div class='pt'>{_h.escape(p)}</div>" for p in pts) + "</div>")
        why = first(c.get("why", ""))
        says.append(f"{order[i]}, {c['kind_label']}는 {c['category']}입니다. {why} "
                    f"대표 기업 {nm}{eun(nm)} {first(c.get('business', ''))}")
    disc = sp.get("disclaimer", "")
    narr = ("마지막으로, 데이터로 본 유망 3대 분야와 대표 기업 스포트라이트입니다. "
            "산업 동향 학습 차원에서 분야마다 데이터상 실적이 두드러지는 기업 한 곳씩을 소개합니다. " + " ".join(says) + " " + disc)
    body = (SPOT_CSS + "<div class='spw'><div class='sp3'>" + "".join(cols) + "</div>"
            f"<div class='spd'>ⓘ {_h.escape(disc)}</div></div>")
    return Slide("⑦ 스포트라이트", "오늘의 유망 3대 분야 & 기업 스포트라이트", body_html=body, badge=("info", "정보 제공"),
                 narration=narr)


# ───────────────────────── 차트·카드 HTML ─────────────────────────
def _donut(items):
    return {"type": "doughnut", "data": {"labels": [f"{n} {v}%" for n, v, _ in items], "datasets": [
        {"data": [v for _, v, _ in items], "backgroundColor": [c for _, _, c in items], "borderColor": "#fff", "borderWidth": 4}]},
        "options": {"cutout": "55%", "plugins": {"legend": {"position": "right", "labels": {"font": {"size": 30}, "boxWidth": 28, "padding": 18}}}}}


def _line_hist(a, mo):
    if not mo:
        return None
    last = mo[-1][0]
    ago_key = f"{int(last[:4]) - 1}{last[4:7]}"
    labels = [p[0][2:7].replace("-", ".") for p in mo]
    vals = [p[1] for p in mo]
    ago_i = next((i for i, p in enumerate(mo) if p[0][:7] == ago_key), -1)
    radius = [12 if i in (len(mo) - 1, ago_i) else 0 for i in range(len(mo))]
    fill = ["#16202A" if i == len(mo) - 1 else "#FFFFFF" for i in range(len(mo))]
    return {"type": "line", "data": {"labels": labels, "datasets": [
        {"label": a["name"], "data": vals, "borderColor": "#0D5C6B", "borderWidth": 6, "pointRadius": radius,
         "pointBackgroundColor": fill, "pointBorderColor": "#16202A", "pointBorderWidth": 4, "tension": 0.2},
        {"label": "3년 평균", "data": [a.get("avg_3y")] * len(vals), "borderColor": "#8793A0", "borderDash": [12, 10], "borderWidth": 3, "pointRadius": 0}]},
        "options": {"plugins": {"legend": {"display": False}},
                    "scales": {"x": {"grid": {"display": False}, "ticks": {"font": {"size": 26}, "autoSkip": False, "maxRotation": 0,
                                                                            "callback": "__YEAR_TICK__"}},
                               "y": {"ticks": {"font": {"size": 26}, "maxTicksLimit": 5}}}}}


def _overlay(AN):
    labels = list(range(-52, 27, 2))

    def data(p):
        d = {k: v for k, v in (p or [])}
        return [d.get(k) for k in labels]
    colors = ["#D0342C", "#1F5FBF", "#B7791F"]
    ds = [{"label": "지금", "data": data(AN.get("now_path_kospi")), "borderColor": "#16202A", "borderWidth": 8, "pointRadius": 0, "spanGaps": True}]
    for i, m in enumerate(AN.get("matches", [])[:3]):
        ds.append({"label": m["date"][:7].replace("-", "."), "data": data(m.get("path_kospi")), "borderColor": colors[i],
                   "borderWidth": 4, "pointRadius": 0, "spanGaps": True})
    return {"type": "line", "data": {"labels": labels, "datasets": ds},
            "options": {"plugins": {"legend": {"position": "bottom", "labels": {"font": {"size": 26}, "boxWidth": 30}}},
                        "scales": {"x": {"grid": {"display": False}, "ticks": {"font": {"size": 24}, "autoSkip": False, "maxRotation": 0,
                                                                                "callback": "__WEEK_TICK__"}},
                                   "y": {"ticks": {"font": {"size": 24}}, "title": {"display": True, "text": "그 시점 = 100", "font": {"size": 24}}}}}}


def _bars(srt):
    return {"type": "bar", "data": {"labels": [c["name"] for c in srt], "datasets": [
        {"data": [c["rs_60d"] for c in srt], "backgroundColor": ["#1E8E3E" if c["rs_60d"] >= 0 else "#C5221F" for c in srt], "borderRadius": 6}]},
        "options": {"indexAxis": "y", "plugins": {"legend": {"display": False}},
                    "scales": {"x": {"ticks": {"font": {"size": 24}}, "title": {"display": True, "text": "시장 평균 대비 (%p, 최근 60일)", "font": {"size": 24}}},
                               "y": {"ticks": {"font": {"size": 26}}, "grid": {"display": False}}}}}


def _reg_card(r):
    v = r.get("value", "")
    kind = "risk" if re.search(r"상승기|강달러|약세|공포|경계|역전|축소|안전선호", v) else "good" if re.search(r"하락기|약달러|강세|저변동|확대|위험선호", v) else "wait"
    ico = BADGE[kind][0]
    return (f"<div class='rc {kind}'><div class='rl'>{html.escape(r.get('label', ''))}</div><div class='rv'>{ico} {html.escape(v)}</div>"
            f"<div class='re'>{html.escape(r.get('evidence', ''))}</div></div>")


def _chain_html(c):
    steps = "".join(f"<span class='ar'>→</span><span class='nd'>{html.escape(s)}</span>" for s in (c.get("steps") or [])[:2])
    return (f"<div class='ch'><span class='nd f'>{html.escape(c.get('from', ''))}</span>{steps}<span class='ar'>→</span>"
            f"<span class='nd l'>{html.escape(c.get('so', ''))}</span>" + (f"<div class='now'>지금: {html.escape(c['now'])}</div>" if c.get("now") else "") + "</div>")


def _gauge(fc, q):
    lo, hi, base = fc["band_low"], fc["band_high"], fc.get("base_level") or q.get("base_close")
    span = (hi - lo) or 1
    L, R = lo - span * 0.35, hi + span * 0.35
    x = lambda v: (v - L) / (R - L) * 100  # noqa: E731
    bs = f"<div class='gb' style='left:{x(base):.1f}%'><span>어제 {base:,.0f}</span></div>" if base else ""
    return (f"<div class='gauge'><div class='gax'></div><div class='gband' style='left:{x(lo):.1f}%;width:{x(hi) - x(lo):.1f}%'></div>{bs}"
            f"<div class='gl' style='left:{x(lo):.1f}%'>{lo:,.0f}</div><div class='gl' style='left:{x(hi):.1f}%'>{hi:,.0f}</div></div>"
            f"<div class='gcap'>색 띠 = 오늘 예상 범위 (대략 3번 중 2번은 이 안에서 끝남)</div>")


def _sec_card(c, s):
    why = first(s.get("why") or "")
    return (f"<div class='secc'><b>{html.escape(c['name'])}</b><span class='v {'p' if c['rs_60d'] >= 0 else 'n'}'>{c['rs_60d']:+.1f}%p</span>"
            + (f"<div>{html.escape(why)}</div>" if why else "") + "</div>")


# ───────────────────────── 렌더링 ─────────────────────────
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px}
body{font-family:'__FONT__','Noto Color Emoji',sans-serif;background:#F5F7F9;color:#16202A;overflow:hidden;position:relative}
.top{position:absolute;top:0;left:0;right:0;height:88px;background:#16202A;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 64px;font-size:32px}
.top span{color:#98A4B1}
.sec{position:absolute;top:112px;left:64px;font-size:32px;font-weight:700;color:#0D5C6B}
h1{position:absolute;top:156px;left:64px;right:64px;font-size:62px;font-weight:900;line-height:1.2;white-space:nowrap}
.badge{position:absolute;top:120px;right:64px;font-size:36px;font-weight:700;padding:8px 26px;border-radius:40px}
.main{position:absolute;top:260px;left:64px;right:64px;bottom:190px;display:flex;gap:48px;align-items:stretch}
.chart{flex:1.35;background:#fff;border-radius:20px;padding:24px 28px;box-shadow:0 6px 20px rgba(22,32,42,.08);position:relative}
.chart canvas{width:100%!important;height:100%!important}
.lines{flex:1;display:flex;flex-direction:column;justify-content:center;gap:26px}
.lines.full{flex:none;width:100%}
.ln{font-size:40px;line-height:1.35;font-weight:500;background:#fff;border-radius:16px;padding:20px 28px;border-left:10px solid #0D5C6B;box-shadow:0 4px 14px rgba(22,32,42,.06)}
.body{flex:1}
.center h1{top:330px;text-align:center;white-space:normal;font-size:80px}
.center .badge{position:absolute;top:560px;left:50%;right:auto;transform:translateX(-50%)}
.center .sub{position:absolute;top:660px;left:0;right:0;text-align:center;font-size:40px;color:#5C6875}
.cards3{display:flex;gap:32px;height:100%;max-height:600px}
.rc{flex:1;background:#fff;border-radius:20px;padding:36px;display:flex;flex-direction:column;gap:22px;border-top:14px solid #B06000}
.rc.risk{border-top-color:#C5221F}.rc.good{border-top-color:#1E8E3E}
.rl{font-size:36px;color:#5C6875;font-weight:700}.rv{font-size:46px;font-weight:900;line-height:1.25}.re{font-size:30px;color:#5C6875;line-height:1.4}
.chains{display:flex;flex-direction:column;gap:40px;justify-content:center;height:100%}
.ch{display:flex;flex-wrap:wrap;align-items:center;gap:16px;background:#fff;border-radius:20px;padding:30px 34px}
.nd{font-size:38px;font-weight:600;background:#F0F3F6;border-radius:12px;padding:14px 22px}
.nd.f{background:#E3ECFA}.nd.l{background:#FCE8E6;font-weight:800}
.ar{font-size:44px;color:#8793A0;font-weight:900}
.now{flex-basis:100%;font-size:30px;color:#5C6875;margin-top:6px}
.gauge{position:relative;height:200px;margin:40px 40px 0}
.gax{position:absolute;left:0;right:0;top:110px;border-top:6px solid #DDE3E9}
.gband{position:absolute;top:80px;height:64px;border-radius:14px;background:rgba(13,92,107,.25);border:4px solid #0D5C6B}
.gb{position:absolute;top:56px;height:112px;border-left:5px dashed #5C6875}
.gb span{position:absolute;top:120px;transform:translateX(-50%);font-size:30px;color:#5C6875;white-space:nowrap}
.gl{position:absolute;top:10px;transform:translateX(-50%);font-size:44px;font-weight:800}
.gcap{text-align:center;font-size:30px;color:#5C6875;margin-top:30px}
.scen{display:flex;gap:28px;margin-top:40px}
.sc{flex:1;border-radius:18px;padding:24px 28px;background:#FEF3E0;font-size:32px;display:flex;flex-direction:column;gap:10px}
.sc.good{background:#E6F4EA}.sc.risk{background:#FCE8E6}.sc b{font-size:38px}
.two{display:flex;gap:40px;height:100%}.two>div{flex:1;display:flex;flex-direction:column;gap:20px}
.two h3{font-size:42px}.two h3.g{color:#1E8E3E}.two h3.r{color:#C5221F}
.secc{background:#fff;border-radius:16px;padding:18px 26px;font-size:30px;line-height:1.35;color:#5C6875}
.secc b{font-size:40px;color:#16202A;margin-right:16px}.secc .v{font-size:38px;font-weight:800}.secc .p{color:#1E8E3E}.secc .n{color:#C5221F}
.subbar{position:absolute;left:0;right:0;bottom:0;height:170px;background:rgba(22,32,42,.92)}
.subbar::before{content:'';position:absolute;left:0;top:0;width:14px;height:100%;background:#0D5C6B}
.disc{position:absolute;bottom:178px;right:64px;font-size:22px;color:#8793A0}
"""

FIT_JS = """<script>(function(){
const h=document.querySelector('h1');
if(h&&!document.body.classList.contains('center')){
 // 제목은 글자 폭만큼만 차지하게 하고, 오른쪽 배지와 겹치지 않을 만큼만 줄인다
 h.style.right='auto';const b=document.querySelector('.badge');
 const w=(b?b.getBoundingClientRect().left-40:1856)-h.getBoundingClientRect().left;
 let f=parseFloat(getComputedStyle(h).fontSize);while(h.getBoundingClientRect().width>w&&f>40){f-=2;h.style.fontSize=f+'px'}}
const m=document.querySelector('.main'); if(!m)return;
const els=[...m.querySelectorAll('*')].filter(e=>!(e instanceof HTMLCanvasElement));
const base=els.map(e=>parseFloat(getComputedStyle(e).fontSize));
const boxes=()=>[m,...m.querySelectorAll('.lines,.body,.cards3,.rc,.ln,.secc,.ch,.sc,.two>div,.chains')];
const over=()=>boxes().some(e=>e.scrollHeight>e.clientHeight+2||e.scrollWidth>e.clientWidth+2);
let k=1; while(over()&&k>0.55){k-=0.04;els.forEach((e,i)=>e.style.fontSize=(base[i]*k)+'px')}
})();</script>"""

TICKS = {
    "__YEAR_TICK__": "function(v){const l=this.getLabelForValue(v);return l.endsWith('.01')?'20'+l.slice(0,2):''}",
    "__WEEK_TICK__": "function(v){const k=this.getLabelForValue(v);return k==0?'지금/그때':k==-52?'1년 전':k==-26?'6개월 전':k==26?'+6개월':''}",
}


_BP = re.compile(r"([+\-−]?)(\d+(?:\.\d+)?)\s?bp(?![A-Za-z])")


def _pp(s: str) -> str:
    return _BP.sub(lambda m: f"{'-' if m.group(1) in '-−' and m.group(1) else m.group(1)}{float(m.group(2)) / 100:.2f}%p", s or "")


def slide_html(s: Slide, i: int, n: int, date: str, slot: str, font: str, disclaimer: str) -> str:
    s.title, s.lines, s.body_html = _pp(s.title), [_pp(x) for x in s.lines], _pp(s.body_html)
    md = f"{int(date[5:7])}월 {int(date[8:10])}일"
    top = f"<div class='top'><div><b>{SLOT_NAME.get(slot, '시장 브리핑')}</b> · {md}</div><span>{i}/{n}</span></div>"
    badge = ""
    if s.badge:
        ico, _, fg, bg = BADGE.get(s.badge[0], BADGE["info"])
        badge = f"<div class='badge' style='color:{fg};background:{bg}'>{ico} {html.escape(s.badge[1])}</div>"
    if s.center:
        body = (f"{top}<h1>{html.escape(s.title)}</h1>{badge}<div class='sub'>{html.escape(s.lines[0] if s.lines else md + ' ' + SLOT_NAME.get(slot, ''))}</div>")
        cls = "center"
    else:
        lines = "".join(f"<div class='ln'>{html.escape(x)}</div>" for x in s.lines[:3])
        if s.chart:
            main = f"<div class='chart'><canvas id='c'></canvas></div>" + (f"<div class='lines'>{lines}</div>" if lines else "")
        elif s.body_html:
            main = f"<div class='body'>{s.body_html}" + (f"<div class='lines full' style='margin-top:26px'>{lines}</div>" if lines else "") + "</div>"
        else:
            main = f"<div class='lines full'>{lines}</div>"
        body = f"{top}<div class='sec'>{html.escape(s.section)}</div><h1>{html.escape(s.title)}</h1>{badge}<div class='main'>{main}</div>"
        cls = ""
    body += f"<div class='disc'>{html.escape(disclaimer)}</div><div class='subbar'></div>" + FIT_JS
    script = ""
    if s.chart and not s.center:
        cfg = json.dumps(s.chart, ensure_ascii=False)
        for k, fn in TICKS.items():
            cfg = cfg.replace(f'"{k}"', fn)
        # set_content 는 같은 문서에 이어 쓰므로, 슬라이드마다 변수 범위를 분리하고 완료 표시를 초기화한다
        script = (f"<script>{_chart_js()}</script>"
                  + f"<script>window.__done=0;(function(){{Chart.defaults.font.family='{font}';Chart.defaults.color='#3A4652';"
                  f"const cfg={cfg};cfg.options=Object.assign({{responsive:true,maintainAspectRatio:false,animation:false}},cfg.options);"
                  f"const ch=new Chart(document.getElementById('c'),cfg);ch.resize();"
                  f"requestAnimationFrame(()=>requestAnimationFrame(()=>{{ch.update('none');window.__done=1}}));}})();</script>")
    else:
        script = "<script>window.__done=1</script>"
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{CSS.replace('__FONT__', font)}</style></head>"
            f"<body class='{cls}'>{body}{script}</body></html>")


_CHART_JS = None


def _chart_js() -> str:
    """Chart.js 를 한 번만 받아 슬라이드 HTML 안에 직접 넣는다 (슬라이드마다 인터넷에서 받다가 실패하는 일 방지)."""
    global _CHART_JS
    if _CHART_JS is None:
        import os
        import time
        import urllib.request
        local = os.environ.get("CHARTJS_PATH")
        if local and Path(local).exists():
            _CHART_JS = Path(local).read_text(encoding="utf-8")
        else:
            for i in range(3):
                try:
                    with urllib.request.urlopen(urllib.request.Request(CHART_CDN, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                        _CHART_JS = r.read().decode("utf-8")
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  Chart.js 받기 재시도 {i + 1}: {e}")
                    time.sleep(3 * (2 ** i))
            else:
                _CHART_JS = ""
        _CHART_JS = _CHART_JS.replace("</script", r"<\/script")
    return _CHART_JS


def render(slides: list[Slide], browser, work: Path, date: str, slot: str, font: str, disclaimer: str) -> list[Path]:
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    js = _chart_js()
    if not js:
        print("  ✗ Chart.js 를 받지 못해 차트 없이 글자 화면만 만듭니다.")
    out = []
    for i, s in enumerate(slides, 1):
        page.set_content(slide_html(s, i, len(slides), date, slot, font, disclaimer), wait_until="load")
        try:
            page.wait_for_function("window.__done === 1", timeout=10000)
        except Exception as e:  # noqa: BLE001  차트를 못 그려도 글자 화면은 남긴다
            print(f"  ✗ 슬라이드 {i} 차트 그리기 실패: {e}")
        page.wait_for_timeout(700)      # 차트가 크기 조정 후 다시 그려질 때까지
        p = work / f"vslide_{i:02d}.png"
        page.screenshot(path=str(p))
        out.append(p)
    page.close()
    return out
