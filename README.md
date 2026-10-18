# 매일 주식 동향 분석 리포트

국내·미국 관심 종목의 시세를 매일 받아 기술적 지표로 추세를 판정하고, Claude가 당일 뉴스를 검색해 해설과 시나리오를 붙인 HTML 대시보드를 만듭니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `config.yaml` | 관심 종목, Claude 모델, 저장 폴더 설정 |
| `main.py` | 실행 진입점 (데이터 수집 → 분석 → 해설 → 리포트) |
| `indicators.py` | 이동평균·RSI·MACD·TSI·볼린저밴드 계산, 추세 점수와 신호 판정 |
| `commentary.py` | Claude API 호출 (웹 검색으로 뉴스 반영) |
| `report.py` | 단일 HTML 대시보드 생성 |
| `screener.py` | 3년 실적·밸류에이션 스크리닝 (저평가 / 성장 기대 / 고평가 위험) |
| `universe.yaml` | 스크리닝 대상 종목 목록 (국내 약 70, 미국 약 90) |
| `run.bat` | 윈도우에서 더블클릭 실행 |
| `.github/workflows/daily.yml` | GitHub Actions 자동 실행 설정 |

## 1. 처음 실행해 보기 (개인 PC)

```bash
pip install -r requirements.txt
python main.py --demo --no-ai --open   # 인터넷 없이 가상 데이터로 화면 확인
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
