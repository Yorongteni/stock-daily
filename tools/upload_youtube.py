#!/usr/bin/env python3
"""
out/<날짜>/ 의 영상을 유튜브에 업로드한다. (기본: 비공개)

필요한 환경변수 (GitHub Secrets):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
선택:
  YT_PRIVACY   private(기본) / unlisted / public
  YT_CATEGORY  유튜브 카테고리 번호 (기본 27 = 교육)

사용법: python tools/upload_youtube.py out/2026-10-19
"""
import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


def main() -> None:
    out = Path(sys.argv[1])
    meta = json.loads((out / "youtube.json").read_text(encoding="utf-8"))
    video = out / f"{meta['date']}.mp4"

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": os.environ.get("YT_CATEGORY", "27"),
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": os.environ.get("YT_PRIVACY", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    req = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True),
    )
    try:
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                print(f"  업로드 {int(status.progress() * 100)}%")
    except HttpError as e:
        sys.exit(f"유튜브 업로드 실패: {e}")

    vid = resp["id"]
    print(f"업로드 완료: https://youtu.be/{vid} (상태: {body['status']['privacyStatus']})")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### 유튜브 업로드 완료\nhttps://youtu.be/{vid} (비공개 상태에서 확인 후 공개로 전환하세요)\n")


if __name__ == "__main__":
    main()
