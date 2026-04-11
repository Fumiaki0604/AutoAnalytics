"""DuckDB への接続・クエリ実行を管理するクライアント。"""

from pathlib import Path
from typing import Any, Optional

import duckdb


class DuckDBClient:
    """DuckDB ラッパー。コンテキストマネージャとして使用可能。

    Usage:
        with DuckDBClient("data/analytics.duckdb") as db:
            db.execute("CREATE TABLE ...")
            rows = db.query("SELECT ...")
    """

    def __init__(self, db_path: str = "data/analytics.duckdb") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(db_path)

    # ------------------------------------------------------------------
    # 書き込み系
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: Optional[list] = None) -> duckdb.DuckDBPyRelation:
        """DDL や INSERT などを実行する。"""
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    # ------------------------------------------------------------------
    # 読み取り系
    # ------------------------------------------------------------------

    def query(self, sql: str) -> list[dict[str, Any]]:
        """SELECT を実行し、行を dict のリストで返す。"""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def get_schema(self, table: str) -> list[dict[str, str]]:
        """テーブルのカラム定義を返す。"""
        return self.query(f"DESCRIBE {table}")

    def list_tables(self) -> list[str]:
        """DB 内のテーブル一覧を返す。"""
        rows = self.query("SHOW TABLES")
        return [list(r.values())[0] for r in rows]

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DuckDBClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
