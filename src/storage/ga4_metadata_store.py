"""GA4プロパティごとのgetMetadata結果をSupabaseに24hキャッシュするストア。"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.auth.session_store import _get_client

_CACHE_HOURS = 24


def get_cached_metadata(property_id: str) -> Optional[dict]:
    """24h以内のキャッシュがあれば {'dimensions': [...], 'metrics': [...]} を返す。
    なければ None。"""
    try:
        res = (
            _get_client()
            .table("ga4_property_metadata")
            .select("dimensions, metrics, fetched_at")
            .eq("property_id", property_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        fetched = datetime.fromisoformat(row["fetched_at"])
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched > timedelta(hours=_CACHE_HOURS):
            return None
        return {"dimensions": row["dimensions"], "metrics": row["metrics"]}
    except Exception:
        return None


def save_metadata(property_id: str, dimensions: list[dict], metrics: list[dict]) -> None:
    """メタデータをSupabaseにupsertする。失敗はサイレントに無視。"""
    try:
        _get_client().table("ga4_property_metadata").upsert({
            "property_id": property_id,
            "dimensions": dimensions,
            "metrics": metrics,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass
