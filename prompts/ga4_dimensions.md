# GA4 APIディメンション・メトリクス 正式名称リファレンス

## 【重要】参照元・メディア系ディメンション（名称が紛らわしいため注意）

| 用途 | 正式API名 | 説明 |
|---|---|---|
| セッションの参照元/メディア | `sessionSourceMedium` | 最もよく使う。セッション開始時の参照元とメディアの組み合わせ |
| セッションの参照元のみ | `sessionSource` | セッション開始時の参照元 |
| セッションのメディアのみ | `sessionMedium` | セッション開始時のメディア |
| セッションのチャネル | `sessionDefaultChannelGroup` | Organic Search, Direct, Referral など |
| 初回ユーザーの参照元/メディア | `firstUserSourceMedium` | ユーザー初回訪問時の参照元/メディア |
| 初回ユーザーの参照元 | `firstUserSource` | ユーザー初回訪問時の参照元 |
| 初回ユーザーのメディア | `firstUserMedium` | ユーザー初回訪問時のメディア |
| イベントの参照元/メディア | `sourceMedium` | コンバージョンイベント時点の参照元/メディア |
| イベントの参照元 | `source` | コンバージョンイベント時点の参照元 |
| イベントのメディア | `medium` | コンバージョンイベント時点のメディア |

> **注意**: ユーザーが「参照元/メディア」と言った場合は `sessionSourceMedium` を使うこと。
> 「source / medium」「sourceMedium」「referrer」などの名称は存在しないか別の意味を持つ。

## 取得済みカラム（ga4_dataテーブルに存在するもの）

現在のデフォルト取得ディメンション：
- `date` - 日付（YYYY-MM-DD形式）
- `sessionDefaultChannelGroup` - チャネルグループ
- `sessionSourceMedium` - 参照元/メディア（セッション）
- `sessionSource` - 参照元（セッション）
- `sessionMedium` - メディア（セッション）
- `deviceCategory` - デバイス種別（desktop/mobile/tablet）
- `landingPage` - ランディングページパス

現在のデフォルト取得メトリクス：
- `sessions` - セッション数
- `conversions` - コンバージョン数
- `totalRevenue` - 売上
- `bounceRate` - 直帰率
- `averageSessionDuration` - 平均セッション時間（秒）
- `newUsers` - 新規ユーザー数

## その他主要ディメンション（デフォルト未取得・参考）

- `pagePath` - ページパス
- `pageTitle` - ページタイトル
- `country` - 国
- `city` - 都市
- `platform` - プラットフォーム（web/android/ios）
- `operatingSystem` - OS
- `browser` - ブラウザ
- `sessionCampaignName` - キャンペーン名
- `eventName` - イベント名
