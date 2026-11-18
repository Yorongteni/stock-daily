# Claude 예약 작업(루틴) 설정 가이드 — 다른 계정에서 등록하기

stock-daily 의 자동 생성은 **GitHub Actions** 가 실제 작업(수집·분석·리포트·PDF·영상)을 하고,
**Claude 예약 작업**은 정해진 시각에 "출발 신호"를 저장소에 푸시하거나 AI 분석을 써서 올리는 역할입니다.
GitHub 예약 실행(cron)은 늦거나 빠지는 일이 잦아, 시각이 정확한 Claude 예약 작업이 출발 신호를 보냅니다.

| 시각 (KST) | 예약 작업 | 하는 일 | 결과 |
|---|---|---|---|
| 매일 17:57 | ① 18시 단타 브리핑 시작 신호 | `docs/trigger-swing/<날짜>.txt` 푸시 (분석 없음, 1분 미만) | 18:00 실전 단타 통합 브리핑 (개인용, 업로드 없음) |
| 평일 06:00 | ② 모닝 브리핑 AI 분석 | 수집 신호 → 데이터 대기 → AI 분석 JSON 푸시 | 07:00 모닝 브리핑 |
| 평일 21:00 | ③ 나이트 브리핑 AI 분석 | 수집 신호 → 데이터 대기 → AI 분석 JSON 푸시 | 22:00 나이트 브리핑 |

예약 작업이 실패해도 GitHub 예약 실행(백업)이 같은 작업을 다시 시도합니다. 이미 만든 날은 건너뜁니다.

---

## 0. 먼저 준비할 것 (다른 계정)

1. **claude.ai 에 다른 계정으로 로그인** → 설정 › 커넥터(Connectors)에서 **GitHub 연결**.
2. 그 GitHub 계정이 `Yorongteni/stock-daily` 에 **푸시할 수 있어야** 합니다.
   - 같은 GitHub 계정(Yorongteni)을 연결하면 바로 됩니다.
   - 다른 GitHub 계정이면 GitHub › stock-daily › Settings › Collaborators 에서 그 계정을 **Write** 권한으로 초대하고 수락합니다.
3. Claude GitHub 앱이 저장소에 설치돼 있는지 확인: https://github.com/apps/claude/installations/select_target

## 1. 예약 작업 만들기 (claude.ai › Code › Routines › New routine)

각 예약 작업을 아래 값으로 만듭니다. **저장소(Repository)에 `Yorongteni/stock-daily` 를 꼭 선택**해야 푸시 권한이 붙습니다.

### ① 18시 단타 브리핑 시작 신호 (필수)

| 항목 | 값 |
|---|---|
| 이름 | stock-daily 18시 단타 브리핑 시작 신호 |
| 저장소 | `Yorongteni/stock-daily` |
| 모델 | Sonnet (가벼운 작업이라 충분) |
| 반복 | 매일 17:57 (Asia/Seoul) — cron 으로 넣는 화면이면 `57 8 * * *` (UTC) |
| 알림 | 끄기 권장 (매일 결과 알림이 필요 없으면) |

**프롬프트 (그대로 붙여 넣기):**

```
stock-daily 저장소의 '오후 6시 실전 단타 통합 브리핑' 시작 신호만 보내는 짧은 작업입니다. 분석은 하지 않습니다.

1. 저장소 폴더에서 git fetch origin main 후 main 최신 상태를 받습니다 (git checkout -B main origin/main).
2. 날짜 D = TZ=Asia/Seoul date +%F.
3. origin/main 에 docs/swing/data/D.json 이 이미 있으면 "이미 생성됨"이라고 보고하고 끝냅니다.
4. 없으면 docs/trigger-swing/D.txt 파일을 만들고 내용으로 현재 시각(TZ=Asia/Seoul date '+%F %T KST')을 한 줄 씁니다.
   이 파일 하나만 커밋합니다 (메시지: "18시 단타 브리핑 시작 신호: D").
5. git push origin HEAD:main 으로 푸시합니다. 거절되면 git pull --rebase origin main 후 다시 푸시(최대 3번).
   그래도 main 푸시가 막히면 현재 브랜치(claude/로 시작)에 푸시합니다 — 그 브랜치 푸시도 GitHub Actions 가 받습니다.
6. PR은 만들지 않고 다른 파일은 절대 건드리지 않습니다. 끝나면 푸시 결과를 한 줄로 보고합니다.
```

### ② 모닝 브리핑 AI 분석 (지금 계정에서 옮길 때만)

| 항목 | 값 |
|---|---|
| 이름 | stock-daily 모닝 브리핑 AI 분석 (06:00 KST) |
| 저장소 | `Yorongteni/stock-daily` |
| 모델 | Sonnet |
| 반복 | 평일(월~금) 06:00 (Asia/Seoul) — cron 이면 `0 21 * * 0-4` (UTC, 한국 월요일 아침 = UTC 일요일) |

**프롬프트:**

```
stock-daily 저장소의 모닝 브리핑(슬롯 am) AI 분석을 작성해 주세요.

저장소의 .claude/skills/daily-briefing/SKILL.md 를 먼저 읽고 그 절차를 처음부터 끝까지 그대로 따르세요. 요약:
1. 날짜는 한국 시간 오늘(TZ=Asia/Seoul date +%F), 슬롯은 am. docs/ai/<날짜>_am.json 이 이미 있으면 끝냅니다.
2. docs/data/<날짜>_am_brief.md 가 없으면 가장 먼저 docs/trigger/<날짜>_am.txt 를 만들어 커밋하고 main에 푸시합니다 (수집 시작 신호, GitHub 예약 실행이 늦거나 빠지는 것을 막기 위함).
3. 1분 간격으로 git pull 하며 brief 를 최대 35분 기다립니다. 끝내 없으면 스킬의 대체 절차를 따르고, 그래도 안 되면 AI 결과는 푸시하지 않고 끝냅니다.
4. brief 전체를 읽고 웹 검색(최소 6회)을 한 뒤, brief의 원칙(초보자용 3단계 해설, 일상 언어 번역 규칙, 데이터 수치 통일, 스포트라이트 4단계 서사·법적 안전장치)과 출력 형식대로 JSON을 docs/ai/<날짜>_am.json 에 저장합니다. script 필드는 .claude/skills/briefing-script/SKILL.md 규칙을 따릅니다.
5. python tools/validate_ai.py docs/ai/<날짜>_am.json 이 '사용 가능'이 될 때까지 고칩니다.
6. 그 파일만 커밋해 main에 푸시합니다(git push origin HEAD:main). main 푸시가 막히면 현재 브랜치에 푸시합니다(git push origin HEAD). PR은 만들지 않고 다른 파일은 건드리지 않습니다.
7. 끝나면 headline, stance, 예측 범위, 푸시 결과를 한두 줄로 보고합니다.
```

### ③ 나이트 브리핑 AI 분석 (지금 계정에서 옮길 때만)

②와 같고 다음만 바꿉니다.

| 항목 | 값 |
|---|---|
| 이름 | stock-daily 나이트 브리핑 AI 분석 (21:00 KST) |
| 반복 | 평일(월~금) 21:00 (Asia/Seoul) — cron 이면 `0 12 * * 1-5` (UTC) |
| 프롬프트 | ②의 프롬프트에서 `모닝`→`나이트`, `am`→`pm` 으로 바꿔 붙여 넣기 |

## 2. 확인

- 예약 작업 화면에서 **Run now(지금 실행)** 를 한 번 눌러 봅니다.
  - ①은 그날 브리핑이 이미 있으면 "이미 생성됨"으로 끝나는 게 정상입니다. 아직 없을 때 누르면 바로 18시 브리핑이 만들어집니다.
- GitHub › stock-daily › Actions 에서 `오후 6시 실전 단타 통합 브리핑` 실행이 `push` 이벤트로 시작되는지 확인합니다.

## 3. 중복 정리

같은 작업을 두 계정에서 동시에 돌릴 필요는 없습니다. 새 계정에서 잘 돌면 원래 계정의 같은 예약 작업은 **끄거나(Disable) 삭제**합니다.
(겹쳐 돌아도 이미 만든 날은 건너뛰므로 자료가 두 번 생기지는 않지만, 사용량이 두 번 듭니다.)

## 참고

- 예약 작업이 하나도 없어도 GitHub 예약 실행(백업)만으로 자료는 만들어집니다. 다만 GitHub 쪽은 수십 분 늦거나 빠지는 날이 있습니다.
- 워크플로 파일: `.github/workflows/us-swing.yml`(18시), `daily.yml`·`daily-report.yml`(07시·22시).
