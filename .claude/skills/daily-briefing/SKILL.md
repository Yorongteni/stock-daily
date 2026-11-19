---
name: daily-briefing
description: stock-daily 저장소의 모닝(am)/나이트(pm) 시장 브리핑 AI 분석을 작성해 docs/ai/<날짜>_<슬롯>.json 으로 커밋·푸시한다. claude.ai 예약 작업(루틴)이 매일 06:00·21:00 KST에 실행하거나, 사용자가 "오늘 브리핑 분석 해줘"라고 할 때 사용.
---

# 매일 시장 브리핑 — AI 분석 단계

이 스킬이 **하루 브리핑의 출발 신호**입니다. GitHub 예약 실행(cron)은 수십 분 늦거나 빠질 수 있어서,
시간이 정확한 루틴이 먼저 `docs/trigger/<날짜>_<슬롯>.txt` 를 푸시해 수집을 바로 시작시킵니다.
수집이 끝나면 `docs/data/<날짜>_<슬롯>_brief.md` 를 읽고 **AI 브리핑 JSON** 을 `docs/ai/<날짜>_<슬롯>.json` 으로 푸시합니다.
그러면 Actions가 리포트(HTML/PDF)와 SunHi 음성 영상을 만들어 올립니다.

## 1. 날짜·슬롯 정하기

- 한국 시간(KST) 기준. 12시 전이면 `am`(모닝), 이후면 `pm`(나이트).
  `TZ=Asia/Seoul date +%F` 와 `TZ=Asia/Seoul date +%H` 로 확인합니다.
- 사용자가 날짜·슬롯을 지정하면 그대로 따릅니다.
- `docs/ai/<날짜>_<슬롯>.json` 이 이미 있으면 덮어쓰지 말고 종료합니다 (사용자가 다시 만들라고 한 경우만 예외).

## 2. 수집 시작 신호 보내기 (가장 먼저)

`docs/data/<날짜>_<슬롯>_brief.md` 가 아직 없으면 바로 신호 파일을 푸시합니다.

```bash
git pull -q
mkdir -p docs/trigger
date -u +%FT%TZ > docs/trigger/<날짜>_<슬롯>.txt
git add docs/trigger/<날짜>_<슬롯>.txt
git commit -q -m "수집 시작: <날짜> (<슬롯>)"
git push -q origin HEAD:main || git push -q origin HEAD
```

이 푸시를 받은 Actions 가 1~5분 안에 수집해서 brief 를 커밋합니다.

## 3. brief 기다리기

- 1분 간격으로 `git pull -q` 하며 `docs/data/<날짜>_<슬롯>_brief.md` 를 **최대 35분** 기다립니다.
- 35분이 지나도 없으면: `pip install -r requirements.txt` 후 `python main.py --slot <슬롯> --collect --out docs` 로
  직접 수집을 시도합니다. 실패하면 **AI 결과는 푸시하지 말고** 종료합니다
  (06:50 / 21:50 누락 복구가 AI 없이 리포트를 만듭니다).

## 4. 분석 작성

1. brief 파일 전체를 읽습니다. 지시·원칙·출력 형식·데이터가 모두 들어 있습니다. **brief의 원칙을 그대로 따릅니다.**
2. brief가 요구하는 웹 검색을 실제로 합니다 (WebSearch). 최소 6회 이상, 슬롯 초점에 맞춰 검색합니다.
3. `script` 필드는 `.claude/skills/briefing-script/SKILL.md` 규칙대로 씁니다.
4. **실제로 열어 읽은 기사**를 `sources` 에 적습니다 (제목·언론사·원문 URL·게시일 YYYY-MM-DD·확인한 내용).
   6개 이상, 그중 2개 이상은 브리핑 날짜 기준 이틀 안 기사. 검색 결과 목록·brief 의 헤드라인만 보고 적지 않습니다.
   원문을 확인하지 못한 헤드라인 내용을 꼭 써야 하면 그 문장 끝에 "(헤드라인 기준, 원문 미확인)"을 붙입니다.
   미국 일정은 brief [시점]의 미국 동부 시각 기준으로 "미국 X일 장 마감 후 = 한국 X+1일 아침"을 확인합니다.
5. **다가오는 이벤트 캘린더**(`upcoming_events`, 3~8개)를 씁니다. brief 의 [다가오는 이벤트 후보]에서 출발해 웹 검색으로
   앞으로 7일(대형은 14일) 일정 — 정상회담·외교, 정책 발표, 연준·한국은행, 경제지표, 대형 실적, 만기·상장 — 을 찾습니다.
   기대감으로 이미 주가가 움직이는 이벤트(예: 정상회담 → 한한령 완화 기대 → 엔터주 급등)는 꼭 넣습니다.
   **모든 이벤트에 결과별 영향(`scenarios`, 2~3개)** — 결과마다 어떤 시장·분야가 어떤 경로로 어떻게 움직이는지.
   내일 일정은 빠짐없이. `script.events` 대본도 씁니다.
6. JSON 을 `docs/ai/<날짜>_<슬롯>.json` 에 저장합니다 (UTF-8, 한글 그대로).

핵심 품질 기준 (brief 원칙의 요약):
- 결론 없는 문장 금지. 방향·밴드·확률·비중(%)을 숫자로.
- 독자는 초보자: 모든 섹션을 **한 줄 결론 → 원인과 배경 → 행동 지침** 순서로 (`easy.<섹션>.one/why/do`).
- brief 의 「일상 언어 번역 규칙」을 지킨다 (bp 대신 %p, 백분위 대신 "최근 5년 중 상위 15%", 모델 통계 언급 금지 등).
- 수치는 brief [데이터] 값 그대로. 웹 기사 수치와 섞지 않는다.
- 모든 판단에 근거 수치(5년 중 위치, 1년 전 대비, %p, 순위 변화)를 붙이고 무효화 조건을 적는다.
- 13개 분야를 데이터 표기 그대로 전부 다룬다.
- allocation 6개 합 = 100.

## 5. 검사 후 푸시

```bash
python tools/validate_ai.py docs/ai/<날짜>_<슬롯>.json
```

- `✗ 사용 불가` 이면 오류를 고쳐 다시 검사합니다. 경고는 가능하면 고칩니다.
  출처 부족(`sources` 6개 미만, 최근 기사 2개 미만, 원문 URL 아님)과 이벤트 부족(`upcoming_events` 3개 미만)도 사용 불가입니다 → 검색을 더 해서 채웁니다.
  끝내 채우지 못하면 AI 결과를 푸시하지 않습니다 (누락 복구가 AI 없이 리포트를 만듭니다).
- 통과하면:

```bash
git add docs/ai/<날짜>_<슬롯>.json
git commit -m "AI 브리핑: <날짜> (<슬롯>)"
git pull --rebase -q && git push origin HEAD:main
```

- **main 브랜치에 직접 푸시**합니다 (PR은 만들지 않습니다). 거부되면 `git pull --rebase` 후 한 번 더 시도합니다.
- 권한 제한으로 main 푸시가 막히면 현재 작업 브랜치(`claude/...`)에 그대로 푸시합니다: `git push origin HEAD`.
  Actions가 `claude/**` 브랜치의 `docs/ai/` 파일도 main으로 가져와 리포트를 만듭니다.
- 다른 파일은 고치거나 커밋하지 않습니다.

## 6. 마무리 보고

한두 줄로: 날짜·슬롯, headline, stance, 예측 밴드, 검색 횟수, 출처 개수(최근 기사 수), 푸시 결과.
