"""오후 6시 실전 단타 통합 브리핑 리포트 (docs/swing/swing_<날짜>.html, index.html = 최신본).

공통 인트로(어제 성적표·보유 긴급 점검) → 1부 미국 주식 → 2부 바이낸스 3배 선물 → 누적 성적 → 규칙."""
from __future__ import annotations

import html
import json
from pathlib import Path

WEEK = "월화수목금토일"


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def usd(v, sign=False) -> str:
    if v is None:
        return "–"
    return (f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}" if sign else f"${v:,.2f}")


def krw(v, sign=False) -> str:
    if v is None:
        return "–"
    return f"{'+' if sign and v > 0 else '-' if v < 0 else ''}{abs(v):,}원"


def pct(v) -> str:
    return "–" if v is None else f"{v:+.2f}%"


def cls(v) -> str:
    return "up" if (v or 0) > 0 else "dn" if (v or 0) < 0 else ""


def md(d: str) -> str:
    from datetime import date
    x = date.fromisoformat(d)
    return f"{x.month}월 {x.day}일 ({WEEK[x.weekday()]})"


def event_html(e: dict) -> str:
    t = e["type"]
    nm = f"<b>{esc(e.get('name') or e['ticker'])}</b> <span class='tk'>{esc(e['ticker'])}</span>"
    if t == "fill":
        return (f"<div class='ev good'><span class='tag'>✅ 매수 체결</span>{nm} — 예약가 {usd(e['limit'])}에 "
                f"{e['qty']}주 체결 (실제 체결 {usd(e['price'])}, 장중 최저 {usd(e['low'])})</div>")
    if t == "missed":
        return f"<div class='ev'><span class='tag'>⏸ 미체결 취소</span>{nm} — {esc(e['reason'])} 손실도 이익도 없어요.</div>"
    if t == "close":
        k = "good" if e["pnl_krw"] > 0 else "risk" if e["pnl_krw"] < 0 else ""
        ico = {"WIN": "🎯", "STOP": "🛑"}.get(e["result"], "↩")
        return (f"<div class='ev {k}'><span class='tag'>{ico} {esc(e['result_ko'])}</span>{nm} — {usd(e['entry'])} → {usd(e['exit'])} × {e['qty']}주 = "
                f"<b class='{cls(e['pnl_krw'])}'>{pct(e['ret_pct'])} · {krw(e['pnl_krw'], True)}</b><div class='why'>{esc(e['reason'])}</div></div>")
    if t == "nodata":
        return f"<div class='ev risk'><span class='tag'>⚠ 시세 없음</span>{nm} — 시세를 못 받아 판정을 미뤘어요. 내일 다시 확인합니다.</div>"
    return ""


def holding_html(h: dict, i: int, sess: dict) -> str:
    pl = h.get("plan") or {}
    last = h.get("last") or {}
    day = pl.get("day") or (h.get("held", 0) + 1)
    k = "good" if h["ret_pct"] > 0 else "risk" if h["ret_pct"] < -2 else "wait"
    if pl.get("mode") == "open":
        big = f"오늘 밤 <b>시초가</b>에 전량 매도 걸어두세요"
    elif pl.get("price"):
        big = f"오늘 밤 <b>{usd(pl['price'])}</b>에 예약 매도 걸어두세요"
    else:
        big = esc(pl.get("action"))
    src = "내 계좌 입력" if h.get("source") == "manual" else "자동 추적(추천가 체결 가정)"
    return f"""
<div class='hold {k}'>
 <div class='hh'><div><b class='nm'>{esc(h.get('name'))}</b> <span class='tk'>{esc(h['ticker'])}</span>
   <span class='pill'>DAY {day} {'(마지막 날)' if pl.get('mode') in ('limit', 'open', 'target') and day >= h.get('max_hold', 2) else ''}</span>
   <span class='src'>{src}</span></div>
  <div class='pnl {cls(h['ret_pct'])}'>{pct(h['ret_pct'])}<small>{usd(h['pnl_usd'], True)} · {krw(h['pnl_krw'], True)}</small></div></div>
 <div class='grid4'>
  <div><span>매수가 × 수량</span><b>{usd(h['entry'])} × {h['qty']}주</b></div>
  <div><span>간밤 고가 / 종가</span><b>{usd(last.get('high'))} / {usd(last.get('close'))}</b></div>
  <div><span>목표가 (+5%)</span><b>{usd(h['target'])}</b></div>
  <div><span>손절가</span><b>{usd(h['stop'])}</b></div>
 </div>
 <div class='act'>👉 {big}</div>
 <div class='act2'>{esc(pl.get('action'))}</div>
 <div class='why'><b>근거</b> {esc(pl.get('reason'))}</div>
 <div class='chartbox small'><canvas id='hc{i}'></canvas></div>
</div>"""


def pick_html(p: dict, i: int) -> str:
    o = p["order"]
    kind = "눌림목 반등형" if p["kind"] == "pullback" else "모멘텀 돌파형"
    news = "".join(f"<li><a href='{esc(n['link'])}' target='_blank' rel='noopener'>{esc(n['title'])}</a> <span>{esc(n['source'])}</span></li>"
                   for n in p.get("news") or [])
    chk = "".join(f"<span class='ck {'on' if v else ''}'>{'✔' if v else '·'} {esc(k)}</span>" for k, v in (p.get("checks") or {}).items())
    return f"""
<div class='pick'>
 <div class='hh'><div><span class='rank'>{i + 1}</span><b class='nm'>{esc(p['name'])}</b> <span class='tk'>{esc(p['ticker'])}</span>
  <span class='pill good'>{kind}</span></div>
  <div class='meta'>어제 종가 {usd(p['close'])} ({pct(p['chg1'])}) · 하루 평균 변동폭 {p['atr_pct']:.1f}% · RSI {p['rsi']:.0f} · 거래량 평소의 {p['vol_ratio']:.1f}배</div></div>
 <ol class='story'>{''.join(f'<li>{esc(s)}</li>' for s in p['story'])}</ol>
 <div class='chartbox'><canvas id='pc{i}'></canvas></div>
 <div class='checks'>{chk}</div>
 {f"<div class='news'><b>관련 뉴스</b><ul>{news}</ul></div>" if news else ""}
</div>"""


def order_html(p: dict, sess: dict) -> str:
    o = p["order"]
    return f"""
<div class='order'>
 <div class='oh'><div class='onm'>{esc(p['name'])} <span>({esc(p['ticker'])})</span></div>
  <div class='oq'>{o['qty']}주 <small>예상 {usd(o['cost_usd'])} / 약 {o['cost_krw']:,}원</small></div></div>
 <div class='orow buy'><span>① 예약 매수 지정가</span><b>{usd(o['limit'])}</b><em>{esc(o['limit_why'])}</em></div>
 <div class='orow tgt'><span>② 1차 목표 익절가 (+5.0%)</span><b>{usd(o['target'])}</b><em>체결되면 바로 걸어 둘 자동 매도가 · 성공 시 약 {krw(o['gain_krw'], True)}</em></div>
 <div class='orow stp'><span>③ 손절·비상 탈출 기준가 (-3.5%)</span><b>{usd(o['stop'])}</b><em>감시(스톱) 주문으로 걸어 두기 · 실패 시 약 {krw(o['loss_krw'], True)}</em></div>
 <div class='orow ddl'><span>④ 최대 보유 기한</span><b>{esc(o['deadline'])}</b><em>그때까지 ②·③에 안 닿으면 장 마감(LOC)에 전량 정리</em></div>
 <div class='ohint'>주문 시간: 오늘 18시 이후 ~ 미국장 개장({esc(sess['open_kst'])}) 전에 '예약 지정가'로 넣으면 개장과 동시에 체결을 기다립니다.</div>
</div>"""


def charts_js(d: dict) -> str:
    out = []

    def line(cid, sp, lines):
        ds = [{"label": "종가", "data": sp["close"], "borderColor": "#16202A", "borderWidth": 2.5, "pointRadius": 0, "tension": .2},
              {"label": "20일 평균선", "data": sp["ma20"], "borderColor": "#8793A0", "borderDash": [6, 4], "borderWidth": 1.5, "pointRadius": 0}]
        for lab, v, col in lines:
            if v:
                ds.append({"label": f"{lab} ${v:.2f}", "data": [v] * len(sp["close"]), "borderColor": col, "borderWidth": 2,
                           "pointRadius": 0, "borderDash": [2, 3]})
        out.append(f"mk('{cid}',{json.dumps(sp['dates'])},{json.dumps(ds, ensure_ascii=False)});")

    for i, h in enumerate(d["holdings"]):
        if h.get("spark"):
            pl = h.get("plan") or {}
            line(f"hc{i}", h["spark"], [("매수가", h["entry"], "#1F5FBF"), ("오늘 매도", pl.get("price"), "#1E8E3E"),
                                         ("손절", h["stop"], "#C5221F")])
    for i, p in enumerate(d["picks"]):
        o = p["order"]
        line(f"pc{i}", p["spark"], [("예약 매수", o["limit"], "#1F5FBF"), ("목표", o["target"], "#1E8E3E"), ("손절", o["stop"], "#C5221F")])
    fu = d.get("futures") or {}
    def cline(cid, sp, lines):
        ds = [{"label": "1시간봉 종가", "data": sp["close"], "borderColor": "#16202A", "borderWidth": 2.2, "pointRadius": 0, "tension": .15},
              {"label": "20봉 평균선", "data": sp["ema20"], "borderColor": "#8793A0", "borderDash": [6, 4], "borderWidth": 1.5, "pointRadius": 0}]
        for lab, v, col in lines:
            if v:
                ds.append({"label": f"{lab} {fpx(v)}", "data": [v] * len(sp["close"]), "borderColor": col, "borderWidth": 2,
                           "pointRadius": 0, "borderDash": [2, 3]})
        out.append(f"mk('{cid}',{json.dumps(sp['t'])},{json.dumps(ds, ensure_ascii=False)});")
    if fu.get("pick"):
        o = fu["pick"]["order"]
        cline("fpc", fu["pick"]["spark"], [("진입", o["entry"], "#1F5FBF"), ("목표", o["tp"], "#1E8E3E"), ("손절", o["sl"], "#C5221F")])
    fcv = (fu.get("record") or {}).get("curve") or []
    if fcv:
        out.append(f"""new Chart(document.getElementById('fcum'),{{type:'line',data:{{labels:{json.dumps([c['date'] for c in fcv])},
datasets:[{{label:'누적 손익(USDT)',data:{json.dumps([c['cum_usdt'] for c in fcv])},borderColor:'#B06000',backgroundColor:'rgba(176,96,0,.12)',fill:true,tension:.2}}]}},
options:{{responsive:true,maintainAspectRatio:false,animation:false,plugins:{{legend:{{display:false}}}}}}}});""")
    cv = d["record"]["curve"]
    if cv:
        out.append(f"""new Chart(document.getElementById('cum'),{{type:'line',data:{{labels:{json.dumps([c['date'][5:] for c in cv])},
datasets:[{{label:'누적 손익(원)',data:{json.dumps([c['cum_krw'] for c in cv])},borderColor:'#0D5C6B',backgroundColor:'rgba(13,92,107,.12)',fill:true,tension:.2}}]}},
options:{{responsive:true,maintainAspectRatio:false,animation:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{ticks:{{callback:v=>v.toLocaleString()+'원'}}}}}}}}}});""")
    return "\n".join(out)


CSS = """
:root{--ink:#16202A;--sub:#5C6875;--line:#DDE3E9;--bg:#F5F7F9;--card:#fff;--teal:#0D5C6B;--good:#1E8E3E;--risk:#C5221F;--wait:#B06000;--blue:#1F5FBF}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans KR','Noto Sans CJK KR','Malgun Gothic',sans-serif;line-height:1.55}
.wrap{max-width:1040px;margin:0 auto;padding:20px 16px 60px}
header{background:var(--ink);color:#fff;border-radius:18px;padding:24px 26px}
header h1{margin:0 0 6px;font-size:26px}header p{margin:2px 0;color:#C3CCD6;font-size:14px}
.strip{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}
.strip div{background:var(--card);border-radius:14px;padding:14px 16px;box-shadow:0 2px 8px rgba(22,32,42,.06)}
.strip span{display:block;font-size:13px;color:var(--sub)}.strip b{font-size:20px}
h2{font-size:21px;margin:34px 0 12px;padding-left:12px;border-left:6px solid var(--teal)}
h2 small{font-size:13px;color:var(--sub);font-weight:500;margin-left:8px}
.ev{background:var(--card);border-radius:12px;padding:12px 16px;margin:8px 0;border-left:6px solid var(--line);font-size:15px}
.ev.good{border-left-color:var(--good)}.ev.risk{border-left-color:var(--risk)}
.tag{display:inline-block;font-weight:700;margin-right:8px}.why{color:var(--sub);font-size:14px;margin-top:4px}
.tk{color:var(--sub);font-size:13px;font-weight:600}
.hold,.pick,.order,.box{background:var(--card);border-radius:16px;padding:18px 20px;margin:12px 0;box-shadow:0 2px 10px rgba(22,32,42,.07)}
.hold{border-top:8px solid var(--wait)}.hold.good{border-top-color:var(--good)}.hold.risk{border-top-color:var(--risk)}
.hh{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.nm{font-size:20px}.pill{display:inline-block;background:#F0F3F6;border-radius:20px;padding:2px 10px;font-size:13px;font-weight:700;margin-left:6px}
.pill.good{background:#E6F4EA;color:var(--good)}.src{font-size:12px;color:var(--sub);margin-left:6px}
.pnl{font-size:24px;font-weight:900;text-align:right}.pnl small{display:block;font-size:13px;font-weight:600}
.up{color:var(--good)}.dn{color:var(--risk)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}
.grid4 div{background:#F5F7F9;border-radius:10px;padding:8px 10px}.grid4 span{display:block;font-size:12px;color:var(--sub)}.grid4 b{font-size:15px}
.act{font-size:20px;font-weight:800;background:#E6F4EA;border-radius:12px;padding:12px 16px;margin-top:6px}
.hold.risk .act{background:#FCE8E6}.hold .act2{font-size:14px;color:var(--sub);margin:6px 2px}
.chartbox{height:230px;margin-top:10px;position:relative}.chartbox.small{height:180px}
.rank{display:inline-flex;width:28px;height:28px;border-radius:50%;background:var(--teal);color:#fff;align-items:center;justify-content:center;font-weight:800;margin-right:8px}
.meta{font-size:13px;color:var(--sub);width:100%}
.story{margin:12px 0 4px;padding-left:22px;font-size:15.5px}.story li{margin:5px 0}
.checks{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.ck{font-size:12px;background:#F0F3F6;border-radius:8px;padding:3px 8px;color:#8793A0}
.ck.on{background:#E6F4EA;color:var(--good);font-weight:700}
.news{font-size:14px;margin-top:10px}.news ul{margin:4px 0;padding-left:18px}.news a{color:var(--ink)}.news span{color:var(--sub);font-size:12px}
.order{border:3px solid var(--ink);padding:0;overflow:hidden}
.oh{background:var(--ink);color:#fff;display:flex;justify-content:space-between;align-items:center;padding:16px 20px;flex-wrap:wrap;gap:8px}
.onm{font-size:24px;font-weight:900}.onm span{font-size:18px;color:#C3CCD6}
.oq{font-size:30px;font-weight:900}.oq small{display:block;font-size:13px;font-weight:500;color:#C3CCD6;text-align:right}
.orow{display:grid;grid-template-columns:230px 1fr;gap:2px 16px;padding:14px 20px;border-bottom:1px solid var(--line);align-items:center}
.orow span{font-weight:700;font-size:15px}.orow b{font-size:28px;font-family:'Roboto Mono',Consolas,monospace}.orow em{grid-column:2;font-style:normal;font-size:13px;color:var(--sub)}
.orow.buy b{color:var(--blue)}.orow.tgt b{color:var(--good)}.orow.stp b{color:var(--risk)}.orow.ddl b{font-size:19px;font-family:inherit}
.ohint{padding:12px 20px;font-size:13px;color:var(--sub);background:#FAFBFC}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stats div{background:var(--card);border-radius:14px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(22,32,42,.06)}
.stats span{display:block;font-size:13px;color:var(--sub)}.stats b{font-size:24px}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);border-radius:12px;overflow:hidden}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}th{background:#F0F3F6;font-size:13px}
.empty{background:var(--card);border-radius:14px;padding:18px 20px;font-size:16px;border-left:6px solid var(--wait)}
.box h3{margin:0 0 8px;font-size:17px}.box ul{margin:4px 0;padding-left:20px;font-size:14.5px}.box li{margin:4px 0}
.gl{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;font-size:14px}.gl b{display:block}
.part{background:var(--ink);color:#fff;border-radius:16px;padding:16px 22px;margin:44px 0 6px;font-size:24px;font-weight:900}
.part small{display:block;font-size:14px;font-weight:500;color:#C3CCD6;margin-top:2px}.part.b{background:#5A3A00}
.sum2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.sum2 .box{margin:0}.sum2 .big{font-size:26px;font-weight:900}
.side{display:inline-block;border-radius:10px;padding:4px 12px;font-weight:900;font-size:18px}
.side.L{background:#E6F4EA;color:var(--good)}.side.S{background:#FCE8E6;color:var(--risk)}.side.N{background:#F0F3F6;color:var(--sub)}
.bias{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.bias .side{font-size:22px}
.src{font-size:12px;color:var(--sub)}
.disc{font-size:12.5px;color:var(--sub);margin-top:30px;text-align:center}
@media (max-width:700px){.sum2{grid-template-columns:1fr}.strip,.stats{grid-template-columns:1fr 1fr}.grid4{grid-template-columns:1fr 1fr}.orow{grid-template-columns:1fr}.orow em{grid-column:1}.gl{grid-template-columns:1fr}}
@media print{body{background:#fff}.hold,.pick,.order,.box,.ev,.stats,table{break-inside:avoid}h2{break-after:avoid}}
"""


GLOSSARY = [
    ("예약 지정가 매수", "내가 정한 가격 이하로 내려와야만 사지는 주문. 장 시작 전에 미리 넣어 둘 수 있어요."),
    ("목표 익절가", "이 가격에 닿으면 자동으로 팔리도록 걸어 두는 매도 주문 (+5%)."),
    ("손절가·감시(스톱) 주문", "이 가격 아래로 떨어지면 자동으로 파는 주문. 손실이 커지는 걸 막는 안전벨트예요."),
    ("LOC (장 마감 지정가)", "장 마감 가격으로 팔겠다는 주문. 기한이 끝난 종목을 정리할 때 씁니다."),
    ("하루 평균 변동폭 (ATR%)", "최근 14일 동안 하루에 평균 몇 % 오르내렸는지. 3.5% 이상이어야 +5%를 노릴 수 있어요."),
    ("RSI", "최근 오름·내림의 힘을 0~100으로 표시. 30 근처면 많이 눌림, 70 이상이면 과열."),
    ("20일 평균선", "최근 20거래일 종가의 평균. 주가가 이 선 위에 있으면 큰 흐름이 오름세예요."),
    ("아래꼬리 양봉", "장중에 크게 밀렸다가 다시 올라와 시가보다 높게 끝난 날. 저가에 사려는 힘이 있다는 신호."),
    ("격리(Isolated) 3배", "이 포지션에 넣은 증거금(360 USDT)만 위험에 노출되는 방식. 3배면 코인 가격 1% 움직임이 내 돈 3% 손익이 돼요."),
    ("롱 / 숏", "롱은 오르면 수익, 숏은 내리면 수익. 선물은 하락장에서도 숏으로 수익을 낼 수 있어요."),
    ("펀딩비", "무기한 선물 가격을 현물에 맞추려고 8시간마다 롱·숏이 주고받는 이자. 크게 플러스면 롱이 과열된 상태예요."),
    ("미결제약정 (OI)", "아직 정리되지 않은 선물 계약 총액. 가격과 함께 늘면 새 돈이 그 방향으로 들어온다는 뜻이에요."),
]




# ───────────────────────── 2부: 바이낸스 선물 ─────────────────────────
def fpx(v) -> str:
    from pricefmt import fmt_px
    return fmt_px(v)


def side_html(sd: str) -> str:
    return {"LONG": "<span class='side L'>🟢 LONG</span>", "SHORT": "<span class='side S'>🔴 SHORT</span>"}.get(sd, "<span class='side N'>⚪ 중립</span>")


def usdt(v, sign=False) -> str:
    if v is None:
        return "–"
    return f"{'+' if sign and v > 0 else ''}{v:,.2f} USDT"


def coin_event_html(e: dict) -> str:
    nm = f"<b>{esc(e.get('name') or e['symbol'])}</b> <span class='tk'>{esc(e['symbol'])}</span> {side_html(e.get('direction'))}"
    t = e["type"]
    if t == "fill":
        from pricefmt import kst
        return f"<div class='ev good'><span class='tag'>✅ 진입 체결</span>{nm} — {fpx(e['price'])} ({esc(kst(e['time']))} 봉)</div>"
    if t == "missed":
        return f"<div class='ev'><span class='tag'>⏸ {esc(e['result_ko'])}</span>{nm} — {esc(e['reason'])}</div>"
    if t == "close":
        k = "good" if e["pnl_usdt"] > 0 else "risk" if e["pnl_usdt"] < 0 else ""
        ico = {"WIN": "🎯", "LOSS": "🛑", "TIME_EXIT": "⏱"}.get(e["result"], "↩")
        return (f"<div class='ev {k}'><span class='tag'>{ico} {esc(e['result_ko'])}</span>{nm} — {fpx(e['entry'])} → {fpx(e['exit'])} · "
                f"<b class='{cls(e['pnl_usdt'])}'>수익률 {e['roe']:+.2f}% · {usdt(e['pnl_usdt'], True)} ≈ {krw(e['pnl_krw'], True)}</b>"
                f"<div class='why'>{esc(e['reason'])}</div></div>")
    if t == "nodata":
        return f"<div class='ev risk'><span class='tag'>⚠ 시세 없음</span>{nm} — {esc(e.get('reason'))}</div>"
    return ""


def coin_holding_html(h: dict) -> str:
    from pricefmt import kst
    pl = h.get("plan") or {}
    k = pl.get("kind", "wait")
    st = "진입 대기(예약)" if h["status"] == "PENDING" else "보유 중"
    src = "내 계좌 입력" if h.get("source") == "manual" else "자동 추적(추천가 체결 가정)"
    roe = h.get("roe_now")
    return f"""
<div class='hold {k}'>
 <div class='hh'><div><b class='nm'>{esc(h.get('name'))}</b> <span class='tk'>{esc(h['symbol'])}</span> {side_html(h['direction'])}
   <span class='pill'>{st} · 남은 시간 {pl.get('left', 0)}시간</span><span class='src'>{src}</span></div>
  <div class='pnl {cls(roe)}'>{'–' if roe is None else f'{roe:+.2f}%'}<small>{usdt(h.get('pnl_now'), True) if roe is not None else '미진입'}</small></div></div>
 <div class='grid4'>
  <div><span>진입가 · 격리 {h.get('leverage', 3)}배</span><b>{fpx(h.get('entry') or h.get('limit'))}</b></div>
  <div><span>현재가</span><b>{fpx(h.get('now'))}</b></div>
  <div><span>목표가 (TP)</span><b>{fpx(h['tp'])}</b></div>
  <div><span>손절가 (SL)</span><b>{fpx(h['sl'])}</b></div>
 </div>
 <div class='act'>👉 {esc(pl.get('action'))}</div>
 <div class='why'><b>근거</b> {esc(pl.get('reason'))}</div>
</div>"""


def coin_pick_html(p: dict, bias: dict) -> str:
    o = p["order"]
    L = p["side"] == "LONG"
    chk = "".join(f"<span class='ck {'on' if v else ''}'>{'✔' if v else '·'} {esc(k)}</span>" for k, v in (p.get("checks") or {}).items())
    fr = "–" if p.get("funding") is None else f"{p['funding']:+.4f}%"
    oi = "–" if p.get("oi_chg24") is None else f"{p['oi_chg24']:+.1f}%"
    return f"""
<div class='pick'>
 <div class='hh'><div><b class='nm'>{esc(p['name'])}</b> <span class='tk'>{esc(p['symbol'])}</span> {side_html(p['side'])}</div>
  <div class='meta'>현재가 {fpx(p['close'])} · 24시간 {pct(p['chg24'])} · 1시간 RSI {p['rsi1h']:.0f} · 펀딩비 {fr} · 미결제약정 24h {oi} · 거래량 평소의 {p['vol_ratio']:.1f}배</div></div>
 <ol class='story'>{''.join(f'<li>{esc(s)}</li>' for s in p['story'])}</ol>
 <div class='chartbox'><canvas id='fpc'></canvas></div>
 <div class='checks'>{chk}</div>
</div>
<div class='order'>
 <div class='oh'><div class='onm'>{esc(p['symbol'])} <span>{'🟢 LONG (오르면 수익)' if L else '🔴 SHORT (내리면 수익)'}</span></div>
  <div class='oq'>격리 {o['leverage']}배<small>증거금 {o['margin']:,.0f} USDT · 포지션 {o['notional']:,.0f} USDT · 수량 {o['qty']}</small></div></div>
 <div class='orow buy'><span>① 진입 지정가</span><b>{fpx(o['entry'])}</b><em>현재가보다 {o['off_pct']}% {'아래' if L else '위'} (1시간 평균 변동폭의 약 30%) · 24시간 안에 안 닿으면 취소</em></div>
 <div class='orow tgt'><span>② 목표 익절가 TP ({'+' if L else '-'}2.45%)</span><b>{fpx(o['tp'])}</b><em>레버리지 포함 순수익 약 +7% ≈ {usdt(o['win_usdt'], True)}</em></div>
 <div class='orow stp'><span>③ 자동 손절가 SL ({'-' if L else '+'}1.50%)</span><b>{fpx(o['sl'])}</b><em>레버리지 포함 약 -4.5% ≈ {usdt(o['loss_usdt'], True)} · 진입과 동시에 TP/SL 함께 설정</em></div>
 <div class='orow ddl'><span>④ 시간 정리</span><b>{esc(p['valid_until_kst'])}</b><em>그때까지 ②·③에 안 닿으면 시장가로 정리 (TIME_EXIT)</em></div>
 <div class='ohint'>참고 청산가(격리 {o['leverage']}배): 약 {fpx(o['liq'])} — 손절가가 훨씬 먼저 오므로 손절 주문만 지키면 청산까지 가지 않아요.</div>
</div>"""


def futures_part(fu: dict) -> str:
    if not fu:
        return "<div class='empty'>코인 파트 데이터가 없어요.</div>"
    if fu.get("error"):
        return f"<div class='empty'>⚠ 오늘은 코인 데이터를 받지 못해 2부를 건너뜁니다. ({esc(fu['error'])})</div>"
    b = fu["bias"]
    nq = fu.get("nq") or {}
    out = [f"""<div class='box'><div class='bias'><b>오늘의 방향</b> {side_html(b['side'])} <span class='why'>점수 {b['score']:+.2f} (비트코인 {b['btc_score']:+.1f} · 나스닥 선물 {b['nq_score']:+.1f}×0.6)</span></div>
<ul>{''.join(f'<li>{esc(w)}</li>' for w in b['why'])}</ul><div class='src'>데이터: {esc(fu['source_label'])} · 기준 {esc(fu['data_time'])} (한국 시간) · 분석 {fu['universe']}종목</div></div>"""]
    if fu.get("pick"):
        out.append(coin_pick_html(fu["pick"], b))
    else:
        rows = "".join(f"<li><b>{esc(n['name'])} ({esc(n['symbol'])})</b> {side_html(n['side'])} 충족 {n['passed']}/7 · "
                       f"{esc(', '.join(k for k, v in n['checks'].items() if v) or '없음')}</li>" for n in fu.get("near") or [])
        out.append(f"<div class='empty'>⏸ {esc(fu['block'])}</div>" + (f"<div class='box'><h3>아깝게 빠진 후보</h3><ul>{rows}</ul></div>" if rows else ""))
    if fu.get("pick") and fu.get("near"):
        rows = "".join(f"<tr><td>{esc(n['name'])} <span class='tk'>{esc(n['symbol'])}</span></td><td>{side_html(n['side'])}</td><td>{n['passed']}/7</td>"
                       f"<td>{pct(n['chg24'])}</td><td>{n['score']:.2f}</td></tr>" for n in fu["near"][:4])
        out.append(f"<div class='box'><h3>다음 후보 (참고만)</h3><table><tr><th>코인</th><th>방향</th><th>충족</th><th>24시간</th><th>점수</th></tr>{rows}</table></div>")
    return "".join(out)


def coin_record_html(rec: dict) -> str:
    wr = f"{rec['winrate']:.0f}%" if rec.get("winrate") is not None else "–"
    from pricefmt import kst
    rows = "".join(
        f"<tr><td>{esc(kst(h['exit_time'], '%m/%d %H시'))}</td><td>{esc(h['name'])} {side_html(h['direction'])}</td><td>{esc(h['result_ko'])}</td>"
        f"<td>{fpx(h['entry'])} → {fpx(h['exit'])}</td><td class='{cls(h['roe'])}'>{h['roe']:+.2f}%</td>"
        f"<td class='{cls(h['pnl_usdt'])}'>{usdt(h['pnl_usdt'], True)}</td></tr>" for h in rec.get("recent") or [])
    out = (f"<div class='stats'><div><span>총 매매</span><b>{rec['trades']}회</b></div><div><span>승률</span><b>{wr}</b></div>"
           f"<div><span>누적 손익</span><b class='{cls(rec['pnl_usdt'])}'>{usdt(rec['pnl_usdt'], True)}</b></div>"
           f"<div><span>원화 환산</span><b class='{cls(rec['pnl_krw'])}'>{krw(rec['pnl_krw'], True)}</b></div></div>"
           f"<div class='why' style='margin:8px 2px'>시작일 {esc(rec['since'])} · TP 달성 {rec['tp_hits']}회 · 손절 {rec['sl_hits']}회 · 미체결 {rec['no_fill']}회(성적 제외)</div>")
    if rec.get("curve"):
        out += "<div class='box'><div class='chartbox'><canvas id='fcum'></canvas></div></div>"
    out += (f"<table><tr><th>정리</th><th>코인</th><th>결과</th><th>진입→정리</th><th>수익률</th><th>손익</th></tr>{rows}</table>"
            if rows else "<div class='empty'>아직 끝난 코인 매매가 없어요. 첫 매매가 끝나면 여기에 쌓입니다.</div>")
    return out


def write(d: dict, out: Path) -> Path:
    sess, rec = d["session"], d["record"]
    fu = d.get("futures") or {}
    frec = fu.get("record") or {}
    if fu.get("pick"):
        from pricefmt import kst
        fu["pick"]["valid_until_kst"] = kst(fu["pick"]["valid_until"]) + " (한국 시간)"
    S = out / "swing"
    S.mkdir(parents=True, exist_ok=True)
    hold_n, pick_n = len(d["holdings"]), len(d["picks"])
    wr = f"{rec['winrate']:.0f}%" if rec["winrate"] is not None else "–"
    fwr = f"{frec['winrate']:.0f}%" if frec.get("winrate") is not None else "–"
    open_note = f"오늘 밤 미국장 개장 {sess['open_kst']} (한국 시간{', 서머타임' if sess['dst'] else ''}) · 마감 {sess['close_kst']}"
    if not sess["trading"]:
        open_note = "오늘 밤 미국 증시 휴장 (코인은 24시간 거래)"
    parts = []
    # ── 공통 인트로
    coin_sum = (f"{frec.get('trades', 0)}회 · 승률 {fwr} · <span class='{cls(frec.get('pnl_usdt'))}'>{usdt(frec.get('pnl_usdt'), True)}</span>"
                if frec else "–")
    intro = (f"<div class='sum2'><div class='box'><h3>🇺🇸 미국 주식 누적</h3><div class='big'>{rec['trades']}회 · 승률 {wr}</div>"
             f"<div class='{cls(rec['pnl_krw'])}' style='font-size:20px;font-weight:800'>{krw(rec['pnl_krw'], True)} <small>({usd(rec['pnl_usd'], True)})</small></div></div>"
             f"<div class='box'><h3>🪙 바이낸스 선물 누적</h3><div class='big'>{coin_sum}</div>"
             f"<div class='{cls(frec.get('pnl_krw'))}' style='font-size:20px;font-weight:800'>{krw(frec.get('pnl_krw'), True) if frec else '–'}</div></div></div>")
    urgent = "".join(holding_html(h, i, sess) for i, h in enumerate(d["holdings"]))
    urgent += "".join(coin_holding_html(h) for h in fu.get("holdings") or [])
    intro += "<h3 style='margin:22px 0 6px'>🚨 보유 포지션 긴급 점검 — 오늘 밤 탈출·대응 지정가</h3>"
    intro += urgent or "<div class='empty'>지금 물려 있거나 정리 안 된 포지션이 없어요. 오늘은 새 타점에 집중합니다.</div>"
    evs = "".join(event_html(e) for e in d["events"]) + "".join(coin_event_html(e) for e in fu.get("events") or [])
    intro += "<h3 style='margin:22px 0 6px'>📋 어제 추천 결과</h3>"
    intro += evs or "<div class='ev'>어제 판정할 추천·보유 종목이 없었어요.</div>"
    parts.append(f"<div class='part'>공통 인트로 · 어제 매매 성적표 & 보유 포지션 긴급 점검"
                 f"<small>미국 {esc((d.get('data_date') or '')[5:].replace('-', '/'))} 종가 · 코인 {esc(fu.get('data_time') or '–')} 1시간봉 기준</small></div>{intro}")
    # ── 1부 미국 주식
    p2 = "".join(pick_html(p, i) for i, p in enumerate(d["picks"]))
    if not d["picks"]:
        near = "".join(f"<li><b>{esc(n['name'])} ({esc(n['ticker'])})</b> 변동폭 {n['atr_pct']:.1f}% · RSI {n['rsi']:.0f} · "
                       f"충족: {', '.join(k for k, v in n['checks'].items() if v) or '없음'}</li>" for n in d.get("near") or [])
        p2 = f"<div class='empty'>⏸ {esc(d['block'])}</div>" + (f"<div class='box'><h3>아깝게 빠진 후보</h3><ul>{near}</ul></div>" if near else "")
    if d["picks"]:
        p3 = "".join(order_html(p, sess) for p in d["picks"])
        p3 += f"<div class='why' style='margin-top:6px'>수량 = 50만 원 ÷ (예약가 × 원/달러 {d['fx']:,.1f}) 의 정수 부분 · 수수료·환전 비용 제외</div>"
    else:
        p3 = "<div class='empty'>오늘은 새로 넣을 예약 주문이 없어요. 보유 종목의 매도 주문만 확인하세요.</div>"
    q = d.get("qqq") or {}
    parts.append(f"<div class='part'>1부 · 오늘 밤 미국 주식 50만 원 단타 타점<small>1~2거래일 보유 · 목표 +5.0% · 손절 -3.5% · "
                 f"{esc(open_note)}</small></div><h2>오늘 밤 타점<small>{pick_n}종목 · 나스닥100(QQQ) {pct(q.get('chg1'))}"
                 f"{' · VIX ' + str(d['vix']) if d.get('vix') else ''}</small></h2>{p2}<h2>증권사 앱 예약 주문표</h2>{p3}")
    # ── 2부 바이낸스
    parts.append(f"<div class='part b'>2부 · 오늘의 바이낸스 3배 레버리지 롱/숏 원픽<small>격리 3배 · 증거금 360 USDT · 24시간 이내 · 목표 +7% / 손절 -4.5% (레버리지 포함)</small></div>"
                 f"{futures_part(fu)}")
    # ── 누적 성적
    rows = "".join(
        f"<tr><td>{esc(h['exit_date'][5:])}</td><td>{esc(h['name'])} <span class='tk'>{esc(h['ticker'])}</span></td><td>{esc(h['result_ko'])}</td>"
        f"<td>{usd(h['entry'])} → {usd(h['exit'])}</td><td class='{cls(h['ret_pct'])}'>{pct(h['ret_pct'])}</td>"
        f"<td class='{cls(h['pnl_krw'])}'>{krw(h['pnl_krw'], True)}</td></tr>" for h in rec["recent"])
    p4 = (f"<div class='stats'><div><span>총 매매</span><b>{rec['trades']}회</b></div><div><span>승률</span><b>{wr}</b></div>"
          f"<div><span>누적 가상 수익</span><b class='{cls(rec['pnl_krw'])}'>{krw(rec['pnl_krw'], True)}</b></div>"
          f"<div><span>평균 수익률</span><b>{pct(rec['avg_ret'])}</b></div></div>"
          f"<div class='why' style='margin:8px 2px'>시작일 {esc(rec['since'])} · 목표가 달성 {rec['targets']}회 · 미체결 {rec['missed']}회(성적 제외)</div>")
    if rec["curve"]:
        p4 += "<div class='box'><div class='chartbox'><canvas id='cum'></canvas></div></div>"
    p4 += (f"<table><tr><th>매도일</th><th>종목</th><th>결과</th><th>매수→매도</th><th>수익률</th><th>손익</th></tr>{rows}</table>"
           if rows else "<div class='empty'>아직 끝난 매매가 없어요. 첫 매매가 끝나면 여기에 쌓입니다.</div>")
    parts.append(f"<h2>누적 트랙레코드 · 🇺🇸 미국 주식</h2>{p4}")
    if frec:
        parts.append(f"<h2>누적 트랙레코드 · 🪙 바이낸스 선물</h2>{coin_record_html(frec)}")
    # ── 규칙·용어·입력 방법
    R = d["rules"]
    FR = fu.get("rules") or {}
    parts.append(f"""<h2>규칙과 용어</h2>
<div class='box'><h3>1부 미국 주식 고정 규칙</h3><ul>
<li>1회 최대 {R['budget_krw']:,}원 · 목표 +{R['target_pct']}% · 손절 -{R['stop_pct']}% · 최대 {R['max_hold']}거래일 보유</li>
<li>동시 보유 최대 {R['max_slots']}종목(예약 포함). 슬롯이 다 차면 신규 매수 보류</li>
<li>마지막 날: 수익 +2% 이상이면 목표가 유지 후 마감 정리, 5일선 지지면 +2% 약익절, 약하면 본전 탈출, 20일선까지 깨지면 시초가 정리</li>
<li>예외적 1일 연장: 수익 +2% 이상 + 5일·20일선 위 + 거래량 유지 + RSI 70 미만일 때만, 손절가를 본전으로 올리고 하루 더</li>
<li>자동 판정: 같은 날 목표가와 손절가에 모두 닿으면 순서를 알 수 없어 손절로 계산(보수적)</li></ul></div>
<div class='box'><h3>2부 바이낸스 선물 고정 규칙</h3><ul>
<li>격리(Isolated) {FR.get('leverage', 3)}배 고정 · 1회 증거금 {FR.get('margin_usdt', 360):,.0f} USDT(약 50만 원) · 하루 원픽 1개 · 최대 24시간</li>
<li>목표 익절 TP: 진입가 대비 ±{FR.get('tp_pct', 2.45)}% (레버리지 포함 수수료 감안 순수익 +{FR.get('win_roe', 7.0)}%) · 손절 SL: ∓{FR.get('sl_pct', 1.5)}% (-{FR.get('loss_roe', 4.5)}%)</li>
<li>방향: 비트코인 4시간봉 추세·24시간 등락 + 나스닥100 선물로 롱 우위/숏 우위를 먼저 정하고, 그 방향 코인만 고릅니다(중립이면 양방향)</li>
<li>코인 조건 7가지(4시간봉 추세·1시간봉 눌림/반등·캔들·거래량·미결제약정·펀딩비·변동폭) 중 5개 이상 + 추세·변동폭 필수</li>
<li>자동 판정: 추천 이후 1시간봉으로 진입 → TP/SL 중 먼저 닿은 쪽(같은 봉에서 둘 다면 손절), 24시간 지나면 TIME_EXIT, 예약가 미도달은 NO_FILL</li></ul></div>
<div class='box'><h3>용어 풀이</h3><div class='gl'>{''.join(f'<div><b>{esc(a)}</b>{esc(b)}</div>' for a, b in GLOSSARY)}</div></div>
<div class='box'><h3>실제로 다르게 샀거나 팔았다면 (스마트폰)</h3><ul>
<li>GitHub 앱 → stock-daily → Actions → <b>보유 포지션 수동 입력</b> → Run workflow</li>
<li>market(US_STOCK / BINANCE), action(BUY 신규·단가수정 / CLOSE 매도·청산 / CANCEL 미체결 취소), ticker(NVDA · SOLUSDT), direction(LONG/SHORT), price, qty 입력</li>
<li>코인 qty: 숫자만 넣으면 투입 증거금 USDT(예: 360), 코인 수량이면 '개'를 붙여요(예: 7.6개). 비우면 360 USDT</li></ul></div>""")

    page = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>오후 6시 단타 통합 브리핑 {esc(d['date'])}</title>
<link rel='preconnect' href='https://fonts.googleapis.com'><link href='https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap' rel='stylesheet'>
<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js'></script><style>{CSS}</style></head><body><div class='wrap'>
<header><h1>⏰ 오후 6시 실전 단타 통합 브리핑 · {md(d['date'])}</h1>
<p>1부 미국 주식 50만 원 단타 + 2부 바이낸스 3배 선물 원픽 · 개인 연습용 (외부 배포 없음)</p>
<p>{esc(open_note)} · 원/달러 {d['fx']:,.1f}</p></header>
<div class='strip'><div><span>🇺🇸 보유 · 오늘 밤 신규</span><b>{hold_n}종목 · {pick_n}종목</b></div>
<div><span>🪙 오늘의 방향 · 원픽</span><b>{esc(((fu.get('bias') or {}).get('label') or '–').split(' ')[0])} {esc((fu.get('pick') or {}).get('coin') or '쉬어가기' if not fu.get('error') else '데이터 없음')}</b></div>
<div><span>누적 (미국 · 코인)</span><b><span class='{cls(rec['pnl_krw'])}'>{krw(rec['pnl_krw'], True)}</span> · <span class='{cls(frec.get('pnl_usdt'))}'>{usdt(frec.get('pnl_usdt'), True) if frec else '–'}</span></b></div></div>
{''.join(parts)}
<p class='disc'>개인 연습용 가상 매매 기록입니다. 투자 권유가 아니며, 실제 매매 판단과 책임은 본인에게 있습니다. 주식 수수료·세금·환전 비용은 계산에 넣지 않았고, 코인 선물은 레버리지로 손실이 커질 수 있습니다.</p>
</div><script>
const DATA_DATE={json.dumps(d['date'])};
function mk(id,labels,ds){{const el=document.getElementById(id);if(!el||!window.Chart)return;new Chart(el,{{type:'line',data:{{labels,datasets:ds}},
options:{{responsive:true,maintainAspectRatio:false,animation:false,plugins:{{legend:{{labels:{{boxWidth:12,font:{{size:11}}}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:8}}}}}}}}}})}}
{charts_js(d)}
</script></body></html>"""
    p = S / f"swing_{d['date']}.html"
    p.write_text(page, encoding="utf-8")
    (S / "index.html").write_text(page, encoding="utf-8")
    return p
