"""分析メモリの保存・取得。Supabase の analysis_memory テーブルを使う。"""

from src.auth.session_store import _get_client


def save_memory(
    email: str,
    property_id: str,
    kpi: str,
    request_summary: str,
    findings: str,
    actions: list[str],
) -> None:
    """分析結果を Supabase に保存する。"""
    _get_client().table("analysis_memory").insert({
        "email": email,
        "property_id": property_id,
        "kpi": kpi,
        "request_summary": request_summary,
        "findings": findings,
        "actions": actions,
    }).execute()


def get_recent_memories(
    email: str,
    property_id: str,
    limit: int = 3,
) -> list[dict]:
    """直近 N 件の分析メモリを新しい順で返す。"""
    res = (
        _get_client()
        .table("analysis_memory")
        .select("created_at, kpi, request_summary, findings, actions")
        .eq("email", email)
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data if res.data else []


def format_past_context(memories: list[dict]) -> str:
    """メモリリストを hypothesis_prompt に注入できる文字列に変換する。"""
    if not memories:
        return "（過去の分析履歴なし）"

    lines = ["【直近の分析履歴】"]
    for m in memories:
        date = m.get("created_at", "")[:10]
        kpi = m.get("kpi") or ""
        summary = m.get("request_summary") or ""
        findings = m.get("findings") or ""
        actions = m.get("actions") or []

        lines.append(f"\n- {date} 分析: {summary}（KPI: {kpi}）")
        if findings:
            lines.append(f"  発見: {findings}")
        if actions:
            lines.append(f"  推奨アクション: {', '.join(actions)}")

    return "\n".join(lines)
