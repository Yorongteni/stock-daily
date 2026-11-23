"""채팅용 코인 단타 원픽 — 리포트 없이 지금 시세로 원픽만 계산해 요약을 출력하고, 원픽 일지(복기)는 내부에 계속 쌓는다.

  python3 tools/coin_pick.py            # 요약 JSON 출력 + data/pick_journal.json 갱신
사용자가 "단타 원픽 추천"이라고 하면 Claude 가 이걸 돌려 채팅으로 답한다 (.claude/skills/coin-pick).
리포트(깃허브 Actions · docs/swing)는 사용자가 "리포트 만들어줘"라고 할 때만 만든다 (.claude/skills/swing-brief).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import futures as F  # noqa: E402
import yaml  # noqa: E402

KST = timezone(timedelta(hours=9))


def _curl_get(url, params=None, timeout=15):
    """이 작업 환경은 파이썬 HTTP 가 막혀 있어 curl 로 받는다 (OKX 공개 API)."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    out = subprocess.run(["curl", "-s", "-m", str(timeout), url], capture_output=True, text=True).stdout
    return json.loads(out)


def _fx() -> float:
    try:
        latest = sorted((ROOT / "docs" / "swing" / "data").glob("*.json"))[-1]
        return float(json.loads(latest.read_text(encoding="utf-8")).get("fx") or 1350.0)
    except Exception:  # noqa: BLE001
        return 1350.0


def main():
    F._get = _curl_get
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    now = datetime.now(timezone.utc)
    today = now.astimezone(KST).date().isoformat()
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):          # 진행 로그는 stderr 로 — stdout 은 요약 JSON 만
        fu = F.run(today, cfg, _fx(), now=now, force_source="okx")
    g = fu.get("btc_gate") or {}
    P = g.get("panel") or {}

    def pk(p):
        if not p:
            return None
        o = p["order"]
        return {"name": p.get("name"), "symbol": p["symbol"], "side": p["side"], "live": p.get("live"), "chg24": round(p.get("chg24") or 0, 2),
                "entry": o["entry"], "tp": o["tp"], "sl": o["sl"], "qty": o["qty"], "margin": o["margin"], "leverage": o["leverage"],
                "sl_dist": o["sl_dist"], "tp_pct": o["tp_pct"], "win_usdt": o["win_usdt"], "loss_usdt": o["loss_usdt"],
                "valid_until_kst": F.kst(p["valid_until"]), "cancel_level": p.get("cancel_level"),
                "sweep": p.get("sweep"), "sl_basis": o.get("sl_basis"), "limit_basis": o.get("limit_basis")}

    out = {"at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
           "btc": {"label": g.get("label"), "covering": g.get("covering"), "frames": P.get("frames"),
                   **{k: P.get(k) for k in ("price", "chg24", "chg4h", "oi_chg4h", "oi_chg24", "oi_read", "funding", "ls_ratio",
                                            "hi24", "lo24", "hi7", "lo7", "e20d", "e50d", "events")}},
           "pick": pk(fu.get("pick")), "pick2": pk(fu.get("pick2")), "block": fu.get("block"),
           "signals": fu.get("sweep_signals"), "journal_total": (fu.get("journal") or {}).get("total"),
           "journal_by_engine": ((fu.get("journal") or {}).get("by") or {}).get("엔진")}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
