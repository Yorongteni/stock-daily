"""Claude API로 시장 해설·시나리오를 생성."""
import json
import os
import re

PROMPT = """당신은 한국 개인투자자를 위한 시장 애널리스트입니다.
아래는 오늘({today}) 기준 관심 종목들의 기술적 지표 요약(JSON)입니다.
{search_line}

[지표 데이터]
{data}

{screens}

다음 JSON 형식으로만 답하세요. JSON 앞뒤에 다른 글자나 ``` 표시를 넣지 마세요.
{{
  "headline": "오늘 시장을 한 문장으로 (40자 이내)",
  "market_overview": "국내·미국 시장 흐름과 주요 원인 (4~6문장)",
  "kr_view": "국내 시장 관전 포인트 (2~3문장)",
  "us_view": "미국 시장 관전 포인트 (2~3문장)",
  "scenarios": {{
    "bull": "강세 시나리오와 그 조건 (2문장)",
    "base": "기본 시나리오 (2문장)",
    "bear": "약세 시나리오와 그 조건 (2문장)"
  }},
  "categories": {{ "<분야명>": "해당 분야의 최근 뉴스·수요/기술 변화·단기 흐름 (2~3문장)" }},
  "tickers": {{ "<code>": "종목별 한 줄 코멘트 (지표 근거 포함, 60자 이내)" }},
  "risks": ["향후 1~2주 주의할 이벤트/리스크", "..."],
  "watch_events": ["다가오는 주요 일정(실적, FOMC, 지표 발표 등)", "..."],
  "picks": [
    {{"ticker": "티커", "name": "종목명", "category": "분야명", "thesis": "주목하는 이유 (실적·밸류에이션·뉴스 근거, 2문장)",
      "risk": "핵심 리스크 (1문장)", "check": "투자 전 확인할 점 (1문장)"}}
  ]
}}

원칙:
- 지표 수치와 뉴스를 근거로 쓰고, 단정적 예측이나 매수/매도 권유는 하지 마세요.
- 확인되지 않은 정보는 쓰지 마세요.
- tickers에는 데이터에 있는 모든 code를 넣으세요.
- categories에는 [분야별 동향]의 모든 분야를 빠짐없이 넣으세요. 그날 주목받은 분야만이 아니라
  부진하거나 소외된 분야도 각각 분야 고유의 뉴스로 채우세요. 분야마다 웹 검색을 따로 해도 좋습니다.
- picks는 스크리닝 결과와 뉴스를 종합해 지금 살펴볼 만한 종목 5개입니다. 5개 모두 서로 다른 분야에서 고르고,
  최소 1개는 최근 20일 부진했던 분야에서 실적·밸류에이션상 회복 근거가 있는 종목으로 고르세요.
  고평가 위험 목록 종목은 제외하고, 매수 권유가 아니라 검토 후보로 쓰세요.
"""


def _compact(results: dict) -> dict:
    out = {}
    for code, r in results.items():
        if "error" in r:
            continue
        out[code] = {
            "name": r["name"], "market": r["market"], "date": r["date"],
            "close": r["close"], "chg_1d%": r["chg_1d"], "chg_5d%": r["chg_5d"],
            "chg_20d%": r["chg_20d"], "pos_52w%": r["pos_52w"],
            "rsi": r["rsi"], "tsi": r["tsi"], "score(-6~6)": r["score"],
            "label": r["label"], "signals": [s[1] for s in r["signals"]],
        }
    return out


def _extract_json(text: str):
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")
    return json.loads(text[start:end + 1])


def generate(results: dict, screens: dict, today: str, cfg: dict) -> dict:
    """성공 시 해설 dict, 실패 시 {"error": "..."} 반환."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY 환경변수가 없어 AI 해설을 건너뛰었습니다."}
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic 패키지가 설치되지 않았습니다 (pip install anthropic)."}

    use_search = cfg.get("web_search", True)
    prompt = PROMPT.format(
        today=today,
        data=json.dumps(_compact(results), ensure_ascii=False, indent=1),
        screens=screens_text(screens),
        search_line=("먼저 웹 검색으로 오늘·어제의 국내/미국 증시 주요 뉴스와 "
                     "다가오는 일정을 확인한 뒤 분석에 반영하세요." if use_search else ""),
    )
    kwargs = dict(
        model=cfg.get("model", "claude-sonnet-5-5"),
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    if use_search:
        kwargs["tools"] = [{
            "type": "web_search_20250305", "name": "web_search",
            "max_uses": cfg.get("max_searches", 15),
        }]

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(**kwargs)
        # 웹 검색을 쓰면 텍스트 블록이 여러 개로 나뉘므로 마지막 JSON을 추출
        text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _extract_json(text)
    except Exception as e:  # noqa: BLE001
        return {"error": f"AI 해설 생성 실패: {e}"}


CHAT_PROMPT = """아래는 {today} 기준 내 관심 종목 지표와, 분야별로 나눈 160여 종목의 동향·스크리닝 결과입니다.
웹 검색으로 최근 뉴스를 확인하되, 시장 전체 뉴스만 보지 말고 아래 분야마다 따로 검색해서
분야별로 고르게 정리해 주세요. 그날 크게 움직인 분야에 치우치지 않는 것이 중요합니다.

1. 오늘 시장 한 줄 요약과 국내·미국 시장 흐름 (짧게)
2. 분야별 뉴스와 흐름 — [분야별 동향]의 모든 분야를 하나도 빠짐없이, 분야마다
   - 최근 주요 뉴스 1~2개 (수요 변화, 신기술, 정책, 실적 등)
   - 지금 흐름과 앞으로 1~3개월 관전 포인트
   - 분야 안에서 눈여겨볼 종목 1개와 이유
3. 강세 / 기본 / 약세 시나리오와 각각의 조건
4. "지금 살펴볼 만한 종목" 5개
   - 5개 모두 서로 다른 분야에서
   - 최소 1개는 최근 부진했던 분야에서 실적·밸류에이션상 회복 근거가 있는 종목
   - 고평가 위험 목록 종목은 제외
   - 종목마다 주목 이유(실적·밸류에이션·뉴스 근거), 핵심 리스크, 투자 전 확인할 점
5. 향후 1~2주 주의할 리스크와 주요 일정

단정적 예측이나 매수/매도 권유는 하지 말고, 확인되지 않은 정보는 쓰지 마세요.

[관심 종목 지표] 점수는 -6~+6 (이동평균 배열, MACD, TSI 시그널, RSI 50선 합산)
{data}

{screens}
"""


def chat_prompt(results: dict, screens: dict, today: str) -> str:
    """API 없이 Claude 채팅에 붙여넣을 질문 텍스트."""
    def f(v, fmt):
        return "-" if v is None else format(v, fmt)

    lines = []
    for code, r in _compact(results).items():
        sig = ", ".join(r["signals"]) or "특이 신호 없음"
        lines.append(
            f"- {r['name']}({code}, {'국내' if r['market']=='kr' else '미국'}) "
            f"종가 {f(r['close'], ',.2f')} | 1일 {f(r['chg_1d%'], '+.2f')}% "
            f"5일 {f(r['chg_5d%'], '+.2f')}% 20일 {f(r['chg_20d%'], '+.2f')}% "
            f"| 52주위치 {f(r['pos_52w%'], '.0f')}% | RSI {f(r['rsi'], '.0f')} TSI {f(r['tsi'], '.1f')} "
            f"| {r['label']}({r['score(-6~6)']:+d}) | 신호: {sig}")
    return CHAT_PROMPT.format(today=today, data="\n".join(lines), screens=screens_text(screens))


SCREEN_TITLES = {"value": "저평가 후보", "growth": "성장 기대 후보", "overvalued": "고평가 위험"}


def screens_text(screens: dict) -> str:
    if not screens or "error" in screens:
        return "(스크리닝 결과 없음)"

    def p(v):
        return "-" if v is None else f"{v:+.1f}%"
    out = ["[분야별 동향] 분야 평균 등락률 / 20일선 위 종목 비율 / 최근 매출성장 중앙값 / 5일 최강·최약"]
    for c in screens.get("categories", []):
        best = f"{c['best'][0]} {p(c['best'][1])}" if c.get("best") else "-"
        worst = f"{c['worst'][0]} {p(c['worst'][1])}" if c.get("worst") else "-"
        out.append(f"- {c['name']}({c['n']}종목): 1일 {p(c['ret_1d'])}, 5일 {p(c['ret_5d'])}, 20일 {p(c['ret_20d'])}"
                   f" | 20일선 위 {c['breadth']}% | 매출성장 {p(c['rev_g'])} | 강 {best} / 약 {worst}")
    out.append("")
    out.append("[스크리닝 결과 — 3년 실적·밸류에이션 기준, 목록마다 분야당 1종목]")
    for key, title in SCREEN_TITLES.items():
        out.append(f"■ {title}")
        for r in screens.get(key, []):
            m = ", ".join(f"{k} {v}" for k, v in r["metrics"].items())
            out.append(f"- {r['name']}({r['ticker']}, {r.get('category', r['sector'])}): {m}")
    return "\n".join(out)
