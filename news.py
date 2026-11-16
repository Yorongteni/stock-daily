"""국내외 경제·사회 뉴스 헤드라인 수집 (API 키 없이 RSS).

- 경제 섹션 RSS + 구글 뉴스 검색 RSS(주제별, 13개 분야별)를 모아 최근 N시간만 남깁니다.
- 제목 중복 제거, 핵심 키워드 집계. 피드 하나가 실패해도 나머지는 계속 진행합니다.
"""
from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (stock-daily briefing bot)"

NOISE = re.compile(r"^\[(게시판|인사|부고|포토|사진|화보|오늘의 운세|날씨)\]|이벤트 실시|경품|할인 행사|출시 기념")
KO_STOP = set("""
있다 했다 한다 위해 대한 관련 이번 지난 올해 내년 오늘 어제 이날 오전 오후 전망 가능성 우려 기대 속보 단독 종합 포토 영상
기자 뉴스 사진 시장 경제 정부 한국 국내 미국 증시 주가 기업 투자 발표 이후 상승 하락 최대 최고 최저 기록 계획 추진 확대 강화
것 등 및 또 더 수 중 의 를 을 에 와 과 는 은 이 가 도 로 으로 에서 까지 부터 만 한 했 된 될 하는
""".split())
EN_STOP = set("""
the a an and or of to in on for with at by from as is are was were be been it its this that these those after before over
into amid says said say new news report reports update live stock stocks market markets us u.s. year week day today how why
what will could would may might up down more less than vs not no has have had who about inc corp co ltd
""".split())


def _fetch(url: str, timeout: int = 15):
    from netretry import retry
    return retry(_fetch_once, url, timeout, tries=3, base=1.5, label="RSS")


def _fetch_once(url: str, timeout: int = 15):
    import feedparser
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return feedparser.parse(r.read())


def _gnews(q: str, lang: str) -> str:
    qs = urllib.parse.quote(q + " when:2d")
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={qs}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={qs}&hl=en-US&gl=US&ceid=US:en"


def _clean_title(t: str) -> tuple[str, str]:
    """'제목 - 언론사' → (제목, 언론사)."""
    t = re.sub(r"\s+", " ", t or "").strip()
    m = re.match(r"(.+?)\s+[-–|]\s+([^-–|]{2,30})$", t)
    return (m.group(1).strip(), m.group(2).strip()) if m else (t, "")


def _summary(entry) -> str:
    raw = entry.get("summary") or ""
    try:
        from bs4 import BeautifulSoup
        txt = BeautifulSoup(raw, "html.parser").get_text(" ")
    except Exception:  # noqa: BLE001
        txt = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", txt).strip()[:220]


def _when(entry):
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc)
    return None


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", t.lower())[:40]


def keywords(titles: list[str], lang: str, n: int = 15) -> list[list]:
    c = Counter()
    for t in titles:
        if lang == "ko":
            words = re.findall(r"[가-힣A-Za-z0-9]{2,}", t)
            words = [re.sub(r"(은|는|이|가|을|를|의|에|와|과|도|로|으로|에서|까지|부터|만|께|들)$", "", w) for w in words]
            words = [w for w in words if len(w) >= 2 and w not in KO_STOP and not w.isdigit()]
        else:
            words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{2,}", t)]
            words = [w for w in words if w not in EN_STOP]
        c.update(set(words))
    return [[w, k] for w, k in c.most_common(n) if k >= 2]


def run(cfg: dict, categories: list[str] | None = None, demo: bool = False) -> dict:
    if demo:
        return {"items": [], "keywords": {"ko": [], "en": []}, "by_sector": {}, "errors": ["demo"], "count": 0}
    hours = cfg.get("hours", 36)
    per = cfg.get("per_feed", 8)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = [(f["name"], f["lang"], f["url"], "general") for f in cfg.get("feeds", [])]
    for lang, qs in (cfg.get("queries") or {}).items():
        jobs += [(f"검색: {q}", lang, _gnews(q, lang), "topic") for q in qs]
    if cfg.get("sector_queries") and categories:
        for c in categories:
            q = " OR ".join(c.split("·")[:2]) + " 주가"
            jobs.append((f"분야: {c}", "ko", _gnews(q, "ko"), "sector:" + c))

    items, seen, errors = [], set(), []
    by_sector: dict[str, list] = {}
    import time
    for name, lang, url, tag in jobs:
        time.sleep(0.4)          # 구글 뉴스 RSS 과다 요청(429) 방지
        try:
            feed = _fetch(url)
            n = 0
            for e in feed.entries:
                when = _when(e)
                if when and when < since:
                    continue
                title, src = _clean_title(e.get("title", ""))
                key = _norm(title)
                if not title or key in seen or NOISE.search(title):
                    continue
                seen.add(key)
                it = {"title": title, "source": src or name, "lang": lang, "feed": name,
                      "time": when.astimezone(KST).strftime("%m-%d %H:%M") if when else "",
                      "summary": _summary(e) if "news.google" not in url else "", "link": e.get("link", "")}
                if tag.startswith("sector:"):
                    by_sector.setdefault(tag[7:], []).append(it)
                else:
                    items.append(it)
                n += 1
                if n >= per:
                    break
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{name}: {type(ex).__name__}")
    items.sort(key=lambda x: x["time"], reverse=True)
    titles = {"ko": [i["title"] for i in items if i["lang"] == "ko"] + [i["title"] for v in by_sector.values() for i in v],
              "en": [i["title"] for i in items if i["lang"] == "en"]}
    return {
        "items": items[:80], "by_sector": {k: v[:5] for k, v in by_sector.items()},
        "keywords": {"ko": keywords(titles["ko"], "ko"), "en": keywords(titles["en"], "en")},
        "errors": errors, "count": len(items) + sum(len(v) for v in by_sector.values()),
        "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
