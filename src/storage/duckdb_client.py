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
        self.db_path = db_path
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

    def get_data_context(self, table: str, sample_rows: int = 3) -> str:
        """スキーマ・サンプル行・カラム値域を LLM に渡すための文字列を返す。

        これを渡すことで LLM が実データの日付・値域を把握し、
        WHERE 句などに正確な値を使えるようになる。
        """
        schema = self.get_schema(table)

        # サンプル行
        sample = self.query(f'SELECT * FROM "{table}" LIMIT {sample_rows}')

        # カラムごとの統計情報を収集
        numeric_stats: dict[str, tuple] = {}
        categorical_values: dict[str, list] = {}

        for col_info in schema:
            col = col_info["column_name"]
            col_type = col_info.get("column_type", "").upper()
            is_text = any(t in col_type for t in ("VARCHAR", "TEXT", "CHAR", "STRING", "ENUM"))
            is_bool = "BOOL" in col_type

            if is_bool:
                continue

            if is_text:
                # カテゴリ列: ユニーク値の上位 10 件
                try:
                    rows = self.query(
                        f'SELECT DISTINCT "{col}" FROM "{table}" '
                        f'ORDER BY "{col}" LIMIT 10'
                    )
                    vals = [str(list(r.values())[0]) for r in rows if list(r.values())[0] is not None]
                    if vals:
                        categorical_values[col] = vals
                except Exception:
                    pass
            else:
                # 数値・日付列: min / max
                try:
                    row = self.query(
                        f'SELECT MIN("{col}") AS mn, MAX("{col}") AS mx FROM "{table}"'
                    )[0]
                    numeric_stats[col] = (row["mn"], row["mx"])
                except Exception:
                    pass

        # --- フォーマット ---
        lines: list[str] = []

        lines.append("### スキーマ")
        for s in schema:
            lines.append(f"- {s['column_name']}: {s['column_type']}")

        if sample:
            lines.append("\n### サンプルデータ（先頭 3 行）")
            headers = list(sample[0].keys())
            lines.append(" | ".join(headers))
            for row in sample:
                lines.append(" | ".join(str(v) for v in row.values()))

        if numeric_stats:
            lines.append("\n### 数値・日付カラムの値域（min 〜 max）")
            for col, (mn, mx) in numeric_stats.items():
                lines.append(f"- {col}: {mn} 〜 {mx}")

        if categorical_values:
            lines.append("\n### カテゴリカラムのユニーク値（上位10件）")
            for col, vals in categorical_values.items():
                lines.append(f"- {col}: {', '.join(vals)}")

        return "\n".join(lines)

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
