"""보유 포지션 수동 입력 (스마트폰 GitHub 앱 → Actions → '보유 포지션 수동 입력').

  python positions.py --market US_STOCK --action BUY    --ticker NVDA    --price 181.2 --qty 2
  python positions.py --market BINANCE  --action BUY    --ticker SOLUSDT --direction SHORT --price 142.3 --qty 360
  python positions.py --market US_STOCK --action CLOSE  --ticker NVDA    --price 190.1
  python positions.py --market BINANCE  --action CANCEL --ticker SOLUSDT

market: US_STOCK / BINANCE,  action: BUY(신규매수·단가수정) / CLOSE(매도·청산완료) / CANCEL(미체결취소)
'US_STOCK (미국주식)' 처럼 괄호 설명이 붙어 와도 앞 단어만 씁니다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def word(s: str | None) -> str:
    return (s or "").strip().split(" ")[0].split("(")[0].upper()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--direction", default="LONG")
    ap.add_argument("--price", default="")
    ap.add_argument("--qty", default="")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    market, action = word(a.market), word(a.action)
    price = float(a.price.replace("$", "").replace(",", "")) if a.price.strip() else None
    if action not in ("BUY", "CLOSE", "CANCEL"):
        raise SystemExit(f"action 은 BUY / CLOSE / CANCEL 중 하나: {a.action}")

    if market == "US_STOCK":
        import swing
        if word(a.direction) == "SHORT":
            raise SystemExit("미국 주식 연습은 매수(LONG)만 기록합니다.")
        t = a.ticker.strip().upper()
        qty = int(float(a.qty.replace("주", "").replace(",", ""))) if a.qty.strip() else None
        port, _ = swing.load_state()
        held = any(p["ticker"] == t and p["status"] == "HOLDING" for p in port["positions"])
        if action == "BUY":
            act = "수량·단가수정" if held else "매수추가"
        elif action == "CLOSE":
            act = "매도완료"
        else:
            act = "미체결삭제"
        print(swing.manual(act, t, price, qty, cfg))
    elif market == "BINANCE":
        import futures
        from swing import usdkrw
        fx, _ = usdkrw()
        print(futures.manual(action, a.ticker, word(a.direction), price, a.qty, cfg, fx))
    else:
        raise SystemExit(f"market 은 US_STOCK 또는 BINANCE: {a.market}")


if __name__ == "__main__":
    main()
