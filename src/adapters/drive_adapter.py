"""Google Drive アダプター。クライアント資料（議事録等）を取得する。"""

import httpx

_DRIVE_API = "https://www.googleapis.com/drive/v3"
MAX_CHARS_PER_DOC = 2000


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def list_folders(access_token: str) -> list[dict]:
    """アクセス可能なフォルダ一覧を返す（name昇順）。"""
    res = httpx.get(
        f"{_DRIVE_API}/files",
        headers=_headers(access_token),
        params={
            "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
            "fields": "files(id,name)",
            "pageSize": 50,
            "orderBy": "name",
        },
        timeout=15,
    )
    res.raise_for_status()
    return res.json().get("files", [])


def find_folder_by_name(access_token: str, name: str) -> str | None:
    """フォルダ名で検索して folder_id を返す。なければ None。"""
    res = httpx.get(
        f"{_DRIVE_API}/files",
        headers=_headers(access_token),
        params={
            "q": f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false",
            "fields": "files(id,name)",
            "pageSize": 1,
        },
        timeout=15,
    )
    if res.status_code != 200:
        return None
    files = res.json().get("files", [])
    return files[0]["id"] if files else None


def get_recent_docs_text(access_token: str, folder_id: str, max_docs: int = 3) -> str:
    """
    指定フォルダ内の最新 Google Docs を取得してテキストを返す。
    複数ある場合は区切り線で結合。取得失敗時は空文字列。
    """
    res = httpx.get(
        f"{_DRIVE_API}/files",
        headers=_headers(access_token),
        params={
            "q": (
                f"'{folder_id}' in parents"
                " and mimeType='application/vnd.google-apps.document'"
                " and trashed=false"
            ),
            "fields": "files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": max_docs,
        },
        timeout=15,
    )
    if res.status_code != 200:
        return ""
    files = res.json().get("files", [])
    if not files:
        return ""

    parts = []
    for f in files:
        text = _export_doc_text(access_token, f["id"], f["name"])
        if text:
            parts.append(text)

    return "\n\n---\n\n".join(parts)


def upload_file(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
) -> str:
    """ファイルを Google Drive の指定フォルダにアップロードして file_id を返す。"""
    import json as _json
    metadata = _json.dumps({"name": filename, "parents": [folder_id]}).encode()
    boundary = b"--boundary_autoanalytics"
    body = (
        boundary + b"\r\n"
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata + b"\r\n"
        + boundary + b"\r\n"
        + f"Content-Type: {mime_type}\r\n\r\n".encode()
        + content + b"\r\n"
        + boundary + b"--"
    )
    res = httpx.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers={
            **_headers(access_token),
            "Content-Type": "multipart/related; boundary=boundary_autoanalytics",
        },
        content=body,
        timeout=30,
    )
    res.raise_for_status()
    return res.json().get("id", "")


def _export_doc_text(access_token: str, file_id: str, name: str) -> str:
    """Google Doc をプレーンテキストでエクスポートして先頭 MAX_CHARS_PER_DOC 文字を返す。"""
    res = httpx.get(
        f"{_DRIVE_API}/files/{file_id}/export",
        headers=_headers(access_token),
        params={"mimeType": "text/plain"},
        timeout=15,
    )
    if res.status_code != 200:
        return ""
    text = res.text.strip()[:MAX_CHARS_PER_DOC]
    return f"【{name}】\n{text}"
