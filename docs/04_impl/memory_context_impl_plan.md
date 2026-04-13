# 実装計画書：memory.md コンテキスト層

## 概要

分析履歴を Supabase に蓄積し、次回の仮説生成プロンプトに過去の発見を注入することで、
分析の連続性と品質を向上させる。

---

### 担当凡例

| 記号 | 担当者 | 説明 |
|------|--------|------|
| 👤 | 人間 | 外部サービス設定、手動確認 |
| 🤖 | AI (Claude Code) | コーディング、テスト実行 |
| 👤+🤖 | 共同 | AIが実行し、人間が確認・承認 |

### 状態凡例

| 記号 | 状態 |
|------|------|
| ⏳ | 未着手 |
| 🚧 | 進行中 |
| ✅ | 完了 |

---

### フェーズ一覧

| Phase | 名称 | 主な担当 | 目標 | 状態 |
|-------|------|---------|------|------|
| 0 | Supabase テーブル作成 | 👤 | `analysis_memory` テーブルを用意する | ⏳ |
| 1 | MemoryStore 実装 | 🤖 | 保存・取得の共通クラスを作る | ⏳ |
| 2 | メモリ保存フロー | 🤖 | 分析完了時に自動保存する | ⏳ |
| 3 | メモリ注入フロー | 🤖 | 仮説生成プロンプトに過去発見を注入する | ⏳ |
| 4 | 動作確認・デプロイ | 👤+🤖 | 本番で end-to-end 確認する | ⏳ |

---

## Phase 0: Supabase テーブル作成 ⏳

**目標**: `analysis_memory` テーブルを Supabase に作成する
**担当**: 👤

### 0.1 テーブル作成 (👤)

**Step 1: Supabase SQL エディタにアクセス**
1. https://supabase.com/dashboard にアクセスしてログイン
2. 対象プロジェクトを選択
3. 左メニュー「SQL Editor」をクリック
4. 「New query」をクリック
5. 以下の SQL を貼り付けて「Run」をクリック

```sql
create table analysis_memory (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  property_id text not null default 'csv',
  kpi         text,
  request_summary text,
  findings    text,
  actions     text[],
  created_at  timestamptz not null default now()
);

-- email + property_id で新しい順に取得するためのインデックス
create index idx_analysis_memory_user
  on analysis_memory (email, property_id, created_at desc);
```

**Step 2: 作成確認**
1. 左メニュー「Table Editor」をクリック
2. `analysis_memory` テーブルが表示されることを確認

### Phase 0 完了条件

- [ ] `analysis_memory` テーブルが Supabase に存在する (👤)
- [ ] 全カラム・インデックスが正しく作成されている (👤)

---

## Phase 1: MemoryStore 実装 ⏳

**目標**: 分析メモリの保存・取得を担う `MemoryStore` クラスを実装する
**担当**: 🤖

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 1.1 | `src/storage/memory_store.py` を作成 | 🤖 | save / get 関数が動作する | ⏳ |
| 1.2 | 動作確認（単体テスト相当） | 🤖 | Supabase に書き込み・読み込みできる | ⏳ |

### 1.1 実装内容 (🤖)

**作成ファイル**: `src/storage/memory_store.py`

```python
# 実装するインターフェース（参考）

def save_memory(
    email: str,
    property_id: str,  # GA4 property ID or "csv"
    kpi: str,
    request_summary: str,
    findings: str,      # レポートから抽出した発見サマリ
    actions: list[str], # 推奨アクション一覧
) -> None:
    """分析結果を Supabase に保存する。"""

def get_recent_memories(
    email: str,
    property_id: str,
    limit: int = 3,
) -> list[dict]:
    """直近 N 件の分析メモリを返す。"""
```

### Phase 1 完了条件

- [ ] `src/storage/memory_store.py` が存在する (🤖)
- [ ] `save_memory()` が Supabase に書き込める (🤖)
- [ ] `get_recent_memories()` が正しい順序で返せる (🤖)

---

## Phase 2: メモリ保存フロー ⏳

**目標**: 分析完了後に自動でメモリを Supabase に保存する
**担当**: 🤖

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 2.1 | `ReportGenerator.generate()` の戻り値からサマリ・推奨アクションを抽出するヘルパーを追加 | 🤖 | Markdown レポートから findings / actions を抽出できる | ⏳ |
| 2.2 | `app.py` の `_run_analysis` / `_run_ga4_analysis` に保存処理を追加 | 🤖 | Step 4 完了後に `save_memory()` が呼ばれる | ⏳ |
| 2.3 | `email` をスレッドランナーに渡す | 🤖 | セッションから email を取得して渡せる | ⏳ |

### 2.1 実装ポイント (🤖)

`report_generator.py` に以下のヘルパーを追加する。

```python
# 実装方針（参考）
def extract_summary_and_actions(report_md: str) -> tuple[str, list[str]]:
    """
    生成済みレポート Markdown から
    - findings: ## エグゼクティブサマリ セクションの本文
    - actions : ## 推奨アクション セクションの箇条書き
    を抽出して返す。
    """
```

### 2.2 実装ポイント (🤖)

`app.py` の変更箇所：
- `_run_analysis(... email: str ...)` にパラメータ追加
- `_run_ga4_analysis(... email: str ...)` にパラメータ追加
- Step 4 完了後に `save_memory(email, property_id, ...)` を呼ぶ
- CSV 分析の場合は `property_id="csv"` を渡す

### Phase 2 完了条件

- [ ] GA4 分析後に `analysis_memory` テーブルにレコードが追加される (👤+🤖)
- [ ] CSV 分析後も同様に保存される (🤖)
- [ ] `property_id`, `email`, `findings`, `actions` が正しく入っている (👤)

---

## Phase 3: メモリ注入フロー ⏳

**目標**: 仮説生成プロンプトに過去の分析発見を注入し、前回比較・継続分析を可能にする
**担当**: 🤖

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 3.1 | `hypothesis_prompt.md` に `{past_context}` プレースホルダを追加 | 🤖 | テンプレートが更新されている | ⏳ |
| 3.2 | `HypothesisGenerator.generate()` に `past_context` 引数を追加 | 🤖 | メモリを受け取ってプロンプトに注入できる | ⏳ |
| 3.3 | `app.py` で `get_recent_memories()` を呼んで渡す | 🤖 | 分析ごとに直近 3 件のメモリが注入される | ⏳ |
| 3.4 | メモリが 0 件のとき（初回分析）は「過去履歴なし」と表示 | 🤖 | KeyError / 空文字エラーが出ない | ⏳ |

### 3.1 プロンプト変更ポイント (🤖)

`prompts/hypothesis_prompt.md` の先頭に以下を追加：

```markdown
## 過去の分析コンテキスト
{past_context}

---
```

`past_context` の内容（メモリがある場合）：

```
【直近の分析履歴】
- 2026年4月13日 分析: CVR低下の原因調査（Direct チャネルの流入増が主因）
  推奨アクション: Direct チャネルのLPO改善、広告プレイスメント見直し
- 2026年4月10日 分析: ...
```

### 3.2 実装ポイント (🤖)

`hypothesis_generator.py` の変更：

```python
def generate(
    self,
    parsed: ParsedRequest,
    data_context: str,
    past_context: str = "",   # ← 追加
) -> list[Hypothesis]:
    prompt = self.template.format(
        ...
        past_context=past_context or "（過去の分析履歴なし）",
    )
```

### Phase 3 完了条件

- [ ] 初回分析時に「過去の分析履歴なし」が表示される (🤖)
- [ ] 2 回目以降の分析で前回の発見がプロンプトに含まれる (👤+🤖)
- [ ] LLM が「前回〜だったが、今回は〜」という形で仮説を立てる (👤)

---

## Phase 4: 動作確認・デプロイ ⏳

**目標**: Render 本番環境で end-to-end 動作を確認する
**担当**: 👤+🤖

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 4.1 | `git push` して Render に自動デプロイ | 🤖 | デプロイ成功 | ⏳ |
| 4.2 | GA4 分析を 1 回実行し、Supabase にメモリが保存されることを確認 | 👤 | `analysis_memory` テーブルにレコードあり | ⏳ |
| 4.3 | 同じプロパティで 2 回目の分析を実行し、過去コンテキストが反映されていることを確認 | 👤 | レポートに前回分析への言及がある | ⏳ |

### 4.2 確認手順 (👤)

**Step 1: Supabase でレコード確認**
1. https://supabase.com/dashboard にアクセス
2. 対象プロジェクト → 「Table Editor」→ `analysis_memory` テーブルを開く
3. 分析後にレコードが 1 件追加されていることを確認
4. `email`, `findings`, `actions` に値が入っていることを確認

**トラブルシューティング**:

| 症状 | 原因 | 対処 |
|------|------|------|
| レコードが保存されない | `email` が session から取れていない | `app.py` で `session.get("email")` の値をログ確認 |
| `{past_context}` が KeyError | prompt テンプレートに `{past_context}` が未追加 | `hypothesis_prompt.md` を確認 |
| 2 回目も「過去履歴なし」 | `property_id` の不一致 | CSV は `"csv"` 固定、GA4 は property_id が一致しているか確認 |

### Phase 4 完了条件

- [ ] Render デプロイが成功する (🤖)
- [ ] Supabase の `analysis_memory` にレコードが保存される (👤)
- [ ] 2 回目の分析レポートに前回の発見への言及がある (👤)

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/storage/memory_store.py` | 新規作成（保存・取得） |
| `src/orchestrator/report_generator.py` | `extract_summary_and_actions()` 追加 |
| `src/orchestrator/hypothesis_generator.py` | `generate()` に `past_context` 引数追加 |
| `src/api/app.py` | メモリ保存・取得の呼び出し追加 |
| `prompts/hypothesis_prompt.md` | `{past_context}` セクション追加 |
| Supabase（👤） | `analysis_memory` テーブル作成 |
