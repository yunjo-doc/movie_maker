"""YouTube OAuth 토큰 관리 — .env 기반 + 자동 갱신"""

import json
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _ensure_client_secrets(path: str = "secrets/client_secret.json") -> str:
    """client_secret.json이 없으면 .env의 값으로 자동 생성"""
    p = Path(path)
    if p.exists():
        return str(p)

    client_id = settings.youtube_client_id
    client_secret = settings.youtube_client_secret

    if not client_id or not client_secret:
        raise ValueError(
            "YouTube OAuth 설정이 없습니다.\n"
            ".env에 YOUTUBE_CLIENT_ID와 YOUTUBE_CLIENT_SECRET을 설정하세요."
        )

    # Google OAuth 클라이언트 시크릿 JSON 형식으로 생성
    data = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"client_secret.json 자동 생성: {p}")
    return str(p)


def get_youtube_service(
    token_file: str = "secrets/youtube_token.json",
):
    """YouTube API 서비스 객체 반환 (토큰 자동 갱신)"""
    creds = None
    token_path = Path(token_file)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("OAuth 토큰 갱신 중...")
            creds.refresh(Request())
        else:
            client_secrets = _ensure_client_secrets()
            logger.info("OAuth 인증 시작 (브라우저가 열립니다)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets, SCOPES
            )
            creds = flow.run_local_server(port=8080, prompt="consent")

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        logger.info("OAuth 토큰 저장 완료")

    return build("youtube", "v3", credentials=creds)
