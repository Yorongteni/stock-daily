"""분석 결과를 단일 HTML 대시보드 파일로 저장."""
import json
from pathlib import Path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>시장 일일 리포트 · __DATE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  --bg:#F5F7F9; --panel:#FFFFFF; --ink:#16202A; --sub:#5C6875; --line:#DDE3E9;
  --up:#D0342C; --down:#1F5FBF; --flat:#8793A0; --accent:#0D5C6B;
  --up-soft:#FBE7E5; --down-soft:#E3ECFA; --warn:#B7791F; --warn-soft:#FBF1DE;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#121820; --panel:#19212B; --ink:#E7ECF1; --sub:#98A4B1; --line:#2A3542;
    --up:#F06A60; --down:#5C95EC; --flat:#7D8996; --accent:#5FB7C7;
    --up-soft:#3A2224; --down-soft:#1E2B40; --warn:#E0A84A; --warn-soft:#3A2F1C;
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
header h1{font-size:28px;line-height:1.3;margin:0;font-weight:700;max-width:30ch}
header .meta{color:var(--sub);font-size:14px}
.nav{display:flex;gap:14px;margin-top:2px;font-size:14px}
.nav a{color:var(--accent);font-weight:500}
.new{font-size:11px;font-weight:700;color:var(--panel);background:var(--c);border-radius:3px;padding:0 5px;margin-left:6px;vertical-align:2px}
h2{font-size:18px;margin:36px 0 12px;font-weight:700}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}

/* 시장 온도계: 점수에 따라 색이 진해지는 타일 줄 */
.thermo{display:grid;grid-template-columns:72px 1fr;gap:10px 14px;align-items:stretch;margin-top:22px}
.thermo .mk{font-weight:700;font-size:14px;align-self:center;color:var(--sub)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:6px}
.tile{display:block;text-decoration:none;color:inherit;padding:10px 12px;border-radius:6px;
  border:1px solid var(--line);background:var(--panel)}
.tile:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tile .n{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .c{font-size:18px;font-weight:700}
.tile .s{font-size:12px;color:var(--sub)}
.legend{font-size:12px;color:var(--sub);margin-top:8px}

.ai{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);
  border-radius:4px;padding:20px 22px}
.ai p{margin:0 0 12px;max-width:72ch}
.ai .two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;margin-top:6px}
.ai h3{font-size:15px;margin:0 0 4px}
.scen{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:16px}
.scen div{padding:12px 14px;border-radius:4px;font-size:14px}
.scen .b{background:var(--up-soft)} .scen .m{background:var(--bg)} .scen .r{background:var(--down-soft)}
.scen b{display:block;margin-bottom:2px}
.ai ul{margin:4px 0 0;padding-left:18px;font-size:14px}
.cp{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin:4px 0 12px}
.cp button{font:inherit;font-weight:700;font-size:15px;padding:10px 18px;border:0;border-radius:4px;
  background:var(--accent);color:var(--panel);cursor:pointer}
.cp button:focus-visible,.cp a:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.cp a{color:var(--accent);font-weight:500}
#cpMsg{font-size:14px;color:var(--sub)}
.ai summary{cursor:pointer;font-size:14px;color:var(--sub)}
.ai textarea{width:100%;height:220px;margin-top:8px;font:inherit;font-size:13px;color:var(--ink);
  background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:10px}
.scr{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px}
.box{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--c);border-radius:4px;padding:16px 18px}
.box h3{margin:0;font-size:16px}
.box .how{font-size:13px;color:var(--sub);margin:2px 0 10px}
.box ol{margin:0;padding:0;list-style:none;counter-reset:r}
.box li{counter-increment:r;display:grid;grid-template-columns:22px 1fr;gap:0 8px;padding:10px 0;border-top:1px solid var(--line)}
.box li::before{content:counter(r);font-weight:700;color:var(--c);font-size:15px}
.box .nm{font-weight:700}
.box .tk{font-size:12px;color:var(--sub);font-weight:400;margin-left:6px}
.box .mt{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12.5px;color:var(--sub);margin:2px 0}
.box .mt b{color:var(--ink);font-weight:500}
.box .rs{font-size:13.5px}
.box .rk{font-size:13px;color:var(--sub);margin-top:2px}
.box .empty{font-size:14px;color:var(--sub);padding:8px 0}
.err{color:var(--warn);background:var(--warn-soft);padding:12px 14px;border-radius:4px;font-size:14px}

.tbl{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:760px}
th,td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-weight:500;color:var(--sub);background:var(--bg)}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:500}
.badge.강세{background:var(--up-soft);color:var(--up)}
.badge.약세{background:var(--down-soft);color:var(--down)}
.badge.중립{background:var(--bg);color:var(--sub);border:1px solid var(--line)}

.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:14px}
@media (max-width:600px){.cards{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:16px 18px;scroll-margin-top:12px}
.card .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.card h3{margin:0;font-size:17px}
.card .code{color:var(--sub);font-size:13px;font-weight:400;margin-left:6px}
.card .px{font-size:20px;font-weight:700}
.card .chg{font-size:13px;color:var(--sub)}
.card .cm{font-size:14px;margin:8px 0 6px;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
.chip{font-size:12px;padding:2px 8px;border-radius:3px}
.chip.bull{background:var(--up-soft);color:var(--up)}
.chip.bear{background:var(--down-soft);color:var(--down)}
.chip.warn{background:var(--warn-soft);color:var(--warn)}
.cv1{height:190px} .cv2{height:110px;margin-top:6px}
@media (max-width:600px){
  .wrap{padding:18px 14px 48px}
  header h1{font-size:23px}
  .thermo{grid-template-columns:1fr;gap:4px}
  .thermo .mk{margin-top:8px}
  .tiles{grid-template-columns:repeat(3,1fr)}
  .tile{padding:8px 9px}
  .tile .c{font-size:16px}
  .card,.box{padding:14px}
}
footer{margin-top:44px;font-size:12px;color:var(--sub);border-top:1px solid var(--line);padding-top:14px;max-width:80ch}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const DATA = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const cls = v => v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat";
const pct = v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(2) + "%";
const num = v => v == null ? "–" : v.toLocaleString("ko-KR", {maximumFractionDigits: 2});
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function tileBg(score){
  // -6..+6 → 파랑(약세) ~ 회색 ~ 빨강(강세). 한국식 상승=빨강
  const t = Math.min(Math.abs(score) / 6, 1);
  const col = score > 0 ? css("--up") : score < 0 ? css("--down") : css("--flat");
  return `color-mix(in srgb, ${col} ${Math.round(8 + t * 30)}%, var(--panel))`;
}

const ai = DATA.ai || {};
const items = Object.entries(DATA.results);
const ok = items.filter(([, r]) => !r.error);
const failed = items.filter(([, r]) => r.error);

let h = `<header><h1>${esc(ai.headline || "오늘의 시장 점검")}</h1>
<div class="meta">${esc(DATA.today)} 생성
  <nav class="nav">${DATA.prev ? `<a href="report_${esc(DATA.prev)}.html">← ${esc(DATA.prev)}</a>` : ""}
  <a href="archive.html">지난 리포트 전체</a></nav></div></header>`;

h += `<div class="thermo">`;
for (const [mk, label] of [["kr", "국내"], ["us", "미국"]]) {
  const row = ok.filter(([, r]) => r.market === mk);
  if (!row.length) continue;
  h += `<div class="mk">${label}</div><div class="tiles">` + row.map(([code, r]) =>
    `<a class="tile" href="#t-${esc(code)}" style="background:${tileBg(r.score)}">
      <div class="n">${esc(r.name)}</div>
      <div class="c ${cls(r.chg_1d)}">${pct(r.chg_1d)}</div>
      <div class="s">${r.label} · 점수 ${r.score > 0 ? "+" : ""}${r.score}</div></a>`).join("") + `</div>`;
}
h += `</div><div class="legend">타일 색: 추세 점수(−6~+6). 빨강일수록 상승 추세, 파랑일수록 하락 추세. 누르면 상세 차트로 이동합니다.</div>`;

h += `<h2>AI 시장 해설</h2>`;
if (ai.prompt && !ai.market_overview) {
  h += `<div class="ai"><p>오늘의 지표 요약을 질문으로 만들어 두었습니다. 복사해서 Claude 채팅에 붙여넣으면 뉴스를 반영한 해설과 시나리오를 받을 수 있습니다.</p>
  <div class="cp"><button id="cpBtn" type="button">해설용 질문 복사</button>
  <a href="https://claude.ai/new" target="_blank" rel="noopener">Claude 새 채팅 열기</a>
  <span id="cpMsg" role="status"></span></div>
  <details><summary>질문 내용 보기</summary><textarea id="cpTxt" readonly>${esc(ai.prompt)}</textarea></details></div>`;
} else if (ai.error || !ai.market_overview) {
  h += `<div class="err">${esc(ai.error || "AI 해설이 없습니다.")}</div>`;
} else {
  const s = ai.scenarios || {};
  h += `<div class="ai"><p>${esc(ai.market_overview)}</p>
  <div class="two"><div><h3>국내</h3><p>${esc(ai.kr_view)}</p></div><div><h3>미국</h3><p>${esc(ai.us_view)}</p></div></div>
  <div class="scen"><div class="b"><b>강세 시나리오</b>${esc(s.bull)}</div>
  <div class="m"><b>기본 시나리오</b>${esc(s.base)}</div>
  <div class="r"><b>약세 시나리오</b>${esc(s.bear)}</div></div>
  <div class="two" style="margin-top:16px">
    <div><h3>주의할 리스크</h3><ul>${(ai.risks||[]).map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>
    <div><h3>다가오는 일정</h3><ul>${(ai.watch_events||[]).map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>
  </div></div>`;
}


const SC = DATA.screens || {};
const BOXES = [
  ["value", "저평가 후보", "--accent", "3년 연속 흑자 기업 중 업종 대비 PER·PBR이 낮고 ROE와 이익 성장이 양호한 순"],
  ["growth", "성장 기대 후보", "--up", "3년 매출 성장, 최근 매출·이익 증가, 이익 전망 개선, 6개월 주가 흐름을 종합한 순"],
  ["overvalued", "고평가 위험", "--warn", "업종 대비 PER·PSR이 과도하고 주가가 과열된 순. 추격 매수 주의 대상"],
];
h += `<h2>종목 스크리닝</h2>`;
if (SC.error) h += `<div class="err">${esc(SC.error)}</div>`;
else if (SC.universe_size) {
  h += `<p style="margin:-6px 0 12px;font-size:13px;color:var(--sub)">스크리닝 대상 ${SC.universe_size}종목 (universe.yaml), 실적은 최근 3개 회계연도 기준</p><div class="scr">`;
  for (const [key, title, color, how] of BOXES) {
    const list = SC[key] || [];
    h += `<section class="box" style="--c:var(${color})"><h3>${title}</h3><div class="how">${how}</div><ol>` +
      (list.length ? list.map(r => `<li><div>
        <div><span class="nm">${esc(r.name)}</span>${DATA.prev_lists && !(DATA.prev_lists[key] || []).includes(r.ticker) ? `<span class="new">신규</span>` : ""}<span class="tk">${esc(r.ticker)} · ${r.market === "kr" ? "국내" : "미국"} · ${esc(r.sector)}</span></div>
        <div class="mt">${Object.entries(r.metrics).map(([k, v]) => `<span>${esc(k)} <b>${esc(v)}</b></span>`).join("")}</div>
        <div class="rs">${esc(r.reason)}</div></div></li>`).join("")
        : `<div class="empty">조건에 맞는 종목이 없습니다.</div>`) + `</ol></section>`;
  }
  const picks = ai.picks || [];
  h += `<section class="box" style="--c:var(--ink)"><h3>AI 관심 종목</h3>
    <div class="how">스크리닝 결과와 당일 뉴스를 AI가 종합한 검토 후보. 매수 권유가 아닙니다</div><ol>` +
    (picks.length ? picks.map(p => `<li><div><div><span class="nm">${esc(p.name)}</span><span class="tk">${esc(p.ticker)}</span></div>
      <div class="rs">${esc(p.thesis)}</div><div class="rk">리스크: ${esc(p.risk)}</div>
      ${p.check ? `<div class="rk">확인할 점: ${esc(p.check)}</div>` : ""}</div></li>`).join("")
      : `<div class="empty">"AI 시장 해설" 칸에서 해설용 질문을 복사해 Claude 채팅에 붙여넣으면, 이 스크리닝 결과를 반영한 관심 종목 5개를 함께 받을 수 있습니다.</div>`) +
    `</ol></section></div>`;
}

h += `<h2>종목 요약</h2><div class="tbl"><table><thead><tr>
<th>종목</th><th>종가</th><th>1일</th><th>5일</th><th>20일</th><th>52주 위치</th><th>RSI</th><th>TSI</th><th>판정</th></tr></thead><tbody>`;
for (const [code, r] of ok) {
  h += `<tr><td><a href="#t-${esc(code)}" style="color:inherit">${esc(r.name)}</a></td><td>${num(r.close)}</td>
  <td class="${cls(r.chg_1d)}">${pct(r.chg_1d)}</td><td class="${cls(r.chg_5d)}">${pct(r.chg_5d)}</td>
  <td class="${cls(r.chg_20d)}">${pct(r.chg_20d)}</td><td>${r.pos_52w == null ? "–" : r.pos_52w + "%"}</td>
  <td>${num(r.rsi)}</td><td>${num(r.tsi)}</td><td><span class="badge ${r.label}">${r.label} ${r.score > 0 ? "+" : ""}${r.score}</span></td></tr>`;
}
h += `</tbody></table></div>`;
if (failed.length) h += `<p class="err" style="margin-top:10px">데이터를 가져오지 못한 종목: ${failed.map(([c, r]) => esc(r.name + " (" + c + ") — " + r.error)).join(", ")}</p>`;

h += `<h2>종목별 상세</h2><div class="cards">`;
for (const [code, r] of ok) {
  const cm = (ai.tickers || {})[code];
  h += `<section class="card" id="t-${esc(code)}"><div class="top">
    <h3>${esc(r.name)}<span class="code">${esc(code)}</span></h3>
    <div><span class="px">${num(r.close)}</span> <span class="${cls(r.chg_1d)}">${pct(r.chg_1d)}</span></div></div>
    <div class="chg">기준일 ${esc(r.date)} · 5일 ${pct(r.chg_5d)} · 20일 ${pct(r.chg_20d)} · <span class="badge ${r.label}">${r.label} ${r.score > 0 ? "+" : ""}${r.score}</span></div>
    ${cm ? `<div class="cm">${esc(cm)}</div>` : ""}
    <div class="chips">${r.signals.map(([k, t]) => `<span class="chip ${k}">${esc(t)}</span>`).join("") || `<span class="chip" style="color:var(--sub)">특이 신호 없음</span>`}</div>
    <div class="cv1"><canvas id="p-${esc(code)}" aria-label="${esc(r.name)} 가격 차트"></canvas></div>
    <div class="cv2"><canvas id="m-${esc(code)}" aria-label="${esc(r.name)} 모멘텀 차트"></canvas></div>
  </section>`;
}
h += `</div><footer>이 리포트는 공개 시세 데이터와 기술적 지표, AI 요약을 바탕으로 자동 생성된 참고 자료이며 투자 권유가 아닙니다.
지표 점수: 종가·이동평균 배열(20/60/120일), MACD 히스토그램, TSI(25,13,7) 시그널, RSI(14) 50선을 항목별 ±1로 합산.</footer>`;
document.getElementById("app").innerHTML = h;

const cpBtn = document.getElementById("cpBtn");
if (cpBtn) cpBtn.addEventListener("click", async () => {
  const ta = document.getElementById("cpTxt"), msg = document.getElementById("cpMsg");
  try { await navigator.clipboard.writeText(ta.value); }
  catch { ta.closest("details").open = true; ta.select(); document.execCommand("copy"); }
  msg.textContent = "복사했습니다. 채팅창에 붙여넣기(Ctrl+V) 하세요.";
});

// 차트
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.color = css("--sub");
Chart.defaults.borderColor = css("--line");
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
    options:{...base, plugins:{legend:{labels:{boxWidth:10, font:{size:11}}}},
      scales:{x:{display:false}, y:{position:"left", ticks:{font:{size:10}}},
        y2:{position:"right", min:0, max:100, grid:{display:false}, ticks:{font:{size:10}, stepSize:30}}}},
    data:{labels:s.dates, datasets:[
      {label:"TSI", data:s.tsi, borderColor:css("--up"), yAxisID:"y"},
      {label:"TSI 시그널", data:s.tsi_sig, borderColor:css("--down"), yAxisID:"y"},
      {label:"RSI", data:s.rsi, borderColor:css("--warn"), borderDash:[3,3], yAxisID:"y2"}]}});
}
</script>
</body>
</html>
"""


def _summary(results: dict, screens: dict, ai: dict) -> dict:
    def chg(code):
        r = results.get(code, {})
        return r.get("chg_1d")
    lists = {k: [r["ticker"] for r in screens.get(k, [])] for k in ("value", "growth", "overvalued")} \
        if isinstance(screens, dict) and "error" not in screens else {}
    names = {k: [r["name"] for r in screens.get(k, [])] for k in lists}
    return {"kospi": chg("KS11"), "sp500": chg("US500"), "headline": ai.get("headline"),
            "lists": lists, "names": names}


def write(results: dict, ai: dict, today: str, screens: dict, out_dir: str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 날짜별 요약 이력 (history.json) — 리포트 파일은 날짜별로 계속 쌓입니다
    hist_path = out / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
    history[today] = _summary(results, screens, ai)
    hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    earlier = sorted(d for d in history if d < today and (out / f"report_{d}.html").exists())
    prev = earlier[-1] if earlier else None

    payload = json.dumps({"today": today, "results": results, "ai": ai, "screens": screens,
                          "prev": prev, "prev_lists": history[prev]["lists"] if prev else None},
                         ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATE__", today).replace("__DATA__", payload)
    path = out / f"report_{today}.html"
    path.write_text(html, encoding="utf-8")
    (out / "latest.html").write_text(html, encoding="utf-8")
    (out / "index.html").write_text(html, encoding="utf-8")  # 웹 주소로 바로 열리도록

    rows = [{"date": d, **history[d]} for d in sorted(history, reverse=True)
            if (out / f"report_{d}.html").exists()]
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
.day{display:block;text-decoration:none;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:12px 14px;margin-bottom:6px}
.day:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.top{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
.d{font-weight:700;font-size:16px;min-width:96px}
.ix{font-size:14px;color:var(--sub)} .ix b{font-weight:500}
.up{color:var(--up)} .down{color:var(--down)}
.hl{font-size:14px;margin-top:2px}
.ls{font-size:13px;color:var(--sub);margin-top:4px}
.ls span{display:block}
</style></head><body><div class="wrap">
<header><h1>지난 리포트</h1><a href="index.html">오늘 리포트 보기</a></header>
<div id="list"></div></div>
<script>
const ROWS = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pc = v => v == null ? "–" : `<b class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</b>`;
const WD = "일월화수목금토";
let h = "", month = "";
for (const r of ROWS) {
  const m = r.date.slice(0, 7);
  if (m !== month) { month = m; h += `<h2>${m.slice(0, 4)}년 ${+m.slice(5)}월</h2>`; }
  const n = r.names || {};
  const line = (t, a) => a && a.length ? `<span>${t}: ${a.slice(0, 3).map(esc).join(", ")}${a.length > 3 ? " 외" : ""}</span>` : "";
  h += `<a class="day" href="report_${esc(r.date)}.html"><div class="top">
    <span class="d">${+r.date.slice(5, 7)}/${+r.date.slice(8)} (${WD[new Date(r.date).getDay()]})</span>
    <span class="ix">코스피 ${pc(r.kospi)}</span><span class="ix">S&amp;P500 ${pc(r.sp500)}</span></div>
    ${r.headline ? `<div class="hl">${esc(r.headline)}</div>` : ""}
    <div class="ls">${line("저평가", n.value)}${line("성장 기대", n.growth)}${line("고평가 위험", n.overvalued)}</div></a>`;
}
document.getElementById("list").innerHTML = h || "<p>아직 저장된 리포트가 없습니다.</p>";
</script></body></html>
"""
