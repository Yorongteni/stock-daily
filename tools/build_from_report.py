#!/usr/bin/env python3
"""
매일 만드는 브리핑 리포트(docs/report_<날짜>_<am|pm>.html)를 그대로 사용해 PDF와 유튜브 영상을 만든다.

  out/<날짜>/report_<날짜>_<슬롯>.pdf   리포트 화면 그대로 PDF
  out/<날짜>/<날짜>_<슬롯>.mp4          리포트 섹션을 화면으로, 앵커 대본(AI) 또는 수치를 읽어주는 영상
  out/<날짜>/youtube.json               업로드용 제목·설명·태그
  out/<날짜>/description.txt            설명란 (챕터 시간 포함)

영상 순서 (리포트와 동일):
  오프닝 → 오늘의 결론 → ① 과거 대비 진단 → ② 매크로·환율·현물 → ③ 사회 흐름·당일 예측
  → ④ 13개 분야 (+스크리닝·관심 종목) → ⑤ 기회 & 리스크 → ⑥ 종합 투자 총론 → 마무리

사용법:
  python tools/build_from_report.py --date 2026-11-17 --slot am
  python tools/build_from_report.py --date latest --silent      # 음성 없이 시험
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_daily import (DISCLAIMER, FONT, build_video, duration, make_audio,  # noqa: E402
                         mmss, write_srt)

DOCS = Path("docs")
PAGES = os.environ.get("PAGES_URL", "https://yorongteni.github.io/stock-daily")
CHART_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
SLOT_NAME = {"am": "모닝 브리핑", "pm": "나이트 브리핑"}


@dataclass
class Scene:
    title: str
    section: str
    narration: str
    images: list[str] = field(default_factory=list)   # PNG 경로
    center: bool = False


@dataclass
class Job:
    date: str
    data: dict
    slot: str = ""
    scenes: list[Scene] = field(default_factory=list)


# ───────────────────────────── 리포트 읽기 ─────────────────────────────
def find_report(date: str, slot: str) -> tuple[Path, str, str]:
    if date == "latest":
        lj = DOCS / "latest.json"
        if lj.exists():
            info = json.loads(lj.read_text(encoding="utf-8"))
            date, slot = info["date"], slot or info.get("slot", "")
        else:
            files = sorted(DOCS.glob("report_????-??-??.html"))
            if not files:
                sys.exit("docs 폴더에 리포트가 없습니다.")
            date = files[-1].stem.replace("report_", "")
    for p in ([DOCS / f"report_{date}_{slot}.html"] if slot else []) + [DOCS / f"report_{date}.html"]:
        if p.exists():
            return p, date, slot
    sys.exit(f"리포트가 없습니다: {date} {slot}")


def load_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\s*\nconst esc", text, flags=re.S)
    if not m:
        sys.exit("리포트에서 데이터(DATA)를 찾지 못했습니다. report.py 형식이 바뀌었는지 확인하세요.")
    return json.loads(m.group(1))


# ───────────────────────────── 말하기 도우미 ─────────────────────────────
def say_chg(v, unit="퍼센트") -> str:
    if v is None:
        return "변동 정보 없음"
    if abs(v) < 0.05:
        return "보합"
    from decimal import ROUND_HALF_UP, Decimal
    a = Decimal(str(abs(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{a}{unit} {'상승' if v > 0 else '하락'}"


def say_asset_chg(a: dict, key: str) -> str:
    v = a.get(key)
    if a.get("kind") == "rate":
        if v is None:
            return "변동 정보 없음"
        return "보합" if abs(v) < 1 else f"{abs(v):.0f}bp {'상승' if v > 0 else '하락'}"
    return say_chg(v)


def say_level(a: dict) -> str:
    return f"{a['last']:.2f}%" if a.get("kind") == "rate" else f"{a['last']:,.2f}" if a["last"] < 100 else f"{a['last']:,.0f}"


def josa(word: str, pair=("은", "는")) -> str:
    """받침 유무로 은/는, 이/가 고르기 (한글 끝 글자만 판별)."""
    ch = word.strip()[-1:] if word.strip() else ""
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[1]


def _sentences(text: str, n: int) -> str:
    parts = re.split(r"(?<=[.?!])\s+", (text or "").strip())
    return " ".join(parts[:n])


def _cap(text: str, limit: int) -> str:
    """문장 단위로 잘라 limit 글자 안쪽으로 (영상 길이 상한)."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    out = ""
    for s in re.split(r"(?<=[.?!])\s+", text):
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out or text[:limit]


# ───────────────────────────── 장면 구성: 핵심 요약(약 5분) ─────────────────────────────
SHORT_CAP = {"analog": 560, "intro": 220, "easy": 300, "gloss": 380, "sum": 220, "history": 560, "macro": 560, "chains": 620,
             "fc": 700, "heat": 700, "or": 520, "conc": 620}


def plan_short(job: Job, shots: dict[str, list[str]]) -> None:
    """초보자용 핵심판(약 10분): 오프닝 → 쉬운 요약 → 용어 미리 보기 → 결론 → 과거 대비 → 매크로 → 연결고리
    → 당일 예측 → 13개 분야 → 기회·리스크 → 총론 → 마무리."""
    d = job.data
    V = d.get("view") or {}
    RB = bool(V.get("rule_based"))
    sc_ = {} if RB else (V.get("script") or {})
    M = d.get("macro") or {}
    A = {a["key"]: a for a in M.get("assets", []) if "error" not in a}
    cats = (d.get("screens") or {}).get("categories") or []
    md = f"{int(job.date[5:7])}월 {int(job.date[8:10])}일"
    sname = SLOT_NAME.get(job.slot, "시장 브리핑")
    st, fc, al = V.get("stance") or {}, V.get("forecast") or {}, V.get("allocation") or {}
    one = lambda *ks: next(((shots.get(k) or [])[:1] for k in ks if shots.get(k)), [])  # noqa: E731
    S: list[Scene] = []

    ez = {} if RB else (V.get("easy") or {})
    intro = sc_.get("intro") or f"{md} {sname}입니다. 경제를 잘 몰라도 이해할 수 있게 오늘 시장을 정리합니다."
    S.append(Scene(V.get("headline") or f"{md} {sname}", "오프닝", _cap(intro, SHORT_CAP["intro"]), center=True))

    summ = [x for x in (ez.get("summary") or []) if x]
    if summ and shots.get("easy_sum"):
        nums = ["첫째", "둘째", "셋째", "넷째"]
        t = "오늘 시장, 이것만 기억하세요. " + " ".join(f"{nums[i]}, {s}" for i, s in enumerate(summ[:4]))
        S.append(Scene("오늘 이것만 알면 됩니다", "쉬운 요약", _cap(t, SHORT_CAP["easy"]), one("easy_sum")))
    gl = [g for g in (V.get("glossary") or []) if isinstance(g, dict) and g.get("term")] if not RB else []
    if gl and shots.get("gloss"):
        t = "본론에 앞서 오늘 자주 나올 말을 먼저 풀어 드리겠습니다. " + " ".join(
            f"{g['term']}{josa(g['term'])} {g.get('meaning', '')}" for g in gl[:4])
        S.append(Scene("오늘 나올 용어 미리 보기", "쉬운 요약", _cap(t, SHORT_CAP["gloss"]), one("gloss")))

    t = f"결론부터 말씀드립니다. 오늘의 투자 자세는 {st.get('label', '중립')}입니다."
    if fc.get("band_low"):
        t += f" {fc.get('market', '지수')} 예상 범위는 {fc['band_low']:,.0f}에서 {fc['band_high']:,.0f}입니다."
    if al:
        t += (f" 주식 {(al.get('kr_equity') or 0) + (al.get('us_equity') or 0)}%, 금과 원자재 {al.get('gold_commodities', 0)}%, "
              f"달러 {al.get('usd_cash', 0)}%를 제안합니다.")
    S.append(Scene("오늘의 결론", "오늘의 결론", _cap(t, SHORT_CAP["sum"]), one("sum")))

    if sc_.get("history"):
        t = sc_["history"]
    else:
        def hist_line(a):
            sp = [v for _, v in (a.get("spark") or []) if v is not None]
            line = f"{a['name']}{josa(a['name'])} 1년 전보다 {say_asset_chg(a, 'yoy')}"
            if sp and a.get("kind") != "rate" and max(sp) > 0:
                dd = (a["last"] / max(sp) - 1) * 100
                if dd <= -10:
                    line += f", 다만 최근 고점보다는 {abs(dd):.0f}퍼센트 낮은 상태"
            return line + "입니다."
        t = "작년과 비교해 보겠습니다. " + " ".join(hist_line(a) for k in ("kospi", "us10y", "usdkrw") if (a := A.get(k)))
    S.append(Scene("과거 대비 지금의 위치", "① 과거 대비", _cap(t, SHORT_CAP["history"]), one("pctl", "hist_ai")))

    an = (M.get("analogs") or {}).get("matches") or []
    if an and shots.get("analog_ch"):
        aia = ((V.get("history_context") or {}).get("analogs") or []) if not RB else []
        parts = []
        for i, m in enumerate(an[:3]):
            x = next((a for a in aia if a.get("date") == m["date"]), aia[i] if i < len(aia) else {})
            name = x.get("period") or f"{m['date'][:4]}년 {int(m['date'][5:7])}월"
            line = f"{name}. "
            if x.get("what_happened"):
                line += x["what_happened"] + " "
            line += f"그 뒤 코스피는 3개월 {say_chg(m.get('kospi_13w'))}, 6개월 {say_chg(m.get('kospi_26w'))}했습니다."
            if x.get("lesson"):
                line += " " + x["lesson"]
            parts.append(line)
        t = "지금과 비슷했던 과거 사례를 그래프로 겹쳐 보겠습니다. 검은 선이 지금이고, 색 선이 과거입니다. " + " ".join(parts)
        S.append(Scene("지금과 비슷했던 과거 사례", "① 과거 대비", _cap(t, SHORT_CAP["analog"]), one("analog_ch")))

    t = sc_.get("macro") or ("매크로 환경입니다. " + " ".join(f"{r['label']}는 {r['value']}." for r in (M.get("regimes") or [])))
    S.append(Scene("매크로·환율·금리", "② 매크로", _cap(t, SHORT_CAP["macro"]), one("regimes", "macro_ai")))

    ch = [c for c in (V.get("chains") or []) if isinstance(c, dict) and c.get("from")] if not RB else []
    if ch and shots.get("chains"):
        nums = ["첫째", "둘째", "셋째", "넷째", "다섯째"]
        parts = []
        for i, c in enumerate(ch[:5]):
            steps = ", 그러면 ".join(s for s in (c.get("steps") or []) if s)
            parts.append(f"{nums[i]}, {c['from']}." + (f" 그러면 {steps}." if steps else "") + f" 결국 {c.get('so', '')}." +
                         (f" 지금은 {c['now']}." if c.get("now") else ""))
        S.append(Scene("오늘 시장의 연결고리", "③ 당일 예측", _cap("오늘 시장이 왜 이렇게 움직이는지, 연결고리로 보겠습니다. " + " ".join(parts),
                                                       SHORT_CAP["chains"]), one("chains")))

    if sc_.get("social_forecast"):
        t = sc_["social_forecast"]
    else:
        q = M.get("quant") or {}
        t = (f"{fc.get('market', '지수')} 예상입니다. {q.get('driver', '')} 기준으로 범위는 "
             f"{fc.get('band_low', 0):,.0f}에서 {fc.get('band_high', 0):,.0f}입니다.") if fc.get("band_low") else "오늘 시장 예상입니다."
    S.append(Scene(("오늘 국내 증시 예상" if job.slot == "am" else "오늘 밤 미국 증시 예상"), "③ 당일 예측",
                   _cap(t, SHORT_CAP["fc"]), one("fc")))

    if sc_.get("sectors"):
        t = sc_["sectors"]
    else:
        by60 = sorted([c for c in cats if c.get("ret_60d") is not None], key=lambda c: -c["ret_60d"])
        t = (f"{len(cats)}개 분야입니다. 최근 60일 강한 분야는 {', '.join(c['name'] for c in by60[:3])}, "
             f"약한 분야는 {', '.join(c['name'] for c in by60[-3:])}입니다.") if by60 else "분야별 흐름입니다."
    S.append(Scene(f"{len(cats)}개 분야 한눈에", "④ 13개 분야", _cap(t, SHORT_CAP["heat"]), one("heat")))

    if sc_.get("opps_risks"):
        t = sc_["opps_risks"]
    else:
        ops, rks = V.get("opportunities") or [], V.get("risks") or []
        t = ("기회는 " + ", ".join(o["title"] for o in ops[:3]) + ". 리스크는 " + ", ".join(r["title"] for r in rks[:3]) + "입니다.") \
            if ops or rks else "과열 종목과 고평가 위험 목록을 함께 확인하세요."
    S.append(Scene("기회 & 리스크", "⑤ 기회·리스크", _cap(t, SHORT_CAP["or"]), one("or")))

    if sc_.get("conclusion"):
        t = sc_["conclusion"]
    else:
        t = (f"종합하면 {st.get('label', '중립')}입니다. 국내 주식 {al.get('kr_equity', 0)}%, 미국 주식 {al.get('us_equity', 0)}%, "
             f"금과 원자재 {al.get('gold_commodities', 0)}%, 달러 {al.get('usd_cash', 0)}%, 원화 현금과 채권 {al.get('krw_cash_bonds', 0)}%입니다.")
    S.append(Scene("종합 투자 전략", "⑥ 종합 총론", _cap(t, SHORT_CAP["conc"]), one("conc")))

    S.append(Scene("오늘 브리핑은 여기까지입니다", "마무리", center=True,
                   narration="자세한 분석은 설명란의 리포트와 PDF에서 확인하세요. 이 영상은 투자 권유가 아닌 정보 제공 목적입니다."))
    job.scenes = [s for s in S if s.narration.strip()]


# ───────────────────────────── 장면 구성: 전체판 (--full) ─────────────────────────────
def plan_scenes(job: Job, shots: dict[str, list[str]], ticker_details: bool = False) -> None:
    d = job.data
    V = d.get("view") or {}
    RB = bool(V.get("rule_based"))
    sc_ = {} if RB else (V.get("script") or {})
    M = d.get("macro") or {}
    A = {a["key"]: a for a in M.get("assets", []) if "error" not in a}
    SC = d.get("screens") or {}
    cats = SC.get("categories") or []
    res = {c: r for c, r in d["results"].items() if "error" not in r}
    md = f"{int(job.date[5:7])}월 {int(job.date[8:10])}일"
    sname = SLOT_NAME.get(job.slot, "시장 브리핑")
    st, fc, al = V.get("stance") or {}, V.get("forecast") or {}, V.get("allocation") or {}
    S: list[Scene] = []
    one = lambda k: (shots.get(k) or [])[:1]  # noqa: E731

    # 오프닝
    intro = sc_.get("intro") or (
        f"{md} {sname}입니다. " + ("밤사이 마감된 미국 시장과 금리, 환율, 원자재 흐름을 바탕으로 오늘 국내 증시를 점검합니다."
                                   if job.slot == "am" else "오늘 국내 증시를 되짚고, 오늘 밤 미국 증시와 글로벌 매크로 이슈를 점검합니다."))
    S.append(Scene(V.get("headline") or f"{md} {sname}", "오프닝", intro, center=True))

    # 오늘의 결론 요약
    t = f"먼저 결론입니다. 오늘의 투자 자세는 {st.get('label', '중립')}입니다."
    if fc.get("band_low"):
        t += f" {fc.get('market', '지수')} 예상 범위는 {fc['band_low']:,.0f}에서 {fc['band_high']:,.0f}, 방향은 {fc.get('direction', '보합')}으로 봅니다."
    if al:
        eq = (al.get("kr_equity") or 0) + (al.get("us_equity") or 0)
        t += f" 자산 배분은 주식 {eq}%, 금과 원자재 {al.get('gold_commodities', 0)}%, 달러 {al.get('usd_cash', 0)}%를 제안합니다."
    S.append(Scene("오늘의 결론", "오늘의 결론", t, one("sum")))

    # ① 과거 대비
    def hist_auto():
        parts = []
        for k in ("kospi", "spx", "us10y", "usdkrw"):
            a = A.get(k)
            if a:
                parts.append(f"{a['name']}{josa(a['name'])} {say_level(a)}로 1년 전보다 {say_asset_chg(a, 'yoy')}, 5년 범위 중 {a.get('pct_5y', 0):.0f} 백분위입니다.")
        return "작년 이맘때와 비교해 보겠습니다. " + " ".join(parts)
    S.append(Scene("과거 대비 현재 시장 진단", "① 과거 대비 진단", sc_.get("history") or hist_auto(),
                   one("hist_ai") or one("pctl")))
    if shots.get("hist_ai") and shots.get("pctl"):
        hi = sorted(A.values(), key=lambda a: -(a.get("pct_5y") or 0))[:3]
        lo = sorted(A.values(), key=lambda a: (a.get("pct_5y") or 0))[:2]
        S.append(Scene("5년 그래프로 본 지금", "① 과거 대비 진단",
                       "최근 5년 그래프로 보면, 지금 5년 중 가장 높은 쪽에 있는 것은 " + ", ".join(a["name"] for a in hi)
                       + "입니다. 반대로 가장 낮은 쪽에 있는 것은 " + ", ".join(a["name"] for a in lo) + "입니다.",
                       one("pctl")))
    an = (M.get("analogs") or {}).get("matches") or []
    if an and shots.get("analog"):
        m0 = an[0]
        t = (f"데이터로 찾은 가장 비슷한 과거 국면은 {int(m0['date'][:4])}년 {int(m0['date'][5:7])}월입니다. 그 뒤 13주 동안 코스피는 "
             f"{say_chg(m0.get('kospi_13w'))}, 에스앤피 500은 {say_chg(m0.get('spx_13w'))}했습니다.")
        ha = (V.get("history_context") or {}).get("analogs") or []
        if ha and not RB:
            t += f" {ha[0].get('lesson', '')}"
        S.append(Scene("유사 국면", "① 과거 대비 진단", t, one("analog")))

    # ② 매크로
    regs = M.get("regimes") or []
    t = sc_.get("macro") or ("매크로 레짐입니다. " + " ".join(f"{r['label']}는 {r['value']}." for r in regs))
    S.append(Scene("매크로 레짐", "② 매크로·환율·현물", t, one("regimes") or one("macro_ai")))
    groups = shots.get("mgrp") or []
    names = [g for g in dict.fromkeys(a["group"] for a in M.get("assets", []))]
    for i, g in enumerate(names[:len(groups)]):
        items = [a for a in A.values() if a["group"] == g]
        if not items:
            continue
        movers = sorted(items, key=lambda a: -abs(a.get("chg_1m") or 0))[:3]
        t = f"{g} 흐름입니다. " + " ".join(f"{a['name']}{josa(a['name'])} {say_level(a)}, 한 달 {say_asset_chg(a, 'chg_1m')}." for a in movers)
        S.append(Scene(g, "② 매크로·환율·현물", t, groups[i:i + 1]))

    # ③ 사회 흐름·예측
    so = V.get("social") or {}
    kw = [w for w, _ in ((d.get("news") or {}).get("keywords") or {}).get("ko", [])[:6]]
    t = (so.get("summary") if not RB and so.get("summary") else
         f"최근 뉴스에서 가장 많이 나온 키워드는 {', '.join(kw)}입니다." if kw else "뉴스 흐름입니다.")
    S.append(Scene("사회적 흐름", "③ 사회 흐름·당일 예측", t, one("social")))
    if sc_.get("social_forecast"):
        t = sc_["social_forecast"]
    else:
        q = M.get("quant") or {}
        t = (f"{fc.get('market', '지수')} 예상입니다. 정량 기준선으로는 {q.get('driver', '')}, 기대 변화 {say_chg(q.get('expected_pct'))}, "
             f"범위는 {fc.get('band_low', 0):,.0f}에서 {fc.get('band_high', 0):,.0f}입니다.") if fc.get("band_low") else "예측 데이터가 없습니다."
    S.append(Scene(("오늘 국내 증시 예상" if job.slot == "am" else "오늘 밤 미국 증시 예상"), "③ 사회 흐름·당일 예측", t, one("fc")))

    # ④ 13개 분야
    by60 = sorted([c for c in cats if c.get("ret_60d") is not None], key=lambda c: -c["ret_60d"])
    t = sc_.get("sectors") or (
        f"{len(cats)}개 분야 전체를 보겠습니다. 최근 60일 가장 강한 분야는 {', '.join(c['name'] for c in by60[:3])}, "
        f"가장 약한 분야는 {', '.join(c['name'] for c in by60[-2:])}입니다." if by60 else "분야별 동향입니다.")
    S.append(Scene(f"{len(cats)}개 분야 한눈에", "④ 13개 분야", t, one("heat")))
    aisec = {s.get("name"): s for s in (V.get("sectors") or [])}
    cat_shots = shots.get("cats") or []
    for i, c in enumerate(cats):
        s = aisec.get(c["name"], {})
        t = (f"{c['name']}. 판단은 {s.get('stance', '중립')}. 20일 {say_chg(c.get('ret_20d'))}, 60일 {say_chg(c.get('ret_60d'))}, "
             f"시장 대비 {say_chg(c.get('rs_60d'), '퍼센트포인트')}.")
        if not RB and s.get("why"):
            t += " " + s["why"]
            if s.get("vs_past"):
                t += " " + s["vs_past"]
        else:
            t += f" 자금 흐름은 {c.get('flow') or '중립'}, 20일선 위 종목은 {c.get('breadth', 0)}%입니다."
        S.append(Scene(c["name"], "④ 13개 분야", t, cat_shots[i:i + 1]))
    titles = {"value": "저평가 후보", "growth": "성장 기대 후보", "overvalued": "고평가 위험"}
    box_shots = shots.get("boxes") or []
    for k, (key, title) in enumerate(titles.items()):
        lst = SC.get(key) or []
        if not lst or k >= len(box_shots):
            continue
        t = f"{title}{josa(title)} {', '.join(r['name'] for r in lst)}입니다."
        if key == "overvalued":
            t += " 밸류에이션 부담이 큰 종목들이라 주의가 필요합니다."
        S.append(Scene(title, "④ 13개 분야", t, box_shots[k:k + 1]))
    over = [r["name"] for r in res.values() if (r.get("rsi") or 50) < 30]
    hot = [r["name"] for r in res.values() if (r.get("rsi") or 50) > 70]
    t = "관심 종목 온도계입니다. 추세 점수 기준 " + ", ".join(
        f"{k} {v}개" for k, v in sorted({r["label"]: sum(1 for x in res.values() if x["label"] == r["label"]) for r in res.values()}.items())) + "입니다."
    if over:
        t += f" 과매도권은 {', '.join(over)}."
    if hot:
        t += f" 과열권은 {', '.join(hot)}."
    S.append(Scene("관심 종목 점검", "④ 13개 분야", t, one("thermo")))
    if ticker_details:
        cards, items = shots.get("cards") or [], list(res.values())
        for i in range(0, len(items), 2):
            pair = items[i:i + 2]
            S.append(Scene(" · ".join(r["name"] for r in pair), "④ 13개 분야",
                           " ".join(f"{r['name']}{josa(r['name'])} 하루 {say_chg(r.get('chg_1d'))}, 판정 {r['label']}." for r in pair),
                           cards[i:i + 2]))

    # ⑤ 기회·리스크
    if sc_.get("opps_risks"):
        t = sc_["opps_risks"]
    else:
        ops, rks = V.get("opportunities") or [], V.get("risks") or []
        t = ("기회 요인은 " + ", ".join(o["title"] for o in ops) + ". 리스크는 " + ", ".join(r["title"] for r in rks) + "입니다.") \
            if ops or rks else "지표상 기회와 리스크를 정리했습니다. 과열 종목과 고평가 위험 목록을 확인하세요."
    S.append(Scene("핵심 기회 & 조심할 리스크", "⑤ 기회 & 리스크", t, one("or")))

    # ⑥ 총론
    if sc_.get("conclusion"):
        t = sc_["conclusion"]
    else:
        t = (f"종합 결론입니다. 정량 모델의 판단은 {st.get('label', '중립')}입니다. 국내 주식 {al.get('kr_equity', 0)}%, 미국 주식 {al.get('us_equity', 0)}%, "
             f"금과 원자재 {al.get('gold_commodities', 0)}%, 달러 현금성 {al.get('usd_cash', 0)}%, 원화 현금과 채권 {al.get('krw_cash_bonds', 0)}%, "
             f"대체자산 {al.get('alternatives', 0)}%입니다.")
    S.append(Scene("종합 투자 전략 및 총론", "⑥ 종합 총론", t, one("conc")))
    plan = V.get("action_plan") or []
    if plan and shots.get("plan"):
        S.append(Scene("오늘의 액션 플랜", "⑥ 종합 총론",
                       "오늘의 액션 플랜입니다. " + " ".join(f"{i + 1}번, {p}" for i, p in enumerate(plan)), one("plan")))

    S.append(Scene("오늘 브리핑은 여기까지입니다", "마무리", center=True,
                   narration=f"{sname}는 여기까지입니다. 전체 리포트와 PDF는 설명란 링크에서 확인하실 수 있습니다. "
                             "이 영상은 투자 권유가 아닌 정보 제공 목적이며, 투자 판단과 책임은 본인에게 있습니다."))
    job.scenes = [s for s in S if s.narration.strip()]


# ───────────────────────────── 브라우저 작업 ─────────────────────────────
CLEAN_JS = """() => { document.querySelectorAll('.nav').forEach(n => n.remove()); }"""


def open_report(browser, path: Path, dpr: int = 2):
    ctx = browser.new_context(viewport={"width": 1240, "height": 900}, device_scale_factor=dpr,
                              color_scheme="light")
    page = ctx.new_page()
    local_chart = os.environ.get("CHARTJS_PATH")       # 오프라인 시험용
    if local_chart:
        page.route(CHART_CDN, lambda r: r.fulfill(path=local_chart, content_type="application/javascript"))
        page.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    page.goto(path.resolve().as_uri(), wait_until="networkidle")
    page.wait_for_timeout(800)
    page.evaluate(CLEAN_JS)
    return ctx, page


SHOTS = {  # 키: (선택자, 여러 개)
    "easy_sum": ("#easy-sum", False), "analog_ch": (".analog > .grid2", False), "chains": ("#chains", False), "gloss": ("h3 + .gloss", False),
    "sum": ("#sum", False), "hist_ai": (".hist-ai", False), "pctl": (".hist-key", False), "analog": (".analog", False),
    "regimes": (".regimes", False), "macro_ai": (".macro-ai", False), "mgrp": (".mgrp", True),
    "social": (".social", False), "fc": (".fc", False), "heat": (".heat", False), "cats": ("section.cat", True),
    "or": (".or", False), "conc": (".conc", False), "plan": (".conc .plan", False),
    "thermo": (".thermo", False), "boxes": (".scr .box", True), "cards": (".card", True),
}


def take_shots(browser, path: Path, work: Path) -> dict[str, list[str]]:
    ctx, page = open_report(browser, path)
    # 영상용: 스크리닝 상자 한 줄에 하나, 총론 표는 넓게
    page.add_style_tag(content=".scr{grid-template-columns:1fr !important;max-width:1000px}")
    shots: dict[str, list[str]] = {}
    for key, (sel, many) in SHOTS.items():
        els = page.query_selector_all(sel) if many else [page.query_selector(sel)]
        out = []
        for i, el in enumerate(e for e in els if e):
            p = work / f"shot_{key}_{i:02d}.png"
            el.scroll_into_view_if_needed()
            el.screenshot(path=str(p))
            out.append(str(p))
        shots[key] = out
    ctx.close()
    return shots


def make_pdf(browser, path: Path, out_pdf: Path, title: str) -> None:
    ctx, page = open_report(browser, path, dpr=1)
    page.emulate_media(media="print", color_scheme="light")
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")   # 용어 풀이 펼치기
    page.add_style_tag(content=(".card,.cat,.box,.tbl,.thermo,.mc,.panel,.regime div,.sum,.easy,.chain,.gloss div,.easysum{break-inside:avoid}"
                                "h2{break-after:avoid} #sec-conclusion{break-before:page}"))
    style = f"font-family:'{FONT}';font-size:8px;color:#7a8494;width:100%;padding:0 12mm;"
    page.pdf(path=str(out_pdf), format="A4", print_background=True, scale=0.62,
             margin={"top": "14mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
             display_header_footer=True,
             header_template=f"<div style=\"{style}text-align:right;\">{html.escape(title)}</div>",
             footer_template=f"<div style=\"{style}text-align:center;\"><span class='pageNumber'></span> / <span class='totalPages'></span></div>")
    ctx.close()


# ───────────────────────────── 슬라이드 ─────────────────────────────
SLIDE_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1920px; height:1080px; }}
body {{ font-family:'{FONT}', sans-serif; background:#F5F7F9; color:#16202A; overflow:hidden; }}
.bar {{ position:absolute; top:0; left:0; right:0; height:96px; background:#16202A; color:#fff;
  display:flex; align-items:center; justify-content:space-between; padding:0 72px; font-size:30px; }}
.bar b {{ font-weight:700; }} .bar span {{ color:#98A4B1; }}
.sec {{ position:absolute; top:122px; left:72px; font-size:28px; color:#0D5C6B; font-weight:700; }}
h1 {{ position:absolute; top:160px; left:72px; right:72px; font-size:60px; font-weight:900;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.shots {{ position:absolute; top:262px; left:72px; right:72px; bottom:178px; display:flex; gap:36px;
  align-items:center; justify-content:center; }}
.shots img {{ width:100%; height:100%; object-fit:contain; border-radius:10px;
  filter:drop-shadow(0 6px 18px rgba(22,32,42,0.12)); }}
.shots.two img {{ width:calc(50% - 18px); }}
.center h1 {{ top:360px; text-align:center; white-space:normal; font-size:76px; line-height:1.25; }}
.center .sub {{ position:absolute; top:610px; left:0; right:0; text-align:center; font-size:36px; color:#5C6875; }}
.foot {{ position:absolute; bottom:22px; left:72px; right:72px; font-size:20px; color:#8793A0; text-align:right; }}
"""


def img_uri(p: str) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def slide_html(job: Job, i: int, sc: Scene) -> str:
    md = f"{int(job.date[5:7])}월 {int(job.date[8:10])}일"
    sname = SLOT_NAME.get(job.slot, "매일 시장 브리핑")
    bar = f"<div class='bar'><div><b>{sname}</b> · {md}</div><span>{i}/{len(job.scenes)}</span></div>"
    foot = f"<div class='foot'>{html.escape(DISCLAIMER)}</div>"
    if sc.center or not sc.images:
        body = (f"{bar}<h1>{html.escape(sc.title)}</h1>"
                f"<div class='sub'>{md} {sname}</div>{foot}")
        cls = "center"
    else:
        sec = "" if sc.section == sc.title else f"<div class='sec'>{html.escape(sc.section)}</div>"
        imgs = "".join(f"<img src='{img_uri(p)}'>" for p in sc.images)
        two = " two" if len(sc.images) > 1 else ""
        body = f"{bar}{sec}<h1>{html.escape(sc.title)}</h1><div class='shots{two}'>{imgs}</div>{foot}"
        cls = ""
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{SLIDE_CSS}</style></head>"
            f"<body class='{cls}'>{body}</body></html>")


def render_slides(job: Job, browser, work: Path) -> list[Path]:
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    out = []
    for i, sc in enumerate(job.scenes, 1):
        page.set_content(slide_html(job, i, sc), wait_until="load")
        p = work / f"slide_{i:02d}.png"
        page.screenshot(path=str(p))
        out.append(p)
    page.close()
    return out


# ───────────────────────────── 유튜브 정보 ─────────────────────────────
def write_meta(job: Job, starts: list[float], out: Path, suffix: str = "") -> None:
    d = job.data
    V = d.get("view") or {}
    m, day = int(job.date[5:7]), int(job.date[8:10])
    when = {"_am": " 모닝", "_pm": " 나이트"}.get(suffix, "")
    st = (V.get("stance") or {}).get("label")
    title = f"[{m}/{day}{when}] {V.get('headline') or '시장 브리핑'}{f' | {st}' if st else ''}"[:100]

    chap, last = [], None
    for s, sc in zip(starts, job.scenes):
        if sc.section != last:
            chap.append(f"{mmss(s)} {sc.section}")
            last = sc.section
    cats = (d.get("screens") or {}).get("categories") or []
    tags = ["주식", "코스피", "나스닥", "S&P500", "시장브리핑", "환율", "금리", "자산배분", "매크로"] + \
           [c["name"].split("·")[0] for c in cats[:6]]
    al = V.get("allocation") or {}
    desc = "\n\n".join([
        f"{m}월 {day}일 {SLOT_NAME.get(job.slot, '시장 브리핑')} — 과거 대비 진단, 매크로·환율·현물, 당일 예측, "
        f"{len(cats)}개 분야, 기회·리스크, 종합 자산 배분을 정리합니다.",
        f"오늘의 자세: {st or '–'} · 주식 {(al.get('kr_equity') or 0) + (al.get('us_equity') or 0)}% / 금·원자재 {al.get('gold_commodities', 0)}% / "
        f"달러 {al.get('usd_cash', 0)}% / 원화 현금·채권 {al.get('krw_cash_bonds', 0)}% / 대체 {al.get('alternatives', 0)}%",
        f"📊 전체 리포트: {PAGES}/report_{job.date}{suffix}.html\n📄 PDF: {PAGES}/pdf/report_{job.date}{suffix}.pdf",
        "⏱ 목차\n" + "\n".join(chap),
        f"※ {DISCLAIMER}",
        "#주식 #코스피 #나스닥 #시장브리핑 #자산배분",
    ])
    (out / "description.txt").write_text(desc, encoding="utf-8")
    (out / "youtube.json").write_text(json.dumps(
        {"date": job.date, "video": f"{job.date}{suffix}.mp4", "title": title,
         "description": desc[:4900], "tags": tags},
        ensure_ascii=False, indent=2), encoding="utf-8")


# ───────────────────────────── 실행 ─────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="YYYY-MM-DD 또는 latest")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--silent", action="store_true", help="음성 대신 무음 (시험용)")
    ap.add_argument("--pdf-only", action="store_true")
    ap.add_argument("--slot", choices=["am", "pm", ""], default="", help="am=모닝, pm=나이트")
    ap.add_argument("--ticker-details", action="store_true", help="관심 종목 상세 차트도 영상에 넣기 (--full 일 때)")
    ap.add_argument("--full", action="store_true", help="전체판 영상(15분 안팎). 기본은 핵심 요약(약 5분)")
    a = ap.parse_args()

    path, date, slot = find_report(a.date, a.slot)
    suffix = f"_{slot}" if slot else ""
    job = Job(date=date, data=load_payload(path), slot=slot)
    out = a.out or Path("out") / date
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    print(f"리포트: {path}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pdf = out / f"report_{date}{suffix}.pdf"
        make_pdf(browser, path, pdf, f"{SLOT_NAME.get(slot, '시장 브리핑')} · {date}")
        print(f"PDF 완료: {pdf}")
        if a.pdf_only:
            browser.close()
            print(f"DATE={date}")
            return
        shots = take_shots(browser, path, work)
        if a.full or os.environ.get("VIDEO_MODE") == "full":
            plan_scenes(job, shots, a.ticker_details or os.environ.get("TICKER_DETAILS") == "true")
        else:
            plan_short(job, shots)
        print(f"영상 화면 {len(job.scenes)}장")
        slides = render_slides(job, browser, work)
        browser.close()

    audio = make_audio(job, work, a.silent)
    srt = work / "subs.srt"
    starts = write_srt(job, audio, srt)
    mp4 = out / f"{date}{suffix}.mp4"
    build_video(slides, audio, srt, mp4, work)
    write_meta(job, starts, out, suffix)
    print(f"영상 완료: {mp4} ({mmss(duration(mp4))})")


if __name__ == "__main__":
    main()
