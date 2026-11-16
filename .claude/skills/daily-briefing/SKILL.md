---
name: daily-briefing
description: stock-daily 저장소의 모닝(am)/나이트(pm) 시장 브리핑 AI 분석을 작성해 docs/ai/<날짜>_<슬롯>.json 으로 커밋·푸시한다. claude.ai 예약 작업(루틴)이 매일 06:15·21:15 KST에 실행하거나, 사용자가 "오늘 브리핑 분석 해줘"라고 할 때 사용.
---

# 매일 시장 브리핑 — AI 분석 단계

GitHub Actions가 06:05/21:05 KST에 데이터를 모아 `docs/data/<날짜>_<슬롯>_brief.md` 를 커밋합니다.
이 스킬은 그 brief를 읽고 **AI 브리핑 JSON** 을 만들어 `docs/ai/<날짜>_<슬롯>.json` 으로 푸시합니다.
푸시되면 Actions가 리포트(HTML/PDF)와 SunHi 음성 영상을 만들어 올립니다.

## 1. 날짜·슬롯 정하기

- 한국 시간(KST) 기준. 12시 전이면 `am`(모닝), 이후면 `pm`(나이트).
  `TZ=Asia/Seoul date +%F` 와 `TZ=Asia/Seoul date +%H` 로 확인합니다.
- 사용자가 날짜·슬롯을 지정하면 그대로 따릅니다.

## 2. brief 기다리기

```bash
git pull -q
ls docs/data/<날짜>_<슬롯>_brief.md
```

- 없으면 2분 간격으로 `git pull` 하며 **최대 30분** 기다립니다 (Actions 예약 실행이 늦어질 수 있음).
- 30분이 지나도 없으면: `pip install -r requirements.txt` 후 `python main.py --slot <슬롯> --collect --out docs` 로
  직접 수집을 시도합니다. 네트워크 제한으로 실패하면 **아무것도 푸시하지 말고** 종료합니다
  (06:45/21:45 안전장치가 AI 없이 리포트를 만듭니다).
- `docs/ai/<날짜>_<슬롯>.json` 이 이미 있으면 덮어쓰지 말고 종료합니다 (사용자가 다시 만들라고 한 경우만 예외).

## 3. 분석 작성

1. brief 파일 전체를 읽습니다. 지시·원칙·출력 형식·데이터가 모두 들어 있습니다. **brief의 원칙을 그대로 따릅니다.**
2. brief가 요구하는 웹 검색을 실제로 합니다 (WebSearch). 최소 6회 이상, 슬롯 초점에 맞춰 검색합니다.
3. `script` 필드는 `.claude/skills/briefing-script/SKILL.md` 규칙대로 씁니다.
4. JSON 을 `docs/ai/<날짜>_<슬롯>.json` 에 저장합니다 (UTF-8, 한글 그대로).

핵심 품질 기준 (brief 원칙의 요약):
- 결론 없는 문장 금지. 방향·밴드·확률·비중(%)을 숫자로.
- 모든 판단에 근거 수치(백분위, YoY, bp, 순위 변화)를 붙이고 무효화 조건을 적는다.
- 13개 분야를 데이터 표기 그대로 전부 다룬다.
- allocation 6개 합 = 100.

## 4. 검사 후 푸시

```bash
python tools/validate_ai.py docs/ai/<날짜>_<슬롯>.json
```

- `✗ 사용 불가` 이면 오류를 고쳐 다시 검사합니다. 경고는 가능하면 고칩니다.
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

## 5. 마무리 보고

한두 줄로: 날짜·슬롯, headline, stance, 예측 밴드, 검색 횟수, 푸시 결과.
