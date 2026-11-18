"""AI 브리핑 입력(brief) 만들기와, API 모드일 때 Claude 호출.

- build_brief(): 수집한 데이터 묶음 + prompts/briefing.md → 루틴/API가 읽을 마크다운 한 파일.
- generate_api(): mode: api 일 때 GitHub Actions 안에서 직접 호출 (ANTHROPIC_API_KEY 필요).
루틴 모드에서는 claude.ai 예약 작업이 brief 파일을 읽고 docs/ai/<날짜>_<슬롯>.json 을 씁니다
(.claude/skills/daily-briefing/SKILL.md).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SLOT_FOCUS = {
    "am": ("모닝 브리핑(07:00 공개). 밤사이 마감된 미국·유럽 증시와 금리·환율·원자재·비트코인 움직임을 근거로 "
           "**오늘 한국 시장(코스피·코스닥)**을 예측합니다: 개장 예상(시초가 갭 크기), 장중 흐름 시나리오"
           "(09:00~10:00 / 오전 / 오후·마감), 예상 종가 밴드, 오늘 집중할 주도 섹터. forecast.market = \"코스피\"."),
    "pm": ("나이트 브리핑(22:00 공개). 오늘 한국장 마감을 복기(지수·섹터·수급·원인)하고, 미국 선물·프리마켓 흐름과 "
           "오늘 밤 발표 지표·연준 발언·실적을 근거로 **오늘 밤 미국 증시(S&P 500·나스닥)**를 예측합니다. "
           "금리·달러·유가·지정학 등 글로벌 매크로 이슈를 점검합니다. forecast.market = \"S&P 500\"."),
}
SEARCH_LIST = {
    "am": "간밤 미국 증시 마감 원인 · 미국채 금리와 달러 움직임 · 오늘 국내 증시 전망과 외국인 수급 · 오늘 국내외 발표 일정 · "
          "주요 기업 실적·정부 정책 뉴스 · 13개 분야 중 뉴스가 있는 분야",
    "pm": "오늘 코스피·코스닥 마감 원인과 외국인·기관 수급 · 미국 지수 선물과 프리마켓 특징주 · 오늘 밤 미국 경제지표·연준 발언·실적 · "
          "유가·지정학 · 13개 분야 중 뉴스가 있는 분야",
}

SCHEMA = """{
  "headline": "핵심 뷰가 담긴 한 줄 제목 (35자 이내)",
  "stance": {"label": "적극 매수 (주식 비중 늘리기) | 골라서 매수 (좋은 종목만 조금씩) | 관망 (지금 비중 유지) | 현금 확보·관망 (주식 비중 줄이기) 중 하나 (글자 그대로)", "score": 1, "one_liner": "결론 한 문장 (근거 수치 포함)"},
  "history_context": {
    "summary": "작년 이맘때·최근 3~5년과 비교해 지금 시장이 결정적으로 달라진 점 (5~7문장, 수치 포함)",
    "regime": {"market_type": "유동성 장세 | 실적 장세 | 역금융 장세 | 역실적 장세 + 근거", "leadership_shift": "작년 주도 섹터 → 지금 주도 섹터와 이유", "rate_fx": "금리·환율 레짐 변화"},
    "same": ["과거와 같은 점"], "different": ["과거와 다른 점"],
    "analogs": [{"date": "[유사 국면] 데이터의 날짜 그대로 (예: 2008-09-05)", "period": "예: 2008년 9월 — 리먼 브라더스 파산 직전",
                 "what_happened": "그때 무슨 일이 있었는지 쉬운 말 2문장", "why_similar": "지금과 닮은 점 (수치)", "what_differs": "지금과 다른 점 (수치)",
                 "lesson": "그 뒤 시장이 어떻게 됐고, 지금 우리에게 주는 시사점 (쉬운 말)"}]
  },
  "macro": {"summary": "매크로·다중 자산 진단 (4~6문장)",
            "assets": [{"name": "원/달러 환율", "view": "상승 | 보합 | 하락", "level_comment": "역사적 위치와 의미", "impact": "주식·섹터에 주는 영향"}]},
  "social": {"summary": "사회·정책·지정학 흐름과 시장 반영 (4~6문장)",
             "themes": [{"theme": "이슈", "channel": "금리 | 환율 | 실적 | 수급 | 심리 | 정책", "impact": "영향받는 자산·섹터와 방향", "priced_in": "미반영 | 일부 반영 | 대부분 반영", "signal": "확인할 선행 신호"}]},
  "forecast": {"market": "코스피 또는 S&P 500", "base_level": 0, "band_low": 0, "band_high": 0, "direction": "상승 | 보합 | 하락", "prob_up": 55,
               "open_view": "시초가 예상 (갭 크기 포함)", "intraday": "장중 흐름 시나리오 (시간대별)", "secondary": "모닝=코스닥 / 나이트=나스닥 예상",
               "scenarios": [{"name": "강세", "prob": 25, "trigger": "조건", "path": "전개"}, {"name": "기본", "prob": 50, "trigger": "", "path": ""}, {"name": "약세", "prob": 25, "trigger": "", "path": ""}],
               "focus_sectors": ["오늘 집중할 분야"], "adjustment": "정량 기준선 대비 조정한 이유"},
  "opportunities": [{"title": "", "why": "근거 수치", "how": "대응 전략·타점 (가격대·조건)", "sectors": ["관련 분야"]}],
  "risks": [{"title": "", "why": "", "signal": "감시 지표와 경계 수준", "severity": "높음 | 중간 | 낮음"}],
  "sectors": [{"name": "분야명 (데이터 표기 그대로)", "stance": "비중확대 | 중립 | 비중축소", "score": 0, "flow": "유입 | 유출 | 중립",
               "why": "지금 강·약한 이유 (2문장, 수치·뉴스)", "vs_past": "1년 전·3년 범위 대비 위치 변화", "trigger": "판단을 바꿀 조건"}],
  "allocation": {"kr_equity": 25, "us_equity": 30, "gold_commodities": 10, "usd_cash": 15, "krw_cash_bonds": 15, "alternatives": 5,
                 "neutral": {"kr_equity": 25, "us_equity": 30, "gold_commodities": 10, "usd_cash": 15, "krw_cash_bonds": 15, "alternatives": 5},
                 "rationale": "비중 근거 (4~6문장: 달러·금리·원자재·주식의 역사적 위치)", "hedges": "헤지 수단과 규모", "rebalance_trigger": "비중을 바꿀 조건"},
  "action_plan": ["오늘의 구체적 행동 (예: 반도체 비중 5%p 이내 분할 매수, 코스피 5,150 이탈 시 중단)"],
  "invalidation": ["이 뷰가 틀렸다고 판단할 조건 (수치)"],
  "watch_events": ["오늘·이번 주 주요 일정 (KST 시각)"],
  "tickers": {"관심 종목 code": "한 줄 코멘트 (60자 이내)"},
  "easy": {"summary": ["경제를 모르는 사람도 이해하는 오늘의 핵심 3줄 (각 60자 안팎)"],
           "history": {"one": "[한 줄 결론] 지금 시장이 왜 이런지 쉬운 말 1문장", "why": "[원인과 배경] 뉴스·지표를 연결한 이유 1~2문장", "do": "[행동 지침] 그래서 오늘 어떻게 대응할지 1문장"},
           "macro": {"one": "", "why": "", "do": ""}, "forecast": {"one": "", "why": "", "do": ""},
           "sectors": {"one": "", "why": "", "do": ""}, "opps_risks": {"one": "", "why": "", "do": ""}, "conclusion": {"one": "", "why": "", "do": ""}},
  "chains": [{"from": "출발 사건 (예: 미국 금리 상승)", "steps": ["중간 연결 1 (예: 돈 빌리는 비용 증가)", "중간 연결 2"], "so": "결과 (예: 반도체·성장주 주가 부담)", "now": "지금 이 고리가 어디까지 진행됐는지 (수치)"}],
  "glossary": [{"term": "오늘 리포트에 나온 용어", "meaning": "중학생도 알아듣는 뜻 (1문장)", "why": "오늘 이 용어가 왜 중요한지 (1문장)"}],
  "script": {"intro": "", "history": "", "macro": "", "social_forecast": "", "sectors": "", "opps_risks": "", "conclusion": ""},
  "spotlight": [{"category": "[스포트라이트 대상]의 분야명 그대로", "company": "대표 기업 이름 그대로",
                 "past_now": "[1단계 산업의 어제와 오늘] '이 분야는 2~3년 전 ~한 흐름 속에서 두각을 드러내기 시작해, 최근에는 ~와 맞물려 다시 주목받고 있습니다' 식의 시간 흐름 서술 + 3년·1년 수치 (3~4문장)",
                 "market_link": "[2단계 시장·사회 흐름과의 연결] 지금의 금리·환율·유가·공포지수 환경과 최신 뉴스(수출 통계·정책·규제·소비 트렌드)가 이 산업에 주는 구체적 영향 (3~4문장)",
                 "company_story": "[3단계 대표 기업과 3년 실적 검증] 무엇을 팔아 어떻게 돈을 버는지 쉬운 소개 + '왜 하필 이 기업인가'를 3년 매출·이익 성장, 업종 내 위치(PER·점유율·수주)로 증명 (3~4문장)",
                 "business": "대표 기업이 하는 일 1문장 (영상 화면용 요약)",
                 "risk": "[4단계 균형 잡힌 체크 포인트] 흐름이 꺾이거나 주의할 거시적·산업적 변수 (1~2문장)"}],
  "sources": [{"title": "실제로 열어 읽은 기사·자료 제목 그대로", "publisher": "언론사·기관", "url": "https://… (기사 원문 주소)",
               "date": "기사 게시일 YYYY-MM-DD (기사에 적힌 날짜)", "used_for": "이 자료로 확인한 내용 (어느 섹션의 어떤 사실)"}]
}
분량: easy.summary 3개, chains 3~5개, glossary 8~12개, opportunities 3~4개, risks 3~4개, sectors 13개 전부, macro.assets 9개 이상(환율·달러·미국 10년·장단기 금리차·VIX·금·원유·구리·비트코인),
social.themes 3~6개, history_context.analogs 1~2개, action_plan 3~5개, invalidation 2~3개, spotlight 3개([스포트라이트 대상] 순서 그대로),
sources 6개 이상(그중 2개 이상은 브리핑 날짜 기준 이틀 안에 게시된 기사).
allocation 6개 비중의 합은 100. neutral 은 평소 기준 비중(위 예시값 그대로 써도 됨)."""


# ───────────────────────── 데이터 → 텍스트 ─────────────────────────
def _f(v, fmt="+.1f", unit=""):
    return "–" if v is None else format(v, fmt) + unit


def _macro_text(macro: dict) -> str:
    rows = ["| 자산 | 기준일 | 현재 | 1일 | 1주 | 1개월 | 작년 동기 대비 | 1년 전 값 | 3년 평균 대비 | 5년 백분위 | 5년 범위 | 200일선 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in macro.get("assets", []):
        if "error" in a:
            rows.append(f"| {a['name']} | 데이터 없음 ({a['error'][:40]}) |||||||||||")
            continue
        rate = a["kind"] == "rate"
        u, fm = ("%p", "+.2f") if rate else ("%", "+.1f")
        cv = (lambda v: None if v is None else v / 100) if rate else (lambda v: v)  # 금리는 bp → %p
        rows.append(f"| {a['name']} | {a['date']} | {a['last']:,} | {_f(cv(a['chg_1d']), fm, u)} | {_f(cv(a['chg_1w']), fm, u)} | "
                    f"{_f(cv(a['chg_1m']), fm, u)} | {_f(cv(a['yoy']), fm, u)} | {a.get('year_ago') or '–'} | {_f(cv(a['vs_avg_3y']), fm, u)} | "
                    f"{_f(a['pct_5y'], '.0f')} | {a['min_5y']:,}~{a['max_5y']:,} | {a.get('trend') or '–'} |")
    out = ["## 매크로·다중 자산 (과거 5년 비교, 금리 변화는 %p. 5년 백분위 85 = 최근 5년 중 상위 15%)", "\n".join(rows), "", "## 레짐 판정"]
    out += [f"- {r['label']}: **{r['value']}** — {r['evidence']}" for r in macro.get("regimes", [])]
    an = macro.get("analogs") or {}
    if an.get("matches"):
        feats = an.get("features") or {}
        unit = {"pct": "%", "rate": "%", "pp": "%p", "num": ""}

        def st(s):
            return ", ".join(f"{feats.get(k, [k, ''])[0]} {v}{unit.get(feats.get(k, ['', ''])[1], '')}"
                             for k, v in (s or {}).items() if v is not None)
        out += ["", f"## 유사 국면 ({an.get('since', '')[:4]}년 이후 주간 데이터 중 지금과 가장 비슷했던 시점, 비슷한 순)",
                f"- 지금: {st(an['now'])}"]
        for m in an["matches"]:
            out.append(f"- {m['date']} (유사도 {m['similarity']}): 당시 {st(m['state'])} → 이후 코스피 1개월 {_f(m.get('kospi_4w'), '+.1f', '%')}, "
                       f"3개월 {_f(m.get('kospi_13w'), '+.1f', '%')}, 6개월 {_f(m.get('kospi_26w'), '+.1f', '%')} / S&P500 1개월 {_f(m.get('spx_4w'), '+.1f', '%')}, "
                       f"3개월 {_f(m.get('spx_13w'), '+.1f', '%')}, 6개월 {_f(m.get('spx_26w'), '+.1f', '%')}")
        out.append("- history_context.analogs 에 위 사례를 같은 순서로 모두 설명하세요 (date 는 위 날짜 그대로).")
    q = macro.get("quant") or {}
    out += ["", "## 정량 예측 기준선"]
    if "error" in q or not q:
        out.append(f"- 계산 실패: {q.get('error', '데이터 없음')}")
    else:
        out.append(f"- {q['target']}: 전일 종가 {q['base_close']:,} → 기대 {q['expected']:,} ({_f(q['expected_pct'], '+.2f', '%')}), "
                   f"일반적인 예상 등락 범위 {q['band_low']:,} ~ {q['band_high']:,}, 하루 평균 변동 {q['sigma_pct']}%, 상승 확률 {q.get('prob_up')}% · 근거: {q['driver']} (내부 모델: {q.get('model', '')} — 본문에 쓰지 말 것)")
    return "\n".join(out)


def _results_text(results: dict) -> str:
    lines = ["## 관심 종목 기술적 지표 (추세 점수 -6~+6: 이동평균 배열·MACD·TSI·RSI 합산)"]
    for code, r in results.items():
        if "error" in r:
            continue
        sig = ", ".join(s[1] for s in r.get("signals", [])) or "특이 신호 없음"
        lines.append(f"- {r['name']}({code}) {r['date']} 종가 {r['close']:,} | 1일 {_f(r['chg_1d'], '+.2f', '%')} 5일 {_f(r['chg_5d'], '+.2f', '%')} "
                     f"20일 {_f(r['chg_20d'], '+.2f', '%')} | 52주 위치 {_f(r['pos_52w'], '.0f', '%')} | RSI {_f(r['rsi'], '.0f')} TSI {_f(r['tsi'], '.1f')} "
                     f"| {r['label']}({r['score']:+d}) | {sig}")
    return "\n".join(lines)


def _sector_text(screens: dict) -> str:
    if not screens or "error" in screens:
        return "## 13개 분야\n(분야 데이터 없음)"
    rows = ["## 13개 분야 (동일가중 분야 지수, 상대강도 = 분야 수익률 − 전체 유니버스 수익률)",
            "| 분야 | 종목수 | 1일 | 5일 | 20일 | 60일 | 1년 | 3년 | 시장대비 60일 | 1년 전 시장대비 60일 | 상대강도 3년 백분위 | 60일 순위(지금/1년 전) | 20일선 위 | 거래대금(5일/60일) | 자금 흐름 | 매출성장 중앙값 | PER 중앙값 국내/미국 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in screens.get("categories", []):
        rows.append(f"| {c['name']} | {c['n']} | {_f(c.get('ret_1d'))} | {_f(c.get('ret_5d'))} | {_f(c.get('ret_20d'))} | {_f(c.get('ret_60d'))} | "
                    f"{_f(c.get('ret_1y'))} | {_f(c.get('ret_3y'))} | {_f(c.get('rs_60d'))} | {_f(c.get('rs_60d_1y_ago'))} | {_f(c.get('rs_pct_3y'), '.0f')} | "
                    f"{c.get('rank_60d') or '–'}/{c.get('rank_60d_1y_ago') or '–'} | {c.get('breadth', '–')}% | {c.get('turnover_ratio') or '–'} | {c.get('flow') or '–'} | "
                    f"{_f(c.get('rev_g'))} | {c.get('pe_kr') or '–'}/{c.get('pe_us') or '–'} |")
    ld = screens.get("leadership") or {}
    out = ["\n".join(rows)]
    if ld:
        out.append(f"\n## 분야 리더십\n- 지금 60일 상위: {', '.join(ld.get('now', []))} / 하위: {', '.join(ld.get('laggards_now', []))}\n"
                   f"- 1년 전 60일 상위: {', '.join(ld.get('year_ago', []))}")
    val = screens.get("valuation") or {}
    if val:
        out.append("\n## 밸류에이션 (유니버스 중앙값)\n" + "\n".join(
            f"- {'국내' if m == 'kr' else '미국'}: PER {v.get('pe_median') or '–'}배, PBR {v.get('pb_median') or '–'}배, "
            f"이익수익률 {v.get('earnings_yield') or '–'}% ({v.get('n')}종목)" for m, v in val.items()))
    titles = {"value": "저평가 후보", "growth": "성장 기대 후보", "overvalued": "고평가 위험"}
    out.append("\n## 종목 스크리닝 (3년 실적·밸류에이션, 목록마다 분야당 1종목)")
    for k, t in titles.items():
        out.append(f"- {t}: " + "; ".join(f"{r['name']}({r['ticker']}, {r['category']}) {r['reason']}" for r in screens.get(k, [])))
    return "\n".join(out)


def _val_hist_text(valhist: dict) -> str:
    if not valhist:
        return ""
    lines = ["\n## 밸류에이션 누적 기록 (매일 쌓는 값, 기간이 짧을 수 있음)"]
    for m, v in valhist.items():
        lines.append(f"- {'국내' if m == 'kr' else '미국'} PER 중앙값: 현재 {v.get('now')}, 누적 {v.get('days')}일 평균 {v.get('avg')}, "
                     f"누적 범위 내 백분위 {v.get('pct')}")
    return "\n".join(lines)


def _news_text(news: dict) -> str:
    if not news or not news.get("count"):
        return "## 뉴스 헤드라인\n(수집 실패 — 웹 검색으로 직접 확인)"
    ko = [i for i in news["items"] if i["lang"] == "ko"][:28]
    en = [i for i in news["items"] if i["lang"] == "en"][:22]
    out = [f"## 뉴스 헤드라인 (수집 {news.get('collected_at')} KST, 최근 36시간)",
           "- 국내 키워드: " + ", ".join(f"{w}({n})" for w, n in news["keywords"].get("ko", [])),
           "- 해외 키워드: " + ", ".join(f"{w}({n})" for w, n in news["keywords"].get("en", [])), "", "### 국내"]
    out += [f"- [{i['time']}] {i['title']} ({i['source']})" for i in ko]
    # 해외 기사는 미국 현지 날짜를 함께 적는다 ('after the bell', 'today' 같은 표현이 미국 날짜 기준이라서)
    out += ["", "### 해외 (한국 시각 · 미국 동부 시각 ET)"] + [
        f"- [{i['time']} KST · 미국 {i['time_et']} ET] {i['title']} ({i['source']})" if i.get("time_et")
        else f"- [{i['time']} KST] {i['title']} ({i['source']})" for i in en]
    out += ["", "### 분야별"]
    for k, v in (news.get("by_sector") or {}).items():
        out.append(f"- {k}: " + " / ".join(i["title"] for i in v[:3]))
    return "\n".join(out)


def _spotlight_text(bundle: dict) -> str:
    try:
        import spotlight
        return spotlight.brief_text(bundle.get("screens") or {}, bundle.get("macro") or {}, bundle.get("news") or {})
    except Exception:  # noqa: BLE001
        return ""


def _time_anchor(collected_at: str) -> str:
    """한국·미국 날짜 기준점. AI 가 '미국 17일 장 마감 후'를 '미국 18일'로 하루 밀려 쓰지 않게 한다."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    kst = datetime.strptime(collected_at, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    et = kst.astimezone(ZoneInfo("America/New_York"))
    dst = bool(et.dst())
    close_kst = "05:00" if dst else "06:00"
    open_kst = "22:30" if dst else "23:30"
    m = et.hour * 60 + et.minute
    state = ("개장 전(프리마켓)" if m < 570 else "정규장 진행 중" if m < 960 else "장 마감 후(시간외)") if et.weekday() < 5 else "주말 휴장"
    nxt = kst + timedelta(days=1)
    return "\n".join([
        f"- 지금 미국 동부(ET) 시각: {et:%Y-%m-%d %H:%M} ({['월','화','수','목','금','토','일'][et.weekday()]}) · 미국 증시 {state}"
        + (" · 서머타임" if dst else ""),
        f"- 미국 정규장 = 한국 {open_kst} ~ 다음 날 {close_kst}. 그래서 **미국 X일 장 마감 후(after the bell) 발표 = 한국 X+1일 {close_kst}~ 아침**입니다.",
        f"- 예: 미국 {et:%m월 %d일} 장 마감 후 발표 → 한국 {(et + timedelta(days=1)):%m월 %d일} 아침. "
        f"한국 {kst:%m월 %d일} 기준 '오늘 밤 미국장'은 미국 {kst:%m월 %d일} 장이고, 그 장 마감 후 발표는 한국 {nxt:%m월 %d일} 아침입니다.",
        "- 해외 기사의 'today·tonight·after the bell'은 기사 옆에 적힌 **미국 날짜** 기준입니다. 일정을 쓸 때는 미국 날짜와 한국 날짜를 둘 다 적고, 위 규칙으로 하루 밀리지 않았는지 확인하세요.",
    ])


def build_brief(bundle: dict, slot_cfg: dict) -> str:
    slot = bundle["slot"]
    data = "\n\n".join([
        f"## 시점\n- 수집 시각: {bundle['collected_at']} KST · 슬롯: {slot} ({slot_cfg.get('name', '')})\n"
        + _time_anchor(bundle["collected_at"]),
        _macro_text(bundle.get("macro") or {}),
        _results_text(bundle.get("results") or {}),
        _sector_text(bundle.get("screens") or {}) + _val_hist_text(bundle.get("valuation_history") or {}),
        _spotlight_text(bundle),
        _news_text(bundle.get("news") or {}),
    ])
    tpl = (ROOT / "prompts" / "briefing.md").read_text(encoding="utf-8")
    rep = {"{date}": bundle["date"], "{slot_name}": slot_cfg.get("name", slot), "{ready}": slot_cfg.get("ready", ""),
           "{slot_focus}": SLOT_FOCUS[slot], "{search_list}": SEARCH_LIST[slot], "{schema}": SCHEMA, "{data}": data}
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    return tpl


# ───────────────────────── API 모드 ─────────────────────────
def extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")
    return json.loads(text[start:end + 1])


def generate_api(brief: str, cfg: dict) -> dict:
    """성공 시 AI dict, 실패 시 {"error": ...}."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY 가 없어 API 모드를 건너뜀"}
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic 패키지 없음"}
    kwargs = dict(model=cfg.get("model", "claude-sonnet-5-5"), max_tokens=16000,
                  messages=[{"role": "user", "content": brief}])
    if cfg.get("web_search", True):
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": cfg.get("max_searches", 15)}]
    import time
    last = None
    for i in range(3):
        try:
            resp = anthropic.Anthropic().messages.create(**kwargs)
            text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return extract_json(text)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (2 ** i))
    return {"error": f"API 브리핑 생성 실패: {last}"}
