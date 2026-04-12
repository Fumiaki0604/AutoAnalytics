"""GA4 Data API からデータを取得して DuckDB テーブルに格納する Adapter。"""

from dataclasses import dataclass
from typing import Optional

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)
from google.oauth2.credentials import Credentials

from src.storage.duckdb_client import DuckDBClient


# デフォルトで取得するディメンション・指標
DEFAULT_DIMENSIONS = [
    "date",
    "sessionDefaultChannelGroup",
    "deviceCategory",
    "landingPage",
]

DEFAULT_METRICS = [
    "sessions",
    "conversions",
    "totalRevenue",
    "bounceRate",
    "averageSessionDuration",
    "newUsers",
]


@dataclass
class GA4LoadResult:
    table: str
    property_id: str
    rows: int
    columns: list[str]
    date_range: tuple[str, str]

    def summary(self) -> str:
        return (
            f"GA4 プロパティ {self.property_id} から {self.rows:,} 行取得 "
            f"（{self.date_range[0]} 〜 {self.date_range[1]}）"
            f" → テーブル '{self.table}'"
        )


class GA4Adapter:
    """GA4 Data API → DuckDB ローダー。

    ユーザーの OAuth アクセストークンを使って API を叩くため、
    そのユーザーが権限を持つプロパティのデータのみ取得できる。
    """

    def __init__(self, db: DuckDBClient, access_token: str) -> None:
        self.db = db
        credentials = Credentials(token=access_token)
        self.client = BetaAnalyticsDataClient(credentials=credentials)

    def load(
        self,
        property_id: str,
        start_date: str,
        end_date: str,
        table_name: str = "ga4_data",
        dimensions: Optional[list[str]] = None,
        metrics: Optional[list[str]] = None,
    ) -> GA4LoadResult:
        """GA4 からデータを取得して DuckDB テーブルを作成する。

        Args:
            property_id: GA4 プロパティ ID（例: "123456789"）
            start_date: 開始日（例: "2026-03-01" or "30daysAgo"）
            end_date: 終了日（例: "2026-04-10" or "yesterday"）
            table_name: 作成する DuckDB テーブル名
        """
        dims = dimensions or DEFAULT_DIMENSIONS
        mets = metrics or DEFAULT_METRICS

        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in mets],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        )

        response = self.client.run_report(request)

        # レスポンスを行リストに変換
        rows = []
        for row in response.rows:
            record: dict = {}
            for i, dim in enumerate(dims):
                record[dim] = row.dimension_values[i].value
            for i, met in enumerate(mets):
                val = row.metric_values[i].value
                # 数値に変換できるものは変換
                try:
                    record[met] = float(val) if "." in val else int(val)
                except (ValueError, TypeError):
                    record[met] = val
            rows.append(record)

        if not rows:
            raise ValueError(
                f"GA4 からデータが取得できませんでした。"
                f"プロパティID・期間・権限を確認してください。"
            )

        # DuckDB に保存
        import pandas as pd
        df = pd.DataFrame(rows)
        self.db.conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df"
        )

        columns = list(df.columns)
        return GA4LoadResult(
            table=table_name,
            property_id=property_id,
            rows=len(df),
            columns=columns,
            date_range=(start_date, end_date),
        )
