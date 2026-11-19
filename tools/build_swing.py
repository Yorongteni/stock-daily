#!/usr/bin/env python3
"""실전 단타 통합 브리핑 PDF + 16:9 영상 (1부 미국 주식 + 2부 바이낸스 3배 선물). 개인 연습용 — 업로드하지 않음.

  python tools/build_swing.py --date 2026-11-17 --out out/swing-2026-11-17 [--silent] [--pdf-only]

입력: docs/swing/data/<날짜>.json, docs/swing/swing_<날짜>.html (swing.py 가 만든 것)
출력: swing_<날짜>.pdf, swing_<날짜>.mp4, description.txt (GitHub 릴리스 설명용)
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
sys.path.insert(0, str(ROOT))
PAGES = os.environ.get("PAGES_URL", "https://yorongteni.github.io/stock-daily")
DISCLAIMER = "개인 연습용 가상 매매입니다. 투자 권유가 아니며 판단과 책임은 본인에게 있습니다."
vs.SLOT_NAME["swing"] = "실전 단타 통합"


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
.tk3{display:flex;flex-direction:column;gap:16px;height:100%}
.tk3 .top{display:flex;justify-content:space-between;align-items:center;background:#16202A;color:#fff;border-radius:20px;padding:16px 30px}
.tk3 .top b{font-size:44px;font-weight:900}.tk3 .top span{font-size:30px;color:#C3CCD6}
.tri3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;flex:1}
.tri3 div{border-radius:22px;border:6px solid #DDE3E9;background:#fff;padding:20px 24px;display:flex;flex-direction:column;justify-content:center}
.tri3 span{font-size:30px;font-weight:800;color:#5C6875}.tri3 b{font-size:64px;font-weight:900;line-height:1.15;margin:6px 0}
.tri3 em{font-style:normal;font-size:30px;font-weight:800;line-height:1.3}.tri3 small{display:block;font-size:24px;font-weight:600;color:#5C6875}
.tri3 .en{border-color:#16202A}.tri3 .tp{border-color:#1E8E3E;background:#F3FAF5}.tri3 .tp b,.tri3 .tp em{color:#1E8E3E}
.tri3 .sl{border-color:#E8710A;background:#FFF6EE}.tri3 .sl b,.tri3 .sl em{color:#E8710A}
.tk3 .tip{background:#EEF4FF;border-radius:16px;padding:14px 26px;font-size:28px;line-height:1.35}.tk3 .tip b{color:#1F5FBF}
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


def fpx(v) -> str:
    from pricefmt import fmt_px
    return fmt_px(v)


def speak_px(text: str) -> str:
    """'목표가 0.1560' 같은 코인 가격 표기를 읽기 쉽게 (숫자는 그대로, 기호만 정리)."""
    return text.replace("TP", "목표가").replace("SL", "손절가")


def coin_rec_say(fu: dict) -> str:
    fr = (fu or {}).get("record") or {}
    if not fr:
        return ""
    if not fr.get("trades"):
        return " 바이낸스 선물도 아직 끝난 매매가 없습니다."
    return (f" 바이낸스 선물은 {fr['trades']}번 매매해 {fr['wins']}번 이겼고, 누적 {abs(fr['pnl_usdt']):,.1f} 테더 "
            f"{'이익' if fr['pnl_usdt'] >= 0 else '손실'}입니다.")


def coin_chart(sp: dict, lines: list) -> dict:
    ds = [{"label": "1시간봉 종가", "data": sp["close"], "borderColor": "#16202A", "borderWidth": 5, "pointRadius": 0, "tension": .15},
          {"label": "20봉 평균선", "data": sp["ema20"], "borderColor": "#8793A0", "borderDash": [10, 6], "borderWidth": 3, "pointRadius": 0}]
    for lab, v, col in lines:
        ds.append({"label": f"{lab} {fpx(v)}", "data": [v] * len(sp["close"]), "borderColor": col, "borderWidth": 4,
                   "pointRadius": 0, "borderDash": [4, 5]})
    return {"type": "line", "data": {"labels": sp["t"], "datasets": ds},
            "options": {"plugins": {"legend": {"labels": {"font": {"size": 24}, "boxWidth": 26}}},
                        "scales": {"x": {"ticks": {"font": {"size": 22}, "maxTicksLimit": 6}}, "y": {"ticks": {"font": {"size": 24}}}}}}


def coin_slides(fu: dict) -> list:
    S = []
    if not fu or fu.get("error"):
        S.append(vs.Slide("2부 · 바이낸스 3배 선물 원픽", "오늘은 코인 데이터를 받지 못했어요",
                          "2부 바이낸스 선물입니다. 오늘은 코인 시세 데이터를 받지 못해 원픽을 건너뜁니다. 보유 포지션이 있다면 처음 정한 목표가와 손절가를 그대로 지켜 주세요.",
                          ["코인 데이터 수신 실패 → 원픽 건너뜀", "보유 포지션은 기존 TP·SL 유지"], ("risk", "데이터 없음")))
        return S
    b, p = fu["bias"], fu.get("pick")
    side_ko = {"LONG": "롱 우위", "SHORT": "숏 우위", "NEUTRAL": "중립"}[b["side"]]
    narr = (f"2부, 바이낸스 3배 레버리지 롱 숏 원픽입니다. 먼저 오늘의 방향은 {side_ko}입니다. " + " ".join(w + "." for w in b["why"])
            + (" 그래서 오늘은 롱 쪽 코인만 봅니다." if b["side"] == "LONG" else " 그래서 오늘은 숏 쪽 코인만 봅니다." if b["side"] == "SHORT"
               else " 방향이 뚜렷하지 않아 롱과 숏 모두 조건을 더 엄격하게 봅니다."))
    S.append(vs.Slide("2부 · 바이낸스 3배 선물 원픽", f"오늘의 방향: {b['label']}", narr,
                      b["why"] + [f"데이터: {fu['source_label'].split(' (')[0]} · {fu['data_time']} 기준"],
                      ("good" if b["side"] == "LONG" else "risk" if b["side"] == "SHORT" else "wait", side_ko)))
    if not p:
        near = fu.get("near") or []
        S.append(vs.Slide("2부 · 바이낸스 3배 선물 원픽", "오늘 코인은 쉬어 갑니다",
                          "오늘의 코인 원픽입니다. " + fu["block"] + " 레버리지 거래에서는 조건이 안 맞는 날 들어가지 않는 것이 가장 큰 수익입니다.",
                          [fu["block"]] + ([f"아깝게 빠진 후보: {', '.join(n['name'] + (' 롱' if n['side'] == 'LONG' else ' 숏') for n in near[:3])}"] if near else []),
                          ("wait", "관망")))
        return S
    o, nm, L = p["order"], p["name"], p["side"] == "LONG"
    sd = "롱" if L else "숏"
    narr = f"오늘의 원픽은 {nm} {sd}입니다. " + " ".join(p["story"])
    S.append(vs.Slide("2부 · 바이낸스 3배 선물 원픽", f"{'🟢' if L else '🔴'} {nm} ({p['symbol']}) {p['side']}", narr,
                      [vs.first(x) for x in p["story"]], ("good" if L else "risk", f"{sd} · 격리 3배"),
                      chart=coin_chart(p["spark"], [("진입", o["entry"], "#1F5FBF"), ("목표", o["tp"], "#1E8E3E"), ("손절", o["sl"], "#C5221F")])))
    from pricefmt import kst
    sg, sgo = ("+", "-") if L else ("-", "+")
    body = tri3(f"{p['symbol']} {'🟢 LONG' if L else '🔴 SHORT'} · 격리 {o['leverage']}배",
                f"증거금 {o['margin']:,.0f} USDT · 수량 {o['qty']} · 예약 {kst(p['valid_until'])}까지",
                ("① 진입 지정가", fpx(o["entry"]), "Entry", f"현재가보다 {o['off_pct']}% {'아래' if L else '위'}"),
                (f"② 처리값 TP ({sg}{o.get('tp_pct', 2.45)}%)", fpx(o["tp"]), f"+약 {o.get('win_krw', 0):,}원", f"{o['win_usdt']:+.1f} USDT · +{o.get('win_roe', 7)}%"),
                (f"③ 비상 로스값 SL ({sgo}{o.get('sl_dist', 1.5):.2f}%)", fpx(o["sl"]), f"-약 {abs(o.get('loss_krw', 0)):,}원",
                 f"{o['loss_usdt']:+.1f} USDT · -{o.get('loss_roe', 4.5)}%"),
                f"🛡 <b>본절 방어</b> {fpx(o.get('be_trigger'))}({sg}1.2%, 레버리지 +{o.get('be_trigger_roe', 3.6)}%) 도달 시 SL을 본전 <b>{fpx(o.get('be_price'))}</b>로 이동"
                f"<br><small>로스값 근거: {html.escape(o.get('sl_basis', ''))}</small>")
    narr = (f"{nm} {sd} 주문표입니다. 바이낸스 선물에서 격리, 3배로 설정하고 증거금 360 테더를 넣습니다. "
            f"첫째, 진입 지정가는 {fpx(o['entry'])}달러입니다. "
            f"둘째, 목표 처리값은 {fpx(o['tp'])}달러, 닿으면 약 {say_won(o.get('win_krw', 0))}, {o['win_usdt']:.1f} 테더 수익입니다. "
            f"셋째, 비상 로스값은 {fpx(o['sl'])}달러입니다. {o.get('sl_basis', '')} 자리라 꼬리에 걸려 억울하게 손절될 일이 적고, "
            f"닿으면 최대 {say_won(abs(o.get('loss_krw', 0)))}, {abs(o['loss_usdt']):.1f} 테더 손실로 끝납니다. "
            f"진입과 동시에 목표가와 로스값을 함께 걸어 두세요. "
            f"가격이 {fpx(o.get('be_trigger'))}달러까지 유리하게 오면, 로스값을 본전인 {fpx(o.get('be_price'))}달러로 옮겨 손실 없이 잠그세요. "
            f"예약 주문은 {kst(p['valid_until'], '%d일 %H시')}까지만 유효하고, 그 전에 1시간봉이 24시간 {'저점' if L else '고점'} 밖에서 마감하면 취소합니다. "
            f"체결되면 그때부터 24시간 안에 목표가나 로스값에 닿지 않을 경우 정리합니다.")
    S.append(vs.Slide("2부 · 바이낸스 선물 주문표", "바이낸스 앱에 이대로 입력하세요", narr, [], ("good" if L else "risk", f"{sd} · 360 USDT"), body_html=body))
    return S


def tri3(top_l, top_r, en, tp, sl, tip) -> str:
    """주문표 슬라이드: ① 진입 ② 처리값(TP) ③ 비상 로스값(SL) 나란히 + 본절 방어 팁."""
    cell = lambda k, x: f"<div class='{k}'><span>{x[0]}</span><b>{x[1]}</b><em>{x[2]}</em><small>{x[3]}</small></div>"
    return (EXTRA_CSS + f"<div class='tk3'><div class='top'><b>{top_l}</b><span>{top_r}</span></div><div class='tri3'>"
            + cell("en", en) + cell("tp", tp) + cell("sl", sl) + f"</div><div class='tip'>{tip}</div></div>")


def build(d: dict) -> list:
    S = []
    sess, rec = d["session"], d["record"]
    m, day = int(d["date"][5:7]), int(d["date"][8:10])
    picks, holds = d["picks"], d["holdings"]
    open_say = say_time(sess["open_kst"])
    fu = d.get("futures") or {}
    sub = (f"{m}월 {day}일 · 미국장 {sess['open_kst']} 개장 · 바이낸스 3배 원픽" if sess["trading"]
           else f"{m}월 {day}일 · 미국 증시 휴장 · 바이낸스 3배 원픽")
    intro = (f"안녕하세요, {m}월 {day}일 실전 단타 통합 브리핑입니다. "
             + (f"오늘 밤 미국 증시는 한국 시간 {open_say}에 열립니다. " if sess["trading"] else "오늘 밤 미국 증시는 쉬는 날입니다. ")
             + "먼저 어제 매매 성적표와 보유 포지션을 점검하고, 1부에서 미국 주식 50만 원 타점, "
             "2부에서 바이낸스 3배 선물 롱 숏 원픽을 보겠습니다.")
    S.append(vs.Slide("오프닝", "실전 단타 통합 브리핑", intro, [sub, "공통 인트로 → 1부 미국 주식 → 2부 바이낸스 선물"],
                      ("info", "개인 연습용"), center=True))

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
    for e in [x for x in fu.get("events") or [] if x["type"] in ("close", "missed")][:2]:
        nm = e.get("name") or e["symbol"]
        sd = "롱" if e.get("direction") == "LONG" else "숏"
        if e["type"] == "missed":
            rows.append(f"<div class='e'>⏸ <b>{html.escape(nm)} {sd}</b> 미체결<small>{html.escape(e.get('reason', '')[:60])}</small></div>")
            says.append(f"코인 원픽 {nm} {sd}은 진입가에 닿지 않아 체결되지 않았습니다.")
        else:
            k = "good" if e["pnl_usdt"] > 0 else "risk" if e["pnl_usdt"] < 0 else ""
            c = "up" if e["pnl_usdt"] > 0 else "dn" if e["pnl_usdt"] < 0 else ""
            ico = {"WIN": "🎯", "LOSS": "🛑", "TIME_EXIT": "⏱"}.get(e["result"], "↩")
            rows.append(f"<div class='e {k}'>{ico} <b>{html.escape(nm)} {sd}</b> {html.escape(e['result_ko'])} "
                        f"<b class='{c}'>{e['roe']:+.2f}% · {e['pnl_usdt']:+,.2f} USDT</b><small>{fpx(e['entry'])} → {fpx(e['exit'])} · 격리 3배</small></div>")
            says.append(f"코인 원픽 {nm} {sd}은 {e['result_ko'].split(' (')[0]}로 끝났습니다. 수익률 {e['roe']:+.1f}%, "
                        f"{abs(e['pnl_usdt']):,.1f} 테더 {'이익' if e['pnl_usdt'] > 0 else '손실'}입니다.")
    if rows:
        wins = sum(1 for e in evs if e["type"] == "close" and e["pnl_krw"] > 0)
        loss = sum(1 for e in evs if e["type"] == "close" and e["pnl_krw"] < 0)
        badge = ("good", "익절") if wins and not loss else ("risk", "손실 정리") if loss and not wins else ("info", "판정 결과")
        S.append(vs.Slide("공통 인트로 · 어제 매매 성적표", "어제 추천 결과", "먼저 어제 매매 성적표입니다. " + " ".join(says), [],
                          badge, body_html=EXTRA_CSS + f"<div class='ev3'>{''.join(rows)}</div>"))
    else:
        S.append(vs.Slide("공통 인트로 · 어제 매매 성적표", "어제 판정할 추천 없음",
                          "먼저 어제 매매 성적표입니다. 미국 주식도 코인도 어제 추천하거나 들고 있던 포지션이 없어서 판정할 결과가 없습니다.",
                          ["어제는 예약·보유 포지션이 없었어요", "오늘 타점부터 보겠습니다"], ("info", "판정 없음")))

    for r in (fu.get("reviews") or [])[:2]:      # 끝난 코인 매매 복기
        nm, sd = r.get("name") or r["symbol"], "롱" if r.get("direction") == "LONG" else "숏"
        win = (r.get("pnl_usdt") or 0) > 0
        facts = [f"{fpx(r['entry'])} → {fpx(r['exit'])} · {(r.get('roe') or 0):+.2f}% ({(r.get('pnl_usdt') or 0):+.2f} USDT)"]
        if r.get("mfe") is not None:
            facts.append(f"최대 유리 {r['mfe']:+.2f}% · 최대 불리 {r['mae']:+.2f}%" + (f" · 체결까지 {r['fill_delay_h']:.0f}시간" if r.get("fill_delay_h") else ""))
        facts += [vs.first(x) for x in (r.get("flags") or [])[:2]]
        narr = (f"이어서 매매 복기입니다. {nm} {sd}은 {r.get('result_ko', '')}로 끝났습니다. "
                + (f"진입 뒤 가장 유리했을 때가 {abs(r['mfe']):.1f}%, 가장 불리했을 때가 {abs(r['mae']):.1f}%였습니다. " if r.get("mfe") is not None else "")
                + ("당시 근거를 다시 보면, " + " 그리고 ".join(r["flags"][:2]) + "였습니다. " if r.get("flags") else "")
                + " ".join(r.get("lessons") or [])[:400])
        S.append(vs.Slide("공통 인트로 · 매매 복기", f"🔍 {nm} {sd} 복기", narr, facts[:4], ("good" if win else "risk", "복기")))

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
        S.append(vs.Slide("공통 인트로 · 보유 포지션 긴급 점검", f"{nm} ({h['ticker']}) 오늘 밤 대응", narr, [],
                          (k, "수익 중" if ret > 0 else "물림 관리"), body_html=body))

    for h in (fu.get("holdings") or [])[:2]:
        pl = h.get("plan") or {}
        nm, sd = h.get("name") or h["symbol"], "롱" if h["direction"] == "LONG" else "숏"
        k = pl.get("kind", "wait")
        roe = h.get("roe_now")
        body = (EXTRA_CSS + "<div class='hd'><div class='cards3' style='height:230px'>"
                + card("진입가 · 격리 3배", fpx(h.get("entry") or h.get("limit")), "미진입(예약)" if h["status"] == "PENDING" else "")
                + card("현재가", fpx(h.get("now")), f"남은 시간 {pl.get('left', 0)}시간")
                + card("지금 수익률", "–" if roe is None else f"<span class='{'up' if roe > 0 else 'dn'}'>{roe:+.2f}%</span>", "", k)
                + f"</div><div class='big {'r' if k == 'risk' else ''}'>👉 {html.escape(pl.get('action', ''))}</div>"
                f"<div class='rsn'>{html.escape(vs.first(pl.get('reason', '')))}</div></div>")
        narr = (f"코인 {nm} {sd} 포지션 점검입니다. " + (f"지금 수익률은 {roe:+.1f}%입니다. " if roe is not None else "아직 진입가에 닿지 않았습니다. ")
                + f"{speak_px(pl.get('action', ''))}. {pl.get('reason', '')}")
        S.append(vs.Slide("공통 인트로 · 보유 포지션 긴급 점검", f"🪙 {nm} {h['direction']} 대응", narr, [], (k, "코인 포지션"), body_html=body))

    # 1부 미국 주식
    if picks:
        for i, p in enumerate(picks):
            o, nm = p["order"], p["name"]
            kind = "눌림목 반등형" if p["kind"] == "pullback" else "모멘텀 돌파형"
            lines = [vs.first(s) for s in p["story"]]
            narr = (f"오늘 밤 {'첫 번째' if i == 0 else '두 번째'} 타점은 {nm}, {kind}입니다. " + " ".join(p["story"][:3]))
            narr = narr.replace("“", "").replace("”", "")
            S.append(vs.Slide("1부 · 미국 주식 50만 원 타점", f"{i + 1}. {nm} ({p['ticker']}) · {kind}", narr,
                              [x.split(" 관련 뉴스")[0] for x in lines], ("good", "+5% 노림"),
                              chart=line_chart(p["spark"], [("예약 매수", o["limit"], "#1F5FBF"), ("목표", o["target"], "#1E8E3E"),
                                                            ("손절", o["stop"], "#C5221F")])))
        for p in picks:
            o, nm = p["order"], p["name"]
            body = tri3(f"{html.escape(nm)} ({p['ticker']}) · {o['qty']}주", f"약 ${o['cost_usd']:,.0f} · {o['cost_krw']:,}원",
                        ("① 예약 매수 지정가", f"${o['limit']:.2f}", "Entry", f"전일 종가 대비 -{o['dip_pct']}%"),
                        ("② 처리값 TP (+5.0%)", f"${o['target']:.2f}", f"+약 {o['gain_krw']:,}원", f"+${o['gain_usd']:,.2f}"),
                        (f"③ 비상 로스값 SL (-{o['stop_pct']}%)", f"${o['stop']:.2f}", f"-약 {abs(o['loss_krw']):,}원", f"-${abs(o['loss_usd']):,.2f}"),
                        f"🛡 <b>본절 방어</b> ${o['be_trigger']:.2f}(+2.5%) 도달 시 감시가를 본전 <b>${o['be_price']:.2f}</b>로 · "
                        f"자동감시 주문: 감시가 ${o['stop']:.2f} 이하 시장가 매도<br><small>로스값 근거: {html.escape(o['stop_basis'])}</small>")
            narr = (f"{nm} 예약 주문표입니다. 수량은 {o['qty']}주, 예상 금액은 {say_won(o['cost_krw'])}입니다. "
                    f"첫째, 예약 매수 지정가는 {say_usd(o['limit'])}입니다. "
                    f"둘째, 체결되면 바로 목표 처리값 {say_usd(o['target'])}에 매도를 걸어 두세요. 닿으면 {say_won(o['gain_krw'])} 수익입니다. "
                    f"셋째, 비상 로스값은 {say_usd(o['stop'])}, {o['stop_basis']}입니다. 증권사 앱의 자동감시 주문에 이 가격을 감시가로 넣어 두세요. "
                    f"닿으면 최대 {say_won(abs(o['loss_krw']))} 손실로 끝납니다. "
                    f"주가가 {say_usd(o['be_trigger'])}까지 오르면 감시가를 본전인 {say_usd(o['be_price'])}로 올려 손실 없이 잠그세요. "
                    f"최대 보유 기한은 내일 밤 미국장 마감까지입니다.")
            S.append(vs.Slide("1부 · 미국 주식 예약 주문표", "증권사 앱에 이대로 입력하세요", narr, [], ("info", f"{o['qty']}주 · 50만 원 이내"), body_html=body))
    else:
        near = d.get("near") or []
        lines = [d["block"]] + ([f"아깝게 빠진 후보: {', '.join(n['name'] for n in near)}"] if near else [])
        q, weather = d.get("qqq") or {}, ""
        if q and not q.get("above20"):
            weather = "시장 전체도 약합니다. 나스닥100이 20일 평균선 아래에 있어 오르던 주식도 쉽게 밀리는 구간입니다. "
            lines.append(f"시장 날씨: 나스닥100 20일선 아래" + (f" · VIX {d['vix']:.0f}" if d.get("vix") else ""))
        narr = ("1부, 오늘 밤 미국 주식 타점입니다. " + d["block"] + " " + weather + "단타 연습에서 가장 중요한 건 조건이 안 맞는 날 쉬는 겁니다. "
                "보유 종목이 있다면 앞에서 말씀드린 매도 주문만 확인하세요.")
        S.append(vs.Slide("1부 · 미국 주식 50만 원 타점", "오늘 밤 미국 주식은 쉬어 갑니다", narr, lines[:3], ("wait", "관망")))

    # 2부 바이낸스 선물
    S.extend(coin_slides(fu))

    # 누적 성적
    wr = f"{rec['winrate']:.0f}%" if rec["winrate"] is not None else "–"
    c = "up" if rec["pnl_krw"] > 0 else "dn" if rec["pnl_krw"] < 0 else ""
    if rec["trades"]:
        narr = (f"마지막으로 누적 성적입니다. 미국 주식은 {rec['since'][5:7].lstrip('0')}월 {rec['since'][8:].lstrip('0')}일부터 지금까지 {rec['trades']}번 매매해 "
                f"{rec['wins']}번 이겼습니다. 승률은 {wr}, 누적 가상 손익은 {say_won(rec['pnl_krw'], True)}입니다. "
                f"목표가 5%를 채운 건 {rec['targets']}번입니다. 이기는 날보다 지는 날을 짧게 끊는 연습이 핵심입니다.")
        chart = {"type": "line", "data": {"labels": [x["date"][5:] for x in rec["curve"]],
                                          "datasets": [{"label": "누적 손익(원)", "data": [x["cum_krw"] for x in rec["curve"]],
                                                        "borderColor": "#0D5C6B", "backgroundColor": "rgba(13,92,107,.15)", "fill": True,
                                                        "borderWidth": 5, "pointRadius": 5}]},
                 "options": {"plugins": {"legend": {"display": False}},
                             "scales": {"x": {"ticks": {"font": {"size": 22}}}, "y": {"ticks": {"font": {"size": 24}}}}}}
        S.append(vs.Slide("누적 트랙레코드", "누적 연습 성적", narr + coin_rec_say(fu),
                          [f"총 {rec['trades']}회 · 승률 {wr}", f"누적 {rec['pnl_krw']:+,}원", f"목표가 달성 {rec['targets']}회 · 평균 {rec['avg_ret']:+.2f}%"],
                          ("good" if rec["pnl_krw"] > 0 else "risk" if rec["pnl_krw"] < 0 else "info", f"승률 {wr}"), chart=chart))
    else:
        fr = (fu.get("record") or {})
        S.append(vs.Slide("누적 트랙레코드", "누적 연습 성적",
                          "마지막으로 누적 성적입니다. 미국 주식은 아직 끝난 매매가 없습니다." + coin_rec_say(fu),
                          ["미국 주식: 아직 끝난 매매 없음",
                           f"바이낸스 선물: {fr.get('trades', 0)}회 · {fr.get('pnl_usdt', 0):+,.2f} USDT" if fr else "바이낸스 선물: 기록 없음"],
                          ("info", "기록 중")))

    S.append(vs.Slide("마무리", "오늘 밤 작전은 여기까지입니다",
                      "실제로 다른 가격에 샀거나 팔았다면, 스마트폰 깃허브 앱의 보유 포지션 수동 입력에서 미국 주식인지 바이낸스인지 고르고 가격을 넣어 주세요. "
                      "다음 브리핑부터 내 실제 진입가로 작전을 짭니다. 개인 연습용 가상 매매이며 투자 권유가 아닙니다. 감사합니다.",
                      ["다르게 샀다면: GitHub 앱 → Actions → 보유 포지션 수동 입력", "market · action · ticker · direction · price · qty"],
                      ("info", "필요할 때 다시 요청하세요"), center=True))
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
    fu = d.get("futures") or {}
    what = " · ".join(f"{p['name']} {p['order']['qty']}주" for p in picks) or "미국 쉬어가기"
    cp = fu.get("pick")
    what += " | " + (f"{cp['symbol']} {cp['side']}" if cp else "코인 쉬어가기")
    title = f"[{m}/{day}] 단타 통합 | {what}"[:100]
    chap, last = [], None
    for s, sc in zip(starts, job.scenes):
        sec = sc.section.split(" · ")[0]
        if sec != last:
            chap.append(f"{mmss(s)} {sc.section}")
            last = sec
    rec = d["record"]
    desc = "\n\n".join([
        f"{m}월 {day}일 실전 단타 통합 브리핑 (개인 연습용) — 어제 성적표·보유 점검, 1부 미국 주식 50만 원 타점, 2부 바이낸스 3배 선물 원픽.",
        f"미국 누적: {rec['trades']}회 · 승률 {rec['winrate'] if rec['winrate'] is not None else '–'}% · {rec['pnl_krw']:+,}원",
        f"코인 누적: {(fu.get('record') or {}).get('trades', 0)}회 · {(fu.get('record') or {}).get('pnl_usdt', 0):+,.2f} USDT",
        f"📊 리포트: {PAGES}/swing/swing_{d['date']}.html\n📄 PDF: {PAGES}/swing/pdf/swing_{d['date']}.pdf",
        "⏱ 목차\n" + "\n".join(chap),
        f"※ {DISCLAIMER}",
    ])
    (out / "description.txt").write_text(desc, encoding="utf-8")


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
        make_pdf(browser, a.docs / "swing" / f"swing_{a.date}.html", pdf, f"실전 단타 통합 브리핑 · {a.date}")
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
