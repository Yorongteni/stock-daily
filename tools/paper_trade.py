"""3시간마다 가상 매매(모의 투자) → 결과 데이터 → 하루 한 번 보고.

  python3 tools/paper_trade.py open /tmp/pick.json   # 매시간 불러도 3시간 칸(KST 0·3·6·…시)마다 1번만, 원픽(A > 실험 > 시험 B/C)으로 가상 진입
  python3 tools/paper_trade.py settle                # 열린 가상 매매를 15분봉으로 채점 (TP·SL·24시간 정리)
  python3 tools/paper_trade.py report [시간=24]       # 최근 N시간 결과 + 누적 성적 (텍스트)

규칙: 증거금 60 USDT · 격리 3배 · **지금 가격으로 진입**(지정가 미체결 없이 매번 데이터가 쌓이도록) ·
TP/SL 은 원픽의 진입가 대비 % 거리를 그대로 · 같은 15분봉에서 TP·SL 둘 다 닿으면 손절로 처리(보수적) ·
24시간 지나면 그 봉 종가로 정리 · 수수료 0.055% × 2 (테이커) · 펀딩비 무시.
원픽 규칙(futures.py)은 건드리지 않는다 — 기록만.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "paper_trades.json"
KST = timezone(timedelta(hours=9))
MARGIN, LEV, FEE, HOLD_H = 60.0, 3, 0.00055, 24


def get(path):
    out = subprocess.run(["curl", "-s", "-m", "20", "https://www.okx.com" + path], capture_output=True, text=True).stdout
    return json.loads(out)["data"]


def inst(sym):
    return sym.replace("USDT", "") + "-USDT-SWAP"


def load():
    return json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else {"rules": __doc__.split("규칙: ")[1].strip(), "trades": []}


def save(d):
    DB.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def open_trade(pick_path):
    now = datetime.now(timezone.utc)
    k = now.astimezone(KST); slot = k.replace(hour=k.hour // 3 * 3, minute=0, second=0, microsecond=0)   # 3시간 칸 (매시간 불려도 칸마다 1번)
    sid = slot.strftime("%Y-%m-%d %H시")
    d = load()
    if any(t["slot"] == sid for t in d["trades"]):
        print("이미 기록된 슬롯", sid); return
    r = json.loads(Path(pick_path).read_text(encoding="utf-8"))
    src, p = next(((k, r.get(k)) for k in ("pick", "exp_pick", "try_pick") if r.get(k)), (None, None))
    if not p:
        d["trades"].append({"slot": sid, "status": "none", "why": r.get("block")}); save(d); print("원픽 없음", sid); return
    L = p["side"] == "LONG"
    live = float(get(f"/api/v5/market/ticker?instId={inst(p['symbol'])}")[0]["last"])
    tp_pct = abs(p["tp"] / p["entry"] - 1); sl_pct = abs(p["sl"] / p["entry"] - 1)
    grade = {"pick": "A", "exp_pick": "실험"}.get(src) or p.get("grade") or "C"
    t = {"slot": sid, "status": "open", "src": src, "grade": grade, "symbol": p["symbol"], "name": p.get("name"), "side": p["side"],
         "entry": live, "entry_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "tp": round(live * (1 + tp_pct if L else 1 - tp_pct), 8), "sl": round(live * (1 - sl_pct if L else 1 + sl_pct), 8),
         "tp_pct": round(tp_pct * 100, 2), "sl_pct": round(sl_pct * 100, 2), "pick_entry": p["entry"],
         "btc_label": (r.get("btc") or {}).get("label"), "btc_price": (r.get("btc") or {}).get("price")}
    d["trades"].append(t); save(d); print("가상 진입", sid, t["symbol"], t["side"], live)


def settle():
    d = load(); now = datetime.now(timezone.utc); n = 0
    for t in d["trades"]:
        if t["status"] != "open":
            continue
        t0 = datetime.strptime(t["entry_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        try:
            rows = get(f"/api/v5/market/candles?instId={inst(t['symbol'])}&bar=15m&limit=300")[::-1]
        except Exception as e:  # noqa: BLE001
            print("시세 실패", t["symbol"], e); continue
        L = t["side"] == "LONG"; end = t0 + timedelta(hours=HOLD_H); res = None
        for c in rows:
            ts = datetime.fromtimestamp(int(c[0]) / 1000, timezone.utc)
            if ts + timedelta(minutes=15) <= t0 or c[8] != "1":
                continue                                    # 진입 전 봉·미완성 봉 제외
            hi, lo, cl = float(c[2]), float(c[3]), float(c[4])
            hit_sl = lo <= t["sl"] if L else hi >= t["sl"]
            hit_tp = hi >= t["tp"] if L else lo <= t["tp"]
            if hit_sl:
                res = ("LOSS", t["sl"], ts); break
            if hit_tp:
                res = ("WIN", t["tp"], ts); break
            if ts + timedelta(minutes=15) >= end:
                res = ("TIME", cl, ts + timedelta(minutes=15)); break
        if not res:
            continue
        kind, px, ts = res
        move = (px / t["entry"] - 1) * (1 if L else -1)
        pnl = MARGIN * LEV * move - MARGIN * LEV * FEE * 2
        t.update(status=kind, exit=px, exit_time=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 held_h=round((ts - t0).total_seconds() / 3600, 1), pnl_usdt=round(pnl, 2), roe=round(pnl / MARGIN * 100, 2)); n += 1
    save(d); print("채점", n, "건")


def stats(ts):
    n = len(ts); w = sum(t["pnl_usdt"] > 0 for t in ts); s = sum(t["pnl_usdt"] for t in ts)
    return f"{n}건 승 {w} ({w / n * 100:.0f}%) · 합계 {s:+.2f} USDT" if n else "0건"


def report(hours=24):
    d = load(); now = datetime.now(timezone.utc); since = now - timedelta(hours=hours)
    done = [t for t in d["trades"] if t["status"] in ("WIN", "LOSS", "TIME")]
    recent = [t for t in done if datetime.strptime(t["exit_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) >= since]
    opened = [t for t in d["trades"] if t["status"] == "open"]
    ko = {"WIN": "익절", "LOSS": "손절", "TIME": "24h정리"}
    out = [f"📒 가상 매매 일일 보고 ({now.astimezone(KST):%m/%d %H:%M}) — 3시간마다 60 USDT·3배 모의 진입",
           f"최근 {hours}시간 청산: {stats(recent)}"]
    for t in recent:
        out.append(f" · {t['slot'][5:]} {t['name']} {'롱' if t['side'] == 'LONG' else '숏'}({t['grade']}) {ko[t['status']]} {t['pnl_usdt']:+.2f}")
    out.append(f"진행 중 {len(opened)}건: " + ", ".join(f"{t['name']} {'롱' if t['side'] == 'LONG' else '숏'}" for t in opened) if opened else "진행 중 0건")
    out.append(f"누적: {stats(done)}")
    for key, lab in (("grade", "등급"), ("side", "방향")):
        g = {}
        for t in done:
            g.setdefault(t[key], []).append(t)
        if g:
            out.append(f"{lab}별: " + " / ".join(f"{k} {stats(v)}" for k, v in sorted(g.items())))
    print("\n".join(out))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "open":
        open_trade(sys.argv[2])
    elif cmd == "settle":
        settle()
    else:
        report(int(sys.argv[2]) if len(sys.argv) > 2 else 24)
