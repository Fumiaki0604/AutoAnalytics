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
# GA4 API は1リクエストで最大9ディメンション・10メトリクスまで
DEFAULT_DIMENSIONS = [
    "date",
    "sessionDefaultChannelGroup",
    "sessionSourceMedium",   # 参照元/メディア（セッション）
    "sessionSource",         # 参照元（セッション）
    "sessionMedium",         # メディア（セッション）
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
    date_ranges: Optional[list[tuple[str, str]]] = None  # 複数期間指定時

    def summary(self) -> str:
        if self.date_ranges and len(self.date_ranges) > 1:
            periods = " / ".join(f"{s} 〜 {e}" for s, e in self.date_ranges)
            return (
                f"GA4 プロパティ {self.property_id} から {self.rows:,} 行取得 "
                f"（{periods}）"
                f" → テーブル '{self.table}'"
            )
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
        start_date: str = "",
        end_date: str = "",
        table_name: str = "ga4_data",
        dimensions: Optional[list[str]] = None,
        metrics: Optional[list[str]] = None,
        date_ranges: Optional[list[tuple[str, str]]] = None,
    ) -> GA4LoadResult:
        """GA4 からデータを取得して DuckDB テーブルを作成する。

        Args:
            property_id: GA4 プロパティ ID（例: "123456789"）
            start_date: 開始日（単一期間時）
            end_date: 終了日（単一期間時）
            table_name: 作成する DuckDB テーブル名
            date_ranges: 複数期間指定時 [(start1, end1), (start2, end2)]。指定時は start_date/end_date より優先。
        """
        dims = list(dimensions or DEFAULT_DIMENSIONS)
        mets = metrics or DEFAULT_METRICS

        # 複数期間指定時: 期間ごとに別々にAPIを叩いてdateRange列を手動付与
        # （GA4 APIの dateRange はディメンションとして指定不可のため）
        if date_ranges and len(date_ranges) > 1:
            rows = []
            for range_idx, (range_start, range_end) in enumerate(date_ranges):
                req = RunReportRequest(
                    property=f"properties/{property_id}",
                    dimensions=[Dimension(name=d) for d in dims],
                    metrics=[Metric(name=m) for m in mets],
                    date_ranges=[DateRange(start_date=range_start, end_date=range_end)],
                )
                resp = self.client.run_report(req)
                for row in resp.rows:
                    record: dict = {}
                    for i, dim in enumerate(dims):
                        record[dim] = row.dimension_values[i].value
                    for i, met in enumerate(mets):
                        val = row.metric_values[i].value
                        try:
                            record[met] = float(val) if "." in val else int(val)
                        except (ValueError, TypeError):
                            record[met] = val
                    record["dateRange"] = f"date_range_{range_idx}"
                    rows.append(record)
        else:
            date_ranges = None  # 単一期間はNoneに統一
            request = RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name=d) for d in dims],
                metrics=[Metric(name=m) for m in mets],
                date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            )
            response = self.client.run_report(request)
            rows = []
            for row in response.rows:
                record = {}
                for i, dim in enumerate(dims):
                    record[dim] = row.dimension_values[i].value
                for i, met in enumerate(mets):
                    val = row.metric_values[i].value
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
        primary_range = date_ranges[0] if date_ranges else (start_date, end_date)
        return GA4LoadResult(
            table=table_name,
            property_id=property_id,
            rows=len(df),
            columns=columns,
            date_range=primary_range,
            date_ranges=date_ranges,
        )
