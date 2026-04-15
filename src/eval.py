"""プロンプト品質の回帰テスト（固定テストケース）。

Usage:
    python -m src.eval

テストケースは eval/cases/ に YAML で定義する。
各テストケースで以下をチェックする:
- 仮説が 3 件以上生成されるか
- SQL 成功率が閾値以上か
- レポートの必須セクションが揃っているか
"""

import sys
from pathlib import Path
from typing import Any

import yaml

from src.adapters.csv_adapter import CSVAdapter
from src.llm.anthropic_client import AnthropicClient
from src.orchestrator.hypothesis_generator import HypothesisGenerator
from src.orchestrator.report_generator import ReportGenerator
from src.orchestrator.request_parser import RequestParser
from src.storage.duckdb_client import DuckDBClient
from src.storage.sql_validator import SQLValidationError, validate_and_sanitize

CASES_DIR = Path("eval/cases")
REQUIRED_SECTIONS = [
    "エグゼクティブサマリ",
    "仮説と検証結果",
    "推奨アクション",
]


def load_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def fmt_result(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "（結果なし）"
    headers = list(rows[0].keys())
    lines = [" | ".join(headers)]
    for row in rows[:5]:
        lines.append(" | ".join(str(v) for v in row.values()))
    return "\n".join(lines)


def run_case(case: dict, system_prompt: str, hypothesis_prompt: str, report_prompt: str) -> dict:
    """1テストケースを実行してスコアを返す。"""
    csv_path = case["csv"]
    request_text = case["request"]
    min_sql_success_rate = case.get("min_sql_success_rate", 0.5)

    result = {
        "name": case["name"],
        "passed": False,
        "hypothesis_count": 0,
        "sql_success": 0,
        "sql_error": 0,
        "sql_no_data": 0,
        "sql_no_sql": 0,
        "sql_success_rate": 0.0,
        "missing_sections": [],
        "errors": [],
    }

    try:
        llm = AnthropicClient()

        with DuckDBClient(":memory:") as db:
            CSVAdapter(db).load(csv_path, "main_data")

            parsed = RequestParser(llm, system_prompt).parse(request_text, db.list_tables())
            context = db.get_data_context(parsed.target_table)
            hypotheses = HypothesisGenerator(llm, system_prompt, hypothesis_prompt).generate(
                parsed, context
            )

            result["hypothesis_count"] = len(hypotheses)
            if len(hypotheses) < 3:
                result["errors"].append(f"仮説数が少ない: {len(hypotheses)} 件（3 件以上必要）")

            allowed_tables = db.list_tables()
            for h in hypotheses:
                if not h.sql:
                    h.status = "no_sql"
                    result["sql_no_sql"] += 1
                    continue
                try:
                    rows = db.query(validate_and_sanitize(h.sql, allowed_tables))
                    if rows:
                        h.result = fmt_result(rows)
                        h.status = "supported"
                        result["sql_success"] += 1
                    else:
                        h.result = "（該当データなし）"
                        h.status = "no_data"
                        result["sql_no_data"] += 1
                except (SQLValidationError, Exception) as e:
                    h.result = f"エラー: {e}"
                    h.status = "error"
                    result["sql_error"] += 1

            total_with_sql = result["hypothesis_count"] - result["sql_no_sql"]
            if total_with_sql > 0:
                result["sql_success_rate"] = result["sql_success"] / total_with_sql
            if result["sql_success_rate"] < min_sql_success_rate:
                result["errors"].append(
                    f"SQL 成功率が低い: {result['sql_success_rate']:.0%}（閾値 {min_sql_success_rate:.0%}）"
                )

            rep_gen = ReportGenerator(llm, system_prompt, report_prompt)
            report = rep_gen.generate(parsed, hypotheses)

            for section in REQUIRED_SECTIONS:
                if section not in report:
                    result["missing_sections"].append(section)
            if result["missing_sections"]:
                result["errors"].append(f"必須セクションが欠落: {result['missing_sections']}")

    except Exception as e:
        result["errors"].append(f"実行エラー: {e}")

    result["passed"] = len(result["errors"]) == 0
    return result


def main() -> None:
    system_prompt = load_prompt("prompts/system_prompt.md")
    hypothesis_prompt = load_prompt("prompts/hypothesis_prompt.md")
    report_prompt = load_prompt("prompts/report_prompt.md")

    case_files = sorted(CASES_DIR.glob("*.yaml")) if CASES_DIR.exists() else []
    if not case_files:
        print("テストケースが見つかりません。eval/cases/*.yaml を作成してください。")
        sys.exit(1)

    results = []
    for f in case_files:
        case = yaml.safe_load(f.read_text(encoding="utf-8"))
        print(f"\n▶ {case['name']} ...", end=" ", flush=True)
        r = run_case(case, system_prompt, hypothesis_prompt, report_prompt)
        results.append(r)
        print("✅ PASS" if r["passed"] else "❌ FAIL")
        print(f"   仮説: {r['hypothesis_count']} 件 / SQL成功率: {r['sql_success_rate']:.0%}"
              f" (成功:{r['sql_success']} エラー:{r['sql_error']} データなし:{r['sql_no_data']})")
        for e in r["errors"]:
            print(f"   ⚠ {e}")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n{'='*50}")
    print(f"結果: {passed}/{total} PASS")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
