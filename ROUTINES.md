# 자동 실행 설정 가이드 — GitHub Actions 만으로 매일 3번

모든 자료는 **GitHub Actions 예약 실행**으로 만들어집니다. Claude 예약 작업(루틴)은 쓰지 않습니다.
AI 분석(모닝·나이트)은 GitHub Actions 가 **Anthropic API 키**로 직접 호출합니다 (`config.yaml` → `claude.mode: api`).

| 공개 (KST) | 자료 | 요일 | 시작 (GitHub 예약 실행, 늦거나 빠질 때 대비해 여러 번) | AI |
|---|---|---|---|---|
| 07:00 | 모닝 브리핑 (리포트·PDF·영상·유튜브) | 월~금 | 06:00 · 06:10 · 06:25, 복구 06:50 · 07:15 · 07:45 | API 키 |
| 18:00 | 실전 단타 통합 브리핑 (개인용, 업로드 없음) | 매일 | 18:00 · 18:07 · 18:20 · 18:45 · 19:15 | 없음 |
| 22:00 | 나이트 브리핑 (리포트·PDF·영상·유튜브) | 월~금 | 21:00 · 21:10 · 21:25, 복구 21:50 · 22:15 · 22:45 | API 키 |

이미 만든 날은 다음 시각들이 자동으로 건너뜁니다. 그래서 겹쳐 둬도 자료가 두 번 생기지 않습니다.

---

## 1. API 키 넣기 (한 번만)

1. **API 키 만들기:** 키를 쓸 계정으로 https://console.anthropic.com 에 로그인 → Settings › **API Keys** › Create Key → 키를 복사합니다.
   - Claude 구독(Pro·Max)과 별개로, API 콘솔에서 결제 수단을 등록하거나 크레딧을 충전해야 합니다. 쓴 만큼 청구됩니다.
   - 콘솔의 Limits 에서 월 사용 한도를 정해 두면 예상 밖 청구를 막을 수 있습니다.
2. **GitHub 저장소에 저장:** GitHub › `Yorongteni/stock-daily` › Settings › Secrets and variables › **Actions** › New repository secret
   - Name: `ANTHROPIC_API_KEY`
   - Secret: 복사한 키
   - 휴대폰 GitHub 앱에는 이 메뉴가 없어 **웹 브라우저(PC 또는 휴대폰 브라우저의 데스크톱 모드)** 에서 해야 합니다.
3. 끝. 다음 모닝·나이트 실행부터 AI 분석이 들어갑니다.

키가 없거나 API 호출이 실패하면 그날 리포트·영상은 **AI 없이 규칙 기반 결론**으로 만들어지고, 다음 복구 시각에 AI 분석을 한 번 더 시도합니다.

## 2. 지금 바로 시험하기

GitHub › Actions › 왼쪽에서 워크플로 선택 › **Run workflow**

| 워크플로 | 입력 |
|---|---|
| `daily-market-report` (모닝·나이트) | step `all`, slot `am` 또는 `pm`, 날짜 비움 |
| `오후 6시 실전 단타 통합 브리핑` | 날짜 비움, 다시 만들기 `force` 필요하면 체크 |
| `보유 포지션 수동 입력` | 실제 체결가가 다를 때 |

실행 화면의 '수집' 단계 로그에 `✓ docs/ai/<날짜>_<슬롯>.json` 이 보이면 API 키가 정상입니다. `ANTHROPIC_API_KEY 가 없어` 가 보이면 비밀값 이름을 확인하세요.

## 3. AI 설정 바꾸기 (`config.yaml` › `claude`)

| 항목 | 지금 값 | 설명 |
|---|---|---|
| `mode` | `api` | `api` = GitHub 에서 API 키로 분석 / `routine` = Claude 예약 작업이 분석해 푸시하던 이전 방식 |
| `model` | `claude-sonnet-5-5` | 분석 모델 |
| `web_search` | `true` | 분석할 때 최신 뉴스를 웹 검색 |
| `max_searches` | `15` | 한 번 분석할 때 최대 검색 횟수 (줄이면 API 비용이 줄어듭니다) |

## 참고

- 워크플로 파일: `.github/workflows/daily.yml`(수집·AI·리포트) → `daily-report.yml`(PDF·영상), `us-swing.yml`(18시), `update_positions.yml`(수동 입력).
- GitHub 는 저장소에 60일 동안 활동이 없으면 예약 실행을 멈춥니다. 이 저장소는 매일 자동 커밋이 생기므로 해당되지 않습니다.
- 예약 실행이 하루 통째로 빠지면 Actions 화면에서 **Run workflow** 로 직접 실행하면 됩니다.
