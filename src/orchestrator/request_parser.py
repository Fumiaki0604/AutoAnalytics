"""自然言語の分析依頼を構造化データに変換する。"""

import json
import re
from dataclasses import dataclass, field

from src.llm.llm_client import LLMClient, LLMMessage


@dataclass
class ParsedRequest:
    kpi: str
    period: str
    dimensions: list[str]
    target_table: str
    summary: str
    raw_request: str = ""


class RequestParser:
    """LLM を使って自然言語の依頼を ParsedRequest に変換する。

    LLM に JSON を返させ、コードで安全にパースする。
    JSON が壊れていた場合はフォールバック値を返す。
    """

    def __init__(self, llm: LLMClient, system_prompt: str) -> None:
        self.llm = llm
        self.system_prompt = system_prompt

    def parse(self, user_request: str, available_tables: list[str]) -> ParsedRequest:
        tables_str = ", ".join(available_tables)
        prompt = f"""以下の分析依頼を解析し、JSON のみを返してください（説明文は不要）。

利用可能なテーブル: {tables_str}

依頼:
{user_request}

返却する JSON の形式:
{{
  "kpi": "分析対象の指標（例: CVR, 売上, 離脱率）",
  "period": "分析期間（例: 直近30日, 2026年1月）",
  "dimensions": ["切り口1", "切り口2"],
  "target_table": "{available_tables[0] if available_tables else 'main_data'}",
  "summary": "依頼の一行要約"
}}"""

        response = self.llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            system=self.system_prompt,
        )

        return self._parse_json(response.content, user_request, available_tables)

    def _parse_json(
        self,
        text: str,
        raw_request: str,
        available_tables: list[str],
    ) -> ParsedRequest:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            data = json.loads(match.group()) if match else {}
        except json.JSONDecodeError:
            data = {}

        return ParsedRequest(
            kpi=data.get("kpi", "不明"),
            period=data.get("period", "不明"),
            dimensions=data.get("dimensions", []),
            target_table=data.get("target_table", available_tables[0] if available_tables else ""),
            summary=data.get("summary", raw_request[:80]),
            raw_request=raw_request,
        )
