"""Supabase を使ったサーバーサイドセッションストア。

in-memory の _sessions dict を置き換え、
サーバー再起動・複数インスタンスをまたいでセッションを永続化する。
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client, create_client

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def create_session(user_data: dict, ttl_hours: int = 8) -> str:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    _get_client().table("sessions").insert({
        "id": session_id,
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "picture": user_data.get("picture"),
        "access_token": user_data.get("access_token"),
        "refresh_token": user_data.get("refresh_token"),
        "expires_at": expires_at.isoformat(),
    }).execute()

    return session_id


def get_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None

    res = (
        _get_client()
        .table("sessions")
        .select("*")
        .eq("id", session_id)
        .gt("expires_at", datetime.now(timezone.utc).isoformat())
        .single()
        .execute()
    )

    return res.data if res.data else None


def delete_session(session_id: str) -> None:
    _get_client().table("sessions").delete().eq("id", session_id).execute()
