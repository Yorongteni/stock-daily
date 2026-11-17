# 매일 시장 브리핑 — 종합 투자 어드바이저

평일 하루 두 번, 국내·미국 시장과 금리·환율·원자재·가상자산의 **과거 5년 대비 현재 위치**, 13개 분야 자금 흐름,
국내외 뉴스를 모아 Claude가 **당일 시장 예측과 자산 배분 전략**을 붙인 리포트(HTML·PDF)와 SunHi 음성 영상을 만듭니다.

| 브리핑 | 완성 | 내용 |
|---|---|---|
| 모닝 (am) | 07:00 KST | 밤사이 미국·글로벌 마감 → 오늘 코스피·코스닥 개장·장중 시나리오, 주도 섹터 |
| 나이트 (pm) | 22:00 KST | 국내장 마감 복기 → 오늘 밤 미국 증시 예측, 글로벌 매크로 점검 |

| 미국 단타 연습 | 18:00 KST | 보유 종목 성적표·탈출 작전 → 오늘 밤 50만 원 타점 1~2개 → 예약 주문표 → 누적 성적 (아래 '미국 주식 실전 단타 연습') |

리포트·영상 순서: 오늘의 결론 → ① 과거 대비 진단 → ② 매크로·환율·현물 → ③ 사회 흐름·당일 예측 → ④ 13개 분야 → ⑤ 기회 & 리스크 → ⑥ 종합 투자 총론(자산 배분·액션 플랜) → 부록

## 자동 실행 구조 (API 키 없이)

```
06:00 / 21:00  claude.ai 루틴   docs/trigger/<날짜>_<슬롯>.txt 푸시 = 수집 시작 신호   (.claude/skills/daily-briefing)
   (푸시 직후)  GitHub Actions  수집 → docs/data/<날짜>_<슬롯>.json, _brief.md 커밋
   (수집 직후)  claude.ai 루틴   brief 읽기 + 웹 검색 → docs/ai/<날짜>_<슬롯>.json 푸시
   (푸시 즉시)  GitHub Actions  리포트 생성 → PDF·영상 → Pages·Releases·유튜브(비공개)
06:10·06:25 / 21:10·21:25   GitHub Actions  백업 수집 (이미 했으면 건너뜀)
06:50·07:15·07:45 / 21:50·22:15·22:45  누락 복구: 리포트가 없으면 AI 없이(데이터 기반 쉬운 요약) 리포트·영상 생성
```

- AI 분석은 claude.ai 예약 작업(루틴)이 맡아 **API 키가 필요 없습니다** (Claude 요금제 사용량을 씁니다).
- API 키로 바꾸려면 `config.yaml` 의 `claude.mode` 를 `api` 로 바꾸고 Secrets 에 `ANTHROPIC_API_KEY` 를 등록합니다.
- GitHub 예약 실행은 수십 분 늦거나 빠질 수 있어(2026-11-16 실제 발생), 시작 신호는 시간이 정확한 루틴이 푸시로 보냅니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `config.yaml` | 관심 종목, 매크로 자산(출처 순서), 뉴스 피드, AI 방식, 브리핑 슬롯 |
| `main.py` | 진입점 (`--collect` 수집 / `--build` 리포트, `--slot am/pm`) |
| `macro.py` | 금리·환율·원자재·비트코인 5년 수집, YoY·백분위·레짐·유사 국면·정량 예측 기준선 |
| `news.py` | 국내외 경제·사회 뉴스 RSS 수집, 키워드 |
| `screener.py` | 13개 분야 장기 비교(상대강도·거래대금) + 3년 실적 스크리닝 |
| `indicators.py` | 이동평균·RSI·MACD·TSI·볼린저밴드, 추세 점수와 신호 |
| `commentary.py`, `prompts/briefing.md` | AI 입력(brief) 생성, API 모드 호출 |
| `advisor.py`, `tools/validate_ai.py` | AI 결과 검사·정리, AI 없을 때 규칙 기반 결론 |
| `report.py` | HTML 리포트 |
| `tools/build_from_report.py` | PDF·영상·유튜브 정보 |
| `.claude/skills/` | 루틴용 분석 절차, 앵커 대본 규칙, 개발 가이드 |
| `.github/workflows/daily.yml` | 수집·리포트 자동 실행 / `daily-report.yml` PDF·영상 |
| `swing.py`, `swing_report.py` | 미국 단타 연습: 보유 판정·작전·타점·주문표·성적, 수동 입력(`--manual`) |
| `tools/build_swing.py` | 단타 연습 PDF·영상 |
| `data/us_swing_portfolio.json`, `data/trade_history.json` | 단타 보유 목록(상태) / 매매 이력 |
| `.github/workflows/us-swing.yml`, `update_portfolio.yml` | 18:00 자동 실행 / 스마트폰 수동 입력 |

## 미국 주식 실전 단타 연습 (18:00 KST)

매일 18시(월~금)에 그날 밤 미국장을 대상으로 **1~2거래일 단타를 연습하고, 산 종목을 끝까지 추적**합니다. AI 루틴 없이 GitHub Actions 만으로 돌아갑니다 (Claude 사용량 0).

```
18:00 (18:20·18:45 누락 방지)  us-swing.yml
  ① data/us_swing_portfolio.json 읽기 → 간밤 미국장 일봉으로 판정
       예약 매수: 장중 저가 ≤ 예약가 → 체결 / 아니면 미체결 취소
       보유: 고가 ≥ 매도가 → 익절, 저가 ≤ 손절가 → 손절, 기한 끝 → 종가 정리 (같은 날 둘 다 닿으면 손절로 보수 계산)
  ② 남은 보유 종목 오늘 밤 작전: 목표가 유지 / +2% 약익절 / 본전 탈출 / 시초가 정리 / 예외적 1일 연장
  ③ 빈 슬롯(최대 3종목)만큼 신규 타점 1~2개: 하루 변동폭(ATR) 3.5% 이상 + 눌림목 반등형 또는 거래량 돌파형
  ④ 50만 원 ÷ (예약가 × 환율) = 정수 주식 수, 예약가·목표가(+5%)·손절가(-3.5%)·보유 기한
  ⑤ data/*.json, docs/swing/ 커밋 → PDF·영상(3~5분) → docs/swing/pdf, 릴리스 swing-<날짜>, 유튜브(비공개)
```

- 리포트: `https://yorongteni.github.io/stock-daily/swing/` (최신), `swing/swing_<날짜>.html`
- 규칙 숫자(예산·목표·손절·슬롯·종목 목록)는 `config.yaml` 의 `swing:` 에서 바꿉니다.
- **실제 계좌가 다르면 (스마트폰)**: GitHub 앱 → Actions → `보유 종목 수동 입력` → Run workflow
  - `매수추가` (ticker, price=내 매수가, qty) · `수량·단가수정` · `매도완료` (qty 비우면 전량) · `미체결삭제`
  - `오늘 18시 브리핑 다시 만들기` 를 켜면 바로 내 평단가 기준으로 리포트·PDF를 다시 만듭니다 (영상은 다시 안 만듦).
  - 입력이 없으면 추천 예약가대로 체결됐다고 보고 자동 추적합니다.
- 연습용 가상 매매입니다. 수수료·세금·환전 비용은 계산에 넣지 않습니다.

## 1. 처음 실행해 보기 (개인 PC)

```bash
pip install -r requirements.txt
python main.py --demo --no-ai --open   # 인터넷 없이 가상 데이터로 화면 확인 (--slot am/pm)
python main.py --no-ai --open          # 실제 시세, AI 해설 없이
```

AI 해설까지 쓰려면 API 키를 환경변수로 등록한 뒤 실행합니다.

```bash
# Windows (명령 프롬프트, 한 번만 하면 됨)
setx ANTHROPIC_API_KEY "sk-ant-..."
# Mac/Linux
export ANTHROPIC_API_KEY="sk-ant-..."

python main.py --open
```

결과는 `reports/report_날짜.html`과 `reports/latest.html`(항상 최신)에 저장됩니다.

## 2. 매일 자동 실행

**방법 A — 개인 PC 작업 스케줄러 (Windows)**
작업 스케줄러 → 기본 작업 만들기 → 매일 오전 7시 → 프로그램 시작에 `run.bat` 지정. PC가 켜져 있어야 합니다.

**방법 B — GitHub Actions + Pages (PC 꺼져 있어도 됨, 스마트폰으로 확인, 무료)**
1. github.com 가입 후 New repository → 이름 `stock-daily`, **Public** 선택 → Create.
2. "uploading an existing file"을 눌러 압축 푼 폴더 안의 파일을 모두 끌어다 올립니다. (`.github` 폴더는 숨김이라 안 보일 수 있으니, 탐색기 보기 → 숨긴 항목 표시를 켜고 함께 올리세요.)
3. 저장소 Settings → Actions → General → Workflow permissions를 "Read and write permissions"로 바꾸고 Save.
4. Actions 탭 → daily-market-report → Run workflow로 첫 실행 (실적 수집 때문에 5~10분).
5. Settings → Pages → Branch를 `main`, 폴더를 `/docs`로 선택하고 Save.
6. 1~2분 뒤 `https://내아이디.github.io/stock-daily/` 주소로 접속하면 리포트가 열립니다. 휴대폰에서 이 주소를 홈 화면에 추가해 두세요.

이후 평일 오전 7시마다 자동으로 갱신됩니다. 무료 Pages는 공개 저장소에서만 되므로 주소를 아는 사람은 리포트를 볼 수 있습니다(시세·지표만 있고 개인정보는 없습니다).

> 직장망은 방화벽으로 시세 사이트·API 접속이 막힐 수 있으니, 실행은 집 PC나 GitHub Actions에서 하는 것을 권장합니다.

## 3. 종목 바꾸기

`config.yaml`의 `watchlist`만 수정하면 됩니다.

```yaml
  kr:
    - { code: "373220", name: LG에너지솔루션 }   # 국내는 6자리 코드, 따옴표 필수
  us:
    - { code: TSLA, name: 테슬라 }
```

## 4. 추세 점수 읽는 법

아래 6개 항목을 각각 ±1로 합산합니다(−6 ~ +6). +3 이상 **강세**, −3 이하 **약세**, 그 사이 **중립**.

- 종가 > 20일선 / 20일선 > 60일선 / 60일선 > 120일선
- MACD 히스토그램 양수
- TSI(25,13) > 시그널(7)
- RSI(14) > 50

별도로 골든/데드크로스, TSI·MACD 시그널 교차, RSI 과열/과매도, 볼린저밴드 이탈, 52주 신고가/신저가 근접을 신호 칩으로 표시합니다.

## 5. 분야별 동향과 종목 스크리닝

`universe.yaml`의 160여 종목을 13개 분야(반도체, IT하드웨어·AI인프라, 소프트웨어·보안, 인터넷·플랫폼, 2차전지·소재, 자동차·모빌리티, 바이오·헬스케어, 금융, 조선·방산·기계, 전력·에너지, 소비재·유통, 통신·미디어·게임, 지주·운송)로 나눠 분석합니다. 분야를 새로 만들거나 종목을 옮기려면 yaml만 고치면 됩니다.

**분야별 동향**: 분야마다 평균 등락률(1·5·20일), 20일선 위 종목 비율, 매출성장·PER 중앙값, 5일 강세·약세 종목, 분야 안의 저평가·성장 대표 종목을 보여줍니다. 부진한 분야도 빠짐없이 나옵니다.

**스크리닝 목록** (각 5종목, `max_per_category: 1`이면 한 분야에서 1종목씩만 — 편중 방지)
- **저평가 후보**: 3년 연속 흑자 + 같은 분야 PER 중앙값보다 낮은 PER. 분야 대비 PER(35%), PBR(20%), ROE(20%), 3년 순이익 성장률(25%)
- **성장 기대 후보**: 3년 매출 성장률(30%), 최근 매출 성장(25%), 최근 이익 성장(20%), 선행PER 개선(20%), 6개월 주가(5%)
- **고평가 위험**: 분야 PER의 1.8배 초과 또는 적자인데 PSR 8배 초과 종목 중 PER·PSR, 200일선 대비 과열, RSI, 성장 둔화를 합산
- **AI 관심 종목**: 서로 다른 분야 5종목, 최소 1개는 부진 분야의 회복 후보 (API가 없으면 해설용 질문 복사 → 채팅에 붙여넣기)

실적 데이터는 야후 파이낸스(yfinance)에서 받으며 `cache/fundamentals.json`에 저장해 7일마다 갱신합니다. 국내 중소형주는 재무 데이터가 비어 있으면 자동으로 빠집니다.

## 6. 지난 기록

리포트는 날짜별 파일(`report_2026-10-16.html` 등)로 계속 쌓이고 지워지지 않습니다.
- 각 리포트 상단의 `← 이전 날짜` 링크로 하루씩 거슬러 볼 수 있습니다.
- `지난 리포트 전체`(archive.html)에서 날짜별 코스피·S&P500 등락과 스크리닝 상위 종목을 한눈에 보고 원하는 날짜를 열 수 있습니다.
- 스크리닝 목록에서 전날에 없던 종목은 `신규`로 표시됩니다.
- 요약 이력은 `history.json`에 함께 저장됩니다.

## 비용 참고

Claude 해설은 하루 1회 호출(웹 검색 최대 6회 포함)이라 비용이 크지 않지만, 정확한 요금은 Anthropic 콘솔에서 확인하세요. `config.yaml`에서 `web_search: false`로 하면 검색 없이 지표만 해설합니다.

※ 자동 생성 참고 자료이며 투자 권유가 아닙니다.
