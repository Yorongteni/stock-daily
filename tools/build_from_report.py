#!/usr/bin/env python3
"""
stock-daily 프로그램이 매일 만드는 리포트(docs/report_YYYY-MM-DD.html)를 그대로 사용해
PDF와 유튜브 영상을 만든다. Claude 채팅 답변은 필요 없다.

  out/<날짜>/report_<날짜>.pdf   리포트 화면 그대로 PDF
  out/<날짜>/<날짜>.mp4          리포트 각 부분을 화면으로, 수치를 읽어주는 영상
  out/<날짜>/youtube.json        업로드용 제목·설명·태그
  out/<날짜>/description.txt     설명란 (챕터 시간 포함)

사용법:
  python tools/build_from_report.py --date 2026-10-18
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
    scenes: list[Scene] = field(default_factory=list)


# ───────────────────────────── 리포트 읽기 ─────────────────────────────
def find_report(date: str) -> Path:
    if date == "latest":
        files = sorted(DOCS.glob("report_????-??-??.html"))
        if not files:
            sys.exit("docs 폴더에 report_YYYY-MM-DD.html 이 없습니다.")
        return files[-1]
    p = DOCS / f"report_{date}.html"
    if not p.exists():
        sys.exit(f"리포트가 없습니다: {p}")
    return p


def load_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\s*\nconst esc", text, flags=re.S)
    if not m:
        sys.exit("리포트에서 데이터(DATA)를 찾지 못했습니다. report.py 형식이 바뀌었는지 확인하세요.")
    return json.loads(m.group(1))


# ───────────────────────────── 말하기 도우미 ─────────────────────────────
def say_chg(v) -> str:
    if v is None:
        return "변동 정보 없음"
    if abs(v) < 0.05:
        return "보합"
    from decimal import ROUND_HALF_UP, Decimal
    a = Decimal(str(abs(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{a}퍼센트 {'상승' if v > 0 else '하락'}"


def say_score(s: int) -> str:
    return f"{'플러스 ' if s > 0 else '마이너스 ' if s < 0 else ''}{abs(s)}점"


def say_num(v) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def josa(word: str, pair=("은", "는")) -> str:
    """받침 유무로 은/는, 이/가 고르기 (한글 끝 글자만 판별)."""
    ch = word.strip()[-1:] if word.strip() else ""
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[1]


# ───────────────────────────── 장면 구성 ─────────────────────────────
def plan_scenes(job: Job, shots: dict[str, list[str]]) -> None:
    d = job.data
    ai = d.get("ai") or {}
    res = {c: r for c, r in d["results"].items() if "error" not in r}
    sc = d.get("screens") or {}
    cats = sc.get("categories") or []
    md = f"{int(job.date[5:7])}월 {int(job.date[8:10])}일"
    S: list[Scene] = []

    S.append(Scene(
        title=ai.get("headline") or f"{md} 시장 일일 리포트", section="인트로", center=True,
        narration=f"매일 시장 브리핑입니다. {md} 리포트를 순서대로 보겠습니다. "
                  f"관심 종목 {len(res)}개의 지표와"
                  + (f" {sc.get('universe_size')}개 종목의 분야별 동향, 스크리닝 결과를 정리했습니다."
                     if sc.get("universe_size") else " 주요 흐름을 정리했습니다.")))

    # 시장 온도계
    parts = []
    for mk, label in (("kr", "국내는"), ("us", "미국은")):
        idx = [r for c, r in res.items() if r["market"] == mk and c in ("KS11", "KQ11", "US500", "IXIC", "DJI")]
        if idx:
            parts.append(f"{label} " + ", ".join(f"{r['name']} {say_chg(r['chg_1d'])}" for r in idx) + ".")
    labels = {}
    for r in res.values():
        labels[r["label"]] = labels.get(r["label"], 0) + 1
    parts.append("추세 판정은 " + ", ".join(f"{k} {v}개" for k, v in labels.items()) + "입니다.")
    movers = sorted(res.values(), key=lambda r: r.get("chg_1d") or 0)
    if len(movers) >= 2:
        parts.append(f"하루 기준으로 가장 많이 오른 종목은 {movers[-1]['name']}, "
                     f"가장 부진한 종목은 {movers[0]['name']}입니다.")
    S.append(Scene("시장 온도계", "시장 온도계", " ".join(parts), shots.get("thermo", [])))

    # AI 해설 (API 를 켠 날만)
    if ai.get("market_overview"):
        s = ai.get("scenarios") or {}
        S.append(Scene("AI 시장 해설", "AI 시장 해설",
                       f"{ai['market_overview']} 강세 시나리오는 {s.get('bull', '')} "
                       f"기본 시나리오는 {s.get('base', '')} 약세 시나리오는 {s.get('bear', '')}",
                       shots.get("ai", [])))

    # 분야별 동향
    if cats:
        by20 = sorted([c for c in cats if c.get("ret_20d") is not None], key=lambda c: c["ret_20d"])
        up = sum(1 for c in by20 if c["ret_20d"] > 0)
        txt = (f"분야별 동향입니다. {len(cats)}개 분야 중 최근 20일 동안 오른 분야는 {up}개입니다. "
               f"가장 강한 분야는 {by20[-1]['name']}, 그다음은 {by20[-2]['name']}이고, "
               f"가장 약한 분야는 {by20[0]['name']}, 그다음은 {by20[1]['name']}입니다.") if len(by20) >= 2 else "분야별 동향입니다."
        S.append(Scene("분야별 동향", "분야별 동향", txt, shots.get("bars", [])))
        aicat = ai.get("categories") or {}
        cat_shots = shots.get("cats", [])
        for i, c in enumerate(cats):
            t = (f"{c['name']}. 최근 20일 {say_chg(c.get('ret_20d'))}, 5일 {say_chg(c.get('ret_5d'))}. "
                 f"20일선 위 종목은 {c.get('breadth', 0)}퍼센트입니다.")
            if c.get("best"):
                t += f" 5일 기준 강세는 {c['best'][0]}"
                t += f", 약세는 {c['worst'][0]}입니다." if c.get("worst") else "입니다."
            if c.get("value_pick"):
                t += f" 저평가 후보는 {c['value_pick'][0]}."
            if aicat.get(c["name"]):
                t += " " + aicat[c["name"]]
            S.append(Scene(c["name"], "분야별 동향", t, cat_shots[i:i + 1]))

    # 스크리닝
    titles = {"value": "저평가 후보", "growth": "성장 기대 후보", "overvalued": "고평가 위험"}
    prev = d.get("prev_lists") or {}
    box_shots = shots.get("boxes", [])
    for k, (key, title) in enumerate(titles.items()):
        lst = sc.get(key) or []
        if not lst:
            continue
        names = [r["name"] for r in lst]
        t = f"{title}{josa(title, ('은', '는'))} {', '.join(names)}입니다."
        new = [r["name"] for r in lst if prev and r["ticker"] not in (prev.get(key) or [])]
        if new:
            t += f" 이 중 {', '.join(new)}{josa(new[-1], ('이', '가'))} 새로 들어왔습니다."
        if lst[0].get("reason"):
            t += f" 첫 번째 {lst[0]['name']}{josa(lst[0]['name'])} {lst[0]['reason']}."
        if key == "overvalued":
            t += " 밸류에이션 부담이 큰 종목들이라 검토 시 주의가 필요합니다."
        S.append(Scene(title, "종목 스크리닝", t, box_shots[k:k + 1]))
    if ai.get("picks") and len(box_shots) >= 4:
        t = "AI 관심 종목은 " + ", ".join(p["name"] for p in ai["picks"]) + "입니다. 매수 권유가 아닌 검토 후보입니다."
        S.append(Scene("AI 관심 종목", "종목 스크리닝", t, box_shots[3:4]))

    # 종목 요약표
    over = [r["name"] for r in res.values() if r.get("rsi") is not None and r["rsi"] < 30]
    hot = [r["name"] for r in res.values() if r.get("rsi") is not None and r["rsi"] > 70]
    t = "관심 종목 요약표입니다."
    if over:
        t += f" RSI 30 아래 과매도권 종목은 {', '.join(over)}입니다."
    if hot:
        t += f" RSI 70 위 과열권 종목은 {', '.join(hot)}입니다."
    S.append(Scene("종목 요약", "종목 요약", t, shots.get("table", [])))

    # 종목별 상세 (2개씩)
    cards = shots.get("cards", [])
    items = list(res.values())
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        lines = []
        for r in pair:
            sig = ", ".join(s[1] for s in r.get("signals", [])) or "특이 신호는 없습니다"
            cm = (ai.get("tickers") or {}).get(next(c for c, x in res.items() if x is r), "")
            lines.append(f"{r['name']}{josa(r['name'])} 하루 {say_chg(r.get('chg_1d'))}, "
                         f"판정 {r['label']} {say_score(r['score'])}. 신호는 {sig}." + (f" {cm}" if cm else ""))
        S.append(Scene(" · ".join(r["name"] for r in pair), "종목별 상세", " ".join(lines), cards[i:i + 2]))

    S.append(Scene("오늘 브리핑은 여기까지입니다", "마무리", center=True,
                   narration="오늘 브리핑은 여기까지입니다. 전체 리포트와 PDF는 설명란 링크에서 확인하실 수 있습니다. "
                             "이 영상은 투자 권유가 아닌 정보 제공 목적이며, 투자 판단과 책임은 본인에게 있습니다."))
    job.scenes = S


# ───────────────────────────── 브라우저 작업 ─────────────────────────────
CLEAN_JS = """() => {
  // API 없이 만든 날: 'AI 시장 해설' 질문 복사 상자와 빈 AI 관심 종목 상자는 PDF·영상에서 숨김
  const cp = document.getElementById('cpBtn');
  if (cp) { const box = cp.closest('.ai'); const h2 = box && box.previousElementSibling;
            if (h2 && h2.tagName === 'H2') h2.remove(); if (box) box.remove(); }
  document.querySelectorAll('.scr .box').forEach(b => { if (b.querySelector('.empty') && /AI/.test(b.textContent)) b.remove(); });
  document.querySelectorAll('.nav').forEach(n => n.remove());
}"""


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


def take_shots(browser, path: Path, work: Path) -> dict[str, list[str]]:
    ctx, page = open_report(browser, path)
    # 영상용: 스크리닝 상자를 한 줄에 하나씩 넓게 (화면에서 읽기 쉽도록)
    page.add_style_tag(content=".scr{grid-template-columns:1fr !important;max-width:1000px}")
    shots: dict[str, list[str]] = {}

    def grab(key: str, selector: str, many=False):
        els = page.query_selector_all(selector) if many else [page.query_selector(selector)]
        out = []
        for i, el in enumerate(e for e in els if e):
            p = work / f"shot_{key}_{i:02d}.png"
            el.scroll_into_view_if_needed()
            el.screenshot(path=str(p))
            out.append(str(p))
        shots[key] = out

    grab("thermo", ".thermo")
    grab("ai", ".ai")
    grab("bars", ".bars")
    grab("cats", "section.cat", many=True)
    grab("boxes", ".scr .box", many=True)
    grab("table", ".tbl")
    grab("cards", ".card", many=True)
    ctx.close()
    return shots


def make_pdf(browser, path: Path, out_pdf: Path, date: str) -> None:
    ctx, page = open_report(browser, path, dpr=1)
    page.emulate_media(media="print", color_scheme="light")
    page.add_style_tag(content=".card,.cat,.box,.tbl,.thermo{break-inside:avoid}")
    style = f"font-family:'{FONT}';font-size:8px;color:#7a8494;width:100%;padding:0 12mm;"
    page.pdf(path=str(out_pdf), format="A4", print_background=True, scale=0.62,
             margin={"top": "14mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
             display_header_footer=True,
             header_template=f"<div style=\"{style}text-align:right;\">시장 일일 리포트 · {date}</div>",
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
.center h1 {{ top:390px; text-align:center; white-space:normal; font-size:80px; }}
.center .sub {{ position:absolute; top:560px; left:0; right:0; text-align:center; font-size:36px; color:#5C6875; }}
.foot {{ position:absolute; bottom:22px; left:72px; right:72px; font-size:20px; color:#8793A0; text-align:right; }}
"""


def img_uri(p: str) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def slide_html(job: Job, i: int, sc: Scene) -> str:
    md = f"{int(job.date[5:7])}월 {int(job.date[8:10])}일"
    bar = f"<div class='bar'><div><b>매일 시장 브리핑</b> · {md}</div><span>{i}/{len(job.scenes)}</span></div>"
    foot = f"<div class='foot'>{html.escape(DISCLAIMER)}</div>"
    if sc.center or not sc.images:
        body = (f"{bar}<h1>{html.escape(sc.title)}</h1>"
                f"<div class='sub'>{md} 시장 일일 리포트</div>{foot}")
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
def write_meta(job: Job, starts: list[float], out: Path) -> None:
    d = job.data
    res = d["results"]
    m, day = int(job.date[5:7]), int(job.date[8:10])

    def short(code, name):
        r = res.get(code) or {}
        v = r.get("chg_1d")
        return f"{name} {v:+.2f}%" if v is not None else ""
    head = " · ".join(x for x in [short("KS11", "코스피"), short("US500", "S&P500")] if x)
    ai_head = (d.get("ai") or {}).get("headline")
    title = f"[{m}/{day}] {ai_head or head} | 매일 시장 브리핑"[:100]

    chap, last = [], None
    for s, sc in zip(starts, job.scenes):
        if sc.section != last:
            chap.append(f"{mmss(s)} {sc.section}")
            last = sc.section
    cats = (d.get("screens") or {}).get("categories") or []
    tags = ["주식", "코스피", "나스닥", "S&P500", "시장브리핑", "종목스크리닝"] + [c["name"].split("·")[0] for c in cats[:6]]
    desc = "\n\n".join([
        f"{m}월 {day}일 관심 종목 지표, 분야별 동향, 종목 스크리닝을 리포트 순서대로 정리합니다.",
        f"📊 전체 리포트: {PAGES}/report_{job.date}.html\n📄 PDF: {PAGES}/pdf/report_{job.date}.pdf",
        "⏱ 목차\n" + "\n".join(chap),
        f"※ {DISCLAIMER}",
        "#주식 #코스피 #나스닥 #시장브리핑",
    ])
    (out / "description.txt").write_text(desc, encoding="utf-8")
    (out / "youtube.json").write_text(json.dumps(
        {"date": job.date, "title": title, "description": desc[:4900], "tags": tags},
        ensure_ascii=False, indent=2), encoding="utf-8")


# ───────────────────────────── 실행 ─────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="YYYY-MM-DD 또는 latest")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--silent", action="store_true", help="음성 대신 무음 (시험용)")
    ap.add_argument("--pdf-only", action="store_true")
    a = ap.parse_args()

    path = find_report(a.date)
    date = path.stem.replace("report_", "")
    job = Job(date=date, data=load_payload(path))
    out = a.out or Path("out") / date
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    print(f"리포트: {path}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pdf = out / f"report_{date}.pdf"
        make_pdf(browser, path, pdf, date)
        print(f"PDF 완료: {pdf}")
        if a.pdf_only:
            browser.close()
            print(f"DATE={date}")
            return
        shots = take_shots(browser, path, work)
        plan_scenes(job, shots)
        print(f"영상 화면 {len(job.scenes)}장")
        slides = render_slides(job, browser, work)
        browser.close()

    audio = make_audio(job, work, a.silent)
    srt = work / "subs.srt"
    starts = write_srt(job, audio, srt)
    mp4 = out / f"{date}.mp4"
    build_video(slides, audio, srt, mp4, work)
    write_meta(job, starts, out)
    print(f"영상 완료: {mp4} ({mmss(duration(mp4))})")


if __name__ == "__main__":
    main()
