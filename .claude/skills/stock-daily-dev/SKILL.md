---
name: stock-daily-dev
description: stock-daily 파이프라인(수집 → AI 분석 → HTML/PDF → 영상)을 로컬에서 실행·시험하고 고칠 때 쓰는 절차와 파일 지도.
---

# stock-daily 개발·시험 가이드

## 흐름

```
main.py --collect   → docs/data/<날짜>_<슬롯>.json, _brief.md      (macro.py, news.py, screener.py, indicators.py)
루틴/API             → docs/ai/<날짜>_<슬롯>.json                    (commentary.py, prompts/briefing.md, tools/validate_ai.py)
main.py --build     → docs/report_<날짜>_<슬롯>.html (+ report_<날짜>.html, index.html, latest.json, history.json)
                                                                    (advisor.py: AI 없으면 규칙 기반 결론, report.py)
tools/build_from_report.py → PDF, 영상(mp4), youtube.json          (tools/build_daily.py: TTS·자막·ffmpeg)
```

오후 6시 단타 통합 브리핑 (18:00, AI 없음, 외부 업로드 없음):
```
swing.py --date D   → 1부 미국(data/us_swing_portfolio.json·trade_history.json) + futures.run → 2부 코인(data/binance_futures_log.json)
                      → docs/swing/data/D.json, docs/swing/swing_D.html
tools/build_swing.py --date D → swing_D.pdf, swing_D.mp4 (video_slides.render + build_daily TTS 재사용)
positions.py --market US_STOCK|BINANCE --action BUY|CLOSE|CANCEL --ticker T [--direction] --price P --qty Q   (update_positions.yml)
```
- 코인 데이터 출처는 futures.pick_source: 바이낸스 선물 → OKX 무기한 → 바이낸스 현물 미러. 코인 파트가 실패해도 1부는 그대로 만든다.
- 판정은 오늘 밤 세션 날짜보다 앞선 완성 일봉만 사용, 포지션별 `last_bar` 로 중복 판정 방지. 같은 날 재실행 시 오늘 자동 예약은 다시 계산.
- 시험은 `SWING_DATA_DIR=<임시폴더>` 와 `--out <임시폴더>` 로 실제 상태 파일을 건드리지 않게 합니다.

## 로컬 시험

```bash
pip install -r requirements.txt -r requirements-video.txt
python -m playwright install chromium

python main.py --demo --no-ai --slot am --out /tmp/demo          # 인터넷 없이 화면 확인
python main.py --slot am --out /tmp/live                         # 실데이터 (AI 파일 없으면 정량 결론)
python tools/validate_ai.py /tmp/live/ai/<날짜>_am.json --check   # AI JSON 검사
python main.py --slot am --build --out /tmp/live                 # 저장된 묶음 + AI 로 다시 생성
```

영상 시험은 `docs/` 를 쓰므로, 임시 폴더에 `tools/` 와 `docs/report_<날짜>_<슬롯>.html`, `docs/latest.json` 을 복사해서
그 폴더에서 `python tools/build_from_report.py --date <날짜> --slot am --silent` 로 실행합니다.

## 폴백(실패 대비) 원칙

- 자산마다 출처 목록(config.yaml `macro.assets[].sources`)을 순서대로 시도, 모두 실패하면 그 자산만 "데이터 없음".
- 뉴스 피드 하나가 실패해도 계속. 분야 장기 비교 실패 시 기존 분야 지표만.
- AI JSON 이 없거나 `validate_ai.py` 필수 항목 누락이면 `advisor.rule_based()` 결론으로 같은 화면 구성 유지.
- 리포트·영상은 섹션 선택자(report.py id/class ↔ build_from_report.py `SHOTS`)가 맞아야 합니다. 바꾸면 둘 다 고칩니다.

## 주의

- report.py 의 `const DATA = ...;\nconst esc` 형식을 build_from_report.py 가 정규식으로 읽습니다.
- cron 은 UTC. 시작 신호는 루틴의 docs/trigger 푸시, cron 은 백업(06:10·06:25 수집, 06:50·07:15·07:45 누락 복구).
- 네트워크 작업은 netretry.retry() 로 감싼다 (최대 3회, 지수 백오프).
- 저장소는 Public 입니다. 키·토큰을 파일에 넣지 않습니다.
