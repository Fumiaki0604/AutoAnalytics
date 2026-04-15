"""LLM が生成した SQL を実行前に検証・サニタイズする。

責務:
- SELECT / WITH 以外の書き込み系 SQL を拒否
- 危険なキーワードをブロック
- LIMIT が未指定の場合は自動付与（デフォルト 100 行）
- 参照テーブルをセッションでロード済みのテーブルに制限（ベストエフォート）
"""

import re


class SQLValidationError(Exception):
    """SQL バリデーション失敗時に送出する例外。"""
    pass


# 実行を拒否するキーワード
_BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "MERGE", "EXEC", "EXECUTE",
    "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT",
]

_DEFAULT_LIMIT = 100


def validate_and_sanitize(
    sql: str,
    allowed_tables: list[str],
    default_limit: int = _DEFAULT_LIMIT,
) -> str:
    """SQL を検証し、安全であればサニタイズ済みの SQL を返す。

    Args:
        sql: LLM が生成した SQL 文字列
        allowed_tables: このセッションでロード済みのテーブル名リスト
        default_limit: LIMIT 未指定時に自動付与する行数

    Returns:
        サニタイズ済み SQL

    Raises:
        SQLValidationError: 安全でない SQL が検出された場合
    """
    if not sql or not sql.strip():
        raise SQLValidationError("SQL が空です")

    normalized = sql.strip()

    # --- 0. インラインコメント（-- ...）を除去 ---
    # LLM が先頭行にコメントを生成するケースに対応。DuckDB は -- をネイティブサポートするが
    # バリデーションの誤検知を防ぐため除去してから検証・実行する。
    normalized = re.sub(r"--[^\n]*", "", normalized).strip()
    upper = normalized.upper()

    # --- 1. SELECT / WITH のみ許可 ---
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        first_word = upper.split()[0] if upper.split() else ""
        raise SQLValidationError(
            f"SELECT / WITH 以外の SQL は実行できません（検出: {first_word}）"
        )

    # --- 2. 危険キーワードをブロック ---
    for kw in _BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SQLValidationError(
                f"危険なキーワードが含まれています: {kw}"
            )

    # --- 3. 参照テーブルをセッションテーブルに制限（ベストエフォート）---
    if allowed_tables:
        # FROM / JOIN の後に続くトークンをテーブル名候補として抽出
        referenced = set(
            re.findall(r"(?:FROM|JOIN)\s+\"?(\w+)\"?", upper)
        )
        # サブクエリ名・CTE 名は許容（WITH/カンマ区切りすべてを取得）
        cte_names = set(re.findall(r"(?:WITH|,)\s*(\w+)\s+AS\s*\(", upper))
        unknown = referenced - {t.upper() for t in allowed_tables} - cte_names
        if unknown:
            raise SQLValidationError(
                f"このセッションで未ロードのテーブルを参照しています: {', '.join(unknown)}"
            )

    # --- 4. LIMIT が未指定なら自動付与 ---
    if "LIMIT" not in upper:
        normalized = normalized.rstrip().rstrip(";")
        normalized = f"{normalized}\nLIMIT {default_limit};"

    return normalized
