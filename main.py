"""매일 시장 브리핑 생성기 (모닝 am / 나이트 pm).

사용법:
    python main.py --slot am --open             # 수집 + 리포트 (AI 파일이 있으면 반영)
    python main.py --slot am --collect --out docs   # 1단계: 데이터 묶음 + AI 입력(brief)만 저장
    python main.py --slot am --build --out docs     # 2단계: 묶음 + AI 결과로 리포트 생성
    python main.py --demo --no-ai --open        # 인터넷 없이 가상 데이터로 화면 확인

파일 (out 폴더 기준):
    data/<날짜>_<슬롯>.json        수집한 데이터 묶음
    data/<날짜>_<슬롯>_brief.md    AI(루틴 또는 API)에게 주는 입력
    ai/<날짜>_<슬롯>.json          AI 브리핑 결과 (루틴이 커밋, 또는 API 모드에서 저장)
    report_<날짜>_<슬롯>.html      리포트 (report_<날짜>.html·index.html·latest.html 은 최신본)
"""
import argparse
import json
import webbrowser
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import advisor
import commentary
import macro
import news
import report
import screener
from indicators import analyze
from netretry import retry

KST = timezone(timedelta(hours=9))


def fetch(code: str, days: int) -> pd.DataFrame:
    import FinanceDataReader as fdr
    start = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    df = retry(fdr.DataReader, code, start, tries=3, label=code)
    if df is None or df.empty or "Close" not in df:
        raise ValueError("데이터 없음")
    return df[["Close"]].dropna()


def fake(code: str, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(code.encode()))
    idx = pd.bdate_range(end=datetime.now(KST).date(), periods=int(days * 0.7))
    drift = rng.uniform(-0.0006, 0.0012)
    price = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, len(idx))))
    return pd.DataFrame({"Close": price}, index=idx)


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def valuation_history(out: Path, today_val: dict) -> dict:
    """history.json 에 쌓인 시장 PER 중앙값으로 누적 평균·백분위."""
    hp = out / "history.json"
    hist = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    res = {}
    for m in ("kr", "us"):
        now = (today_val.get(m) or {}).get("pe_median")
        vals = [v["valuation"][m]["pe_median"] for v in hist.values()
                if isinstance(v, dict) and (v.get("valuation") or {}).get(m, {}).get("pe_median")]
        if now is None:
            continue
        allv = vals + [now]
        res[m] = {"now": now, "days": len(allv), "avg": round(sum(allv) / len(allv), 2),
                  "pct": round(sum(1 for v in allv if v < now) / len(allv) * 100)}
    return res


def collect(cfg: dict, slot: str, today: str, demo: bool, out: Path) -> dict:
    days = cfg.get("lookback_days", 420)
    loader = fake if demo else fetch
    print("[1/4] 매크로·다중 자산 (5년 비교 + 20년 유사 국면)")
    _series = {}
    try:
        mac, _series = macro.run(cfg.get("macro", {}), slot, demo)
        print(f"  ✓ {mac['ok']}/{len(mac['assets'])}개 자산, 유사 국면 {len((mac.get('analogs') or {}).get('matches', []))}개")
        for a in mac["assets"]:
            if "error" in a:
                print(f"  ✗ {a['name']}: {a['error']}")
            else:
                print(f"    {a['name']}: {a['last']} ({a['date']}, {mac['sources'].get(a['key'], '')})")
    except Exception as e:  # noqa: BLE001
        mac = {"assets": [], "regimes": [], "analogs": {}, "quant": {"error": str(e)}, "error": str(e)}
        print(f"  ✗ 매크로 수집 실패: {e}")

    # 관심 종목 중 지수는 매크로와 같은 시계열을 써서, 리포트 어디서나 같은 수치가 나오게 한다
    same = {"KS11": "kospi", "KQ11": "kosdaq", "US500": "spx", "IXIC": "ndx", "GLD": "gld"}
    print(f"[2/4] 관심 종목 ({slot})")
    results = {}
    for market, items in cfg["watchlist"].items():
        for it in items:
            code, name = str(it["code"]), it["name"]
            try:
                key = same.get(code)
                if key and key in _series:
                    df = _series[key].to_frame("Close").tail(int(days * 0.75))
                else:
                    df = loader(code, days)
                if len(df) < 60:
                    raise ValueError(f"데이터가 {len(df)}일뿐이라 분석 불가")
                r = analyze(df, cfg.get("chart_days", 180))
                print(f"  ✓ {name:<14} {r['close']:>12,.2f}  {r['chg_1d']:+.2f}%  {r['label']}({r['score']:+d})  {r['date']}")
            except Exception as e:  # noqa: BLE001
                r = {"error": str(e)}
                print(f"  ✗ {name:<14} {e}")
            results[code] = {"name": name, "market": market, **r}

    sc_cfg = cfg.get("screening", {})
    screens = {}
    if sc_cfg.get("enabled", True):
        print("[3/4] 13개 분야·종목 스크리닝")
        try:
            screens = screener.run(sc_cfg, demo)
            print(f"  ✓ {screens['universe_size']}종목, {len(screens['categories'])}개 분야")
        except Exception as e:  # noqa: BLE001
            screens = {"error": f"스크리닝 실패: {e}"}
            print("  ✗ " + screens["error"])

    print("[4/4] 뉴스·사회 흐름")
    nw = {}
    if cfg.get("news", {}).get("enabled", True):
        try:
            cats = [c["name"] for c in screens.get("categories", [])] if "error" not in screens else []
            nw = news.run(cfg["news"], cats, demo)
            print(f"  ✓ 헤드라인 {nw['count']}건" + (f" (실패 피드 {len(nw['errors'])}개)" if nw.get("errors") else ""))
        except Exception as e:  # noqa: BLE001
            nw = {"error": str(e), "count": 0}
            print(f"  ✗ 뉴스 수집 실패: {e}")

    try:   # 앞으로 7일 이벤트 후보 (날짜가 정해진 일정 + 앞으로의 일을 다룬 기사)
        import events
        ev = events.collect(today, nw)
        print(f"  ✓ 이벤트 후보 일정 {len(ev['calendar'])}개 · 관련 기사 {len(ev['headlines'])}건")
    except Exception as e:  # noqa: BLE001
        ev = {"error": str(e)}
        print(f"  ✗ 이벤트 후보 실패: {e}")

    return {
        "date": today, "slot": slot, "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "demo": demo, "results": results, "macro": mac, "screens": screens, "news": nw, "events": ev,
        "valuation_history": valuation_history(out, (screens or {}).get("valuation") or {}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--slot", choices=["am", "pm", "auto"], default="auto")
    ap.add_argument("--date", help="--build 에서 사용할 날짜 (기본: 오늘 KST)")
    ap.add_argument("--collect", action="store_true", help="데이터 묶음과 AI 입력만 저장")
    ap.add_argument("--build", action="store_true", help="저장된 묶음(없으면 새로 수집) + AI 결과로 리포트")
    ap.add_argument("--no-ai", action="store_true", help="AI 결과를 쓰지 않고 규칙 기반 결론만")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", help="저장 폴더 (config의 output_dir 대신)")
    ap.add_argument("--open", action="store_true", help="완료 후 브라우저로 열기")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    now = datetime.now(KST)
    slot = args.slot if args.slot != "auto" else ("am" if now.hour < 12 else "pm")
    today = args.date or now.strftime("%Y-%m-%d")
    out = Path(args.out or cfg.get("output_dir", "reports"))
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "ai").mkdir(parents=True, exist_ok=True)
    stem = f"{today}_{slot}"
    data_p, brief_p, ai_p = out / "data" / f"{stem}.json", out / "data" / f"{stem}_brief.md", out / "ai" / f"{stem}.json"
    ai_cfg = cfg.get("claude", {})
    slot_cfg = (cfg.get("slots") or {}).get(slot, {})

    # ── 1단계: 수집 ──
    if args.build and data_p.exists():
        bundle = json.loads(data_p.read_text(encoding="utf-8"))
        print(f"저장된 데이터 묶음 사용: {data_p}")
        # 수집 때 API 호출이 실패했으면 리포트를 만들기 전에 저장된 AI 입력으로 한 번 더 시도
        if (ai_cfg.get("enabled") and ai_cfg.get("mode") == "api" and not args.no_ai and not args.demo
                and not ai_p.exists() and brief_p.exists()):
            print("… API 모드: AI 결과가 없어 다시 생성")
            res = commentary.generate_api(brief_p.read_text(encoding="utf-8"), ai_cfg)
            if "error" in res:
                print("  ✗ " + res["error"])
            else:
                ai_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  ✓ {ai_p}")
    else:
        bundle = collect(cfg, slot, today, args.demo, out)
        data_p.write_text(json.dumps(bundle, ensure_ascii=False, default=_jsonable), encoding="utf-8")
        brief_p.write_text(commentary.build_brief(bundle, slot_cfg), encoding="utf-8")
        print(f"데이터 묶음: {data_p}\nAI 입력: {brief_p}")
        if (ai_cfg.get("enabled") and ai_cfg.get("mode") == "api" and not args.no_ai and not args.demo
                and not ai_p.exists()):
            print("… API 모드: Claude 브리핑 생성")
            res = commentary.generate_api(brief_p.read_text(encoding="utf-8"), ai_cfg)
            if "error" in res:
                print("  ✗ " + res["error"])
            else:
                ai_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  ✓ {ai_p}")
    if args.collect:
        return

    # ── 2단계: 결론 + 리포트 ──
    sectors = [c["name"] for c in (bundle.get("screens") or {}).get("categories", [])]
    ai = None if (args.no_ai or not ai_cfg.get("enabled", True)) else advisor.load_ai(ai_p, sectors)
    rule = advisor.rule_based(bundle["results"], bundle.get("macro") or {}, bundle.get("screens") or {}, slot)
    view = advisor.stance_from_ai_or_rule(ai, rule)
    # 예측의 기준 종가는 AI 가 쓴 숫자가 아니라 수집 데이터 값으로 통일
    q = (bundle.get("macro") or {}).get("quant") or {}
    if ai and isinstance(view.get("forecast"), dict) and q.get("base_close"):
        view["forecast"]["base_level"] = q["base_close"]
    print("결론: " + ("AI 브리핑" if ai else "규칙 기반(AI 없음)") + f" — {view['stance']['label']}")
    path = report.write(bundle, view, out, slot_cfg)
    print(f"\n리포트 저장: {path.resolve()}")
    if args.open:
        webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    main()
