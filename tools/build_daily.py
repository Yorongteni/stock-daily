#!/usr/bin/env python3
"""
매일 리포트(inbox/YYYY-MM-DD.md) 하나로 아래 결과물을 만든다.

  out/<날짜>/<날짜>.pdf        리포트 PDF
  out/<날짜>/<날짜>.mp4        유튜브용 영상 (슬라이드 + 한국어 음성 + 자막)
  out/<날짜>/youtube.json      업로드용 제목·설명·태그
  out/<날짜>/description.txt   설명란 (챕터 시간 포함)

사용법:
  python tools/build_daily.py inbox/2026-10-19.md --out out/2026-10-19
  python tools/build_daily.py inbox/2026-10-19.md --out out/test --silent   # 음성 없이 시험
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import markdown

FONT = "Noto Sans CJK KR"
VOICE = os.environ.get("TTS_VOICE", "ko-KR-SunHiNeural")
RATE = os.environ.get("TTS_RATE", "+8%")
SCENE_GAP = 0.6          # 장면 사이 쉼(초)
SUB_MAX = 38             # 자막 한 조각 최대 글자 수
DISCLAIMER = "본 콘텐츠는 투자 권유가 아닌 정보 제공 목적입니다. 투자 판단과 책임은 본인에게 있습니다."


# ───────────────────────────── 입력 파싱 ─────────────────────────────
@dataclass
class Scene:
    title: str
    bullets: list[str] = field(default_factory=list)
    narration: str = ""


@dataclass
class Daily:
    date: str
    report_md: str
    yt_title: str = ""
    yt_tags: list[str] = field(default_factory=list)
    yt_desc: str = ""
    scenes: list[Scene] = field(default_factory=list)


SCENE_RE = re.compile(r"^###\s*장면\s*\d*\s*[|:：\-–—]?\s*(.*)$")


def clean_inline(text: str) -> str:
    """마크다운 강조·인용 태그 등을 걷어낸 순수 텍스트."""
    text = re.sub(r"</?cite[^>]*>", "", text)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def parse(path: Path) -> Daily:
    date = path.stem
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        sys.exit(f"파일 이름은 YYYY-MM-DD.md 형식이어야 합니다: {path.name}")
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")

    # 리포트 본문 = '유튜브 정보' / '유튜브 대본' 앞부분
    cut = re.search(r"^##\s*유튜브\s*(정보|대본)", raw, flags=re.M)
    report_md = raw[: cut.start()] if cut else raw
    d = Daily(date=date, report_md=report_md.strip())

    info = re.search(r"^##\s*유튜브\s*정보\s*$(.*?)(?=^##\s|\Z)", raw, flags=re.M | re.S)
    if info:
        for line in info.group(1).splitlines():
            line = clean_inline(line.lstrip("-* "))
            if line.startswith("제목:"):
                d.yt_title = line[3:].strip()
            elif line.startswith("태그:"):
                d.yt_tags = [t.strip(" #") for t in re.split(r"[,，]", line[3:]) if t.strip(" #")]
            elif line.startswith("설명:"):
                d.yt_desc = line[3:].strip()

    script = re.search(r"^##\s*유튜브\s*대본\s*$(.*?)(?=^##\s|\Z)", raw, flags=re.M | re.S)
    if script:
        cur: Scene | None = None
        mode = ""
        for line in script.group(1).splitlines():
            s = line.strip()
            m = SCENE_RE.match(s)
            if m:
                cur = Scene(title=clean_inline(m.group(1)) or f"장면 {len(d.scenes) + 1}")
                d.scenes.append(cur)
                mode = ""
                continue
            if cur is None or not s:
                continue
            s = clean_inline(s.lstrip("-* "))
            if s.startswith("화면:"):
                cur.bullets += [b.strip() for b in s[3:].split(" / ") if b.strip()]
                mode = "screen"
            elif s.startswith("대사:"):
                cur.narration = (cur.narration + " " + s[3:].strip()).strip()
                mode = "talk"
            elif mode == "talk":
                cur.narration = (cur.narration + " " + s).strip()
            elif mode == "screen":
                cur.bullets.append(s)
    d.scenes = [sc for sc in d.scenes if sc.narration]
    return d


# ───────────────────────────── PDF ─────────────────────────────
PDF_CSS = f"""
@page {{ size: A4; }}
* {{ box-sizing: border-box; }}
body {{ font-family: '{FONT}', sans-serif; font-size: 10.5pt; line-height: 1.65; color: #1d2433; }}
h1 {{ font-size: 19pt; margin: 0 0 6pt; padding-bottom: 6pt; border-bottom: 3px solid #1f4e8c; color: #12305a; }}
h2 {{ font-size: 14pt; margin: 18pt 0 6pt; padding-left: 8pt; border-left: 5px solid #1f4e8c; color: #12305a; break-after: avoid; }}
h3 {{ font-size: 11.5pt; margin: 12pt 0 4pt; color: #1f4e8c; break-after: avoid; }}
p, li {{ orphans: 2; widows: 2; }}
ul, ol {{ padding-left: 16pt; }}
li {{ margin: 2pt 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; break-inside: auto; }}
th, td {{ border: 1px solid #c9d2e0; padding: 4pt 6pt; text-align: left; vertical-align: top; }}
th {{ background: #eaf0f8; }}
tr {{ break-inside: avoid; }}
blockquote {{ margin: 8pt 0; padding: 6pt 10pt; background: #f4f6fa; border-left: 4px solid #9fb3cf; }}
strong {{ color: #0f2747; }}
.up {{ color: #c62828; }} .down {{ color: #1565c0; }}
.note {{ margin-top: 18pt; padding-top: 6pt; border-top: 1px solid #c9d2e0; font-size: 8.5pt; color: #5b6575; }}
"""


def color_moves(html_text: str) -> str:
    """+1.2% 는 빨강, -1.2% 는 파랑 (국내 관례)."""
    def rep(m: re.Match) -> str:
        cls = "up" if m.group(1) == "+" else "down"
        return f'<span class="{cls}">{m.group(0)}</span>'
    return re.sub(r"([+\-−])\d[\d,]*(?:\.\d+)?%", rep, html_text)


def build_pdf(d: Daily, out_pdf: Path, browser) -> None:
    md_text = re.sub(r"</?cite[^>]*>", "", d.report_md)
    if not re.search(r"^#\s", md_text, flags=re.M):
        md_text = f"# {d.date} 시장 리포트\n\n" + md_text
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists", "fenced_code"])
    body = color_moves(body)
    page_html = (
        f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{PDF_CSS}</style></head>"
        f"<body>{body}<p class='note'>{html.escape(DISCLAIMER)}</p></body></html>"
    )
    tpl_style = f"font-family:'{FONT}';font-size:8px;color:#7a8494;width:100%;padding:0 14mm;"
    page = browser.new_page()
    page.set_content(page_html, wait_until="load")
    page.pdf(
        path=str(out_pdf),
        format="A4",
        print_background=True,
        margin={"top": "18mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        display_header_footer=True,
        header_template=f"<div style=\"{tpl_style}text-align:right;\">매일 시장 리포트 · {d.date}</div>",
        footer_template=f"<div style=\"{tpl_style}text-align:center;\"><span class='pageNumber'></span> / <span class='totalPages'></span></div>",
    )
    page.close()


# ───────────────────────────── 슬라이드 ─────────────────────────────
SLIDE_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1920px; height:1080px; }}
body {{ font-family:'{FONT}', sans-serif; color:#f3f6fb; overflow:hidden;
  background: radial-gradient(circle at 85% 10%, #1d3a66 0%, #0c1830 55%, #070f1f 100%); }}
.top {{ position:absolute; top:56px; left:96px; right:96px; display:flex; justify-content:space-between;
  align-items:center; font-size:30px; color:#9fb3cf; letter-spacing:1px; }}
.top b {{ color:#f3f6fb; font-weight:700; }}
.no {{ position:absolute; top:150px; left:96px; font-size:28px; color:#6fa8ff; font-weight:700; }}
h1 {{ position:absolute; top:196px; left:96px; right:96px; font-size:76px; font-weight:900; line-height:1.15; }}
.list {{ position:absolute; top:340px; left:96px; right:96px; display:flex; flex-direction:column; gap:22px; }}
.item {{ background:rgba(255,255,255,0.07); border:1px solid rgba(159,179,207,0.25); border-radius:20px;
  padding:22px 34px; font-size:var(--fs); font-weight:500; line-height:1.3; display:flex; gap:22px; align-items:center; }}
.dot {{ flex:none; width:14px; height:14px; border-radius:50%; background:#6fa8ff; }}
.up {{ color:#ff6b6b; font-weight:700; }} .down {{ color:#5aa9ff; font-weight:700; }}
.center h1 {{ top:380px; text-align:center; font-size:96px; }}
.center .sub {{ position:absolute; top:540px; left:0; right:0; text-align:center; font-size:40px; color:#9fb3cf; }}
.foot {{ position:absolute; bottom:28px; left:96px; right:96px; font-size:22px; color:#6b7a92; text-align:right; }}
"""


def slide_html(d: Daily, idx: int, total: int, sc: Scene) -> str:
    md = f"{int(d.date[5:7])}월 {int(d.date[8:10])}일"
    top = f"<div class='top'><span><b>매일 시장 브리핑</b> · {md}</span><span>{idx}/{total}</span></div>"
    foot = f"<div class='foot'>{html.escape(DISCLAIMER)}</div>"
    if sc.bullets:
        n = len(sc.bullets)
        fs = 50 if n <= 3 else 44 if n == 4 else 38 if n == 5 else 33
        items = "".join(
            f"<div class='item'><span class='dot'></span><span>{color_moves(html.escape(b))}</span></div>"
            for b in sc.bullets[:7]
        )
        body = (f"{top}<div class='no'>{idx:02d}</div><h1>{html.escape(sc.title)}</h1>"
                f"<div class='list' style='--fs:{fs}px'>{items}</div>{foot}")
        cls = ""
    else:
        body = f"{top}<h1>{html.escape(sc.title)}</h1><div class='sub'>{md} 시장 브리핑</div>{foot}"
        cls = "center"
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{SLIDE_CSS}</style></head>"
            f"<body class='{cls}'>{body}</body></html>")


def render_slides(d: Daily, work: Path, browser) -> list[Path]:
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    paths = []
    for i, sc in enumerate(d.scenes, 1):
        page.set_content(slide_html(d, i, len(d.scenes), sc), wait_until="load")
        p = work / f"slide_{i:02d}.png"
        page.screenshot(path=str(p))
        paths.append(p)
    page.close()
    return paths


# ───────────────────────────── 음성 ─────────────────────────────
def tts_text(text: str) -> str:
    text = text.replace("→", ", ").replace("·", ", ").replace("~", " 에서 ")
    return re.sub(r"\s+", " ", text).strip()


async def _tts(text: str, out: Path) -> None:
    import edge_tts
    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out))
            return
        except Exception as e:  # 일시적 네트워크 오류 대비
            if attempt == 2:
                raise
            print(f"  음성 생성 재시도 ({e})")
            await asyncio.sleep(3)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(f"명령 실패: {' '.join(cmd[:3])} ...")


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def make_audio(d: Daily, work: Path, silent: bool) -> list[tuple[Path, float]]:
    """장면별 wav(끝에 쉼 포함)와 '말하는 시간'을 돌려준다."""
    result = []
    for i, sc in enumerate(d.scenes, 1):
        wav = work / f"voice_{i:02d}.wav"
        if silent:
            speech = max(3.0, len(sc.narration.replace(" ", "")) * 0.16)
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                 "-t", f"{speech + SCENE_GAP:.2f}", str(wav)])
        else:
            mp3 = work / f"voice_{i:02d}.mp3"
            print(f"  음성 {i}/{len(d.scenes)}: {sc.title}")
            asyncio.run(_tts(tts_text(sc.narration), mp3))
            speech = duration(mp3)
            run(["ffmpeg", "-y", "-i", str(mp3), "-af", f"apad=pad_dur={SCENE_GAP}",
                 "-ar", "44100", "-ac", "1", str(wav)])
        result.append((wav, speech))
    return result


# ───────────────────────────── 자막 ─────────────────────────────
def split_subs(text: str) -> list[str]:
    """문장 단위로 나누고, 긴 문장은 띄어쓰기 기준으로 비슷한 길이로 쪼갠다."""
    sents = [s.strip() for s in re.split(r"(?<=[.?!。])\s+", text) if s.strip()]
    chunks: list[str] = []
    for s in sents:
        n = -(-len(s) // SUB_MAX)  # 올림
        if n <= 1:
            chunks.append(s)
            continue
        words, target, cur = s.split(" "), len(s) / n, ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > target * 1.15:
                chunks.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            chunks.append(cur)
    return chunks


def ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(d: Daily, audio: list[tuple[Path, float]], out: Path) -> list[float]:
    lines, n, t0, starts = [], 1, 0.0, []
    for sc, (wav, speech) in zip(d.scenes, audio):
        starts.append(t0)
        chunks = split_subs(sc.narration)
        weights = [max(1, len(c.replace(" ", ""))) for c in chunks]
        total_w = sum(weights)
        t = t0
        for c, w in zip(chunks, weights):
            dt = speech * w / total_w
            lines += [str(n), f"{ts(t)} --> {ts(t + dt - 0.05)}", c, ""]
            n += 1
            t += dt
        t0 += duration(wav)
    out.write_text("\n".join(lines), encoding="utf-8")
    return starts


# ───────────────────────────── 영상 ─────────────────────────────
def build_video(slides: list[Path], audio: list[tuple[Path, float]], srt: Path, out_mp4: Path, work: Path) -> None:
    durs = [duration(w) for w, _ in audio]
    img_list = work / "images.txt"
    img_list.write_text(
        "".join(f"file '{p.name}'\nduration {dur:.3f}\n" for p, dur in zip(slides, durs))
        + f"file '{slides[-1].name}'\n", encoding="utf-8")
    aud_list = work / "audio.txt"
    aud_list.write_text("".join(f"file '{w.name}'\n" for w, _ in audio), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio.txt", "-c", "copy", "voice_all.wav"], cwd=work)

    style = (f"FontName={FONT},FontSize=17,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=3,BackColour=&H90000000,Outline=1,Shadow=0,MarginV=34,Alignment=2")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "images.txt", "-i", "voice_all.wav",
         "-vf", f"fps=30,format=yuv420p,subtitles={srt.name}:force_style='{style}'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-tune", "stillimage",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
         str(out_mp4.resolve())], cwd=work)


# ───────────────────────────── 유튜브 정보 ─────────────────────────────
def mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def write_youtube_meta(d: Daily, starts: list[float], out_dir: Path) -> None:
    m, day = int(d.date[5:7]), int(d.date[8:10])
    title = (d.yt_title or f"[{m}/{day}] 매일 시장 브리핑")[:100]
    repo = os.environ.get("GITHUB_REPOSITORY", "Yorongteni/stock-daily")
    pdf_url = f"https://github.com/{repo}/blob/main/reports/{d.date}.pdf"
    chapters = "\n".join(f"{mmss(s)} {sc.title}" for s, sc in zip(starts, d.scenes))
    tags = d.yt_tags or ["주식", "코스피", "나스닥", "시장브리핑"]
    desc = "\n\n".join(x for x in [
        d.yt_desc,
        f"📄 오늘 리포트 PDF: {pdf_url}",
        "⏱ 목차\n" + chapters if len(d.scenes) >= 3 else "",
        f"※ {DISCLAIMER}",
        " ".join("#" + t.replace(" ", "") for t in tags[:5]),
    ] if x)
    # 유튜브 태그 총 길이 500자 제한
    kept, total = [], 0
    for t in tags:
        if total + len(t) + 1 > 480:
            break
        kept.append(t)
        total += len(t) + 1
    (out_dir / "description.txt").write_text(desc, encoding="utf-8")
    (out_dir / "youtube.json").write_text(json.dumps(
        {"date": d.date, "title": title, "description": desc[:4900], "tags": kept},
        ensure_ascii=False, indent=2), encoding="utf-8")


# ───────────────────────────── 실행 ─────────────────────────────
def closing_scene() -> Scene:
    return Scene(
        title="오늘 브리핑은 여기까지입니다",
        bullets=["자세한 리포트 PDF는 설명란 링크에서 확인하세요", "투자 권유가 아닌 정보 제공 목적입니다"],
        narration="오늘 브리핑은 여기까지입니다. 자세한 내용은 설명란의 리포트 PDF에서 확인하실 수 있습니다. "
                  "이 영상은 투자 권유가 아닌 정보 제공 목적이며, 투자 판단과 책임은 본인에게 있습니다.",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--silent", action="store_true", help="음성 대신 무음 (시험용)")
    ap.add_argument("--pdf-only", action="store_true")
    a = ap.parse_args()

    d = parse(a.input)
    out = a.out
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pdf = out / f"{d.date}.pdf"
        build_pdf(d, pdf, browser)
        print(f"PDF 완료: {pdf}")

        if a.pdf_only:
            browser.close()
            return
        if not d.scenes:
            browser.close()
            print("'## 유튜브 대본' 이 없어 영상은 건너뜁니다.")
            (out / "NO_VIDEO").write_text("no script", encoding="utf-8")
            return

        d.scenes.append(closing_scene())
        slides = render_slides(d, work, browser)
        browser.close()

    audio = make_audio(d, work, a.silent)
    srt = work / "subs.srt"
    starts = write_srt(d, audio, srt)
    mp4 = out / f"{d.date}.mp4"
    build_video(slides, audio, srt, mp4, work)
    write_youtube_meta(d, starts, out)
    print(f"영상 완료: {mp4} ({mmss(duration(mp4))})")


if __name__ == "__main__":
    main()
