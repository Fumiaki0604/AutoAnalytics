"""マーケティングエージェント。

GA4分析結果を受け取り、書籍RAGから関連知見を検索して
マーケティング視点での提案を生成する。
"""

import json
import os

import httpx
from openai import OpenAI

import anthropic

_anthropic = anthropic.Anthropic()
_openai = OpenAI()

_SUPABASE_URL = os.environ["SUPABASE_URL"]
_SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
_HEADERS = {
    "apikey": _SUPABASE_KEY,
    "Authorization": f"Bearer {_SUPABASE_KEY}",
    "Content-Type": "application/json",
}

EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5  # 取得するチャンク数


def _embed_query(text: str) -> list[float]:
    response = _openai.embeddings.create(model=EMBED_MODEL, input=[text])
    return response.data[0].embedding


def _search_docs(query_embedding: list[float], top_k: int = TOP_K) -> list[str]:
    """Supabase pgvectorで類似チャンクを検索。"""
    res = httpx.post(
        f"{_SUPABASE_URL}/rest/v1/rpc/match_marketing_docs",
        headers=_HEADERS,
        content=json.dumps({
            "query_embedding": query_embedding,
            "match_count": top_k,
        }),
        timeout=15,
    )
    if res.status_code != 200:
        return []
    return [row["content"] for row in res.json()]


def generate_marketing_insight(report_text: str) -> str:
    """
    分析レポートを受け取り、マーケティング視点の提案を返す。

    Args:
        report_text: GA4分析レポートのテキスト

    Returns:
        マーケティング提案テキスト
    """
    # レポート全体をクエリとして使いつつ、要約して検索
    query = f"マーケティング戦略 顧客獲得 チャネル最適化: {report_text[:500]}"
    embedding = _embed_query(query)
    chunks = _search_docs(embedding)

    if not chunks:
        return "（マーケティング知見のデータが見つかりませんでした）"

    context = "\n\n---\n\n".join(chunks)

    prompt = f"""あなたはエビデンスベースのマーケティング専門家です。
以下の「書籍からの知見」を参照しながら、「GA4分析レポート」に対してマーケティング視点での示唆・提案を提供してください。

## 書籍からの知見
{context}

## GA4分析レポート（要約）
{report_text[:2000]}

## 指示
- 書籍の知見をGA4データの文脈に当てはめて解釈してください
- 抽象論ではなく、このデータに即した具体的な提案を3点以内で述べてください
- 書籍の知見を引用する場合は「エビデンスより：」と前置きしてください
- 日本語で回答してください
"""

    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
