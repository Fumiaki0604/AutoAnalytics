"""SQL エラーの学習ログを Supabase に保存・取得する。"""

from src.auth.session_store import _get_client


def save_correction(
    email: str,
    property_id: str,
    error_type: str,
    failed_pattern: str,
    error_message: str,
) -> None:
    """SQL エラーを learned_corrections テーブルに保存する。"""
    _get_client().table("learned_corrections").insert({
        "email": email,
        "property_id": property_id,
        "error_type": error_type,
        "failed_pattern": failed_pattern[:500],
        "error_message": error_message[:500],
    }).execute()


def get_recent_corrections(
    email: str,
    property_id: str,
    limit: int = 5,
) -> list[dict]:
    """直近 N 件のエラーログを新しい順で返す。"""
    res = (
        _get_client()
        .table("learned_corrections")
        .select("error_type, failed_pattern, error_message, created_at")
        .eq("email", email)
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data if res.data else []


def format_corrections_context(corrections: list[dict]) -> str:
    """エラーログを hypothesis_prompt に注入できる文字列に変換する。"""
    if not corrections:
        return "（過去のSQLエラー履歴なし）"

    lines = ["【過去のSQLエラー履歴（同じミスを繰り返さないこと）】"]
    for c in corrections:
        date = c.get("created_at", "")[:10]
        etype = c.get("error_type") or ""
        pattern = c.get("failed_pattern") or ""
        msg = c.get("error_message") or ""
        lines.append(f"\n- {date} [{etype}] {pattern}")
        if msg:
            lines.append(f"  エラー: {msg[:120]}")

    return "\n".join(lines)
