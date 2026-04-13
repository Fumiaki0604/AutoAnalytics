以下の分析依頼に対して、検証可能な仮説を **3つ以上** 生成してください。

## 過去の分析コンテキスト

{past_context}

過去の発見がある場合は、「前回〜だったが今回は〜」という継続的な視点で仮説を立ててください。

---

## 分析依頼の概要
{summary}

## 対象 KPI
{kpi}

## 分析の切り口
{dimensions}

## 利用テーブル
{table}

## テーブル情報（スキーマ・サンプル・値域）
{data_context}

---

## SQL を書くうえでの厳守ルール

1. **日付・値は必ず上記「値域」に記載された実際の値を使うこと。** 推測・架空の値を WHERE 句に入れてはならない。
2. **日付フィルタは `BETWEEN` や `>=` / `<=` を使い、値域内の範囲を指定すること。**
3. **カラム名は「スキーマ」に記載されたものだけを使うこと。** 存在しないカラムを参照してはならない。
4. **DuckDB 構文を使うこと。** `STRFTIME` ではなく `STRPTIME` / `DATE_TRUNC` / `date_part` を使う。
5. SQL が長くなる場合は CTE（WITH 句）で読みやすく書くこと。
6. **CTE 名に DuckDB 予約語を使ってはならない。** 以下の名称は使用禁止。代わりに `_data` や `_result` を末尾に付けた名称を使うこと。
   - 禁止: `pivot`, `unpivot`, `rank`, `ranked`, `sample`, `filter`, `exclude`, `values`, `table`, `index`, `group`, `order`, `select`, `from`, `where`, `join`, `on`, `as`, `by`, `with`
   - 例: `pivot` → `channel_pivot_data`、`ranked` → `ranked_pages`、`monthly_device` → `device_monthly_data`

---

## 出力形式（この形式を厳守してください）

各仮説を以下の形式で番号付きリストとして記述してください。

1. [仮説タイトル（一文）]
   説明: 仮説の内容と、そう考える根拠
   ```sql
   -- DuckDB で実行可能な検証 SQL（実データの値域に基づいた WHERE 句を使う）
   SELECT
     ...
   FROM {table}
   ...
   LIMIT 20;
   ```

2. [仮説タイトル]
   ...

3. [仮説タイトル]
   ...
