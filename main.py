"""매일 주식 동향 분석 리포트 생성기.

사용법:
    python main.py              # 실제 데이터 + AI 해설
    python main.py --no-ai      # AI 해설 없이 지표만
    python main.py --demo       # 인터넷 없이 가상 데이터로 화면 확인
"""
import argparse
import webbrowser
import zlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yaml

import commentary
import report
import screener
from indicators import analyze

KST = timezone(timedelta(hours=9))


def fetch(code: str, days: int) -> pd.DataFrame:
    import FinanceDataReader as fdr
    start = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    df = fdr.DataReader(code, start)
    if df is None or df.empty or "Close" not in df:
        raise ValueError("데이터 없음")
    return df[["Close"]].dropna()


def fake(code: str, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(code.encode()))
    idx = pd.bdate_range(end=datetime.now(KST).date(), periods=int(days * 0.7))
    drift = rng.uniform(-0.0006, 0.0012)
    price = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, len(idx))))
    return pd.DataFrame({"Close": price}, index=idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", help="리포트 저장 폴더 (config의 output_dir 대신)")
    ap.add_argument("--open", action="store_true", help="완료 후 브라우저로 열기")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    days = cfg.get("lookback_days", 420)
    loader = fake if args.demo else fetch

    results = {}
    for market, items in cfg["watchlist"].items():
        for it in items:
            code, name = str(it["code"]), it["name"]
            try:
                df = loader(code, days)
                if len(df) < 60:
                    raise ValueError(f"데이터가 {len(df)}일뿐이라 분석 불가")
                r = analyze(df, cfg.get("chart_days", 180))
                print(f"  ✓ {name:<14} {r['close']:>12,.2f}  {r['chg_1d']:+.2f}%  {r['label']}({r['score']:+d})")
            except Exception as e:  # noqa: BLE001
                r = {"error": str(e)}
                print(f"  ✗ {name:<14} {e}")
            results[code] = {"name": name, "market": market, **r}

    sc_cfg = cfg.get("screening", {})
    screens = {}
    if sc_cfg.get("enabled", True):
        print("  … 종목 스크리닝 (저평가 / 성장 기대 / 고평가 위험)")
        try:
            screens = screener.run(sc_cfg, args.demo)
            print(f"  ✓ 스크리닝 완료 ({screens['universe_size']}종목 분석)")
        except Exception as e:  # noqa: BLE001
            screens = {"error": f"스크리닝 실패: {e}"}
            print("  ✗ " + screens["error"])

    ai_cfg = cfg.get("claude", {})
    if args.no_ai or not ai_cfg.get("enabled", True):
        ai = {"error": "AI 해설 꺼짐", "prompt": commentary.chat_prompt(results, screens, today)}
    else:
        print("  … Claude 해설 생성 중")
        ai = commentary.generate(results, screens, today, ai_cfg)
        if "error" in ai:
            ai["prompt"] = commentary.chat_prompt(results, screens, today)
        print("  ✗ " + ai["error"] if "error" in ai else "  ✓ AI 해설 완료")

    path = report.write(results, ai, today, screens, args.out or cfg.get("output_dir", "reports"))
    print(f"\n리포트 저장: {path.resolve()}")
    if args.open:
        webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    main()
