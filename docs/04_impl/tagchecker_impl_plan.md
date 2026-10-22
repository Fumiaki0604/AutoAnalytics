---
role: plan
depends_on:
  - prototype/PROTOTYPE.md
  - prototype/DESIGN_DECISION.md
---
# TagChecker 実装計画

## 概要

WebサイトのGA4タグ設定（PV2重計測）を自動検出するツールを4フェーズで実装する。
プロトタイプ（`prototype/index.html`）はUI確認済みのため、本番実装の骨格は決まっている。

**アーキテクチャ:**
- `tagchecker/` ディレクトリ内に Node.js アプリとして実装
- Express でHTTPサーバー兼フロントエンド配信
- Playwright でGA4ネットワーク傍受（実ブラウザ起動）
- Supabase でデータ永続化
- 当面はlocalhost動作。将来 Render にデプロイ（チーム展開時）

**スコープ:**
- Phase 0〜3: localhost 動作（認証なし）
- Phase 4: Google OAuth + Render デプロイ（別チケットで管理）

### 担当凡例

| 記号 | 担当者 | 説明 |
|------|--------|------|
| 👤 | 人間 | 外部サービス設定、手動確認、アカウント操作 |
| 🤖 | AI (Claude Code) | コーディング、テスト、ファイル生成 |
| 👤+🤖 | 共同 | AIが実行し、人間が確認・承認する作業 |

### フェーズ一覧

| Phase | 名称 | 主な担当 | 目標 | 状態 |
|-------|------|---------|------|------|
| 0 | 準備ゾーン | 👤+🤖 | Supabase + Node.js 環境構築 | ⏳ 未着手 |
| 1 | タグチェックエンジン | 🤖 | Playwright でGA4傍受・判定 | ⏳ 未着手 |
| 2 | バックエンドAPI | 🤖 | Express + Supabase CRUD | ⏳ 未着手 |
| 3 | フロントエンド接続 | 🤖 | プロトタイプHTMLをリアルAPIに切り替え | ⏳ 未着手 |
| 4 | チーム展開（将来） | 👤+🤖 | Google OAuth + Render デプロイ | ⏳ 未着手（後回し） |

---

## Phase 0: 準備ゾーン ⏳ 未着手

**目標**: Supabaseプロジェクト作成・スキーマ適用・Node.jsプロジェクト初期化
**主な担当**: 👤 が外部サービス設定、🤖 がプロジェクト初期化

> **凡例**: 👤 = 人間が実施 / 🤖 = Claude Codeが実施

---

### 0.1 Supabase プロジェクト作成 ⏳

> 参照: ref-supabase REF-SB-01〜02

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 0.1.1 | Supabase プロジェクト作成 + API Keys 取得 | 👤 | 【SB1】〜【SB3】メモ完了 | ⏳ |
| 0.1.2 | Personal Access Token 取得 | 👤 | 【SB5】メモ完了 | ⏳ |

**0.1.1 プロジェクト作成手順** (👤):

**Step 1: プロジェクト作成**
1. https://supabase.com/dashboard にアクセス（GitHubでログイン）
2. 「New project」をクリック
3. Organization: 自分のOrganizationを選択
4. プロジェクト名: `tagchecker`
5. Database Password: 安全なパスワードを設定 → メモ
6. Region: `Tokyo`
7. 「Create new project」をクリック
8. プロジェクトの初期化を待つ（1〜2分）

**Step 2: API Keys 取得**
1. ダッシュボード左メニュー「Project Settings」→「API」
2. 以下をメモ:
   - **Project URL**: `https://xxxx.supabase.co`
   - **anon public key**: `eyJhbGciOiJIUzI1NiIs...`
   - **service_role secret key**: `eyJhbGciOiJIUzI1NiIs...`

**メモすべき情報**:
- 【SB1】Project URL: `https://xxxx.supabase.co`
- 【SB2】anon key: `eyJhbGciOiJIUzI1NiIs...`
- 【SB3】service_role key: `eyJhbGciOiJIUzI1NiIs...`

**0.1.2 Personal Access Token 取得手順** (👤):

1. https://supabase.com/dashboard/account/tokens にアクセス
2. 「Generate new token」をクリック
3. トークン名: `tagchecker-mcp`
4. 発行されたトークンをメモ（**一度しか表示されない**）

**メモすべき情報**:
- 【SB5】Personal Access Token: `sbp_xxxx...`

---

### 0.2 Supabase MCP 接続 ⏳

> 参照: ref-supabase REF-SB-03

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 0.2.1 | MCPサーバー登録 | 🤖 | `codex mcp add` 成功 | ⏳ |
| 0.2.2 | OAuth認証 | 👤 | `codex mcp login` 認可完了 | ⏳ |
| 0.2.3 | IDE再読み込み | 👤 | 新セッションに反映 | ⏳ |
| 0.2.4 | 接続テスト | 🤖 | `list_projects` 成功 | ⏳ |

**0.2.1 MCPサーバー登録** (🤖):
```bash
codex mcp add supabase --url "https://mcp.supabase.com/mcp"
```

**0.2.2 OAuth認証** (👤):
```bash
codex mcp login supabase
```
1. ターミナルに表示されたURLをブラウザで開く
2. Supabaseで認可する
3. **ターミナルに成功メッセージが出るまで閉じない**

**0.2.3 IDE再読み込み** (👤):
- VSCode: `Ctrl+Shift+P` → `Developer: Reload Window`

**トラブルシューティング**:
| 症状 | 原因 | 対処 |
|------|------|------|
| `Auth required` が出る | OAuth未認証または古いセッション | `codex mcp login supabase` を再実行、成功後にIDE再読み込み |
| `unknown MCP server "supabase"` | 設定未反映 | `codex mcp list` で確認後、IDE再読み込み |
| 接続が不安定 | 旧設定が残っている | `remove` → `add` → `login` の順で再設定 |

---

### 0.3 Node.js プロジェクト初期化 ⏳

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 0.3.1 | `tagchecker/` ディレクトリ構造作成 | 🤖 | ディレクトリ・package.json 作成完了 | ⏳ |
| 0.3.2 | 依存パッケージインストール | 👤 | `npm install` 成功 | ⏳ |
| 0.3.3 | Playwright ブラウザインストール | 👤 | `npx playwright install chromium` 成功 | ⏳ |
| 0.3.4 | `.env.local` 作成 | 👤 | 環境変数設定完了 | ⏳ |

**0.3.1 ディレクトリ構造** (🤖 が作成する):
```
tagchecker/
  src/
    server.js          # Express サーバー
    checker.js         # Playwright GA4 チェックエンジン
    routes/
      sites.js         # GET/POST/PUT/DELETE /api/sites
      check.js         # POST /api/check (スポット), POST /api/batch
      history.js       # GET /api/sessions
    db/
      client.js        # Supabase クライアント初期化
      queries.js       # DB操作関数
  public/
    index.html         # フロントエンド（プロトタイプから移植）
  supabase/
    migrations/
      001_initial_schema.sql
  .env.local           # 環境変数（gitignore済み）
  package.json
```

**0.3.2 依存パッケージインストール** (👤):
```bash
cd tagchecker
npm install
```

**0.3.3 Playwright ブラウザインストール** (👤):
```bash
cd tagchecker
npx playwright install chromium
```
> 約170MBのChromiumをダウンロード。初回のみ。

**0.3.4 .env.local 作成** (👤):
```bash
# tagchecker/.env.local
SUPABASE_URL=（【SB1】の値）
SUPABASE_ANON_KEY=（【SB2】の値）
SUPABASE_SERVICE_ROLE_KEY=（【SB3】の値）
PORT=3001
```

---

### 0.4 DBスキーマ適用 ⏳

> 参照: ref-supabase REF-SB-04

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 0.4.1 | マイグレーションSQL 作成 | 🤖 | `001_initial_schema.sql` 作成 | ⏳ |
| 0.4.2 | Supabase MCP でスキーマ適用 | 🤖 | 3テーブル作成確認 | ⏳ |
| 0.4.3 | サンプルデータ投入 | 🤖 | 7件の sites データ確認 | ⏳ |

**スキーマ（概要）**:
```sql
-- sites テーブル
CREATE TABLE sites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'excluded')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_checked_at TIMESTAMPTZ,
  last_verdict TEXT CHECK (last_verdict IN ('ok', 'ng', 'warning'))
);

-- check_sessions テーブル
CREATE TABLE check_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode TEXT NOT NULL CHECK (mode IN ('batch', 'full')),
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  total_count INTEGER NOT NULL DEFAULT 0,
  ok_count INTEGER NOT NULL DEFAULT 0,
  ng_count INTEGER NOT NULL DEFAULT 0,
  warning_count INTEGER NOT NULL DEFAULT 0
);

-- check_results テーブル
CREATE TABLE check_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
  session_id UUID REFERENCES check_sessions(id) ON DELETE SET NULL,
  checked_at TIMESTAMPTZ DEFAULT NOW(),
  url TEXT NOT NULL,
  page_view_count INTEGER NOT NULL DEFAULT 0,
  measurement_ids TEXT[] NOT NULL DEFAULT '{}',
  verdict TEXT NOT NULL CHECK (verdict IN ('ok', 'ng', 'warning')),
  detail JSONB NOT NULL DEFAULT '{}'
);
```

### Phase 0 完了条件

- [ ] Supabase プロジェクト `tagchecker` が作成済み（👤）
- [ ] `tagchecker/` ディレクトリが初期化済み（🤖）
- [ ] `npm install` + `playwright install chromium` 済み（👤）
- [ ] `.env.local` に Supabase API Keys 設定済み（👤）
- [ ] Supabase に3テーブル作成済み（🤖）
- [ ] サンプルデータ7件投入済み（🤖）

---

## Phase 1: タグチェックエンジン ⏳ 未着手

**目標**: Playwright でGA4 `g/collect` リクエストを傍受し、`page_view` 発火回数と計測IDを返す
**主な担当**: 🤖

> これがTagCheckerの核心。プロトタイプの `setTimeout + 固定結果` をここで本物に置き換える。

| # | タスク | 実施者 | テスト | 完了条件 | 状態 |
|---|--------|--------|--------|---------|------|
| 1.1 | `checker.js` 実装（ネットワーク傍受） | 🤖 | - | NG/OK/Warning を正しく返す | ⏳ |
| 1.2 | ユニットテスト（判定ロジック） | 🤖 | **Unit: checker.test.js** | 全パス | ⏳ |
| 1.3 | 実URL手動検証 | 👤+🤖 | 実ブラウザ確認 | 3種類の判定が確認できる | ⏳ |

#### checker.js の実装内容

**ネットワーク傍受ロジック:**
```javascript
// GA4 collect エンドポイントのURLパターン
// https://www.google-analytics.com/g/collect?...
// en=page_view, tid=G-XXXXXXXX などのパラメータを解析
```

**判定ロジック:**
| 条件 | 判定 | 理由メッセージ |
|------|------|---------------|
| page_view 同一tidで2回以上 | NG | 「page_viewが同一IDで2重計測されています」 |
| page_view 0回 | Warning | 「page_viewが検出されませんでした（同意バナーまたはタグ未設置の可能性）」 |
| 異なるtidでそれぞれ1回 | Warning | 「複数の計測IDでpage_viewが検出されました（要確認）」 |
| page_view 1回 | OK | 「正常です」 |

**タイムアウト設定:**
- ページロード待機: 最大 10秒
- ネットワーク安定待機: DOMContentLoaded + 2秒
- 全体タイムアウト: 30秒

**checker.js の返却値（`CheckResult` 型）:**
```javascript
{
  verdict: 'ok' | 'ng' | 'warning',
  page_view_count: number,
  measurement_ids: string[],
  detail: {
    reason: string,
    requests: [
      { tid: string, en: string, detected_at_ms: number }
    ]
  }
}
```

#### Phase 1 E2Eテストチェックリスト

```
⏳ E2E-P1-01: 正常サイト（OK判定）
  - https://www.sports-depo.jp/ をチェック → verdict=ok, page_view_count=1

⏳ E2E-P1-02: エラー（タイムアウト）
  - 存在しないURL → verdict=warning, reason=「チェック中にエラーが発生しました」

⏳ E2E-P1-03: NG確認（可能であれば）
  - 2重計測が確認されているURLをチェック → verdict=ng
```

#### Phase 1 完了条件

- [ ] `checker.js` が CheckResult を返す（🤖）
- [ ] ユニットテスト全パス（🤖）
- [ ] 実URLで OK / Warning の2種類が確認できる（👤+🤖）

---

## Phase 2: バックエンドAPI ⏳ 未着手

**目標**: Express で REST API を実装し、Supabase と連携する
**主な担当**: 🤖

| # | タスク | 実施者 | テスト | 完了条件 | 状態 |
|---|--------|--------|--------|---------|------|
| 2.1 | Supabase クライアント + クエリ関数 | 🤖 | **Unit: db.test.js** | CRUD全パス | ⏳ |
| 2.2 | サイト管理 API (`/api/sites`) | 🤖 | **Integration: sites.test.js** | 5エンドポイント全パス | ⏳ |
| 2.3 | スポットチェック API (`/api/check`) | 🤖 | **Integration: check.test.js** | 全パス | ⏳ |
| 2.4 | バッチ実行 API (`/api/batch`) | 🤖 | **Integration: batch.test.js** | 全パス | ⏳ |
| 2.5 | 結果履歴 API (`/api/sessions`) | 🤖 | **Integration: history.test.js** | 全パス | ⏳ |
| 2.6 | `server.js` 起動確認 | 👤 | `node src/server.js` | `http://localhost:3001` でアクセス可 | ⏳ |

#### APIエンドポイント一覧

| メソッド | パス | 処理 |
|---------|------|------|
| GET | `/api/sites` | サイト一覧取得（フィルタ: status） |
| POST | `/api/sites` | サイト追加 |
| PUT | `/api/sites/:id` | サイト編集（name, url, status） |
| DELETE | `/api/sites/:id` | サイト削除 |
| POST | `/api/check` | スポットチェック実行（URLを受け取り即時チェック） |
| POST | `/api/batch` | バッチ実行（mode: 'batch' or 'full'） |
| DELETE | `/api/batch/abort` | バッチ中止 |
| GET | `/api/sessions` | セッション一覧（check_sessions） |
| GET | `/api/sessions/:id/results` | セッション別結果（check_results） |

**バッチ実行の注意事項:**
- バッチはサーバー側で逐次実行（1件ずつ Playwright 起動）
- 進捗はポーリング(`GET /api/batch/status`)でフロントから確認
- 中止フラグ（in-memory）でループを止める

#### Phase 2 完了条件

- [ ] 全APIエンドポイントが動作（🤖）
- [ ] Supabase にデータが永続化される（🤖）
- [ ] `localhost:3001` でサーバーが起動する（👤）

---

## Phase 3: フロントエンド接続 ⏳ 未着手

**目標**: プロトタイプ `prototype/index.html` のモック部分をリアルAPI呼び出しに置き換える
**主な担当**: 🤖

> デザイン・レイアウトはプロトタイプを流用。変更するのはデータ層（localStorage→fetch API）のみ。

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 3.1 | `prototype/index.html` を `tagchecker/public/index.html` へコピー | 🤖 | コピー完了 | ⏳ |
| 3.2 | localStorage → fetch API に置き換え（S01 サイト管理） | 🤖 | CRUD全操作が動く | ⏳ |
| 3.3 | setTimeout モック → `/api/check` に置き換え（S03 スポットチェック） | 🤖 | 実チェックが動く | ⏳ |
| 3.4 | バッチモック → `/api/batch` に置き換え（S02 バッチ実行） | 🤖 | バッチ実行が動く | ⏳ |
| 3.5 | 履歴モック → `/api/sessions` に置き換え（S04 結果履歴） | 🤖 | 履歴が表示される | ⏳ |
| 3.6 | Express で `public/index.html` を配信設定 | 🤖 | `localhost:3001` でUIが表示される | ⏳ |
| 3.7 | E2E動作確認 | 👤+🤖 | 全画面が正常動作 | ⏳ |

**置き換え方針:**
- `const load = () => JSON.parse(localStorage.getItem(...))` → `await fetch('/api/sites')`
- `const save = (data) => localStorage.setItem(...)` → `await fetch('/api/sites', {method:'POST', body:...})`
- `function mockCheck(url)` → `await fetch('/api/check', {method:'POST', body:{url}})`
- バッチ進捗はポーリング（500ms間隔で `GET /api/batch/status`）

#### Phase 3 E2Eテストチェックリスト

```
⏳ E2E-P3-01: サイト追加
  - [+ サイト追加] → サイト名・URL入力 → [保存] → テーブルに追加される

⏳ E2E-P3-02: スポットチェック（実URL）
  - https://www.sports-depo.jp/ を入力 → [チェック] → 結果カードが表示される

⏳ E2E-P3-03: バッチ実行
  - [通常バッチ] → [実行開始] → 進捗が動く → 完了結果が表示される

⏳ E2E-P3-04: 結果履歴
  - バッチ完了後、[結果履歴] タブに今回のセッションが表示される

⏳ E2E-P3-05: excluded フラグ
  - サイトの [active] バッジをクリック → ダイアログ → [除外する] → [excluded] に変わる
```

#### Phase 3 完了条件

- [ ] `http://localhost:3001` でUIが表示される（👤）
- [ ] サイト追加・編集・削除が Supabase に反映される（👤）
- [ ] スポットチェックで実URLの判定が表示される（👤）
- [ ] バッチ実行が完了し、結果履歴に保存される（👤）
- [ ] E2E-P3-01〜05 全チェック完了（👤+🤖）

---

## Phase 4: チーム展開（将来） ⏳ 未着手（後回し）

> **このPhaseは「チームで使いたい」と判断したタイミングで実施する。**
> localhost動作が確認できてから着手。

**目標**: Google OAuth認証 + Render デプロイでチーム共有

| # | タスク | 実施者 | 完了条件 | 状態 |
|---|--------|--------|---------|------|
| 4.1 | Google Cloud プロジェクト作成 + OAuth設定 | 👤 | 【G1】【G2】メモ完了 | ⏳ |
| 4.2 | Supabase Auth（Google Provider）設定 | 👤 | ログイン動作確認 | ⏳ |
| 4.3 | フロントエンドにログイン画面追加 | 🤖 | OAuthフロー完成 | ⏳ |
| 4.4 | APIに認証ミドルウェア追加 | 🤖 | 未認証時に401返す | ⏳ |
| 4.5 | Render へデプロイ（Standard $25/月） | 👤 | 本番URLでアクセス可 | ⏳ |
| 4.6 | チームメンバーにアクセス権付与 | 👤 | メンバーがログインできる | ⏳ |

**Renderのポイント:**
- プランは **Standard ($25/月)** 必須（Playwright/Chromiumに ~1GB RAM が必要）
- `render.yaml` は既に `c:\dev\AutoAnalytics\render.yaml` に存在。TagChecker用に更新が必要。

> **Google Cloud OAuth の詳細手順**: `ref-google-cloud` REF-GC-01〜06 を参照
> **Supabase Auth の詳細手順**: `ref-supabase` REF-SB-05〜06 を参照

---

## 実装開始の判断

Phase 0（Supabase設定）は 👤 作業が先行するため、以下の順で進める:

```
1. 【今すぐ】Phase 0.3.1: 🤖 が tagchecker/ プロジェクト構造・package.json・マイグレーションSQL を一括作成
2. 【並行して】Phase 0.1: 👤 が Supabase プロジェクトを作成・API Keys をメモ
3. 【👤作業後】Phase 0.2: 🤖 が Supabase MCP に接続 → スキーマ適用
4. 【その後】Phase 1 → Phase 2 → Phase 3 と順に進める
```

**次のアクション（最初の一歩）:**
- 🤖: `tagchecker/` のプロジェクト構造を作成する
- 👤: Supabaseで `tagchecker` プロジェクトを作成し、API Keysをメモする
