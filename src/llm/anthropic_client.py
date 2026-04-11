"""Anthropic API を使った LLMClient 実装。プロンプトキャッシュを有効化。"""

from pathlib import Path
from typing import Optional

import anthropic
import yaml

from src.llm.llm_client import LLMClient, LLMMessage, LLMResponse

_DEFAULT_CONFIG = Path(__file__).parents[2] / "config" / "llm_config.yaml"


class AnthropicClient(LLMClient):
    """claude-* モデルを呼び出す LLMClient 実装。

    system プロンプトには自動で ephemeral キャッシュを付与し、
    繰り返し呼び出し時のコストを削減する。
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        path = Path(config_path) if config_path else _DEFAULT_CONFIG
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から読む
        self.model: str = cfg["model"]
        self.max_tokens: int = cfg["max_tokens"]

    def complete(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
    ) -> LLMResponse:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": api_messages,
        }

        # system プロンプトをキャッシュ対象ブロックとして渡す
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        response = self.client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
