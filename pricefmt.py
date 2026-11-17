"""코인 가격 표기 (가격 크기에 맞춘 호가 단위). pandas 없이 쓰도록 따로 둔다 (영상 작업 환경에도 쓰임)."""
from __future__ import annotations

import math


def tick_of(price: float) -> float:
    """가격 크기에 맞춘 호가 단위 (거래소 tickSize 를 모를 때)."""
    if price <= 0:
        return 0.0001
    return 10 ** (math.floor(math.log10(price)) - 5)


def fmt_px(v: float | None) -> str:
    if v is None:
        return "–"
    t = tick_of(v)
    dec = max(0, -int(math.floor(math.log10(t) + 1e-9)))
    return f"{v:,.{min(dec, 8)}f}"


# ── 시간 표기 (UTC ISO 문자열 ↔ 한국 시간)
from datetime import datetime, timedelta, timezone  # noqa: E402

KST = timezone(timedelta(hours=9))
UTC = timezone.utc


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(t: str) -> datetime:
    return datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def kst(t: datetime | str, fmt: str = "%m/%d %H:%M") -> str:
    if isinstance(t, str):
        t = parse(t)
    return t.astimezone(KST).strftime(fmt)
