"""抽象LLMクライアント。LLM実装を差し替え可能にするためのインターフェース定義。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMMessage:
    role: str   # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int


class LLMClient(ABC):
    """LLMバックエンドの抽象基底クラス。Anthropic / Bedrock 等に差し替え可能。"""

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
    ) -> LLMResponse:
        """メッセージリストを受け取り、LLMのレスポンスを返す。"""
        pass
