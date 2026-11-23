"""백테스트용 OKX 무기한 선물 과거 시세 받기 (공개 API, curl 사용).
python3 tools/bt_fetch.py <저장 폴더> [코인 수=30] [1h 일수=180] [15m 일수=120]
"""
import json, subprocess, sys, time
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
DAYS = {"1H": int(sys.argv[3]) if len(sys.argv) > 3 else 180, "15m": int(sys.argv[4]) if len(sys.argv) > 4 else 120}
B = "https://www.okx.com"


def get(path):
    for i in range(5):
        try:
            r = subprocess.run(["curl", "-s", "-m", "20", B + path], capture_output=True, text=True).stdout
            j = json.loads(r)
            if str(j.get("code")) == "0":
                return j["data"]
        except Exception:
            pass
        time.sleep(1 + i * 2)
    return []


spot = {r["instId"][:-5] for r in get("/api/v5/market/tickers?instType=SPOT") if r["instId"].endswith("-USDT")}
tk = [r for r in get("/api/v5/market/tickers?instType=SWAP") if r["instId"].endswith("-USDT-SWAP") and r["instId"][:-10] in spot]
tk.sort(key=lambda r: -float(r.get("volCcy24h") or 0) * float(r["last"] or 0))
insts = [r["instId"] for r in tk[:N]]
if "BTC-USDT-SWAP" not in insts:
    insts.insert(0, "BTC-USDT-SWAP")
json.dump(insts, open(out / "universe.json", "w"))
now = int(time.time() * 1000)
for inst in insts:
    for bar, days in DAYS.items():
        f = out / f"{inst}_{bar}.json"
        if f.exists():
            continue
        start = now - days * 86400 * 1000
        rows, after = [], None
        while True:
            d = get(f"/api/v5/market/history-candles?instId={inst}&bar={bar}&limit=100" + (f"&after={after}" if after else ""))
            if not d:
                break
            rows += d
            after = d[-1][0]
            if int(after) <= start:
                break
            time.sleep(0.12)
        rows = sorted({int(r[0]): [int(r[0])] + [float(x) for x in r[1:6]] for r in rows if int(r[0]) >= start}.values())
        json.dump(rows, open(f, "w"))
        print(inst, bar, len(rows), flush=True)
print("done")
