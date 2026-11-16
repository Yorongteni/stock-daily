"""네트워크 작업 재시도 (지수 백오프). 데이터 수집·뉴스·API·음성 합성에서 공통으로 사용."""
from __future__ import annotations

import time


def retry(fn, *args, tries: int = 3, base: float = 2.0, label: str = "", **kwargs):
    """fn(*args, **kwargs) 를 최대 tries 번 시도. 실패 사이 base, base*2, base*4 … 초 대기. 마지막 오류는 그대로 올림."""
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries - 1:
                wait = base * (2 ** i)
                print(f"    … 재시도 {i + 1}/{tries - 1}{f' ({label})' if label else ''}: {type(e).__name__} → {wait:.0f}초 후")
                time.sleep(wait)
    raise last
