"""プロンプトのバージョン管理。Supabase prompt_versions テーブルを使う。"""

from pathlib import Path

from src.auth.session_store import _get_client

PROMPT_FILES = {
    "report_prompt": "prompts/report_prompt.md",
    "hypothesis_prompt": "prompts/hypothesis_prompt.md",
}


def save_prompt_version(prompt_name: str, content: str, review_feedback: str = "") -> None:
    """改善済みプロンプトを Supabase に保存し、ローカルファイルも上書きする。"""
    _get_client().table("prompt_versions").insert({
        "prompt_name": prompt_name,
        "content": content,
        "review_feedback": review_feedback,
    }).execute()

    # ローカルファイルも更新
    path = PROMPT_FILES.get(prompt_name)
    if path:
        Path(path).write_text(content, encoding="utf-8")


def get_latest_prompt(prompt_name: str) -> str | None:
    """Supabase から最新バージョンを取得する。なければ None。"""
    res = (
        _get_client()
        .table("prompt_versions")
        .select("content")
        .eq("prompt_name", prompt_name)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["content"]
    return None


def list_versions(prompt_name: str, limit: int = 10) -> list[dict]:
    """バージョン履歴を新しい順で返す。"""
    res = (
        _get_client()
        .table("prompt_versions")
        .select("id, created_at, review_feedback")
        .eq("prompt_name", prompt_name)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data if res.data else []


def rollback_prompt(prompt_name: str, steps: int = 1) -> str | None:
    """N世代前のバージョンに戻す。戻したコンテンツを返す。"""
    res = (
        _get_client()
        .table("prompt_versions")
        .select("content")
        .eq("prompt_name", prompt_name)
        .order("created_at", desc=True)
        .limit(steps + 1)
        .execute()
    )
    if not res.data or len(res.data) <= steps:
        return None

    old_content = res.data[steps]["content"]
    path = PROMPT_FILES.get(prompt_name)
    if path:
        Path(path).write_text(old_content, encoding="utf-8")
    return old_content
