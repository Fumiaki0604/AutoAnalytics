"""LLM を使って分析仮説を生成し、SQL を抽出する。"""

import re
from dataclasses import dataclass, field

from src.llm.llm_client import LLMClient, LLMMessage
from src.orchestrator.request_parser import ParsedRequest


# SQL 実行後に設定されるステータス
# supported  : 結果が得られ、仮説を支持するデータがある
# no_data    : SQL は成功したが結果が 0 行だった
# error      : SQL 実行エラー（バリデーション含む）
# no_sql     : SQL が生成されなかった
HypothesisStatus = str


@dataclass
class Hypothesis:
    index: int
    title: str
    description: str
    sql: str
    result: str = ""
    status: HypothesisStatus = "pending"


class HypothesisGenerator:
    """LLM に仮説を生成させ、SQL コードブロックを抽出する。

    プロンプトテンプレートは prompts/hypothesis_prompt.md から読む。
    """

    def __init__(
        self,
        llm: LLMClient,
        system_prompt: str,
        hypothesis_prompt_template: str,
    ) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.template = hypothesis_prompt_template

    def generate(
        self,
        parsed: ParsedRequest,
        data_context: str,
        past_context: str = "（過去の分析履歴なし）",
        corrections_context: str = "（過去のSQLエラー履歴なし）",
    ) -> list[Hypothesis]:
        prompt = self.template.format(
            summary=parsed.summary,
            kpi=parsed.kpi,
            dimensions=", ".join(parsed.dimensions) if parsed.dimensions else "指定なし",
            table=parsed.target_table,
            data_context=data_context,
            past_context=past_context,
            corrections_context=corrections_context,
        )

        response = self.llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            system=self.system_prompt,
        )

        return self._extract_hypotheses(response.content)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_hypotheses(self, text: str) -> list[Hypothesis]:
        """LLM レスポンスから番号付き仮説ブロックを抽出する。"""
        # 番号（1. / 1） のいずれか）を区切りとしてブロック分割
        blocks = re.split(r"\n(?=\d+[\.\)]\s)", text.strip())

        hypotheses: list[Hypothesis] = []
        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue

            lines = block.splitlines()
            # 先頭行をタイトルとして取得（番号部分を除去）
            title = re.sub(r"^\d+[\.\)]\s*", "", lines[0]).strip()

            # 説明文（SQL ブロック前まで）
            desc_lines = []
            for line in lines[1:]:
                if line.strip().startswith("```"):
                    break
                desc_lines.append(line)
            description = "\n".join(desc_lines).strip()

            # SQL ブロックを抽出
            sql_match = re.search(r"```(?:sql)?\n(.*?)```", block, re.DOTALL | re.IGNORECASE)
            sql = sql_match.group(1).strip() if sql_match else ""

            hypotheses.append(
                Hypothesis(
                    index=i + 1,
                    title=title,
                    description=description,
                    sql=sql,
                )
            )

        return hypotheses
