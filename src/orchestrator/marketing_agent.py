"""マーケティングエージェント。

GA4分析結果を受け取り、書籍RAGから関連知見を検索して
マーケティング視点での提案を生成する。

Step 5: generate_marketing_advice  … データ × 書籍知見 → 観察点 + 解釈
Step 6: generate_action_proposals  … 観察点 → 即実行できる施策提案
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


def generate_marketing_advice(report_text: str) -> str:
    """Step 5: 書籍RAGを使ってデータに即したマーケティング観察点を生成する。

    「指摘」止まりではなく「なぜそれが問題/機会なのか」の解釈まで含める。
    """
    query = f"マーケティング戦略 顧客獲得 チャネル最適化: {report_text[:500]}"
    embedding = _embed_query(query)
    chunks = _search_docs(embedding)
    context = "\n\n---\n\n".join(chunks) if chunks else "（参考知見なし）"

    prompt = f"""あなたはエビデンスベースのマーケティング専門家です。
書籍の知見を参照しながら、GA4分析レポートに対するマーケティング視点での示唆を提供してください。

## 書籍からの知見
{context}

## GA4分析レポート
{report_text[:4000]}

## 出力ルール
- **マーケティング視点での重要観察点を3点**、Markdownの箇条書きで述べる
- 各観察点は「観察事実 → なぜそれが問題/機会なのか → どの方向に動くべきか」の3段構成にする
- 「〇〇が低い」という指摘だけで終わらず、「〇〇が低い → これは△△の機会を示している → □□という方向性が考えられる」まで踏み込む
- 書籍の知見をデータに当てはめて引用すること
- 日本語で回答
"""

    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_action_proposals(report_text: str, advice: str) -> str:
    """Step 6: マーケティング観察点をもとに即実行できる施策を提案する。

    「誰が・何を・いつ・どのくらいの効果」の形式で具体性を担保する。
    """
    query = f"施策実行 改善手順 キャンペーン設計: {report_text[:300]}"
    embedding = _embed_query(query)
    chunks = _search_docs(embedding)
    context = "\n\n---\n\n".join(chunks) if chunks else "（参考知見なし）"

    prompt = f"""あなたはマーケティング施策の実行専門家です。
以下のGA4分析レポートとマーケティング観察点をもとに、即実行できる具体的な施策提案を作成してください。

## GA4分析レポート（抜粋）
{report_text[:2000]}

## マーケティング観察点
{advice}

## 書籍からの実行知見
{context}

## 出力形式（以下のMarkdown形式を厳守）
施策を優先度順に2〜3件、下記の形式で提案してください。

### 施策N: [施策名]
**優先度**: 高 / 中 / 低
**対象セグメント/チャネル**: （例: Organicユーザー、メールリスト登録者 等）
**具体的なアクション**:
1. （手順1 — 誰が何をするか明記）
2. （手順2）
3. （手順3）
**期待効果**: （KPI名と目標改善幅の目安。例: CVR +10%、直帰率 -5pt）
**推奨担当**: （例: マーケ担当 / 開発チーム / 外部エージェンシー）
**実施目安**: （例: 2週間以内 / 来月の配信から）

---

## 出力ルール
- 「明日から実行できる」レベルの具体性を持たせること
- 書籍知見を各施策の根拠として1文引用すること
- 抽象的な提言（「改善すべき」「検討が必要」等）は禁止
- 日本語で回答
"""

    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# 後方互換: 旧エンドポイント /api/marketing-insight から呼ばれる場合用
def generate_marketing_insight(report_text: str) -> str:
    advice = generate_marketing_advice(report_text)
    proposals = generate_action_proposals(report_text, advice)
    return f"{advice}\n\n---\n\n## 具体的な施策提案\n\n{proposals}"
