"""仮説検証結果を受け取り、Markdown レポートを生成・保存する。"""

import re
from datetime import datetime
from pathlib import Path

from src.llm.llm_client import LLMClient, LLMMessage
from src.orchestrator.hypothesis_generator import Hypothesis
from src.orchestrator.request_parser import ParsedRequest


class ReportGenerator:
    """LLM を使って分析レポートを Markdown 形式で生成する。

    プロンプトテンプレートは prompts/report_prompt.md から読む。
    """

    def __init__(
        self,
        llm: LLMClient,
        system_prompt: str,
        report_prompt_template: str,
    ) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.template = report_prompt_template

    def generate(self, parsed: ParsedRequest, hypotheses: list[Hypothesis]) -> str:
        results_text = self._format_results(hypotheses)

        prompt = self.template.format(
            summary=parsed.summary,
            kpi=parsed.kpi,
            results=results_text,
            today=datetime.now().strftime("%Y年%m月%d日"),
        )

        response = self.llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            system=self.system_prompt,
        )

        return response.content

    def save(self, report: str, output_dir: str = "reports") -> Path:
        """レポートをファイルに保存し、パスを返す。"""
        out = Path(output_dir)
        out.mkdir(exist_ok=True)
        filename = out / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filename.write_text(report, encoding="utf-8")
        return filename

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def extract_summary_and_actions(report_md: str) -> tuple[str, list[str]]:
        """レポート Markdown からサマリと推奨アクション一覧を抽出する。"""
        # エグゼクティブサマリ セクション
        findings = ""
        summary_match = re.search(
            r"##\s*エグゼクティブサマリ[^\n]*\n(.*?)(?=\n##|\Z)",
            report_md,
            re.DOTALL,
        )
        if summary_match:
            findings = summary_match.group(1).strip()[:500]

        # 推奨アクション セクションの箇条書き
        actions: list[str] = []
        actions_match = re.search(
            r"##\s*推奨アクション[^\n]*\n(.*?)(?=\n##|\Z)",
            report_md,
            re.DOTALL,
        )
        if actions_match:
            for line in actions_match.group(1).splitlines():
                line = re.sub(r"^[\s\-\d\.\*]+", "", line).strip()
                if line:
                    actions.append(line[:100])

        return findings, actions[:5]

    def _format_results(self, hypotheses: list[Hypothesis]) -> str:
        sections = []
        for h in hypotheses:
            section = f"### 仮説{h.index}: {h.title}\n"
            if h.description:
                section += f"{h.description}\n\n"
            if h.sql:
                section += f"```sql\n{h.sql}\n```\n\n"
            section += f"**検証結果:**\n{h.result or '結果なし'}"
            sections.append(section)
        return "\n\n".join(sections)
