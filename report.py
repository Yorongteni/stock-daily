"""분석 결과를 단일 HTML 리포트로 저장 (모닝/나이트 브리핑).

섹션 순서 (PDF·영상과 동일):
  오늘의 결론 요약 → ① 과거 대비 현재 시장 진단 → ② 매크로·환율·현물 → ③ 사회 흐름·당일 예측
  → ④ 13개 분야 브리핑 → ⑤ 기회 & 리스크 → ⑥ 종합 투자 총론 → 부록(관심 종목·스크리닝·종목 상세)
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  --bg:#F5F7F9; --panel:#FFFFFF; --ink:#16202A; --sub:#5C6875; --line:#DDE3E9;
  --up:#D0342C; --down:#1F5FBF; --flat:#8793A0; --accent:#0D5C6B;
  --up-soft:#FBE7E5; --down-soft:#E3ECFA; --warn:#B7791F; --warn-soft:#FBF1DE; --acc-soft:#E2F0F2;
  --c1:#0D5C6B; --c2:#D0342C; --c3:#B7791F; --c4:#1F5FBF; --c5:#6B7A88; --c6:#7B4FA0;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#121820; --panel:#19212B; --ink:#E7ECF1; --sub:#98A4B1; --line:#2A3542;
    --up:#F06A60; --down:#5C95EC; --flat:#7D8996; --accent:#5FB7C7;
    --up-soft:#3A2224; --down-soft:#1E2B40; --warn:#E0A84A; --warn-soft:#3A2F1C; --acc-soft:#1B3238;
    --c1:#5FB7C7; --c2:#F06A60; --c3:#E0A84A; --c4:#5C95EC; --c5:#98A4B1; --c6:#B58BD8;
    color-scheme:dark;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:15px;line-height:1.6;font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px 24px;
  border-bottom:2px solid var(--ink);padding-bottom:14px}
header h1{font-size:28px;line-height:1.3;margin:0;font-weight:700;max-width:34ch}
header .kicker{display:block;font-size:14px;font-weight:700;color:var(--accent);margin-bottom:2px}
header .meta{color:var(--sub);font-size:14px}
.nav{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:2px;font-size:14px}
.nav a{color:var(--accent);font-weight:500}
.new{font-size:11px;font-weight:700;color:var(--panel);background:var(--c);border-radius:3px;padding:0 5px;margin-left:6px;vertical-align:2px}
h2{font-size:20px;margin:44px 0 6px;font-weight:700;display:flex;align-items:baseline;gap:10px}
h2 .no{font-size:13px;color:var(--panel);background:var(--accent);border-radius:3px;padding:1px 7px}
h2.appx{font-size:17px;color:var(--sub);border-top:1px solid var(--line);padding-top:24px}
.lead{color:var(--sub);font-size:13.5px;margin:0 0 14px}
h3{font-size:15.5px;margin:0 0 6px}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:18px 20px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:14px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px}
.mt{margin-top:14px}
.txt{max-width:80ch;margin:0 0 10px}
ul.clean{margin:4px 0 0;padding-left:18px} ul.clean li{margin:3px 0}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 9px;border-radius:10px;background:var(--bg);border:1px solid var(--line);color:var(--sub);white-space:nowrap}
.pill.pos{background:var(--up-soft);color:var(--up);border-color:transparent}
.pill.neg{background:var(--down-soft);color:var(--down);border-color:transparent}
.pill.mid{background:var(--warn-soft);color:var(--warn);border-color:transparent}
.pill.acc{background:var(--acc-soft);color:var(--accent);border-color:transparent}
.note{font-size:13px;color:var(--warn);background:var(--warn-soft);padding:8px 12px;border-radius:4px;margin:0 0 12px}
.err{color:var(--warn);background:var(--warn-soft);padding:12px 14px;border-radius:4px;font-size:14px}
.k{font-size:12.5px;color:var(--sub)}

/* 오늘의 결론 요약 */
.sum{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:14px;margin-top:20px}
.sum .panel{padding:16px 18px}
.sum .big{font-size:24px;font-weight:700;line-height:1.25;margin:4px 0}
.sum .one{font-size:14px}
.stack{display:flex;height:16px;border-radius:3px;overflow:hidden;margin:10px 0 6px}
.stack i{display:block;height:100%}
.leg{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12.5px;color:var(--sub)}
.leg b{color:var(--ink);font-weight:500}
.leg span::before{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;background:var(--c);margin-right:5px}

/* 과거 대비 */
.regime{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:10px;margin:12px 0}
.regime div{background:var(--bg);border-radius:4px;padding:10px 12px;font-size:14px}
.regime b{display:block;font-size:12.5px;color:var(--sub);font-weight:500}
.pctl .row{display:grid;grid-template-columns:minmax(110px,170px) 1fr 220px;gap:12px;align-items:center;padding:7px 0;border-top:1px solid var(--line);font-size:14px}
.pctl .row:first-of-type{border-top:none}
.track{position:relative;height:12px;border-radius:6px;background:linear-gradient(90deg,var(--down-soft),var(--bg) 50%,var(--up-soft))}
.track .avg{position:absolute;top:-3px;bottom:-3px;border-left:2px dashed var(--sub)}
.track .ago{position:absolute;top:1px;width:10px;height:10px;margin-left:-5px;border-radius:50%;border:2px solid var(--sub);background:var(--panel)}
.track .now{position:absolute;top:-4px;width:6px;height:20px;margin-left:-3px;border-radius:2px;background:var(--ink)}
.pctl .val{font-size:13px;color:var(--sub);text-align:right}
.pctl .val b{color:var(--ink)}
.pctl .cap{font-size:12px;color:var(--sub);margin-bottom:6px}
table.t{border-collapse:collapse;width:100%;font-size:13.5px}
table.t th,table.t td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.t th{font-weight:500;color:var(--sub);background:var(--bg)}
table.t td:first-child,table.t th:first-child{text-align:left}
table.t tr:last-child td{border-bottom:none}
.scroll{overflow-x:auto}

.ach{height:260px}
.acard .t td,.acard .t th{padding:5px 8px;font-size:13px}
.acard .ln2{font-size:13.5px;margin-top:4px} .acard .ln2 em{font-style:normal;color:var(--sub);margin-right:6px}
.hgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,350px),1fr));gap:12px}
.hcard{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px}
.hcard .hd{display:flex;justify-content:space-between;align-items:baseline}
.hcard .lv{font-size:19px;font-weight:700}
.hcard .state{margin-top:4px}
.hcard .state .pill{font-size:12.5px}
.hcard .hch{height:150px;margin:6px 0}
.hcard ul.hl{list-style:none;margin:0;padding:0;font-size:13.5px}
.hcard ul.hl li{padding:3px 0;border-top:1px dashed var(--line)}
.hcard ul.hl span{display:inline-block;min-width:84px;color:var(--sub)}
.hcard ul.hl b{font-weight:600}

/* 매크로 */
.mgrp{margin-top:14px}
.mgrp h3{font-size:14px;color:var(--sub);font-weight:500;margin:0 0 6px}
.mcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,262px),1fr));gap:10px}
.mc{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px}
.mc .hd{display:flex;justify-content:space-between;align-items:baseline;gap:6px}
.mc .nm{font-weight:700;font-size:14px}
.mc .lv{font-size:19px;font-weight:700}
.mc .ch{display:flex;flex-wrap:wrap;gap:0 10px;font-size:12.5px;color:var(--sub)}
.mc .ch b{font-weight:500}
.mc .sp{height:58px;margin:6px 0 4px}
.mc .pc{font-size:12px;color:var(--sub)}
.mc .ai{font-size:13px;margin-top:6px;padding-top:6px;border-top:1px dashed var(--line)}
.mc.err{opacity:.7}

/* 사회·예측 */
.kw{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px}
.kw span{background:var(--acc-soft);color:var(--accent);border-radius:12px;padding:2px 10px;font-weight:500}
.news{font-size:13.5px;margin:0;padding:0;list-style:none}
.news li{padding:5px 0;border-top:1px solid var(--line)}
.news li:first-child{border-top:none}
.news .s{color:var(--sub);font-size:12px;margin-left:6px}
.themes{display:grid;gap:8px}
.theme{background:var(--bg);border-radius:4px;padding:10px 12px;font-size:14px}
.theme .top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-weight:700}
.fc .gauge{position:relative;height:56px;margin:18px 6px 8px}
.fc .gauge .ax{position:absolute;left:0;right:0;top:26px;border-top:2px solid var(--line)}
.fc .gauge .band{position:absolute;top:16px;height:22px;border-radius:4px;background:color-mix(in srgb,var(--accent) 22%,transparent);border:1px solid var(--accent)}
.fc .gauge .qb{position:absolute;top:40px;height:6px;border-radius:3px;background:var(--line)}
.fc .gauge .bs{position:absolute;top:8px;height:38px;border-left:2px dotted var(--sub)}
.fc .gauge .lbl{position:absolute;top:-6px;font-size:12px;color:var(--sub);transform:translateX(-50%);white-space:nowrap}
.fc .nums{display:flex;flex-wrap:wrap;gap:6px 22px;align-items:baseline}
.fc .nums .v{font-size:22px;font-weight:700}
.scen{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px;margin-top:12px}
.scen>div{padding:12px 14px;border-radius:4px;font-size:14px;background:var(--bg)}
.scen .강세{background:var(--up-soft)} .scen .약세{background:var(--down-soft)}
.scen b{display:flex;justify-content:space-between}

/* 13개 분야 */
.heat td{font-size:13px}
.heat td.c{color:#16202A}
.heat .nm a{color:inherit;text-decoration:none;font-weight:500}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr));gap:12px;margin-top:14px}
.cat{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--sc,var(--line));border-radius:6px;padding:14px 16px;scroll-margin-top:12px}
.cat .hd{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.cat h3{margin:0;font-size:16px}
.cat h3 small{font-size:12px;color:var(--sub);font-weight:400;margin-left:4px}
.cat .big{font-size:18px;font-weight:700}
.cat .sm{font-size:13px;color:var(--sub)}
.cat .sm b{color:var(--ink);font-weight:500}
.cat .sp{height:54px;margin:6px 0}
.cat .ln{font-size:13.5px;margin-top:3px;display:grid;grid-template-columns:56px 1fr;gap:6px}
.cat .ln em{font-style:normal;color:var(--sub)}
.cat .why{font-size:13.5px;margin-top:8px;padding-top:8px;border-top:1px dashed var(--line)}

/* 기회·리스크 */
.or .item{padding:10px 0;border-top:1px solid var(--line);font-size:14px}
.or .item:first-of-type{border-top:none}
.or .item b{display:block}
.or .how{color:var(--accent);font-weight:500}
.or .sig{color:var(--sub);font-size:13px}
.opp{border-top:4px solid var(--up)} .risk{border-top:4px solid var(--down)}

/* 총론 */
.conc{border:2px solid var(--ink)}
.conc .stance{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px}
.conc .stance .big{font-size:30px;font-weight:700}
.alloc{display:grid;grid-template-columns:minmax(220px,300px) 1fr;gap:18px;align-items:center;margin-top:14px}
.alloc>*{min-width:0}
.alloc .dn{height:250px}
.alloc table.t th,.alloc table.t td{white-space:normal}
.alloc td .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:0}
.plan ol{margin:6px 0 0;padding-left:20px} .plan li{margin:5px 0;font-size:15px}
.plan li::marker{font-weight:700;color:var(--accent)}

/* 초보자용: 쉬운 요약 · 쉽게 말하면 · 연결고리 · 용어 */
.easysum{background:var(--acc-soft);border-radius:6px;padding:16px 20px;margin-top:18px}
.easysum h3{margin:0 0 6px;color:var(--accent)}
.easysum ol{margin:0;padding-left:20px;font-size:16px} .easysum li{margin:4px 0}
.easy{background:var(--warn-soft);border-left:4px solid var(--warn);border-radius:4px;padding:10px 14px;margin:12px 0;font-size:14.5px;max-width:90ch}
.easy b{color:var(--warn);margin-right:6px}
.easy.three div{margin:3px 0} .easy.three b{display:inline-block;min-width:92px}
.chains{display:grid;gap:10px}
.chain{display:flex;flex-wrap:wrap;align-items:center;gap:6px;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px;font-size:14px}
.chain span.node{background:var(--bg);border-radius:4px;padding:4px 10px}
.chain span.node.first{background:var(--down-soft);font-weight:700}
.chain span.node.last{background:var(--up-soft);font-weight:700}
.chain span.arr{color:var(--sub);font-weight:700}
.chain .now{flex-basis:100%;font-size:12.5px;color:var(--sub);margin-top:2px}
.gloss{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,330px),1fr));gap:10px}
.gloss>div{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px 14px;font-size:14px}
.gloss b{display:block;font-size:15px}
.gloss .why{color:var(--sub);font-size:13px;margin-top:2px}
details.more{margin-top:12px} details.more summary{cursor:pointer;color:var(--accent);font-weight:500}

/* 부록 (기존) */
.thermo{display:grid;grid-template-columns:72px 1fr;gap:10px 14px;align-items:stretch;margin-top:12px}
.thermo .mk{font-weight:700;font-size:14px;align-self:center;color:var(--sub)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:6px}
.tile{display:block;text-decoration:none;color:inherit;padding:10px 12px;border-radius:6px;border:1px solid var(--line);background:var(--panel)}
.tile .n{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .c{font-size:18px;font-weight:700}
.tile .s{font-size:12px;color:var(--sub)}
.legend{font-size:12px;color:var(--sub);margin-top:8px}
.scr{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px}
.box{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--c);border-radius:4px;padding:16px 18px}
.box h3{margin:0;font-size:16px}
.box .how{font-size:13px;color:var(--sub);margin:2px 0 10px}
.box ol{margin:0;padding:0;list-style:none;counter-reset:r}
.box li{counter-increment:r;display:grid;grid-template-columns:22px 1fr;gap:0 8px;padding:10px 0;border-top:1px solid var(--line)}
.box li::before{content:counter(r);font-weight:700;color:var(--c);font-size:15px}
.box .nm{font-weight:700}
.box .tk{font-size:12px;color:var(--sub);font-weight:400;margin-left:6px}
.box .mt2{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12.5px;color:var(--sub);margin:2px 0}
.box .mt2 b{color:var(--ink);font-weight:500}
.box .rs{font-size:13.5px}
.box .empty{font-size:14px;color:var(--sub);padding:8px 0}
.tbl{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:4px}
.tbl table{border-collapse:collapse;width:100%;font-size:14px;min-width:760px}
.tbl th,.tbl td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl th{font-weight:500;color:var(--sub);background:var(--bg)}
.tbl td:first-child,.tbl th:first-child{text-align:left}
.tbl tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:500}
.badge.강세{background:var(--up-soft);color:var(--up)}
.badge.약세{background:var(--down-soft);color:var(--down)}
.badge.중립{background:var(--bg);color:var(--sub);border:1px solid var(--line)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:16px 18px;scroll-margin-top:12px}
.card .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.card h3{margin:0;font-size:17px}
.card .code{color:var(--sub);font-size:13px;font-weight:400;margin-left:6px}
.card .px{font-size:20px;font-weight:700}
.card .chg{font-size:13px;color:var(--sub)}
.card .cm{font-size:14px;margin:8px 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
.chip{font-size:12px;padding:2px 8px;border-radius:3px}
.chip.bull{background:var(--up-soft);color:var(--up)}
.chip.bear{background:var(--down-soft);color:var(--down)}
.chip.warn{background:var(--warn-soft);color:var(--warn)}
.cv1{height:190px} .cv2{height:110px;margin-top:6px}
@media (max-width:760px){
  .wrap{padding:18px 14px 48px}
  header h1{font-size:23px}
  .sum{grid-template-columns:1fr}
  .pctl .row{grid-template-columns:1fr;gap:4px}
  .pctl .val{text-align:left}
  .alloc{grid-template-columns:1fr}
  .thermo{grid-template-columns:1fr;gap:4px}
  .tiles{grid-template-columns:repeat(3,1fr)}
}
footer{margin-top:44px;font-size:12px;color:var(--sub);border-top:1px solid var(--line);padding-top:14px;max-width:90ch}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const DATA = __DATA__;
const bp2pp = s => String(s ?? "").replace(/([+\-−]?)(\d+(?:\.\d+)?)\s?bp(?![A-Za-z])/g, (m, g, n) => (g === "−" ? "-" : g) + (Number(n) / 100).toFixed(2) + "%p");
const esc = s => bp2pp(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const cls = v => v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat";
const pct = (v, d = 2) => v == null ? "–" : (v > 0 ? "+" : "") + Number(v).toFixed(d) + "%";
const bp = v => v == null ? "–" : (v > 0 ? "+" : "") + (v / 100).toFixed(2) + "%p";
const num = (v, d = 2) => v == null ? "–" : Number(v).toLocaleString("ko-KR", {maximumFractionDigits: d});
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const chgOf = (a, k) => a.kind === "rate" ? bp(a[k]) : pct(a[k], 1);
const lvOf = a => a.kind === "rate" ? Number(a.last).toFixed(2) + "%" : num(a.last, a.last < 10 ? 3 : 2);
const stanceCls = s => /확대|늘리기|매수|상승|강세|유입|기회/.test(s || "") ? "pos" : /축소|방어|줄이기|현금|하락|약세|유출|조심|위험/.test(s || "") ? "neg" : "mid";
const rank5 = p => p == null ? "–" : p >= 50 ? `최근 5년 중 상위 ${Math.max(1, 100 - Math.round(p))}%` : `최근 5년 중 하위 ${Math.max(1, Math.round(p))}%`;
const zone5 = (p, rate) => p == null ? "" : p >= 80 ? (rate ? "높은 구간" : "비싼 구간") : p <= 20 ? (rate ? "낮은 구간" : "싼 구간") : "중간 구간";
const SECW = {"비중확대": "🟢 기회 (늘리기)", "중립": "🟡 관망", "비중축소": "🔴 조심 (줄이기)"};
const secWord = s => SECW[s] || s || "–";
const list = a => (a || []).filter(Boolean);
const V = DATA.view || {}, RB = !!V.rule_based;
const M = DATA.macro || {}, SC = DATA.screens || {}, NW = DATA.news || {};
const A = Object.fromEntries((M.assets || []).map(a => [a.key, a]));
const ALLOC = [["kr_equity","국내 주식","--c2"],["us_equity","미국 주식","--c4"],["gold_commodities","금·원자재(현물)","--c3"],
               ["usd_cash","달러 현금성","--c1"],["krw_cash_bonds","원화 현금·채권","--c5"],["alternatives","대체자산(비트코인 등)","--c6"]];
const rbNote = what => RB ? `<p class="note">오늘은 AI 해설이 제때 도착하지 않아, ${what}은(는) 데이터로 계산한 쉬운 요약으로 대신합니다.</p>` : "";
const sparks = [];
const EZ = V.easy || {};
const easyBox = t => !t ? "" : typeof t === "string" ? `<div class="easy"><b>쉽게 말하면</b>${esc(t)}</div>`
  : `<div class="easy three">${t.one ? `<div><b>한 줄 결론</b>${esc(t.one)}</div>` : ""}${t.why ? `<div><b>왜 그럴까</b>${esc(t.why)}</div>` : ""}${t.do ? `<div><b>그래서 오늘은</b>${esc(t.do)}</div>` : ""}</div>`;
const BASIC_TERMS = [
  ["백분위 (5년)", "최근 5년 동안의 값을 낮은 순으로 줄 세웠을 때 지금이 어디쯤인지. 0이면 5년 중 최저, 100이면 최고, 50이면 중간."],
  ["작년 동기 대비 (YoY)", "1년 전 같은 날과 비교해 얼마나 올랐거나 내렸는지."],
  ["bp (베이시스포인트)", "금리 변화 단위. 1bp = 0.01%포인트. 금리가 4.00%에서 4.25%가 되면 25bp 상승."],
  ["미국채 10년 금리", "미국 정부가 10년 동안 돈을 빌릴 때 내는 이자율. 전 세계 대출·주식 가치의 기준이 되어, 오르면 주식(특히 성장주)에 부담."],
  ["장단기 금리차 (10Y−2Y)", "10년 금리 − 2년 금리. 보통은 플러스인데 마이너스(역전)가 되면 시장이 경기 둔화를 걱정한다는 신호."],
  ["달러 인덱스", "유로·엔 등 주요 통화 대비 달러 가치. 오르면 달러가 강해져 신흥국(한국) 주식에서 외국인 돈이 빠지기 쉬움."],
  ["원/달러 환율", "1달러를 사는 데 필요한 원화. 오르면(원화 약세) 수출 기업엔 유리하지만 외국인 투자자에겐 손실 요인."],
  ["VIX (공포지수)", "앞으로 한 달간 미국 주식시장이 얼마나 출렁일지에 대한 예상치. 20 아래면 평온, 30 위면 공포."],
  ["구리/금 비율", "구리는 공장·건설에 쓰여 경기가 좋을 때, 금은 불안할 때 오름. 구리가 금보다 강하면 경기 기대, 약하면 경기 걱정."],
  ["PER (주가수익비율)", "주가가 1년 이익의 몇 배인지. 높을수록 비싸거나 성장 기대가 큰 것. 같은 업종끼리 비교해야 의미가 있음."],
  ["PBR (주가순자산비율)", "주가가 회사 순자산(장부상 가치)의 몇 배인지. 1 미만이면 장부 가치보다 싸게 거래되는 것."],
  ["이동평균선 (20·60·120일)", "최근 N일 종가의 평균. 주가가 평균선 위에 있으면 상승 흐름, 아래면 하락 흐름으로 봄."],
  ["RSI", "최근 오른 힘과 내린 힘의 비율(0~100). 70 이상이면 너무 많이 올라 과열, 30 이하면 너무 많이 내려 과매도."],
  ["MACD · TSI", "주가 흐름의 '힘(모멘텀)'을 재는 지표. 신호선을 위로 뚫으면 오름세가 강해지는 신호, 아래로 뚫으면 약해지는 신호."],
  ["추세 점수 (−6~+6)", "이동평균·RSI·MACD·TSI 6가지를 각각 +1/−1로 더한 점수. +3 이상 강세, −3 이하 약세."],
  ["상대강도 (시장 대비)", "그 분야 수익률에서 전체 시장 수익률을 뺀 값. 플러스면 시장보다 잘 오른(덜 내린) 분야."],
  ["거래대금 비율", "최근 5일 평균 거래대금 ÷ 60일 평균. 1보다 크면 평소보다 돈이 많이 오가는 중(관심 증가)."],
  ["유동성 장세 · 실적 장세", "유동성 장세는 금리 인하 등으로 풀린 돈이 주가를 올리는 시기, 실적 장세는 기업 이익이 늘어 주가가 오르는 시기."],
  ["예상 등락 범위", "오늘 지수가 움직일 것으로 예상되는 일반적인 범위. 대략 3번 중 2번은 이 안에서 끝난다는 뜻."],
  ["EWY", "미국 시장에 상장된 한국 주식 ETF. 한국 장이 닫힌 밤사이 외국인이 한국을 어떻게 보는지 알려 주는 선행 지표."],
];
const items = Object.entries(DATA.results || {});
const ok = items.filter(([, r]) => !r.error), failed = items.filter(([, r]) => r.error);
let h = "";

// ── 머리말 ──
h += `<header><div><span class="kicker">${esc(DATA.slot_name)} · ${esc(DATA.today)}</span>
<h1>${esc(V.headline || "오늘의 시장 브리핑")}</h1></div>
<div class="meta">데이터 수집 ${esc(DATA.collected_at)} KST · ${RB ? "데이터 기반 요약(AI 해설 지연)" : "AI 분석 반영"}
  <br><span class="k">수치 기준: ${A.kospi ? `코스피 ${esc(A.kospi.date.slice(5).replace("-", "/"))} 종가` : ""}${A.spx ? ` · 미국 ${esc(A.spx.date.slice(5).replace("-", "/"))} 종가` : ""} (리포트 전체 같은 기준)</span>
  <nav class="nav">${DATA.prev ? `<a href="report_${esc(DATA.prev)}.html">← 이전 브리핑</a>` : ""}
  <a href="#sec-conclusion">결론 바로 보기</a><a href="archive.html">지난 리포트 전체</a></nav></div></header>`;

// ── 오늘의 쉬운 요약 ──
if (list(EZ.summary).length) h += `<div class="easysum" id="easy-sum"><h3>오늘 시장, 이것만 알면 됩니다</h3><ol>${EZ.summary.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
  <p class="k" style="margin:8px 0 0">처음 보는 용어는 아래 <a href="#glossary">용어 풀이</a>에서 확인하세요.</p></div>`;

// ── 오늘의 결론 요약 ──
const st = V.stance || {}, fc = V.forecast || {}, al = V.allocation || {};
h += `<div class="sum" id="sum">
 <div class="panel"><span class="k">오늘의 투자 자세</span><div class="big">${esc(st.label || "–")}</div><div class="one">${esc(st.one_liner || "")}</div></div>
 <div class="panel"><span class="k">${esc(fc.market || "시장")} 예상 밴드</span>
   <div class="big">${fc.band_low ? num(fc.band_low, 0) + " ~ " + num(fc.band_high, 0) : "–"}</div>
   <div class="one">${esc(fc.direction || "")}${fc.prob_up != null ? ` · 상승 확률 ${Math.round(fc.prob_up)}%` : ""}</div></div>
 <div class="panel"><span class="k">자산 배분</span>
   <div class="stack">${ALLOC.map(([k, , c]) => `<i style="width:${al[k] || 0}%;background:var(${c})" title="${k}"></i>`).join("")}</div>
   <div class="leg">${ALLOC.filter(([k]) => al[k]).map(([k, n, c]) => `<span style="--c:var(${c})">${n} <b>${al[k]}%</b></span>`).join("")}</div></div>
</div>`;

// ── ① 과거 대비 ──
const HC = V.history_context || {};
h += `<h2 id="sec-history"><span class="no">1</span>과거 대비 현재 시장 진단</h2>
<p class="lead">작년 이맘때, 그리고 최근 5년과 비교해 지금이 높은지 낮은지를 봅니다.</p>`;
if (!RB && HC.summary) {
  const rg = HC.regime || {};
  h += `<div class="panel hist-ai"><p class="txt">${esc(HC.summary)}</p>
   <div class="regime">${[["장세 판단", rg.market_type], ["주도 섹터 이동", rg.leadership_shift], ["금리·환율 흐름", rg.rate_fx]].filter(x => x[1]).map(([k, v]) => `<div><b>${k}</b>${esc(v)}</div>`).join("")}</div>
   <div class="grid2"><div><h3>과거와 같은 점</h3><ul class="clean">${list(HC.same).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
   <div><h3>결정적으로 달라진 점</h3><ul class="clean">${list(HC.different).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div></div>`;
} else h += rbNote("과거 대비 해설");
h += easyBox(EZ.history);
// 5년 월별 그래프 + 문장 설명 (1년 전 → 지금, 5년 중 높고 낮음, 최고점 대비)
const KEY6 = ["kospi", "spx", "usdkrw", "us10y", "vix", "gold"];
const REST = ["kosdaq", "ndx", "sox", "dxy", "us2y", "curve", "wti", "copper", "btc"];
const histCharts = [];
const fmtv = (a, v) => v == null ? "–" : a.kind === "rate" ? Number(v).toFixed(2) + "%" : num(v, v < 10 ? 3 : v < 1000 ? 1 : 0);
const ym = d => d ? d.slice(2, 4) + "." + d.slice(5, 7) : "";
const lvlWord = p => p == null ? "–" : p >= 80 ? "매우 높은 편" : p >= 60 ? "높은 편" : p >= 40 ? "중간" : p >= 20 ? "낮은 편" : "매우 낮은 편";
const monthly = s => { const m = new Map(); for (const p of s || []) m.set(p[0].slice(0, 7), p); return [...m.values()]; };
function histCard(k) {
  const a = A[k];
  if (!a || a.error || !(a.spark || []).length) return "";
  const s = a.spark;
  let hi = s[0], lo = s[0];
  for (const p of s) { if (p[1] > hi[1]) hi = p; if (p[1] < lo[1]) lo = p; }
  const rate = a.kind === "rate";
  // 고점·저점 대비 (금리는 %p 차이, 그 밖은 %)
  const dd = rate ? (a.last - hi[1]) * 100 : (a.last / hi[1] - 1) * 100;     // 최고점 대비 (음수)
  const ru = rate ? (a.last - lo[1]) * 100 : (a.last / lo[1] - 1) * 100;     // 최저점 대비 (양수)
  const big = rate ? 50 : 20, mid = rate ? 25 : 10;                           // 큰 하락/조정 기준 (bp / %)
  const m3 = a.chg_3m, m3big = rate ? 30 : 8;
  const hiDays = (Date.parse(s[s.length - 1][0]) - Date.parse(hi[0])) / 864e5;
  const loDays = (Date.parse(s[s.length - 1][0]) - Date.parse(lo[0])) / 864e5;
  // 지금 상태: 최근 흐름을 먼저 판단하고, 5년 위치는 그 뒤에 덧붙인다
  let state, tone;
  if (dd <= -big && hiDays < 540) { state = `최근 고점에서 크게 하락한 상태`; tone = "neg"; }
  else if (dd <= -mid && hiDays < 540) { state = `최근 고점에서 조정 중`; tone = "mid"; }
  else if (ru >= (rate ? 50 : 20) && loDays < 540 && (m3 ?? 0) > 0) { state = `최근 저점에서 크게 반등한 상태`; tone = "pos"; }
  else if (m3 != null && m3 >= m3big) { state = `최근 3개월 상승 흐름`; tone = "pos"; }
  else if (m3 != null && m3 <= -m3big) { state = `최근 3개월 하락 흐름`; tone = "neg"; }
  else { state = `최근 3개월 큰 변화 없음`; tone = ""; }
  let pos5 = `5년 전체로 보면 ${lvlWord(a.pct_5y)}`;
  if ((a.pct_5y ?? 50) >= 60 && tone === "neg") pos5 += `이지만, 최근 고점보다는 크게 낮아진 상태`;
  else if ((a.pct_5y ?? 50) <= 40 && tone === "pos") pos5 += `이지만, 최근에는 오르는 중`;
  const dChg = v => rate ? bp(v) : pct(v, 1);
  histCharts.push(["hc-" + k, a]);
  return `<div class="hcard"><div class="hd"><b>${esc(a.name)}</b><span class="lv">${lvOf(a)}</span></div>
    <div class="state"><span class="pill ${tone}">${state}</span></div>
    <div class="hch"><canvas id="hc-${k}" aria-label="${esc(a.name)} 5년 월별 그래프"></canvas></div>
    <ul class="hl">
      <li><span>최근 고점 대비</span>${ym(hi[0])} 최고 ${fmtv(a, hi[1])} → 지금 <b class="${cls(dd)}">${dChg(dd)}</b>${m3 != null ? ` · 최근 3개월 <b class="${cls(m3)}">${chgOf(a, "chg_3m")}</b>` : ""}</li>
      <li><span>1년 전 → 지금</span><b>${fmtv(a, a.year_ago)} → ${fmtv(a, a.last)}</b> <b class="${cls(a.yoy)}">(${chgOf(a, "yoy")})</b></li>
      <li><span>5년 전체</span>${pos5} · 최저 ${fmtv(a, lo[1])}(${ym(lo[0])}) ~ 최고 ${fmtv(a, hi[1])}(${ym(hi[0])})</li>
    </ul></div>`;
}
h += `<p class="k mt" style="margin-bottom:6px">그래프 읽는 법: 최근 5년 월별 값입니다. <b style="color:var(--sub)">○ 1년 전</b> · <b>● 지금</b> · 점선 = 3년 평균. 금리는 %, 그 밖은 지수·가격입니다.</p>
<div class="hgrid hist-key">${KEY6.map(histCard).join("")}</div>
<details class="more"><summary>나머지 자산 ${REST.filter(k => A[k] && !A[k].error).length}개 그래프 보기</summary><div class="hgrid mt">${REST.map(histCard).join("")}</div></details>`;
const AN = M.analogs || {};
const AC = ["--c2", "--c4", "--c3"];     // 사례별 색
const analogCharts = [];
if ((AN.matches || []).length) {
  const FT = AN.features || {}, unitOf = {pct: "%", rate: "%", pp: "%p", num: ""};
  const fv = (k, v) => v == null ? "–" : (FT[k] && FT[k][1] === "pct" && v > 0 ? "+" : "") + num(v, 2) + (unitOf[(FT[k] || [])[1]] || "");
  const aiA = list(HC.analogs);
  const ymKo = d => `${d.slice(0, 4)}년 ${+d.slice(5, 7)}월`;
  h += `<div class="analog mt"><h3>지금과 비슷했던 과거 사례 — ${esc((AN.since || "").slice(0, 4))}년 이후 약 ${new Date().getFullYear() - Number((AN.since || "2007").slice(0, 4))}년 중</h3>
  <p class="k" style="margin:0 0 8px">코스피가 1년 고점에서 얼마나 내려왔는지, 6개월 흐름, 미국 금리, 환율, 공포지수(VIX), 구리/금 비율이 지금과 가장 비슷했던 때를 데이터로 찾았습니다.
  아래 그래프는 <b>그 시점(0주)을 100으로 맞춰</b> 그 전 1년과 그 뒤 6개월을 겹친 것입니다. 검은 선이 지금, 색 선이 과거 사례입니다.</p>
  <div class="grid2"><div class="panel"><h3>코스피 — 지금 vs 과거 사례</h3><div class="ach"><canvas id="an-kospi"></canvas></div></div>
  <div class="panel"><h3>S&amp;P 500 — 지금 vs 과거 사례</h3><div class="ach"><canvas id="an-spx"></canvas></div></div></div>
  <div class="grid3 mt">` + AN.matches.map((m, i) => {
    const x = aiA.find(a => a.date === m.date) || aiA[i] || {};
    const keys = ["kospi_dd", "kospi_6m", "us10y", "usdkrw", "vix"].filter(k => k in (m.state || {}));
    const res = (k, l) => m[k] == null ? "" : `${l} <b class="${cls(m[k])}">${pct(m[k], 1)}</b>`;
    const auto = `그때도 코스피가 1년 고점에서 ${num(Math.abs(m.state.kospi_dd ?? 0), 0)}% 내려와 있었습니다(지금 ${num(Math.abs((AN.now || {}).kospi_dd ?? 0), 0)}%). `
      + `그 뒤 코스피는 3개월 ${pct(m.kospi_13w, 1)}, 6개월 ${pct(m.kospi_26w, 1)} 움직였습니다.`;
    return `<div class="panel acard" style="border-top:4px solid var(${AC[i % 3]})">
      <h3>${esc(x.period || ymKo(m.date))}</h3><div class="k">데이터 유사도 ${m.similarity} / 100</div>
      ${!RB && x.what_happened ? `<p class="txt" style="margin:8px 0 6px">${esc(x.what_happened)}</p>` : `<p class="txt" style="margin:8px 0 6px">${esc(auto)}</p>`}
      <table class="t"><thead><tr><th></th><th>그때</th><th>지금</th></tr></thead><tbody>${keys.map(k => `<tr><td>${esc(FT[k][0])}</td><td>${fv(k, m.state[k])}</td><td><b>${fv(k, (AN.now || {})[k])}</b></td></tr>`).join("")}</tbody></table>
      <p style="margin:8px 0 4px;font-size:14px"><b>그 뒤 코스피</b> ${[res("kospi_4w", "1개월"), res("kospi_13w", "3개월"), res("kospi_26w", "6개월")].filter(Boolean).join(" · ")}<br>
      <b>그 뒤 S&amp;P</b> ${[res("spx_4w", "1개월"), res("spx_13w", "3개월"), res("spx_26w", "6개월")].filter(Boolean).join(" · ")}</p>
      ${!RB && x.why_similar ? `<div class="ln2"><em>닮은 점</em>${esc(x.why_similar)}</div>` : ""}
      ${!RB && x.what_differs ? `<div class="ln2"><em>다른 점</em>${esc(x.what_differs)}</div>` : ""}
      ${!RB && x.lesson ? `<div class="easy" style="margin-bottom:0"><b>그래서 지금은</b>${esc(x.lesson)}</div>` : ""}</div>`;
  }).join("") + `</div><p class="k" style="margin-top:6px">과거와 비슷하다고 같은 결과가 반복되는 것은 아닙니다. 그때 무엇이 시장을 바꿨는지를 참고하는 용도입니다.</p></div>`;
  analogCharts.push(["an-kospi", "now_path_kospi", "path_kospi"], ["an-spx", "now_path_spx", "path_spx"]);
}

// ── ② 매크로 ──
h += `<h2 id="sec-macro"><span class="no">2</span>매크로 · 환율 · 금리 · 현물 동향</h2><p class="lead">5년 주간 차트(점선 = 3년 평균). 금리 변화는 bp(0.01%p) 단위입니다.</p>`;
if ((M.regimes || []).length) h += `<div class="regime regimes">${M.regimes.map(r => `<div><b>${esc(r.label)}</b><span class="pill ${stanceCls(r.value)}">${esc(r.value)}</span><div class="k">${esc(r.evidence)}</div></div>`).join("")}</div>`;
const MV = V.macro || {};
if (!RB && MV.summary) h += `<div class="panel macro-ai"><p class="txt" style="margin:0">${esc(MV.summary)}</p></div>`;
h += easyBox(EZ.macro);
const aiAsset = Object.fromEntries(list(MV.assets).map(x => [x.name, x]));
const groups = [...new Set((M.assets || []).map(a => a.group))];
for (const g of groups) {
  h += `<div class="mgrp"><h3>${esc(g)}</h3><div class="mcards">`;
  for (const a of M.assets.filter(x => x.group === g)) {
    if (a.error) { h += `<div class="mc err"><div class="nm">${esc(a.name)}</div><div class="k">데이터 없음</div></div>`; continue; }
    const x = aiAsset[a.name];
    h += `<div class="mc"><div class="hd"><span class="nm">${esc(a.name)}</span><span class="lv">${lvOf(a)}</span></div>
      <div class="ch"><span>1일 <b class="${cls(a.chg_1d)}">${chgOf(a, "chg_1d")}</b></span><span>1개월 <b class="${cls(a.chg_1m)}">${chgOf(a, "chg_1m")}</b></span><span>1년 <b class="${cls(a.yoy)}">${chgOf(a, "yoy")}</b></span></div>
      <div class="sp"><canvas id="ms-${a.key}"></canvas></div>
      <div class="pc">${rank5(a.pct_5y)} (${zone5(a.pct_5y, a.kind === "rate")}) · 5년 범위 ${num(a.min_5y)}~${num(a.max_5y)} · 장기 흐름 ${esc(a.trend || "–")}</div>
      ${x ? `<div class="ai"><span class="pill ${stanceCls(x.view)}">${esc(x.view)}</span> ${esc(x.level_comment)} ${x.impact ? "→ " + esc(x.impact) : ""}</div>` : ""}</div>`;
    sparks.push(["ms-" + a.key, a.spark, a.avg_3y]);
  }
  h += `</div></div>`;
}

// ── ③ 사회 흐름 · 예측 ──
const SO = V.social || {};
h += `<h2 id="sec-forecast"><span class="no">3</span>사회적 흐름과 ${DATA.slot === "am" ? "오늘 국내 증시" : "오늘 밤 미국 증시"} 예측</h2>
<p class="lead">최근 36시간 국내외 경제·사회 뉴스 ${NW.count || 0}건에서 뽑은 흐름과, 밤사이 시장 흐름으로 계산한 예상 범위에 뉴스를 더한 예측입니다.</p>
${list(V.chains).length ? `<h3>오늘 시장의 연결고리 — 무엇이 무엇을 움직이나</h3><div class="chains" id="chains">${V.chains.map(c =>
  `<div class="chain"><span class="node first">${esc(c.from)}</span>${list(c.steps).map(s => `<span class="arr">→</span><span class="node">${esc(s)}</span>`).join("")}<span class="arr">→</span><span class="node last">${esc(c.so)}</span>${c.now ? `<span class="now">지금: ${esc(c.now)}</span>` : ""}</div>`).join("")}</div><div class="mt"></div>` : ""}
<div class="grid2 social"><div class="panel"><h3>뉴스 키워드</h3>
  <div class="kw">${list((NW.keywords || {}).ko).slice(0, 12).map(([w, n]) => `<span>${esc(w)} ${n}</span>`).join("")}</div>
  <div class="kw">${list((NW.keywords || {}).en).slice(0, 10).map(([w, n]) => `<span>${esc(w)} ${n}</span>`).join("")}</div>
  <h3 class="mt">주요 헤드라인</h3><ul class="news">${list(NW.items).filter(i => i.lang === "ko").slice(0, 6).concat(list(NW.items).filter(i => i.lang === "en").slice(0, 4)).map(i => `<li>${esc(i.title)}<span class="s">${esc(i.source)} ${esc(i.time)}</span></li>`).join("") || "<li>수집된 뉴스가 없습니다.</li>"}</ul></div>
 <div class="panel"><h3>사회·정책·지정학 → 시장 반영</h3>${!RB && SO.summary ? `<p class="txt">${esc(SO.summary)}</p>` : rbNote("사회 흐름 해설")}
  <div class="themes">${list(SO.themes).map(t => `<div class="theme"><div class="top"><span>${esc(t.theme)}</span><span class="pill acc">${esc(t.channel)}</span></div>
   <div>${esc(t.impact)}</div><div class="k">가격 반영: ${esc(t.priced_in)} · 선행 신호: ${esc(t.signal)}</div></div>`).join("")}</div></div></div>`;
const Q = M.quant || {};
const lo = Math.min(fc.band_low ?? Infinity, Q.band_low ?? Infinity), hi = Math.max(fc.band_high ?? -Infinity, Q.band_high ?? -Infinity);
const pad = (hi - lo) * 0.25 || 1, L = lo - pad, R = hi + pad, X = v => ((v - L) / (R - L) * 100).toFixed(2);
h += `<div class="panel fc mt"><h3>${esc(fc.market || Q.target || "지수")} ${DATA.slot === "am" ? "오늘" : "오늘 밤"} 예상</h3>
 <div class="nums"><span>방향 <span class="v ${stanceCls(fc.direction)}" style="color:var(${/상승/.test(fc.direction) ? "--up" : /하락/.test(fc.direction) ? "--down" : "--sub"})">${esc(fc.direction || "–")}</span></span>
  <span>예상 밴드 <span class="v">${fc.band_low ? num(fc.band_low, 0) + " ~ " + num(fc.band_high, 0) : "–"}</span></span>
  <span>상승 확률 <span class="v">${fc.prob_up != null ? Math.round(fc.prob_up) + "%" : "–"}</span></span>
  <span class="k">기준 ${num(fc.base_level ?? Q.base_close, 2)}</span></div>
 ${isFinite(lo) && isFinite(hi) ? `<div class="gauge"><div class="ax"></div>
   ${Q.band_low ? `<div class="qb" style="left:${X(Q.band_low)}%;width:${X(Q.band_high) - X(Q.band_low)}%" title="밤사이 시장 흐름으로 계산한 일반적인 예상 등락 범위"></div>` : ""}
   ${fc.band_low ? `<div class="band" style="left:${X(fc.band_low)}%;width:${X(fc.band_high) - X(fc.band_low)}%"></div>
     <span class="lbl" style="left:${X(fc.band_low)}%">${num(fc.band_low, 0)}</span><span class="lbl" style="left:${X(fc.band_high)}%">${num(fc.band_high, 0)}</span>` : ""}
   ${Q.base_close ? `<div class="bs" style="left:${X(Q.base_close)}%"></div>` : ""}</div>
   <div class="k">색 막대 = ${RB ? "데이터" : "AI"} 예상 범위 · 회색 막대 = 밤사이 미국 시장 흐름으로 계산한 일반적인 예상 등락 범위(${esc(Q.driver || "")}) · 점선 = 어제 종가</div>` : ""}
 ${fc.open_view ? `<div class="grid2 mt"><div><h3>개장·초반</h3><p class="txt">${esc(fc.open_view)}</p></div><div><h3>장중 흐름</h3><p class="txt">${esc(fc.intraday)}</p></div></div>` : ""}
 ${fc.secondary ? `<p class="txt"><b>${DATA.slot === "am" ? "코스닥" : "나스닥"}</b> ${esc(fc.secondary)}</p>` : ""}
 ${list(fc.scenarios).length ? `<div class="scen">${fc.scenarios.map(s => `<div class="${esc(s.name)}"><b><span>${esc(s.name)} 시나리오</span><span>${s.prob != null ? s.prob + "%" : ""}</span></b>${esc(s.trigger)}<div class="k">${esc(s.path)}</div></div>`).join("")}</div>` : ""}
 ${list(fc.focus_sectors).length ? `<p class="mt" style="margin-bottom:0"><b>오늘 집중할 분야</b> ${fc.focus_sectors.map(s => `<span class="pill acc">${esc(s)}</span>`).join(" ")}</p>` : ""}
 ${fc.adjustment ? `<p class="k" style="margin:8px 0 0">기준선 대비 조정: ${esc(fc.adjustment)}</p>` : ""}</div>`;
h += easyBox(EZ.forecast);

// ── ④ 13개 분야 ──
const CATS = SC.categories || [];
const aiSec = Object.fromEntries(list(V.sectors).map(s => [s.name, s]));
const LD = SC.leadership || {};
h += `<h2 id="sec-sectors"><span class="no">4</span>${CATS.length}개 분야 전수 브리핑</h2>
<p class="lead">분야마다 대표 종목들의 평균 주가 흐름입니다. "시장 평균 대비 힘"이 플러스면 시장 평균보다 잘 오른 분야, "상승 흐름 종목 비율"은 그 분야에서 최근 한 달 오름세를 타는 종목의 비율, "거래 활발도"가 1보다 크면 평소보다 사고파는 돈이 많은 상태입니다.
${LD.now ? `지금 가장 힘센 분야: <b>${LD.now.map(esc).join(", ")}</b> / 1년 전엔: <b>${(LD.year_ago || []).map(esc).join(", ")}</b>` : ""}</p>`;
if (CATS.length) {
  const cell = (v, s = 10) => { if (v == null) return `<td>–</td>`; const t = Math.min(Math.abs(v) / s, 1);
    return `<td style="background:color-mix(in srgb, var(${v >= 0 ? "--up" : "--down"}) ${Math.round(t * 45)}%, var(--panel))">${(v > 0 ? "+" : "") + v.toFixed(1)}</td>`; };
  h += `<div class="panel scroll heat" style="padding:6px 8px"><table class="t"><thead><tr><th>분야</th><th>판단</th><th>1일</th><th>5일</th><th>20일</th><th>60일</th><th>1년</th><th>시장 평균 대비 힘(60일)</th><th>1년 전의 힘</th><th>힘의 위치(3년 중)</th><th>상승 흐름 종목 비율</th><th>거래 활발도</th><th>돈의 흐름</th></tr></thead><tbody>` +
    CATS.map((c, i) => { const s = aiSec[c.name] || {};
      return `<tr><td class="nm"><a href="#c-${i}">${esc(c.name)}</a></td><td>${s.stance ? `<span class="pill ${stanceCls(secWord(s.stance))}">${esc(secWord(s.stance))}</span>` : "–"}</td>
      ${cell(c.ret_1d, 3)}${cell(c.ret_5d, 6)}${cell(c.ret_20d, 12)}${cell(c.ret_60d, 20)}${cell(c.ret_1y, 50)}${cell(c.rs_60d, 12)}${cell(c.rs_60d_1y_ago, 12)}
      <td>${c.rs_pct_3y ?? "–"}</td><td>${c.breadth ?? "–"}%</td><td>${c.turnover_ratio != null ? c.turnover_ratio.toFixed(2) + "배" : "–"}</td><td>${esc(c.flow || "–")}</td></tr>`; }).join("") + `</tbody></table></div>
  <p class="k" style="margin:6px 0 0">표 읽는 법: 빨간 칸은 오른 것, 파란 칸은 내린 것(진할수록 큼). "1년 전의 힘"과 비교하면 시장을 이끄는 분야가 바뀌었는지 알 수 있어요.</p>`;
  h += easyBox(EZ.sectors);
  h += `<div class="cats">`;
  CATS.forEach((c, i) => { const s = aiSec[c.name] || {};
    const scol = /확대/.test(s.stance) ? "var(--up)" : /축소/.test(s.stance) ? "var(--down)" : "var(--line)";
    h += `<section class="cat" id="c-${i}" style="--sc:${scol}"><div class="hd"><h3>${esc(c.name)}<small>${c.n}종목</small></h3>
      <span>${s.stance ? `<span class="pill ${stanceCls(secWord(s.stance))}">${esc(secWord(s.stance))}</span> ` : ""}<span class="big ${cls(c.ret_20d)}">${pct(c.ret_20d, 1)}</span><span class="sm"> 20일</span></span></div>
      <div class="sm">60일 <b class="${cls(c.ret_60d)}">${pct(c.ret_60d, 1)}</b> · 1년 <b class="${cls(c.ret_1y)}">${pct(c.ret_1y, 1)}</b> · 시장 평균 대비 <b class="${cls(c.rs_60d)}">${pct(c.rs_60d, 1)}</b> (1년 전 ${pct(c.rs_60d_1y_ago, 1)}) · 순위 ${c.rank_60d ?? "–"}위 (1년 전 ${c.rank_60d_1y_ago ?? "–"}위)</div>
      <div class="sp"><canvas id="cs-${i}"></canvas></div>
      <div class="ln"><em>돈의 흐름</em><span>${esc(c.flow || "–")} · 거래 활발도 ${c.turnover_ratio ?? "–"}배 · 상승 흐름 종목 ${c.breadth ?? "–"}%</span></div>
      <div class="ln"><em>실적</em><span>매출성장 중앙값 ${pct(c.rev_g, 1)}${c.pe_kr != null || c.pe_us != null ? ` · PER ${[c.pe_kr != null ? "국내 " + c.pe_kr + "배" : "", c.pe_us != null ? "미국 " + c.pe_us + "배" : ""].filter(Boolean).join(" / ")}` : ""}</span></div>
      ${c.best ? `<div class="ln"><em>5일</em><span>강 ${esc(c.best[0])} <span class="${cls(c.best[1])}">${pct(c.best[1], 1)}</span>${c.worst ? ` · 약 ${esc(c.worst[0])} <span class="${cls(c.worst[1])}">${pct(c.worst[1], 1)}</span>` : ""}</span></div>` : ""}
      ${c.value_pick ? `<div class="ln"><em>저평가</em><span>${esc(c.value_pick[0])} (${esc(c.value_pick[1])})</span></div>` : ""}
      ${c.growth_pick ? `<div class="ln"><em>성장</em><span>${esc(c.growth_pick[0])} (${esc(c.growth_pick[1])})</span></div>` : ""}
      ${c.risk_names && c.risk_names.length ? `<div class="ln"><em>고평가</em><span>${c.risk_names.map(esc).join(", ")}</span></div>` : ""}
      ${s.why ? `<div class="why">${esc(s.why)}${s.vs_past ? `<div class="k">과거 대비: ${esc(s.vs_past)}</div>` : ""}${s.trigger ? `<div class="k">전환 조건: ${esc(s.trigger)}</div>` : ""}</div>` : ""}
    </section>`;
    sparks.push(["cs-" + i, c.spark, null]); });
  h += `</div>`;
} else h += `<div class="err">${esc(SC.error || "분야 데이터가 없습니다.")}</div>`;

// ── ⑤ 기회·리스크 ──
h += `<h2 id="sec-opprisk"><span class="no">5</span>핵심 기회 요인 &amp; 조심할 리스크</h2>`;
if (RB) h += rbNote("기회·리스크");
const OP = list(V.opportunities), RK = list(V.risks);
if (OP.length || RK.length) h += `<div class="grid2 or">
 <div class="panel opp"><h3>지금 이익을 노릴 곳</h3>${OP.map(o => `<div class="item"><b>${esc(o.title)}</b>${esc(o.why)}<div class="how">대응: ${esc(o.how)}</div>${list(o.sectors).length ? `<div class="sig">관련: ${o.sectors.map(esc).join(", ")}</div>` : ""}</div>`).join("")}</div>
 <div class="panel risk"><h3>조심할 것</h3>${RK.map(o => `<div class="item"><b>${esc(o.title)} <span class="pill ${o.severity === "높음" ? "pos" : o.severity === "중간" ? "mid" : ""}">${esc(o.severity)}</span></b>${esc(o.why)}<div class="sig">감시: ${esc(o.signal)}</div></div>`).join("")}</div></div>`;
else {
  const hot = ok.filter(([, r]) => r.rsi > 70).map(([, r]) => r.name), cold = ok.filter(([, r]) => r.rsi < 30).map(([, r]) => r.name);
  h += `<div class="grid2 or"><div class="panel opp"><h3>지표상 강한 곳</h3><div class="item">${CATS.filter(c => c.flow === "유입").map(c => esc(c.name)).join(", ") || "자금 유입 분야 없음"}${cold.length ? `<div class="sig">과매도(RSI 30 미만): ${cold.map(esc).join(", ")}</div>` : ""}</div></div>
   <div class="panel risk"><h3>지표상 조심할 곳</h3><div class="item">${hot.length ? "과열(RSI 70 초과): " + hot.map(esc).join(", ") : "과열 종목 없음"}<div class="sig">고평가 위험 목록: ${list(SC.overvalued).map(r => esc(r.name)).join(", ") || "–"}</div></div></div></div>`;
}

h += easyBox(EZ.opps_risks);

// ── ⑥ 총론 ──
const NE = al.neutral || {};
h += `<h2 id="sec-conclusion"><span class="no">6</span>종합 투자 전략 및 총론</h2>
<div class="panel conc"><div class="stance"><span class="big">${esc(st.label || "–")}</span><span class="k">자세 점수 ${st.score != null ? (st.score > 0 ? "+" : "") + st.score : "–"} (−2 ~ +2)</span></div>
 <p class="txt" style="margin-top:6px">${esc(st.one_liner || "")}</p>
 ${easyBox(EZ.conclusion)}
 <div class="alloc"><div class="dn"><canvas id="alloc"></canvas></div>
  <div><table class="t"><thead><tr><th>자산</th><th>권장 비중</th><th>평소 기준</th><th>조정</th></tr></thead><tbody>` +
  ALLOC.map(([k, n, c]) => { const d = (al[k] || 0) - (NE[k] || 0);
    return `<tr><td><span class="sw" style="background:var(${c})"></span>${n}</td><td><b>${al[k] ?? 0}%</b></td><td>${NE[k] ?? "–"}%</td><td class="${cls(d)}">${d > 0 ? "+" : ""}${d}%p</td></tr>`; }).join("") +
  `</tbody></table>${al.rationale ? `<p class="txt mt">${esc(al.rationale)}</p>` : ""}
  ${al.hedges ? `<p class="txt"><b>헤지</b> ${esc(al.hedges)}</p>` : ""}${al.rebalance_trigger ? `<p class="k">비중 변경 조건: ${esc(al.rebalance_trigger)}</p>` : ""}</div></div>
 ${list(V.action_plan).length ? `<div class="plan mt"><h3>오늘의 액션 플랜</h3><ol>${V.action_plan.map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>` : ""}
 ${list(V.invalidation).length || list(V.watch_events).length ? `<div class="grid2 mt"><div><h3>이 판단이 틀렸다고 볼 조건</h3><ul class="clean">${list(V.invalidation).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
   <div><h3>주요 일정</h3><ul class="clean">${list(V.watch_events).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>` : ""}
 ${!RB && V.quant_reference ? `<p class="k mt" style="margin-bottom:0">참고 — 정량 모델 판단: ${esc(V.quant_reference.stance.label)} (${esc(V.quant_reference.stance.one_liner)})</p>` : ""}
 ${RB ? `<p class="note mt" style="margin-bottom:0">AI 분석이 없어 정량 모델의 결론을 표시합니다. 액션 플랜과 무효화 조건은 AI 브리핑이 있을 때 제공됩니다.</p>` : ""}</div>`;

// ── 용어 풀이 ──
h += `<h2 id="glossary"><span class="no">?</span>용어 풀이</h2><p class="lead">리포트에 나오는 말을 쉬운 말로 풀었습니다.</p>`;
if (list(V.glossary).length) h += `<h3>오늘 나온 용어</h3><div class="gloss">${V.glossary.map(g => `<div><b>${esc(g.term)}</b>${esc(g.meaning)}${g.why ? `<div class="why">오늘 왜 중요한가: ${esc(g.why)}</div>` : ""}</div>`).join("")}</div>`;
h += `<details class="more" ${list(V.glossary).length ? "" : "open"}><summary>기본 용어 ${BASIC_TERMS.length}개 보기</summary><div class="gloss mt">${BASIC_TERMS.map(([t, m]) => `<div><b>${esc(t)}</b>${esc(m)}</div>`).join("")}</div></details>`;

// ── 부록 ──
h += `<h2 class="appx" id="appendix">부록 · 근거 데이터</h2><h3>관심 종목 온도계</h3><div class="thermo">`;
const tileBg = s => { const t = Math.min(Math.abs(s) / 6, 1), col = s > 0 ? css("--up") : s < 0 ? css("--down") : css("--flat");
  return `color-mix(in srgb, ${col} ${Math.round(8 + t * 30)}%, var(--panel))`; };
for (const [mk, label] of [["kr", "국내"], ["us", "미국"]]) {
  const row = ok.filter(([, r]) => r.market === mk);
  if (!row.length) continue;
  h += `<div class="mk">${label}</div><div class="tiles">` + row.map(([code, r]) =>
    `<a class="tile" href="#t-${esc(code)}" style="background:${tileBg(r.score)}"><div class="n">${esc(r.name)}</div>
      <div class="c ${cls(r.chg_1d)}">${pct(r.chg_1d)}</div><div class="s">${r.label} · 점수 ${r.score > 0 ? "+" : ""}${r.score}</div></a>`).join("") + `</div>`;
}
h += `</div><div class="legend">타일 색: 추세 점수(−6~+6). 빨강일수록 상승 추세, 파랑일수록 하락 추세.</div>`;
const BOXES = [["value", "저평가 후보", "--accent", "3년 연속 흑자 기업 중 같은 분야 대비 PER·PBR이 낮고 ROE와 이익 성장이 양호한 순 (분야당 1종목)"],
  ["growth", "성장 기대 후보", "--up", "3년 매출 성장, 최근 매출·이익 증가, 이익 전망 개선을 종합한 순 (분야당 1종목)"],
  ["overvalued", "고평가 위험", "--warn", "같은 분야 대비 PER·PSR이 과도하고 주가가 과열된 순 (분야당 1종목)"]];
h += `<h3 class="mt">종목 스크리닝</h3>`;
if (SC.error) h += `<div class="err">${esc(SC.error)}</div>`;
else if (SC.universe_size) {
  h += `<p class="k" style="margin:-2px 0 10px">대상 ${SC.universe_size}종목 (universe.yaml), 실적은 최근 3개 회계연도 기준</p><div class="scr">`;
  for (const [key, title, color, how] of BOXES) {
    const L2 = SC[key] || [];
    h += `<section class="box" style="--c:var(${color})"><h3>${title}</h3><div class="how">${how}</div><ol>` +
      (L2.length ? L2.map(r => `<li><div><div><span class="nm">${esc(r.name)}</span>${DATA.prev_lists && !(DATA.prev_lists[key] || []).includes(r.ticker) ? `<span class="new">신규</span>` : ""}<span class="tk">${esc(r.ticker)} · ${r.market === "kr" ? "국내" : "미국"} · ${esc(r.category || r.sector)}</span></div>
        <div class="mt2">${Object.entries(r.metrics).map(([k, v]) => `<span>${esc(k)} <b>${esc(v)}</b></span>`).join("")}</div><div class="rs">${esc(r.reason)}</div></div></li>`).join("")
        : `<div class="empty">조건에 맞는 종목이 없습니다.</div>`) + `</ol></section>`;
  }
  h += `</div>`;
}
h += `<h3 class="mt">관심 종목 요약</h3><div class="tbl"><table><thead><tr><th>종목</th><th>종가</th><th>1일</th><th>5일</th><th>20일</th><th>1년 중 위치</th><th>단기 과열·침체(RSI)</th><th>추세 힘(TSI)</th><th>판정</th></tr></thead><tbody>`;
for (const [code, r] of ok) h += `<tr><td><a href="#t-${esc(code)}" style="color:inherit">${esc(r.name)}</a></td><td>${num(r.close)}</td>
  <td class="${cls(r.chg_1d)}">${pct(r.chg_1d)}</td><td class="${cls(r.chg_5d)}">${pct(r.chg_5d)}</td><td class="${cls(r.chg_20d)}">${pct(r.chg_20d)}</td>
  <td>${r.pos_52w == null ? "–" : r.pos_52w + "%"}</td><td>${num(r.rsi)}</td><td>${num(r.tsi)}</td><td><span class="badge ${r.label}">${r.label} ${r.score > 0 ? "+" : ""}${r.score}</span></td></tr>`;
h += `</tbody></table></div>`;
if (failed.length) h += `<p class="err" style="margin-top:10px">데이터를 가져오지 못한 종목: ${failed.map(([c, r]) => esc(r.name + " (" + c + ") — " + r.error)).join(", ")}</p>`;
h += `<h3 class="mt">관심 종목 상세</h3><div class="cards">`;
for (const [code, r] of ok) {
  const cm = (V.tickers || {})[code];
  h += `<section class="card" id="t-${esc(code)}"><div class="top"><h3>${esc(r.name)}<span class="code">${esc(code)}</span></h3>
    <div><span class="px">${num(r.close)}</span> <span class="${cls(r.chg_1d)}">${pct(r.chg_1d)}</span></div></div>
    <div class="chg">기준일 ${esc(r.date)} · 5일 ${pct(r.chg_5d)} · 20일 ${pct(r.chg_20d)} · <span class="badge ${r.label}">${r.label} ${r.score > 0 ? "+" : ""}${r.score}</span></div>
    ${cm ? `<div class="cm">${esc(cm)}</div>` : ""}
    <div class="chips">${r.signals.map(([k, t]) => `<span class="chip ${k}">${esc(t)}</span>`).join("") || `<span class="chip" style="color:var(--sub)">특이 신호 없음</span>`}</div>
    <div class="cv1"><canvas id="p-${esc(code)}" aria-label="${esc(r.name)} 가격 차트"></canvas></div>
    <div class="cv2"><canvas id="m-${esc(code)}" aria-label="${esc(r.name)} 모멘텀 차트"></canvas></div></section>`;
}
h += `</div><footer>이 리포트는 공개 시세·거시 데이터, 뉴스 헤드라인, 기술적 지표와 ${RB ? "규칙 기반 계산" : "AI 분석"}을 바탕으로 자동 생성된 참고 자료이며 투자 권유가 아닙니다. 투자 판단과 책임은 본인에게 있습니다.
지표 점수: 이동평균 배열(20/60/120일), MACD 히스토그램, TSI(25,13,7) 시그널, RSI(14) 50선을 항목별 ±1로 합산. 예상 범위는 일반적인 예상 등락 범위(대략 3번 중 2번 이 안에서 끝나는 범위)입니다.</footer>`;
document.getElementById("app").innerHTML = h;

// ── 차트 ──
if (window.Chart) {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = css("--sub");
  Chart.defaults.borderColor = css("--line");
  const tiny = {responsive:true, maintainAspectRatio:false, animation:false, events:[],
    plugins:{legend:{display:false}, tooltip:{enabled:false}}, elements:{point:{radius:0}, line:{borderWidth:1.6}},
    scales:{x:{display:false}, y:{display:false}}};
  for (const [id, s, avg] of sparks) {
    const el = document.getElementById(id);
    if (!el || !s || !s.length) continue;
    const ys = s.map(p => p[1]), up = ys[ys.length - 1] >= ys[0];
    const ds = [{data: ys, borderColor: css(up ? "--up" : "--down"), fill: false}];
    if (avg != null) ds.push({data: ys.map(() => avg), borderColor: css("--sub"), borderDash: [3, 3], borderWidth: 1});
    new Chart(el, {type: "line", options: tiny, data: {labels: s.map(p => p[0]), datasets: ds}});
  }
  for (const [id, a] of histCharts) {
    const el = document.getElementById(id);
    if (!el) continue;
    const m = monthly(a.spark);
    const lastD = m[m.length - 1][0];
    const agoKey = (Number(lastD.slice(0, 4)) - 1) + lastD.slice(4, 7);
    const agoIdx = m.findIndex(p => p[0].slice(0, 7) === agoKey);
    const ink = css("--ink"), sub = css("--sub");
    const radius = m.map((_, i) => i === m.length - 1 ? 5 : i === agoIdx ? 5 : 0);
    const fill = m.map((_, i) => i === m.length - 1 ? ink : css("--panel"));
    new Chart(el, {type: "line", data: {labels: m.map(p => p[0].slice(2, 7).replace("-", ".")), datasets: [
        {label: a.name, data: m.map(p => p[1]), borderColor: css("--accent"), borderWidth: 1.8,
         pointRadius: radius, pointBackgroundColor: fill, pointBorderColor: m.map((_, i) => i === agoIdx ? sub : ink), pointBorderWidth: 2},
        {label: "3년 평균", data: m.map(() => a.avg_3y), borderColor: sub, borderDash: [4, 4], borderWidth: 1, pointRadius: 0}]},
      options: {responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: "index", intersect: false},
        plugins: {legend: {display: false}, tooltip: {callbacks: {label: c => `${c.dataset.label}: ${fmtv(a, c.parsed.y)}`}}},
        scales: {x: {grid: {display: false}, ticks: {font: {size: 10}, maxRotation: 0, autoSkip: false,
                   callback(v, i) { const l = this.getLabelForValue(v); return l.endsWith(".01") ? "20" + l.slice(0, 2) : ""; }}},
                 y: {ticks: {font: {size: 10}, maxTicksLimit: 4, callback: v => fmtv(a, v)}}}}});
  }
  for (const [id, nowKey, pKey] of analogCharts) {
    const el = document.getElementById(id);
    if (!el) continue;
    const labels = []; for (let k = -52; k <= 26; k += 2) labels.push(k);
    const toData = p => labels.map(k => { const f = (p || []).find(q => q[0] === k); return f ? f[1] : null; });
    const ds = AN.matches.map((m, i) => ({label: (list(HC.analogs).find(a => a.date === m.date) || {}).period || m.date.slice(0, 7),
      data: toData(m[pKey]), borderColor: css(AC[i % 3]), borderWidth: 1.6, pointRadius: 0, spanGaps: true}));
    ds.unshift({label: "지금", data: toData(AN[nowKey]), borderColor: css("--ink"), borderWidth: 3, pointRadius: 0, spanGaps: true});
    new Chart(el, {type: "line", data: {labels, datasets: ds},
      options: {responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
        plugins: {legend: {position: "bottom", labels: {boxWidth: 12, font: {size: 11}}},
                  tooltip: {callbacks: {title: t => `${t[0].label}주 (${t[0].label < 0 ? "그 전" : t[0].label > 0 ? "그 뒤" : "기준 시점"})`, label: c => `${c.dataset.label}: ${c.parsed.y}`}}},
        scales: {x: {grid: {color: c => c.tick && c.tick.value === labels.indexOf(0) ? css("--sub") : "transparent", lineWidth: 2},
                     ticks: {font: {size: 10}, maxRotation: 0, autoSkip: false,
                       callback(v) { const k = labels[v]; return k === 0 ? "지금/그때" : k === -52 ? "1년 전" : k === -26 ? "6개월 전" : k === 13 ? "+3개월" : k === 26 ? "+6개월" : ""; }}},
                 y: {ticks: {font: {size: 10}}, title: {display: true, text: "기준 시점 = 100", font: {size: 10}}}}}});
  }
  const ael = document.getElementById("alloc");
  if (ael) new Chart(ael, {type: "doughnut", options: {responsive:true, maintainAspectRatio:false, animation:false, cutout:"58%",
      plugins:{legend:{display:false}}},
    data: {labels: ALLOC.map(x => x[1]), datasets: [{data: ALLOC.map(([k]) => al[k] || 0), backgroundColor: ALLOC.map(x => css(x[2])), borderColor: css("--panel"), borderWidth: 2}]}});
  const base = {responsive:true, maintainAspectRatio:false, animation:false,
    interaction:{mode:"index", intersect:false}, elements:{point:{radius:0}, line:{borderWidth:1.5}},
    plugins:{legend:{labels:{boxWidth:10, font:{size:11}}}},
    scales:{x:{ticks:{maxTicksLimit:5, maxRotation:0, font:{size:10}, callback(v){ return this.getLabelForValue(v).slice(2).replace(/-/g, "."); }}, grid:{display:false}}, y:{ticks:{font:{size:10}}}}};
  for (const [code, r] of ok) {
    const s = r.series;
    new Chart(document.getElementById("p-" + code), {type:"line", options:base, data:{labels:s.dates, datasets:[
      {label:"종가", data:s.close, borderColor:css("--ink"), borderWidth:1.8},
      {label:"20일", data:s.sma20, borderColor:css("--up")},
      {label:"60일", data:s.sma60, borderColor:css("--accent")},
      {label:"120일", data:s.sma120, borderColor:css("--flat"), borderDash:[4,3]}]}});
    new Chart(document.getElementById("m-" + code), {type:"line",
      options:{...base, scales:{x:{display:false}, y:{position:"left", ticks:{font:{size:10}}},
        y2:{position:"right", min:0, max:100, grid:{display:false}, ticks:{font:{size:10}, stepSize:30}}}},
      data:{labels:s.dates, datasets:[
        {label:"TSI", data:s.tsi, borderColor:css("--up"), yAxisID:"y"},
        {label:"TSI 시그널", data:s.tsi_sig, borderColor:css("--down"), yAxisID:"y"},
        {label:"RSI", data:s.rsi, borderColor:css("--warn"), borderDash:[3,3], yAxisID:"y2"}]}});
  }
}
</script>
</body>
</html>
"""


def _summary(bundle: dict, view: dict) -> dict:
    results, screens = bundle["results"], bundle.get("screens") or {}

    def chg(code):
        return (results.get(code) or {}).get("chg_1d")
    lists = {k: [r["ticker"] for r in screens.get(k, [])] for k in ("value", "growth", "overvalued")} \
        if "error" not in screens else {}
    names = {k: [r["name"] for r in screens.get(k, [])] for k in lists}
    al = view.get("allocation") or {}
    return {"kospi": chg("KS11"), "sp500": chg("US500"), "headline": view.get("headline"),
            "stance": (view.get("stance") or {}).get("label"),
            "allocation": {k: al.get(k) for k in ("kr_equity", "us_equity", "gold_commodities", "usd_cash", "krw_cash_bonds", "alternatives")},
            "lists": lists, "names": names, "valuation": screens.get("valuation")}


def _reports(out: Path) -> list[str]:
    """존재하는 리포트 이름(확장자 없이, 시간순): 2026-10-16, 2026-11-17_am ..."""
    names = [p.stem.replace("report_", "") for p in out.glob("report_????-??-??*.html")]
    order = {"": 1, "_am": 0, "_pm": 2}
    return sorted(set(names), key=lambda s: (s[:10], order.get(s[10:], 1)))


def write(bundle: dict, view: dict, out: Path, slot_cfg: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    today, slot = bundle["date"], bundle["slot"]
    stem = f"{today}_{slot}"

    hist_path = out / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
    entry = history.get(today) or {}
    entry.update(_summary(bundle, view))
    slots = entry.get("slots") or {}
    slots[slot] = {"ai": not view.get("rule_based"), "stance": (view.get("stance") or {}).get("label"),
                   "headline": view.get("headline"), "built_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    entry["slots"] = slots
    history[today] = entry
    hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")

    earlier = [s for s in _reports(out) if s < stem and s != today]
    prev = earlier[-1] if earlier else None
    prev_day = max((d for d in history if d < today and history[d].get("lists")), default=None)

    nw = dict(bundle.get("news") or {})
    nw["items"] = (nw.get("items") or [])[:30]
    nw.pop("by_sector", None)
    payload = {"today": today, "slot": slot, "slot_name": slot_cfg.get("name", slot),
               "collected_at": bundle.get("collected_at"), "results": bundle["results"],
               "macro": bundle.get("macro") or {}, "screens": bundle.get("screens") or {}, "news": nw,
               "view": view, "prev": prev, "prev_lists": history[prev_day]["lists"] if prev_day else None}
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = f"{slot_cfg.get('name', '시장 브리핑')} · {today}"
    html = TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)
    path = out / f"report_{stem}.html"
    path.write_text(html, encoding="utf-8")
    for name in (f"report_{today}.html", "latest.html", "index.html"):   # 날짜별·최신 주소 유지
        (out / name).write_text(html, encoding="utf-8")
    (out / "latest.json").write_text(json.dumps({"date": today, "slot": slot, "ai": not view.get("rule_based")},
                                                ensure_ascii=False), encoding="utf-8")

    rows = []
    for d in sorted(history, reverse=True):
        if not (out / f"report_{d}.html").exists():
            continue
        e = history[d]
        rows.append({"date": d, **{k: e.get(k) for k in ("kospi", "sp500", "headline", "names", "stance")},
                     "slots": {s: v.get("stance") for s, v in (e.get("slots") or {}).items()
                               if (out / f"report_{d}_{s}.html").exists()}})
    arch = ARCHIVE.replace("__DATA__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/"))
    (out / "archive.html").write_text(arch, encoding="utf-8")
    return path


ARCHIVE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>지난 리포트</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#F5F7F9;--panel:#FFFFFF;--ink:#16202A;--sub:#5C6875;--line:#DDE3E9;--up:#D0342C;--down:#1F5FBF;--accent:#0D5C6B;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#121820;--panel:#19212B;--ink:#E7ECF1;--sub:#98A4B1;--line:#2A3542;--up:#F06A60;--down:#5C95EC;--accent:#5FB7C7;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-size:15px;line-height:1.6;font-variant-numeric:tabular-nums}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px 60px}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid var(--ink);padding-bottom:12px}
h1{margin:0;font-size:24px}
a{color:var(--accent)}
h2{font-size:15px;color:var(--sub);font-weight:500;margin:26px 0 8px}
.day{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:12px 14px;margin-bottom:6px}
.top{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
.d{font-weight:700;font-size:16px;min-width:96px;color:inherit;text-decoration:none}
.ix{font-size:14px;color:var(--sub)} .ix b{font-weight:500}
.up{color:var(--up)} .down{color:var(--down)}
.hl{font-size:14px;margin-top:2px}
.sl{display:flex;gap:10px;flex-wrap:wrap;font-size:13.5px;margin-top:4px}
.ls{font-size:13px;color:var(--sub);margin-top:4px}
.ls span{display:block}
</style></head><body><div class="wrap">
<header><h1>지난 리포트</h1><a href="index.html">최신 브리핑 보기</a></header>
<div id="list"></div></div>
<script>
const ROWS = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pc = v => v == null ? "–" : `<b class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;
const WD = "일월화수목금토", SN = {am: "모닝", pm: "나이트"};
let h = "", month = "";
for (const r of ROWS) {
  const m = r.date.slice(0, 7);
  if (m !== month) { month = m; h += `<h2>${m.slice(0, 4)}년 ${+m.slice(5)}월</h2>`; }
  const n = r.names || {};
  const line = (t, a) => a && a.length ? `<span>${t}: ${a.slice(0, 3).map(esc).join(", ")}${a.length > 3 ? " 외" : ""}</span>` : "";
  const sl = Object.entries(r.slots || {});
  h += `<div class="day"><div class="top">
    <a class="d" href="report_${esc(r.date)}.html">${+r.date.slice(5, 7)}/${+r.date.slice(8)} (${WD[new Date(r.date).getDay()]})</a>
    <span class="ix">코스피 ${pc(r.kospi)}</span><span class="ix">S&amp;P500 ${pc(r.sp500)}</span></div>
    ${r.headline ? `<div class="hl">${esc(r.headline)}</div>` : ""}
    ${sl.length ? `<div class="sl">${sl.map(([s, st]) => `<a href="report_${esc(r.date)}_${s}.html">${SN[s] || s} 브리핑</a>${st ? ` <span class="ix">${esc(st)}</span>` : ""}`).join(" · ")}</div>` : ""}
    <div class="ls">${line("저평가", n.value)}${line("성장 기대", n.growth)}${line("고평가 위험", n.overvalued)}</div></div>`;
}
document.getElementById("list").innerHTML = h || "<p>아직 저장된 리포트가 없습니다.</p>";
</script></body></html>
"""
