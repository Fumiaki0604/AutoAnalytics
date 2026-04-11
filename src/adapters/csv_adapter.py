"""CSV ファイルを読み込み、DuckDB テーブルとして登録する Adapter。"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.storage.duckdb_client import DuckDBClient


@dataclass
class LoadResult:
    table: str
    rows: int
    columns: list[str]

    def summary(self) -> str:
        return (
            f"テーブル '{self.table}' に {self.rows:,} 行ロード完了 "
            f"({len(self.columns)} カラム: {', '.join(self.columns)})"
        )


class CSVAdapter:
    """CSV → DuckDB ローダー。

    ロード後はテーブルが DuckDB に永続化されるため、
    同一セッション内で繰り返し SQL 参照が可能。
    """

    def __init__(self, db: DuckDBClient) -> None:
        self.db = db

    def load(self, csv_path: str, table_name: str) -> LoadResult:
        """CSV を読み込んで DuckDB テーブルを作成・置換する。

        Args:
            csv_path: 読み込む CSV ファイルのパス
            table_name: 作成する DuckDB テーブル名

        Returns:
            LoadResult: ロード結果のメタ情報
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV が見つかりません: {csv_path}")

        df = pd.read_csv(csv_path)

        # DataFrame を直接 DuckDB に登録（コピーなしでゼロオーバーヘッド）
        self.db.conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df"
        )

        return LoadResult(
            table=table_name,
            rows=len(df),
            columns=list(df.columns),
        )
