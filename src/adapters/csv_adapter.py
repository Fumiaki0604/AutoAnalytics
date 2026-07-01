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
    note: str = ""

    def summary(self) -> str:
        base = (
            f"テーブル '{self.table}' に {self.rows:,} 行ロード完了 "
            f"({len(self.columns)} カラム: {', '.join(self.columns)})"
        )
        return f"{base}\n{self.note}" if self.note else base


def _to_num(val):
    """数値変換。カンマ区切りや%表記も許容。変換不能はNone。"""
    try:
        s = str(val).replace(",", "").strip()
        if s in ("", "nan", "-", "(not set)"):
            return None
        return int(float(s))
    except Exception:
        return None


def _is_ga4_comparison_report(df: pd.DataFrame) -> bool:
    """GA4の日付比較エクスポート形式かどうか判定する。

    特徴: 1行目(ヘッダー除く)の参照元列が空で、3列目に「変化量」が含まれる。
    """
    if len(df) < 4 or len(df.columns) < 4:
        return False
    try:
        first_col_empty = pd.isna(df.iloc[0, 0]) or str(df.iloc[0, 0]).strip() == ""
        third_col_change = "変化量" in str(df.iloc[0, 2])
        return first_col_empty and third_col_change
    except Exception:
        return False


def _flatten_ga4_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """GA4比較レポートの3行1セット構造を1行に平坦化する。

    入力構造（pandas読み込み後）:
      行0: "", "", "変化量(絶対)", 合計変化率, "合計"  ← 全体サマリー
      行1: "", "", "当期ラベル",   合計当期値, ""
      行2: "", "", "前期ラベル",   合計前期値, ""
      行3: source, page, "変化量(絶対)", 変化率, ""    ← 1件目
      行4: "", "", "当期ラベル", 当期値, ""
      行5: "", "", "前期ラベル", 前期値, ""
      ...（3行ずつ繰り返し）

    出力: 1件1行のフラットなDataFrame
    """
    metric_col = df.columns[3]  # 例: "セッション"

    # 当期・前期のラベルを先頭サマリー行から取得
    current_label = str(df.iloc[1, 2]).strip() if len(df) > 1 else "当期"
    previous_label = str(df.iloc[2, 2]).strip() if len(df) > 2 else "前期"

    records = []
    i = 3  # 先頭3行（全体サマリー）をスキップ
    while i + 2 < len(df):
        r0 = df.iloc[i]
        r1 = df.iloc[i + 1]
        r2 = df.iloc[i + 2]

        source = str(r0.iloc[0]).strip()
        page   = str(r0.iloc[1]).strip()

        # 変化率は文字列のまま保持（"-11.43%" など）
        change_pct = str(r0.iloc[3]).strip()

        current_val  = _to_num(r1.iloc[3])
        previous_val = _to_num(r2.iloc[3])

        # 変化数（絶対値）
        if current_val is not None and previous_val is not None:
            change_abs = current_val - previous_val
        else:
            change_abs = None

        records.append({
            "参照元_メディア":           source,
            "ランディングページ":         page,
            "変化率":                    change_pct,
            f"{metric_col}_当期":        current_val,
            f"{metric_col}_前期":        previous_val,
            f"{metric_col}_増減":        change_abs,
            "当期ラベル":                current_label,
            "前期ラベル":                previous_label,
        })
        i += 3

    return pd.DataFrame(records)


class CSVAdapter:
    """CSV → DuckDB ローダー。

    ロード後はテーブルが DuckDB に永続化されるため、
    同一セッション内で繰り返し SQL 参照が可能。
    GA4の日付比較エクスポート形式を自動検出して平坦化する。
    """

    def __init__(self, db: DuckDBClient) -> None:
        self.db = db

    def load(self, csv_path: str, table_name: str) -> LoadResult:
        """CSV を読み込んで DuckDB テーブルを作成・置換する。"""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV が見つかりません: {csv_path}")

        # エンコーディング自動判定（UTF-8 → UTF-8 BOM付き → Shift-JIS の順で試行）
        df = None
        for encoding in ("utf-8", "utf-8-sig", "cp932"):
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        if df is None:
            raise ValueError(
                "CSV のエンコーディングを判定できませんでした（UTF-8 / Shift-JIS に対応しています）"
            )

        note = ""
        if _is_ga4_comparison_report(df):
            original_rows = len(df)
            df = _flatten_ga4_comparison(df)
            note = (
                f"※ GA4日付比較レポートを検出。{original_rows}行（3行1セット構造）→ "
                f"{len(df)}行のフラットテーブルに変換しました。"
            )

        # DataFrame を直接 DuckDB に登録
        self.db.conn.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df"
        )

        return LoadResult(
            table=table_name,
            rows=len(df),
            columns=list(df.columns),
            note=note,
        )
