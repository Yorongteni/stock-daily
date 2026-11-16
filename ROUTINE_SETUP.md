# AI 분석 루틴을 다른 Claude 계정으로 옮기기

이 저장소의 AI 분석은 claude.ai **예약 작업(루틴)** 이 매일 두 번 실행합니다.
루틴은 만든 Claude 계정의 사용량을 쓰므로, 다른 계정(개인 계정)으로 옮기려면 아래대로 합니다.

> **개인 계정 Claude에게:** 이 파일을 읽고 「3. 루틴 만들기」의 두 루틴을 만들어 주세요.
> Claude Code 에서는 `/schedule` 로 만들 수 있습니다. 시간은 KST 기준이며 cron 은 UTC 입니다.

---

## 1. 준비 (사람이 직접)

1. 개인 계정으로 https://claude.ai/code 에 로그인합니다.
2. GitHub 를 연결합니다 (claude.ai → 설정 → 커넥터 → GitHub).
   - **저장소 주인 `Yorongteni` 계정으로** 로그인해서 연결해야 합니다.
   - Claude GitHub App 은 이미 `Yorongteni/stock-daily` 에 설치되어 있습니다.
     설치 화면이 다시 나오면 **Only select repositories → stock-daily** 로 두면 됩니다.
3. 연결 확인: claude.ai/code 새 세션의 저장소 목록에 `Yorongteni/stock-daily` 가 보이면 됩니다.

## 2. 기존 계정의 루틴 끄기 (중복 실행 방지)

기존(공동) 계정으로 https://claude.ai/code/routines 에 들어가 아래 두 루틴을 **끄거나(비활성화) 삭제**합니다.

- `stock-daily 모닝 브리핑 AI 분석 (06:15 KST)`
- `stock-daily 나이트 브리핑 AI 분석 (21:15 KST)`

둘 다 켜져 있어도 망가지지는 않지만(이미 결과 파일이 있으면 두 번째 실행은 그냥 끝남) 사용량이 두 계정에서 나갑니다.

## 3. 루틴 만들기 (개인 계정)

공통 설정

| 항목 | 값 |
|---|---|
| 저장소 | `https://github.com/Yorongteni/stock-daily` |
| 모델 | `claude-sonnet-5-5` (사용량 절약. 더 깊은 분석을 원하면 Opus) |
| 허용 도구 | Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch |
| 커넥터 | 필요 없음 (모두 빼도 됨) |

### 루틴 A — 모닝

- 이름: `stock-daily 모닝 브리핑 AI 분석 (06:15 KST)`
- 일정: 평일 06:15 KST = cron `15 21 * * 0-4` (UTC, 한국 월요일 아침 = UTC 일요일)
- 지시문:

```
stock-daily 저장소의 모닝 브리핑(슬롯 am) AI 분석을 작성해 주세요.

저장소의 .claude/skills/daily-briefing/SKILL.md 를 먼저 읽고 그 절차를 처음부터 끝까지 그대로 따르세요. 요약:
1. 날짜는 한국 시간 오늘(TZ=Asia/Seoul date +%F), 슬롯은 am.
2. git pull 후 docs/data/<날짜>_am_brief.md 가 생길 때까지 2분 간격으로 최대 30분 기다립니다. 없으면 스킬의 대체 절차를 따르고, 그래도 안 되면 아무것도 푸시하지 말고 끝냅니다. docs/ai/<날짜>_am.json 이 이미 있으면 끝냅니다.
3. brief 전체를 읽고, brief가 요구하는 웹 검색(최소 6회)을 실제로 한 뒤, brief의 원칙과 출력 형식대로 JSON을 docs/ai/<날짜>_am.json 에 저장합니다. script 필드는 .claude/skills/briefing-script/SKILL.md 규칙을 따릅니다. 결론 없는 중립 표현 대신 방향·밴드·확률·자산 비중을 숫자로, 근거 수치와 무효화 조건을 함께 제시합니다.
4. python tools/validate_ai.py docs/ai/<날짜>_am.json 이 '사용 가능'이 될 때까지 고칩니다.
5. 그 파일만 커밋해 main에 푸시합니다(git push origin HEAD:main). main 푸시가 막히면 현재 브랜치에 푸시합니다(git push origin HEAD). PR은 만들지 않고 다른 파일은 건드리지 않습니다.
6. 끝나면 headline, stance, 예측 밴드, 푸시 결과를 한두 줄로 보고합니다.
```

### 루틴 B — 나이트

- 이름: `stock-daily 나이트 브리핑 AI 분석 (21:15 KST)`
- 일정: 평일 21:15 KST = cron `15 12 * * 1-5`
- 지시문: 루틴 A 지시문에서 **`모닝` → `나이트`, `am` → `pm`** 으로 바꾼 것 (네 군데).

## 4. 확인

1. 루틴 A 를 **지금 실행(Run now)** 합니다.
   - 오늘 `docs/ai/<날짜>_am.json` 이 이미 있으면 루틴은 바로 끝나므로, 확인은 다음 날 아침 실행으로 해도 됩니다.
2. 실행 기록에 `git push` 가 **403** 으로 나오면 GitHub 연결이 저장소 주인 계정이 아닌 것입니다 → 1단계 2번을 다시 합니다.
3. 푸시가 되면 GitHub Actions 가 리포트 → PDF·영상 → 유튜브 업로드까지 자동으로 이어갑니다.
   확인: https://github.com/Yorongteni/stock-daily/actions

## 참고

- 루틴이 실패하거나 사용량 한도에 걸려도 06:45 / 21:45 안전장치가 AI 없이(정량 결론) 리포트·영상을 만듭니다.
- 사용량을 줄이려면 나이트 루틴(B)만 끄면 절반이 됩니다.
- API 키 방식으로 바꾸려면 `config.yaml` 의 `claude.mode` 를 `api` 로 바꾸고 GitHub Secrets 에 `ANTHROPIC_API_KEY` 를 등록합니다 (그러면 루틴은 필요 없음).
