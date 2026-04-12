"""Google OAuth 2.0 フロー管理。

セッションはサーバーサイドで in-memory 管理（PoC用）。
本番移行時は Redis 等に差し替える。
"""

import os
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/analytics.readonly",
]

# session_id → {access_token, email, name} の in-memory ストア
_sessions: dict[str, dict] = {}


def get_redirect_uri() -> str:
    base = os.environ.get("APP_BASE_URL", "http://localhost:8001")
    return f"{base}/auth/callback"


def build_auth_url() -> tuple[str, str]:
    """認可 URL と state を返す。"""
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": get_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state


async def exchange_code(code: str) -> dict:
    """認可コードをトークンに交換し、ユーザー情報を取得して返す。"""
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": get_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        token_res.raise_for_status()
        tokens = token_res.json()

        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_res.raise_for_status()
        user = user_res.json()

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    }


def create_session(user_data: dict) -> str:
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = user_data
    return session_id


def get_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
