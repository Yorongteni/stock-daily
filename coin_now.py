"""지금 시세로 보는 코인 수시 분석 — 18시 브리핑 2부(바이낸스 3배 원픽)와 같은 규칙을 원하는 시각에 돌린다.

18시 기록은 건드리지 않습니다.
  - data/ 의 추적 JSON 을 임시 폴더에 복사해 그 사본으로만 계산합니다 (SWING_DATA_DIR).
    그래서 이 분석의 원픽은 가상 매매 기록·성적에 들어가지 않는 '참고용 스냅샷'입니다.
  - 18시에 고른 오늘 원픽과 보유 포지션은 그대로 두고 '지금 상태'를 함께 보여 줍니다.
결과: docs/coin-now/coin_<날짜>_<시각>.html · docs/coin-now/index.html(최신) · docs/coin-now/data/<날짜>_<시각>.json

  python coin_now.py            # 지금 시각 기준
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))


def _isolate_state() -> Path:
    """futures·swing 모듈을 불러오기 전에 추적 JSON 사본 폴더를 정한다 (원본 data/ 는 읽기만)."""
    tmp = Path(tempfile.mkdtemp(prefix="coin-now-"))
    src = ROOT / "data"
    if src.is_dir():
        for p in src.glob("*.json"):
            shutil.copy2(p, tmp / p.name)
    os.environ["SWING_DATA_DIR"] = str(tmp)
    return tmp


def build_page(fu: dict, stamp_kst: str) -> str:
    import swing_report as sr
    from pricefmt import kst

    if fu.get("pick"):
        fu["pick"]["valid_until_kst"] = kst(fu["pick"]["valid_until"]) + " (한국 시간)"
    parts = []
    if fu.get("error"):
        parts.append(f"<div class='empty'>⚠ 지금은 코인 데이터를 받지 못했어요. ({sr.esc(fu['error'])}) 잠시 뒤 다시 실행해 주세요.</div>")
    else:
        hold = "".join(sr.coin_holding_html(h) for h in fu.get("holdings") or [])
        parts.append("<h2>지금 대기·보유 중인 포지션<small>18시 원픽·직접 넣은 포지션의 지금 상태</small></h2>")
        parts.append(hold or "<div class='empty'>지금 대기·보유 중인 코인 포지션이 없어요.</div>")
        evs = "".join(sr.coin_event_html(e) for e in fu.get("events") or [])
        if evs:
            parts.append("<h2>지난 판정 이후 바뀐 것<small>참고 — 공식 판정은 다음 18시 브리핑에서</small></h2>" + evs)
        parts.append("<h2>지금 시세로 본 원픽<small>18시 규칙 그대로 · 기록에 넣지 않는 참고용</small></h2>")
        parts.append(sr.futures_part(fu))

    charts = ""
    if fu.get("pick") and fu["pick"].get("spark"):
        sp, o = fu["pick"]["spark"], fu["pick"]["order"]
        ds = [{"label": "1시간봉 종가", "data": sp["close"], "borderColor": "#16202A", "borderWidth": 2.2, "pointRadius": 0, "tension": .15},
              {"label": "20봉 평균선", "data": sp["ema20"], "borderColor": "#8793A0", "borderDash": [6, 4], "borderWidth": 1.5, "pointRadius": 0}]
        for lab, v, col in (("진입", o["entry"], "#1F5FBF"), ("목표", o["tp"], "#1E8E3E"), ("손절", o["sl"], "#C5221F")):
            if v:
                ds.append({"label": f"{lab} {sr.fpx(v)}", "data": [v] * len(sp["close"]), "borderColor": col, "borderWidth": 2,
                           "pointRadius": 0, "borderDash": [2, 3]})
        charts = f"mk('fpc',{json.dumps(sp['t'])},{json.dumps(ds, ensure_ascii=False)});"

    b = fu.get("bias") or {}
    pick = fu.get("pick") or {}
    head_pick = "데이터 없음" if fu.get("error") else (f"{pick.get('coin') or pick.get('symbol')} {pick.get('side')}" if pick else "쉬어가기")
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>코인 수시 분석 {sr.esc(stamp_kst)}</title>
<link rel='preconnect' href='https://fonts.googleapis.com'><link href='https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap' rel='stylesheet'>
<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js'></script><style>{sr.CSS}</style></head><body><div class='wrap'>
<header><h1>🪙 코인 수시 분석 · {sr.esc(stamp_kst)}</h1>
<p>18시 브리핑 2부(바이낸스 3배 롱/숏 원픽)와 같은 규칙을 지금 시세로 돌린 참고용 스냅샷 · 개인 연습용</p>
<p>이 분석은 가상 매매 기록·성적에 넣지 않아요. 공식 기록은 매일 18시 브리핑입니다.</p></header>
<div class='strip'><div><span>분석 시각</span><b>{sr.esc(stamp_kst)}</b></div>
<div><span>지금의 방향</span><b>{sr.esc((b.get('label') or '–'))}</b></div>
<div><span>지금 원픽</span><b>{sr.esc(head_pick)}</b></div></div>
{''.join(parts)}
<p class='disc'>개인 연습용 참고 자료입니다. 투자 권유가 아니며, 실제 매매 판단과 책임은 본인에게 있습니다. 코인 선물은 레버리지로 손실이 커질 수 있습니다.</p>
</div><script>
function mk(id,labels,ds){{const el=document.getElementById(id);if(!el||!window.Chart)return;new Chart(el,{{type:'line',data:{{labels,datasets:ds}},
options:{{responsive:true,maintainAspectRatio:false,animation:false,plugins:{{legend:{{labels:{{boxWidth:12,font:{{size:11}}}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:8}}}}}}}}}})}}
{charts}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--out", default=str(ROOT / "docs"))
    a = ap.parse_args()

    tmp = _isolate_state()
    import yaml
    import futures
    from swing import usdkrw

    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    now = datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d_%H%M")
    stamp_kst = now.strftime("%Y-%m-%d %H:%M") + " KST"
    # '오늘' 이름을 18시와 다르게 줘서, 18시에 고른 오늘 원픽을 지우지 않고 보유·대기 포지션으로 함께 판정한다
    tag = f"{now:%Y-%m-%d}-now{now:%H%M}"
    try:
        fx, _ = usdkrw()
        fu = futures.run(tag, cfg, fx)
    except Exception as e:  # noqa: BLE001
        print(f"✗ 코인 분석 실패: {type(e).__name__}: {e}")
        fu = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out = Path(a.out) / "coin-now"
    (out / "data").mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": stamp_kst, "snapshot": True, "futures": fu}
    (out / "data" / f"{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    page = build_page(fu, stamp_kst)
    (out / f"coin_{stamp}.html").write_text(page, encoding="utf-8")
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"STAMP={stamp}")
    p = fu.get("pick")
    if fu.get("error"):
        print(f"결과: ⚠ {fu['error']}")
    else:
        print(f"결과: {fu['bias']['label']} · " + (f"{p['symbol']} {p['side']} 진입 {p['order']['entry']} / TP {p['order']['tp']} / SL {p['order']['sl']}"
                                              if p else fu.get("block", "")))
    return 1 if fu.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
