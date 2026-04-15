"""自律プロンプト改善ループ CLI。

Usage:
    python -m src.review_prompt [--dry-run] [--rollback report_prompt|hypothesis_prompt]

オプション:
    --dry-run           改善案を表示するだけでプロンプトを上書きしない
    --rollback <name>   指定プロンプトを1世代前に戻す（最後の改善を取り消す）

動作:
1. reports/ ディレクトリの直近3件のレポートを読み込む
2. Reviewer LLM が品質問題を列挙する
3. PromptEngineer LLM が report_prompt.md / hypothesis_prompt.md を改善する
4. 改善済みプロンプトを Supabase prompt_versions に保存し、ローカルファイルを上書きする
"""

import argparse
import sys
from pathlib import Path

from src.orchestrator.prompt_reviewer import PromptReviewer
from src.storage.prompt_store import (
    get_latest_prompt,
    list_versions,
    rollback_prompt,
    save_prompt_version,
)

REPORTS_DIR = Path("reports")
PROMPT_NAMES = ["report_prompt", "hypothesis_prompt"]
PROMPT_FILES = {
    "report_prompt": Path("prompts/report_prompt.md"),
    "hypothesis_prompt": Path("prompts/hypothesis_prompt.md"),
}
MAX_REPORTS = 3


def load_recent_reports(n: int = MAX_REPORTS) -> list[str]:
    """reports/ から最新 N 件の Markdown を読み込む。"""
    if not REPORTS_DIR.exists():
        return []
    files = sorted(REPORTS_DIR.glob("*.md"), reverse=True)[:n]
    return [f.read_text(encoding="utf-8") for f in files]


def load_current_prompt(name: str) -> str:
    """ローカルファイルからプロンプトを読む。"""
    path = PROMPT_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def do_rollback(name: str) -> None:
    """指定プロンプトを1世代前に戻す。"""
    versions = list_versions(name, limit=2)
    if len(versions) < 2:
        print(f"  ⚠ {name}: ロールバック可能な履歴がありません（バージョン数: {len(versions)}）")
        return

    old_content = rollback_prompt(name, steps=1)
    if old_content:
        print(f"  ✅ {name} を1世代前に戻しました")
    else:
        print(f"  ⚠ {name}: ロールバック失敗")


def main() -> None:
    parser = argparse.ArgumentParser(description="自律プロンプト改善ループ")
    parser.add_argument("--dry-run", action="store_true", help="上書きせず改善案のみ表示")
    parser.add_argument(
        "--rollback",
        choices=PROMPT_NAMES,
        metavar="PROMPT_NAME",
        help=f"1世代前に戻す ({', '.join(PROMPT_NAMES)})",
    )
    args = parser.parse_args()

    # ── ロールバックモード ──────────────────────────────────────────
    if args.rollback:
        print(f"\n⏪ ロールバック: {args.rollback}")
        do_rollback(args.rollback)
        sys.exit(0)

    # ── 通常の改善ループ ────────────────────────────────────────────
    print("\n📋 直近レポートを読み込み中...")
    reports = load_recent_reports()
    if not reports:
        print(f"  ⚠ {REPORTS_DIR}/ にレポートが見つかりません。先に分析を実行してください。")
        sys.exit(1)
    print(f"  {len(reports)} 件のレポートを読み込みました")

    reviewer = PromptReviewer()

    print("\n🔍 Reviewer: レポートを審査中...")
    feedback = reviewer.review(reports)
    print("\n--- レビュー結果 ---")
    print(feedback.raw)
    print("-------------------")

    if feedback.is_empty:
        print("\n✅ 品質上の問題は検出されませんでした。プロンプトの更新はスキップします。")
        sys.exit(0)

    # 各プロンプトを改善
    for name in PROMPT_NAMES:
        print(f"\n✏️  PromptEngineer: {name} を改善中...")
        try:
            current = load_current_prompt(name)
        except FileNotFoundError as e:
            print(f"  ⚠ {e}")
            continue

        improved = reviewer.improve_prompt(name, current, feedback)

        # 差分サマリ表示
        before_lines = len(current.splitlines())
        after_lines = len(improved.splitlines())
        print(f"  変更: {before_lines} 行 → {after_lines} 行")

        if args.dry_run:
            print(f"\n  [DRY RUN] {name} 改善案:")
            print("  " + "\n  ".join(improved.splitlines()[:30]))
            if after_lines > 30:
                print(f"  ... （残り {after_lines - 30} 行は省略）")
        else:
            save_prompt_version(name, improved, review_feedback=feedback.raw)
            print(f"  ✅ {name} を更新しました（Supabase + ローカルファイル）")

    if not args.dry_run:
        print("\n🎉 プロンプト改善完了。ロールバックは --rollback <name> で実行できます。")


if __name__ == "__main__":
    main()
