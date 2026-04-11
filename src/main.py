"""分析エージェント PoC のエントリポイント。

Usage:
    python -m src.main \\
        --csv data/sample.csv \\
        --request "CVRが先月比で低下している。チャネル別・デバイス別に原因を探りたい"
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from src.adapters.csv_adapter import CSVAdapter
from src.llm.anthropic_client import AnthropicClient
from src.orchestrator.hypothesis_generator import Hypothesis, HypothesisGenerator
from src.orchestrator.report_generator import ReportGenerator
from src.orchestrator.request_parser import ParsedRequest, RequestParser
from src.storage.duckdb_client import DuckDBClient


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def load_prompt(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {path}")
    return p.read_text(encoding="utf-8")


def build_data_context(db: DuckDBClient, table: str) -> str:
    try:
        return db.get_data_context(table)
    except Exception as e:
        return f"データコンテキスト取得失敗: {e}"


def format_query_result(rows: list[dict[str, Any]], max_rows: int = 10) -> str:
    if not rows:
        return "（結果なし）"
    headers = list(rows[0].keys())
    sep = " | "
    lines = [sep.join(headers), "-" * (sum(len(h) for h in headers) + len(sep) * (len(headers) - 1))]
    for row in rows[:max_rows]:
        lines.append(sep.join(str(v) for v in row.values()))
    if len(rows) > max_rows:
        lines.append(f"... 他 {len(rows) - max_rows:,} 行")
    return "\n".join(lines)


def run_hypotheses(db: DuckDBClient, hypotheses: list[Hypothesis]) -> None:
    for h in hypotheses:
        if not h.sql:
            h.result = "（SQL なし）"
            continue
        try:
            rows = db.query(h.sql)
            h.result = format_query_result(rows)
        except Exception as e:
            h.result = f"SQL 実行エラー: {e}"


# ------------------------------------------------------------------
# Main flow
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="分析エージェント PoC")
    parser.add_argument("--csv", required=True, help="分析対象 CSV ファイルのパス")
    parser.add_argument("--table", default="main_data", help="DuckDB テーブル名 (default: main_data)")
    parser.add_argument("--request", required=True, help="自然言語での分析依頼")
    parser.add_argument("--db", default="data/analytics.duckdb", help="DuckDB ファイルパス")
    parser.add_argument("--output-dir", default="reports", help="レポート出力ディレクトリ")
    args = parser.parse_args()

    # ---- プロンプト読み込み ----
    system_prompt = load_prompt("prompts/system_prompt.md")
    hypothesis_prompt = load_prompt("prompts/hypothesis_prompt.md")
    report_prompt = load_prompt("prompts/report_prompt.md")

    # ---- コンポーネント初期化 ----
    llm = AnthropicClient()

    with DuckDBClient(args.db) as db:

        # Step 1: CSV ロード
        print(f"\n[1/4] CSV を読み込み中: {args.csv}")
        meta = CSVAdapter(db).load(args.csv, args.table)
        print(f"      {meta.summary()}")

        # Step 2: 依頼パース
        print("\n[2/4] 分析依頼を解析中...")
        parsed: ParsedRequest = RequestParser(llm, system_prompt).parse(
            args.request, db.list_tables()
        )
        print(f"      KPI      : {parsed.kpi}")
        print(f"      期間     : {parsed.period}")
        print(f"      切り口   : {', '.join(parsed.dimensions) or 'なし'}")
        print(f"      要約     : {parsed.summary}")

        # Step 3: 仮説生成 & SQL 実行
        print("\n[3/4] 仮説を生成・検証中...")
        schema_info = build_data_context(db, parsed.target_table)
        hypotheses = HypothesisGenerator(llm, system_prompt, hypothesis_prompt).generate(
            parsed, schema_info
        )
        run_hypotheses(db, hypotheses)
        for h in hypotheses:
            print(f"      仮説{h.index}: {h.title[:50]}{'...' if len(h.title) > 50 else ''}")

        # Step 4: レポート生成
        print("\n[4/4] レポートを生成中...")
        rep_gen = ReportGenerator(llm, system_prompt, report_prompt)
        report = rep_gen.generate(parsed, hypotheses)
        output_path = rep_gen.save(report, args.output_dir)

        print(f"\n完了！ レポート: {output_path}\n")
        print("=" * 60)
        print(report)


if __name__ == "__main__":
    main()
