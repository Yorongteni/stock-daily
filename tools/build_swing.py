#!/usr/bin/env python3
"""미국 단타 연습 PDF + 16:9 영상 (3~5분).

  python tools/build_swing.py --date 2026-11-17 --out out/swing-2026-11-17 [--silent] [--pdf-only]

입력: docs/swing/data/<날짜>.json, docs/swing/swing_<날짜>.html (swing.py 가 만든 것)
출력: swing_<날짜>.pdf, swing_<날짜>.mp4, youtube.json, description.txt
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_slides as vs  # noqa: E402
from build_daily import FONT, build_video, duration, make_audio, mmss, write_srt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAGES = os.environ.get("PAGES_URL", "https://yorongteni.github.io/stock-daily")
DISCLAIMER = "연습용 가상 매매입니다. 투자 권유가 아니며 판단과 책임은 본인에게 있습니다."
vs.SLOT_NAME["swing"] = "미국 단타 연습"


@dataclass
class Scene:
    title: str
    section: str
    narration: str


@dataclass
class Job:
    date: str
    scenes: list


# ───────────────────────── 말하기 도우미 ─────────────────────────
def say_usd(v) -> str:
    return f"{v:,.2f}달러"


def say_won(v: int, signed=False) -> str:
    a = abs(int(v))
    if a >= 10000:
        man, rest = divmod(a, 10000)
        s = f"{man}만 {rest // 1000}천 원" if rest >= 1000 else f"{man}만 원"
    elif a >= 1000:
        s = f"{a // 1000}천 원"
    else:
        s = f"{a}원"
    if signed and v:
        return ("약 " + s + (" 이익" if v > 0 else " 손실"))
    return "약 " + s


def say_time(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    ampm = "밤" if h >= 18 else "새벽" if h < 6 else "오전" if h < 12 else "오후"
    h12 = h - 12 if h > 12 else h
    return f"{ampm} {h12}시" + (f" {m}분" if m else "")


def ga(word: str) -> str:
    return word + ("이" if vs._jong(word[-1]) > 0 else "가")


def card(label, value, note="", kind="") -> str:
    return (f"<div class='rc {kind}'><div class='rl'>{html.escape(label)}</div><div class='rv'>{value}</div>"
            + (f"<div class='re'>{html.escape(note)}</div>" if note else "") + "</div>")


EXTRA_CSS = """<style>
.ord{background:#fff;border:6px solid #16202A;border-radius:24px;overflow:hidden;height:100%;display:flex;flex-direction:column}
.ord .oh{background:#16202A;color:#fff;display:flex;justify-content:space-between;align-items:center;padding:22px 36px}
.ord .on{font-size:50px;font-weight:900}.ord .on span{font-size:36px;color:#C3CCD6}
.ord .oq{font-size:54px;font-weight:900;text-align:right}.ord .oq small{display:block;font-size:28px;color:#C3CCD6;font-weight:500}
.ord .or{display:flex;align-items:center;justify-content:space-between;padding:0 36px;flex:1;border-bottom:2px solid #DDE3E9}
.ord .or span{font-size:36px;font-weight:700}.ord .or b{font-size:62px;font-weight:900}
.ord .or em{font-style:normal;font-size:26px;color:#5C6875;display:block}
.ord .b b{color:#1F5FBF}.ord .t b{color:#1E8E3E}.ord .s b{color:#C5221F}.ord .d b{font-size:40px}
.hd{display:flex;flex-direction:column;gap:22px;height:100%}
.hd .big{font-size:52px;font-weight:900;background:#E6F4EA;border-radius:20px;padding:26px 34px}
.hd .big.r{background:#FCE8E6}
.hd .rsn{font-size:34px;line-height:1.4;color:#3A4652;background:#fff;border-radius:16px;padding:20px 28px}
.ev3{display:flex;flex-direction:column;gap:22px;justify-content:center;height:100%}
.ev3 .e{background:#fff;border-radius:18px;padding:22px 32px;border-left:14px solid #8793A0;font-size:38px;line-height:1.35}
.ev3 .e.good{border-left-color:#1E8E3E}.ev3 .e.risk{border-left-color:#C5221F}.ev3 .e small{display:block;font-size:28px;color:#5C6875}
.up{color:#1E8E3E}.dn{color:#C5221F}
</style>"""


def line_chart(sp: dict, lines: list) -> dict:
    ds = [{"label": "종가", "data": sp["close"], "borderColor": "#16202A", "borderWidth": 5, "pointRadius": 0, "tension": .2},
          {"label": "20일 평균선", "data": sp["ma20"], "borderColor": "#8793A0", "borderDash": [10, 6], "borderWidth": 3, "pointRadius": 0}]
    for lab, v, col in lines:
        if v:
            ds.append({"label": f"{lab} ${v:.2f}", "data": [v] * len(sp["close"]), "borderColor": col, "borderWidth": 4,
                       "pointRadius": 0, "borderDash": [4, 5]})
    return {"type": "line", "data": {"labels": sp["dates"], "datasets": ds},
            "options": {"plugins": {"legend": {"labels": {"font": {"size": 24}, "boxWidth": 26}}},
                        "scales": {"x": {"ticks": {"font": {"size": 22}, "maxTicksLimit": 6}},
                                   "y": {"ticks": {"font": {"size": 24}}}}}}


# ───────────────────────── 슬라이드 ─────────────────────────
def speak(text: str) -> str:
    """화면용 표기 → 읽는 말: $22.26 → 22.26달러, (×2.0) → 2.0배, ($283.66) → 283.66달러"""
    import re
    text = re.sub(r"\(\s*\$([\d,]+(?:\.\d+)?)\s*\)", r" \1달러", text)
    text = re.sub(r"\$([\d,]+(?:\.\d+)?)", r"\1달러", text)
    text = re.sub(r"\(\s*×\s*(\d+(?:\.\d+)?)\s*\)", r" 평소의 \1배", text)
    text = re.sub(r"×\s*(\d+(?:\.\d+)?)", r"\1배", text)
    return re.sub(r"\s+", " ", text).strip()


def build(d: dict) -> list:
    S = []
    sess, rec = d["session"], d["record"]
    m, day = int(d["date"][5:7]), int(d["date"][8:10])
    picks, holds = d["picks"], d["holdings"]
    open_say = say_time(sess["open_kst"])
    sub = (f"{m}월 {day}일 18시 · 미국장 {sess['open_kst']} 개장 · 50만 원 연습" if sess["trading"]
           else f"{m}월 {day}일 18시 · 오늘 밤 미국 증시 휴장")
    intro = (f"안녕하세요, {m}월 {day}일 오후 6시, 미국 주식 실전 단타 연습 브리핑입니다. "
             + (f"오늘 밤 미국 증시는 한국 시간 {open_say}에 열립니다. " if sess["trading"] else "오늘 밤 미국 증시는 쉬는 날입니다. ")
             + "어제 산 종목 성적표, 오늘 밤 타점, 바로 입력할 예약 주문표, 누적 성적 순서로 보겠습니다.")
    S.append(vs.Slide("오프닝", "오늘 밤 미국 단타 작전", intro, [sub], ("info", "연습용 가상 매매"), center=True))

    # Part 1. 성적표
    evs = [e for e in d["events"] if e["type"] in ("fill", "missed", "close")]
    rows, says = [], []
    for e in evs[:4]:
        nm = e.get("name") or e["ticker"]
        if e["type"] == "fill" and not any(x["type"] == "close" and x["ticker"] == e["ticker"] for x in evs):
            rows.append(f"<div class='e good'>✅ <b>{html.escape(nm)}</b> {e['qty']}주 체결 @ ${e['price']:.2f}<small>예약가까지 내려와 사졌어요</small></div>")
            says.append(f"{nm}{'은' if vs._jong(nm[-1]) else '는'} 예약가 {say_usd(e['price'])}에 {e['qty']}주가 체결됐습니다.")
        elif e["type"] == "missed":
            rows.append(f"<div class='e'>⏸ <b>{html.escape(nm)}</b> 미체결 취소<small>장중 최저 ${e['low']:.2f} · 예약가 ${e['limit']:.2f}</small></div>")
            says.append(f"{nm}{'은' if vs._jong(nm[-1]) else '는'} 예약가까지 내려오지 않아 체결되지 않았습니다. 손실도 이익도 없습니다.")
        elif e["type"] == "close":
            k = "good" if e["pnl_krw"] > 0 else "risk" if e["pnl_krw"] < 0 else ""
            ico = {"WIN": "🎯", "STOP": "🛑"}.get(e["result"], "↩")
            c = "up" if e["pnl_krw"] > 0 else "dn" if e["pnl_krw"] < 0 else ""
            rows.append(f"<div class='e {k}'>{ico} <b>{html.escape(nm)}</b> {html.escape(e['result_ko'])} "
                        f"<b class='{c}'>{e['ret_pct']:+.2f}% · {e['pnl_krw']:+,}원</b><small>${e['entry']:.2f} → ${e['exit']:.2f} × {e['qty']}주</small></div>")
            move = f"{abs(e['ret_pct']):.1f}% {'수익' if e['ret_pct'] > 0 else '손실'}"
            says.append(f"{nm}{'은' if vs._jong(nm[-1]) else '는'} {e['result_ko']}로 마무리했습니다. {say_usd(e['entry'])}에 사서 "
                        f"{say_usd(e['exit'])}에 팔아 {move}, {say_won(e['pnl_krw'], True)}입니다.")
    if rows:
        wins = sum(1 for e in evs if e["type"] == "close" and e["pnl_krw"] > 0)
        loss = sum(1 for e in evs if e["type"] == "close" and e["pnl_krw"] < 0)
        badge = ("good", "익절") if wins and not loss else ("risk", "손실 정리") if loss and not wins else ("info", "판정 결과")
        S.append(vs.Slide("Part 1 · 어제 산 종목 성적표", "간밤 미국장 성적표", "먼저 간밤 성적표입니다. " + " ".join(says), [],
                          badge, body_html=EXTRA_CSS + f"<div class='ev3'>{''.join(rows)}</div>"))
    else:
        S.append(vs.Slide("Part 1 · 어제 산 종목 성적표", "간밤에 판정할 종목 없음",
                          "먼저 간밤 성적표입니다. 어제는 예약하거나 들고 있던 종목이 없어서 판정할 결과가 없습니다.",
                          ["어제는 예약·보유 종목이 없었어요", "오늘 밤 신규 타점부터 보겠습니다"], ("info", "판정 없음")))

    for h in holds[:3]:
        pl = h.get("plan") or {}
        nm = h.get("name") or h["ticker"]
        ret = h["ret_pct"]
        k = "good" if ret > 0 else "risk" if ret < -2 else "wait"
        if pl.get("mode") == "open":
            big, act_say = "오늘 밤 시초가에 전량 매도", "오늘 밤 장이 열리자마자 시초가에 전량 매도하세요."
        elif pl.get("price"):
            big = f"오늘 밤 ${pl['price']:.2f} 예약 매도"
            act_say = f"오늘 밤 {say_usd(pl['price'])}에 예약 매도를 걸어 두세요."
        else:
            big, act_say = pl.get("action", ""), pl.get("action", "")
        if pl.get("extend"):
            act_say = f"예외적으로 하루 더 들고 갑니다. 목표가 {say_usd(h['target'])} 매도는 그대로 두고, 손절가를 본전인 {say_usd(h['stop'])}로 올려 두세요."
            big = f"1일 연장 · 손절가 본전 ${h['stop']:.2f}"
        loc = " 그 가격에 안 닿으면 장 마감 직전에 전량 정리합니다." if "LOC" in (pl.get("action") or "") else ""
        c = "up" if ret > 0 else "dn"
        body = (EXTRA_CSS + "<div class='hd'><div class='cards3' style='height:230px'>"
                + card("매수가 × 수량", f"${h['entry']:.2f} × {h['qty']}주")
                + card("어제 종가", f"${h['now']:.2f}", f"고가 ${(h.get('last') or {}).get('high', 0):.2f}")
                + card("지금 손익", f"<span class='{c}'>{ret:+.2f}%</span>", f"{h['pnl_krw']:+,}원", k)
                + f"</div><div class='big {'r' if k == 'risk' else ''}'>👉 {html.escape(big)}</div>"
                f"<div class='rsn'>{html.escape(vs.first(pl.get('reason', '')))}</div></div>")
        narr = (f"{nm}{'은' if vs._jong(nm[-1]) else '는'} {say_usd(h['entry'])}에 {h['qty']}주를 들고 있고, 어제 종가는 {say_usd(h['now'])}로 "
                f"{abs(ret):.1f}% {'수익' if ret >= 0 else '손실'} 중입니다. 오늘 밤이 {pl.get('day', 2)}일째입니다. {act_say}{loc} "
                f"이유는 이렇습니다. {pl.get('reason', '')}")
        S.append(vs.Slide("Part 1 · 보유 종목 관리 작전", f"{nm} ({h['ticker']}) 오늘 밤 대응", narr, [],
                          (k, "수익 중" if ret > 0 else "물림 관리"), body_html=body))

    # Part 2 · 3
    if picks:
        for i, p in enumerate(picks):
            o, nm = p["order"], p["name"]
            kind = "눌림목 반등형" if p["kind"] == "pullback" else "모멘텀 돌파형"
            lines = [vs.first(s) for s in p["story"]]
            narr = (f"오늘 밤 {'첫 번째' if i == 0 else '두 번째'} 타점은 {nm}, {kind}입니다. " + " ".join(p["story"][:3]))
            narr = narr.replace("“", "").replace("”", "")
            S.append(vs.Slide("Part 2 · 오늘 밤의 50만 원 타점", f"{i + 1}. {nm} ({p['ticker']}) · {kind}", narr,
                              [x.split(" 관련 뉴스")[0] for x in lines], ("good", "+5% 노림"),
                              chart=line_chart(p["spark"], [("예약 매수", o["limit"], "#1F5FBF"), ("목표", o["target"], "#1E8E3E"),
                                                            ("손절", o["stop"], "#C5221F")])))
        for p in picks:
            o, nm = p["order"], p["name"]
            body = (EXTRA_CSS + f"<div class='ord'><div class='oh'><div class='on'>{html.escape(nm)} <span>({p['ticker']})</span></div>"
                    f"<div class='oq'>{o['qty']}주<small>약 ${o['cost_usd']:,.0f} · {o['cost_krw']:,}원</small></div></div>"
                    f"<div class='or b'><span>① 예약 매수 지정가<em>전일 종가 대비 -{o['dip_pct']}%</em></span><b>${o['limit']:.2f}</b></div>"
                    f"<div class='or t'><span>② 목표 익절가 (+5.0%)<em>체결 즉시 자동 매도 걸기</em></span><b>${o['target']:.2f}</b></div>"
                    f"<div class='or s'><span>③ 손절·비상 탈출가 (-3.5%)<em>감시(스톱) 주문</em></span><b>${o['stop']:.2f}</b></div>"
                    f"<div class='or d'><span>④ 최대 보유 기한</span><b>{html.escape(o['deadline'].split(' (')[0])}</b></div></div>")
            narr = (f"{nm} 예약 주문표입니다. 수량은 {o['qty']}주, 예상 금액은 {say_won(o['cost_krw'])}입니다. "
                    f"첫째, 예약 매수 지정가는 {say_usd(o['limit'])}입니다. 둘째, 체결되면 바로 목표 익절가 {say_usd(o['target'])}에 매도를 걸어 두세요. "
                    f"셋째, 손절 기준가는 {say_usd(o['stop'])}입니다. 이 가격 아래로 밀리면 미련 없이 정리합니다. "
                    f"넷째, 최대 보유 기한은 내일 밤 미국장 마감까지입니다. 그때까지 목표가에 안 닿으면 장 마감에 정리합니다.")
            S.append(vs.Slide("Part 3 · 예약 주문표", "증권사 앱에 이대로 입력하세요", narr, [], ("info", f"{o['qty']}주 · 50만 원 이내"), body_html=body))
    else:
        near = d.get("near") or []
        lines = [d["block"]] + ([f"아깝게 빠진 후보: {', '.join(n['name'] for n in near)}"] if near else [])
        q, weather = d.get("qqq") or {}, ""
        if q and not q.get("above20"):
            weather = "시장 전체도 약합니다. 나스닥100이 20일 평균선 아래에 있어 오르던 주식도 쉽게 밀리는 구간입니다. "
            lines.append(f"시장 날씨: 나스닥100 20일선 아래" + (f" · VIX {d['vix']:.0f}" if d.get("vix") else ""))
        narr = ("오늘 밤 신규 타점입니다. " + d["block"] + " " + weather + "단타 연습에서 가장 중요한 건 조건이 안 맞는 날 쉬는 겁니다. "
                "보유 종목이 있다면 앞에서 말씀드린 매도 주문만 확인하세요.")
        S.append(vs.Slide("Part 2 · 오늘 밤의 50만 원 타점", "오늘 밤은 신규 매수 쉬어 갑니다", narr, lines[:3], ("wait", "관망")))

    # Part 4
    wr = f"{rec['winrate']:.0f}%" if rec["winrate"] is not None else "–"
    c = "up" if rec["pnl_krw"] > 0 else "dn" if rec["pnl_krw"] < 0 else ""
    if rec["trades"]:
        narr = (f"마지막으로 누적 성적입니다. {rec['since'][5:7].lstrip('0')}월 {rec['since'][8:].lstrip('0')}일부터 지금까지 {rec['trades']}번 매매해 "
                f"{rec['wins']}번 이겼습니다. 승률은 {wr}, 누적 가상 손익은 {say_won(rec['pnl_krw'], True)}입니다. "
                f"목표가 5%를 채운 건 {rec['targets']}번입니다. 이기는 날보다 지는 날을 짧게 끊는 연습이 핵심입니다.")
        chart = {"type": "line", "data": {"labels": [x["date"][5:] for x in rec["curve"]],
                                          "datasets": [{"label": "누적 손익(원)", "data": [x["cum_krw"] for x in rec["curve"]],
                                                        "borderColor": "#0D5C6B", "backgroundColor": "rgba(13,92,107,.15)", "fill": True,
                                                        "borderWidth": 5, "pointRadius": 5}]},
                 "options": {"plugins": {"legend": {"display": False}},
                             "scales": {"x": {"ticks": {"font": {"size": 22}}}, "y": {"ticks": {"font": {"size": 24}}}}}}
        S.append(vs.Slide("Part 4 · 누적 실전 연습 트랙레코드", "누적 연습 성적", narr,
                          [f"총 {rec['trades']}회 · 승률 {wr}", f"누적 {rec['pnl_krw']:+,}원", f"목표가 달성 {rec['targets']}회 · 평균 {rec['avg_ret']:+.2f}%"],
                          ("good" if rec["pnl_krw"] > 0 else "risk" if rec["pnl_krw"] < 0 else "info", f"승률 {wr}"), chart=chart))
    else:
        S.append(vs.Slide("Part 4 · 누적 실전 연습 트랙레코드", "누적 연습 성적",
                          "마지막으로 누적 성적입니다. 아직 끝난 매매가 없습니다. 첫 매매가 끝나면 매매 횟수, 승률, 누적 손익을 여기서 보여드리겠습니다.",
                          ["아직 끝난 매매가 없어요", f"시작일 {rec['since']}"], ("info", "기록 시작")))

    S.append(vs.Slide("마무리", "오늘 밤 작전은 여기까지입니다",
                      "실제로 다른 가격에 샀거나 팔았다면, 스마트폰 깃허브 앱의 보유 종목 수동 입력에서 고쳐 주세요. "
                      "다음 브리핑부터 내 실제 평단가로 작전을 짭니다. 연습용 가상 매매이며 투자 권유가 아닙니다. 감사합니다.",
                      ["다르게 샀다면: GitHub 앱 → Actions → 보유 종목 수동 입력"], ("info", "내일 18시에 만나요"), center=True))
    for s in S:
        s.narration = speak(s.narration)
    return S


def make_pdf(browser, html_path: Path, out_pdf: Path, title: str) -> None:
    page = browser.new_page(viewport={"width": 1100, "height": 1400})
    page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
    page.wait_for_timeout(800)
    page.emulate_media(media="print")
    style = f"font-family:'{FONT}';font-size:8px;color:#7a8494;width:100%;padding:0 12mm;"
    page.pdf(path=str(out_pdf), format="A4", print_background=True, scale=0.72,
             margin={"top": "14mm", "bottom": "14mm", "left": "8mm", "right": "8mm"}, display_header_footer=True,
             header_template=f"<div style=\"{style}text-align:right;\">{html.escape(title)}</div>",
             footer_template=f"<div style=\"{style}text-align:center;\"><span class='pageNumber'></span> / <span class='totalPages'></span></div>")
    page.close()


def write_meta(d: dict, job: Job, starts: list, out: Path) -> None:
    m, day = int(d["date"][5:7]), int(d["date"][8:10])
    picks = d["picks"]
    what = " · ".join(f"{p['name']} {p['order']['qty']}주" for p in picks) or "신규 쉬어가기"
    title = f"[{m}/{day} 18시] 미국 단타 연습 | {what}"[:100]
    chap, last = [], None
    for s, sc in zip(starts, job.scenes):
        sec = sc.section.split(" · ")[0]
        if sec != last:
            chap.append(f"{mmss(s)} {sc.section}")
            last = sec
    rec = d["record"]
    desc = "\n\n".join([
        f"{m}월 {day}일 18시 미국 주식 실전 단타 연습 — 보유 종목 성적표·탈출 작전, 오늘 밤 50만 원 타점, 예약 주문표, 누적 성적.",
        f"누적: {rec['trades']}회 · 승률 {rec['winrate'] if rec['winrate'] is not None else '–'}% · {rec['pnl_krw']:+,}원",
        f"📊 리포트: {PAGES}/swing/swing_{d['date']}.html\n📄 PDF: {PAGES}/swing/pdf/swing_{d['date']}.pdf",
        "⏱ 목차\n" + "\n".join(chap),
        f"※ {DISCLAIMER}", "#미국주식 #단타 #스윙 #주식공부",
    ])
    (out / "description.txt").write_text(desc, encoding="utf-8")
    (out / "youtube.json").write_text(json.dumps({"date": d["date"], "video": f"swing_{d['date']}.mp4", "title": title,
                                                  "description": desc[:4900], "tags": ["미국주식", "단타", "스윙매매", "주식공부", "예약주문"]},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--docs", type=Path, default=ROOT / "docs")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--silent", action="store_true")
    ap.add_argument("--pdf-only", action="store_true")
    a = ap.parse_args()
    d = json.loads((a.docs / "swing" / "data" / f"{a.date}.json").read_text(encoding="utf-8"))
    out = a.out or ROOT / "out" / f"swing-{a.date}"
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pdf = out / f"swing_{a.date}.pdf"
        make_pdf(browser, a.docs / "swing" / f"swing_{a.date}.html", pdf, f"미국 단타 연습 · {a.date}")
        print(f"PDF 완료: {pdf}")
        if a.pdf_only:
            browser.close()
            return
        slides = build(d)
        job = Job(a.date, [Scene(s.title, s.section, s.narration) for s in slides])
        pngs = vs.render(slides, browser, work, a.date, "swing", FONT, DISCLAIMER)
        browser.close()
    print(f"영상 화면 {len(pngs)}장")
    audio = make_audio(job, work, a.silent)
    srt = work / "subs.srt"
    starts = write_srt(job, audio, srt)
    mp4 = out / f"swing_{a.date}.mp4"
    build_video(pngs, audio, srt, mp4, work)
    write_meta(d, job, starts, out)
    print(f"영상 완료: {mp4} ({mmss(duration(mp4))})")


if __name__ == "__main__":
    main()
