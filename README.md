# AutoAnalytics

自然言語で分析依頼を投げると、CSV / GA4 データを DuckDB に取り込み、仮説生成・SQL 検証・Markdown レポート出力までを半自動化する分析エージェント PoC。

Anthropic API（Claude）を LLM 基盤、DuckDB を軽量分析基盤として採用しており、特定の DWH に依存しない設計になっています。

---

## デモ

**https://autoanalytics.onrender.com**

---

## 特徴

- **自然言語で依頼** — 「CVR が先月比で低下している。チャネル別・デバイス別に原因を探りたい」のように日本語で入力
- **CSV / GA4 対応** — CSV アップロードまたは Google Analytics 4 プロパティを直接指定してデータ取得
- **仮説を自動生成** — LLM が 3 本以上の検証可能な仮説を生成し、DuckDB 上で SQL を実行
- **SQL 安全化** — SELECT/WITH 以外のクエリは実行拒否。未ロードテーブルへの参照もブロック
- **リアルタイム進捗** — ブラウザ上で 4 ステップの進捗を SSE でストリーミング表示
- **Markdown レポート出力** — 仮説ごとに支持/棄却の判定とビジネス示唆を含むレポートを生成・ダウンロード可能
- **Google OAuth 認証** — Google アカウントでログイン。自分の GA4 プロパティのみアクセス可能
- **マルチインスタンス対応** — Supabase でセッション永続化。Render のスケールアウト環境でも動作

---

## システム構成

```
自然言語の依頼
  ↓
Web UI（ブラウザ） ← Google OAuth（Supabase セッション管理）
  ↓
FastAPI + SSE
  ↓
Analysis Orchestrator
  ├─ RequestParser       — 依頼を KPI・期間・切り口に構造化
  ├─ HypothesisGenerator — 仮説生成 + SQL 抽出
  └─ ReportGenerator     — Markdown レポート生成
  ↓
CSV Adapter / GA4 Adapter → DuckDB
  ↓
SQL Validator → SQL 実行
  ↓
Markdown Report
```

---

## 技術スタック

| 役割 | 技術 |
|---|---|
| LLM | Anthropic API（claude-sonnet-4-6） |
| 分析基盤 | DuckDB |
| バックエンド | FastAPI + uvicorn |
| フロントエンド | Vanilla JS（依存ゼロ） |
| データ処理 | pandas / pyarrow |
| データソース | CSV / Google Analytics 4 Data API |
| 認証 | Google OAuth 2.0 |
| セッション管理 | Supabase |
| ホスティング | Render |

---

## セットアップ

### 前提条件

- Python 3.11 以上
- Anthropic API キー（[console.anthropic.com](https://console.anthropic.com/settings/keys) で取得）
- Google Cloud OAuth クライアント（GA4 連携・ログインに必要）
- Supabase プロジェクト（セッション永続化に必要）

### インストール

```bash
git clone https://github.com/Fumiaki0604/AutoAnalytics.git
cd AutoAnalytics

pip install -r requirements.txt

cp .env.example .env
# .env を編集して各種キーを設定
```

### 必要な環境変数

```bash
ANTHROPIC_API_KEY=        # Anthropic API キー
GOOGLE_CLIENT_ID=         # Google Cloud OAuth クライアントID
GOOGLE_CLIENT_SECRET=     # Google Cloud OAuth クライアントシークレット
SUPABASE_URL=             # Supabase プロジェクト URL
SUPABASE_SERVICE_ROLE_KEY= # Supabase service_role キー
APP_BASE_URL=             # 本番URL（例: https://autoanalytics.onrender.com）
```

### Supabase テーブル作成

```sql
create table sessions (
  id text primary key,
  email text,
  name text,
  picture text,
  access_token text,
  refresh_token text,
  expires_at timestamptz not null
);
```

### 起動

```bash
# Web UI
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --reload

# ブラウザで http://localhost:8001 を開く
```

### CLI での実行

```bash
python -m src.main \
  --csv data/sample.csv \
  --request "CVRが3月比で4月に低下している。チャネル別・デバイス別に原因を探りたい"
```

---

## サンプルデータ

`data/` に 3 種類のサンプル CSV を同梱しています。

| ファイル | 内容 | 試せる依頼例 |
|---|---|---|
| `sample.csv` | チャネル×デバイス別 セッション・CV・売上（日次） | CVR 低下の原因分析 |
| `sample_ec_orders.csv` | EC 注文明細（カテゴリ・返品フラグ付き） | 返品率上昇の要因分析 |
| `sample_saas_metrics.csv` | SaaS 月次 KPI（プラン・地域別 MRR・チャーン） | チャーン急増の要因分析 |

---

## ディレクトリ構成

```
AutoAnalytics/
├── src/
│   ├── main.py                      # CLI エントリポイント
│   ├── api/
│   │   └── app.py                   # FastAPI + SSE
│   ├── llm/
│   │   ├── llm_client.py            # 抽象基底クラス（Bedrock 等に差し替え可）
│   │   └── anthropic_client.py      # Anthropic API 実装（プロンプトキャッシュ付き）
│   ├── storage/
│   │   ├── duckdb_client.py         # DuckDB 接続・クエリ・データコンテキスト生成
│   │   └── sql_validator.py         # SQL 安全化（SELECT 専用・LIMIT 自動付与）
│   ├── adapters/
│   │   ├── csv_adapter.py           # CSV → DuckDB ローダー
│   │   └── ga4_adapter.py           # GA4 Data API → DuckDB ローダー
│   ├── auth/
│   │   ├── google_oauth.py          # Google OAuth 2.0 フロー
│   │   └── session_store.py         # Supabase バックのセッション管理
│   └── orchestrator/
│       ├── request_parser.py        # 自然言語 → 構造化リクエスト
│       ├── hypothesis_generator.py  # 仮説生成・SQL 抽出・ステータス管理
│       └── report_generator.py      # Markdown レポート生成・保存
├── config/
│   └── llm_config.yaml              # モデル名・max_tokens
├── prompts/
│   ├── system_prompt.md             # エージェントの行動原則
│   ├── hypothesis_prompt.md         # 仮説生成テンプレート
│   └── report_prompt.md             # レポート生成テンプレート
├── data/                            # CSV 置き場（DuckDB ファイルは .gitignore）
├── reports/                         # 生成レポートの出力先
├── static/
│   └── index.html                   # ブラウザ UI（単一ファイル）
├── render.yaml                      # Render デプロイ設定
└── requirements.txt
```

---

## Render へのデプロイ

1. [render.com](https://render.com) で「New Web Service」を作成
2. `Fumiaki0604/AutoAnalytics` リポジトリを接続
3. 「Environment」タブで以下を設定：
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
   - `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`
   - `APP_BASE_URL`（例: `https://autoanalytics.onrender.com`）
4. 「Create Web Service」をクリック

`render.yaml` により Build/Start コマンドは自動設定されます。

---

## 今後の予定

### Phase 2 - データソース拡充

- [ ] Google Sheets Adapter
- [ ] 複数データソースの同時ロード・JOIN 補助

### Phase 3 - UI 改善

- [ ] レポート履歴の一覧 UI 改善

### Phase 4 - 分析品質向上

- [ ] 評価セット（プロンプト改善の指標化）
- [ ] memory.md コンテキスト層（KPI 定義・過去分析の発見・未実施 TODO を永続化し次回分析に引き継ぐ）
- [ ] learned-corrections 蓄積（SQL エラーや仮説棄却パターンをプロンプトにフィードバック）

### Phase 5 - 基盤拡張

- [ ] Bedrock 対応（LLM 差し替え）
- [ ] 専門プラグイン並列実行（KPI / SEO / 広告など分析ドメイン別エージェントを並列起動）
- [ ] 外部サービス連携（Slack / Notion / JIRA への自動投稿 + cron 定期分析）
