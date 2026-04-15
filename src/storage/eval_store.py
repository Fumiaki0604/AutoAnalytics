"""分析ごとの定量スコアを Supabase に保存・取得する。"""

import re

from src.auth.session_store import _get_client
from src.orchestrator.hypothesis_generator import Hypothesis


def compute_and_save(
    email: str,
    property_id: str,
    hypotheses: list[Hypothesis],
    report_md: str,
) -> None:
    """仮説リストとレポートからメトリクスを計算して保存する。"""
    total = len(hypotheses)
    success = sum(1 for h in hypotheses if h.status == "supported")
    error = sum(1 for h in hypotheses if h.status == "error")
    no_data = sum(1 for h in hypotheses if h.status == "no_data")

    has_summary = bool(re.search(r"##\s*エグゼクティブサマリ", report_md))
    has_actions = bool(re.search(r"##\s*推奨アクション", report_md))

    try:
        _get_client().table("eval_logs").insert({
            "email": email,
            "property_id": property_id,
            "hypothesis_count": total,
            "sql_success_count": success,
            "sql_error_count": error,
            "sql_no_data_count": no_data,
            "report_has_summary": has_summary,
            "report_has_actions": has_actions,
        }).execute()
    except Exception:
        pass  # eval ログ保存失敗は分析結果に影響させない


def get_summary(email: str, property_id: str, limit: int = 10) -> list[dict]:
    """直近 N 件のスコアを返す。"""
    res = (
        _get_client()
        .table("eval_logs")
        .select("created_at,hypothesis_count,sql_success_count,sql_error_count,report_has_summary,report_has_actions")
        .eq("email", email)
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data if res.data else []
