#!/usr/bin/env python3
"""
[처음 한 번만, 개인 PC에서 실행] 유튜브 업로드용 refresh token 발급.

준비: Google Cloud Console에서 받은 OAuth 클라이언트 파일(데스크톱 앱 유형)을
      client_secret.json 이름으로 이 파일과 같은 폴더에 둔다.
실행: pip install google-auth-oauthlib
      python tools/get_youtube_token.py
→ 브라우저에서 유튜브 채널 계정으로 로그인·허용하면 아래 세 값이 출력된다.
  출력된 값을 GitHub 저장소 Settings > Secrets and variables > Actions 에 등록.
※ client_secret.json 과 출력된 값은 절대 저장소에 올리지 말 것.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

here = Path(__file__).resolve().parent
secret = here / "client_secret.json"
if not secret.exists():
    secret = Path("client_secret.json")

flow = InstalledAppFlow.from_client_secrets_file(
    str(secret), scopes=["https://www.googleapis.com/auth/youtube.upload"]
)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
info = json.loads(secret.read_text(encoding="utf-8"))
client = info.get("installed") or info.get("web")

print("\n아래 세 값을 GitHub Secrets에 등록하세요.\n")
print(f"YT_CLIENT_ID      = {client['client_id']}")
print(f"YT_CLIENT_SECRET  = {client['client_secret']}")
print(f"YT_REFRESH_TOKEN  = {creds.refresh_token}")
