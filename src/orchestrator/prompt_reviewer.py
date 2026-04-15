"""自律プロンプト改善ループ。

2段階LLM:
1. Reviewer  : 直近レポートを読み、品質上の問題点を列挙する
2. PromptEngineer : 問題点 + 現在のプロンプトを受け取り、改善案を出力する
"""

from dataclasses import dataclass

from src.llm.anthropic_client import AnthropicClient
from src.llm.llm_client import LLMMessage

# --------------------------------------------------------------------------
# Reviewer プロンプト
# --------------------------------------------------------------------------

_REVIEWER_SYSTEM = """あなたはデータ分析レポートの品質審査員です。
与えられたレポート群を読み、以下の評価基準で問題点を日本語で列挙してください。

【評価基準】
1. エグゼクティブサマリーが3文以内に収まっているか
2. 仮説ごとに独立した ### 仮説N 節が設けられているか（複数仮説がある場合）
3. 変化率だけでなく絶対数も観測事実に記載されているか
4. 推奨アクションに担当ロール・期限のイメージが含まれているか
5. 未確定事項セクションで前年同期比データの欠如理由が説明されているか（前年比データがない場合）
6. 全仮説が展開されているか（途中で省略されていないか）

出力形式:
## 問題点
- （問題があった評価基準の番号と具体的な記述）

## 改善の方向性
- （プロンプト側でどう指示すれば改善できるか）
"""

_REVIEWER_USER_TEMPLATE = """以下の直近 {count} 件のレポートを審査してください。

{reports}
"""

# --------------------------------------------------------------------------
# PromptEngineer プロンプト
# --------------------------------------------------------------------------

_ENGINEER_SYSTEM = """あなたはLLMプロンプトエンジニアです。
レビューアーの指摘を踏まえ、現在のプロンプトを改善した新しいプロンプトを出力してください。

制約:
- 元のプロンプトの構造・変数プレースホルダ（{...}形式）を必ず維持すること
- 追加・変更したルールは既存ルールと矛盾しないこと
- 出力は改善後のプロンプト全文のみとし、説明文や前置きは一切含めないこと
- 過剰に長くしない。必要最小限の追記・修正にとどめること
"""

_ENGINEER_USER_TEMPLATE = """## レビューアーの指摘

{feedback}

## 現在のプロンプト（{prompt_name}）

{current_prompt}

上記の指摘を反映した改善後のプロンプト全文を出力してください。"""


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------

@dataclass
class ReviewFeedback:
    raw: str          # Reviewer の出力（Markdown）
    is_empty: bool    # 問題なしと判断された場合 True


# --------------------------------------------------------------------------
# Main class
# --------------------------------------------------------------------------

class PromptReviewer:
    """2段階LLMによるプロンプト自動改善を実行する。"""

    def __init__(self) -> None:
        self.llm = AnthropicClient()

    # ------------------------------------------------------------------
    # Stage 1: Review
    # ------------------------------------------------------------------

    def review(self, reports: list[str]) -> ReviewFeedback:
        """レポート群を審査して問題点フィードバックを返す。"""
        if not reports:
            return ReviewFeedback(raw="（レポートがありません）", is_empty=True)

        joined = "\n\n---\n\n".join(
            f"### レポート {i+1}\n{r}" for i, r in enumerate(reports)
        )
        user_msg = _REVIEWER_USER_TEMPLATE.format(count=len(reports), reports=joined)

        response = self.llm.complete(
            messages=[LLMMessage(role="user", content=user_msg)],
            system=_REVIEWER_SYSTEM,
        )
        raw = response.content.strip()

        # 問題点がなければ is_empty=True
        is_empty = "問題点" not in raw or "なし" in raw[:200]
        return ReviewFeedback(raw=raw, is_empty=is_empty)

    # ------------------------------------------------------------------
    # Stage 2: Improve
    # ------------------------------------------------------------------

    def improve_prompt(
        self,
        prompt_name: str,
        current_prompt: str,
        feedback: ReviewFeedback,
    ) -> str:
        """フィードバックを反映した改善済みプロンプトを返す。"""
        user_msg = _ENGINEER_USER_TEMPLATE.format(
            feedback=feedback.raw,
            prompt_name=prompt_name,
            current_prompt=current_prompt,
        )
        response = self.llm.complete(
            messages=[LLMMessage(role="user", content=user_msg)],
            system=_ENGINEER_SYSTEM,
        )
        return response.content.strip()
