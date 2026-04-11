# 分析エージェント PoC 要件定義書（Anthropic API + DuckDB版）

作成日: 2026-04-11 JST

## 1. 背景
データ分析案件では、案件ごとに利用可能なデータ基盤や接続条件が異なる。

- BigQueryが使える案件もあれば使えない案件もある
- GA4 APIのみ利用可能な案件がある
- CSVやGoogle Sheetsでデータ受領する案件がある
- クライアント保有DBへ接続可能な案件もある
- 生成AI活用においても、利用可能な基盤やセキュリティ条件が案件ごとに異なる

このため、特定DWHに依存した分析エージェントでは案件適用のハードルが高い。  
そこで本PoCでは、**Anthropic APIをLLM基盤、DuckDBを軽量分析基盤として採用し、データ取得元を抽象化した分析支援エージェント** を構築する。

## 2. 目的
Claude Codeで実装を進めつつ、Anthropic APIを用いた分析支援エージェントのPoCを構築する。  
本エージェントは、自然言語による分析依頼を受け、データ取得、仮説生成、SQL/Pythonによる検証、レポート生成までを半自動化することを目的とする。

## 3. PoCのゴール
1. ユーザーが自然言語で分析依頼を入力できる
2. 対象KPI・期間・切り口を解釈できる
3. 必要なデータを対象ソースから取得できる
4. 取得データをDuckDBに保存し再利用できる
5. 最低3つ以上の仮説を生成できる
6. SQLおよびPython処理で仮説検証できる
7. Markdown形式の分析レポートを出力できる

## 4. 技術スタック
- AIプラットフォーム: Anthropic API
- 実装支援環境: Claude Code
- 実装言語: Python（主）, TypeScript/Node.js（補助）
- 分析基盤: DuckDB
- データ処理: pandas / pyarrow
- データ取得: GA4 API / CSV / Google Sheets / DB Adapter
- 出力: Markdown

## 5. システム全体像
```text
自然言語の依頼
  ↓
CLI / 実行入口
  ↓
Analysis Orchestrator
  ├─ Request Parser
  ├─ LLM Client (Anthropic API)
  ├─ Hypothesis Generator
  ├─ Query Planner
  ├─ Report Generator
  ↓
Data Adapters
  ↓
DuckDB
  ↓
SQL / Python Analysis
  ↓
Markdown Report
```

## 6. 機能要件（要約）
- 自然言語での分析依頼受付
- Anthropic APIによる仮説生成 / 要約
- DuckDBへのデータ保存
- SQL分析
- Python補助分析
- Markdownレポート生成

## 7. 非機能要件（要約）
- 保守性: LLM層・Adapter層を分離
- 再現性: SQL / Prompt / 設定値を保存
- 安全性: 読み取り専用
- 拡張性: 将来的なBedrock差し替え可能
- コスト効率: BQ非依存・ローカル分析中心

## 8. 成功条件
- 自然言語依頼から分析開始
- 仮説生成とレポート草案生成
- DuckDBで一元管理
- 手作業より短時間で初期分析レポート作成
