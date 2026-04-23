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

---

## 選択可能なディメンション一覧（最大8つまで選択、dateは常に含む）

### 時間・日付
- `date` — 日付（常に含める）
- `year` — 年
- `month` — 月（YYYYMM形式）
- `week` — 週番号
- `dayOfWeek` — 曜日（0=日曜）
- `hour` — 時間帯

### チャネル・参照元
- `sessionDefaultChannelGroup` — チャネルグループ（Organic Search/Direct/Referral等）
- `sessionSourceMedium` — 参照元/メディア（セッション）★よく使う
- `sessionSource` — 参照元（セッション）
- `sessionMedium` — メディア（セッション）
- `sessionCampaignName` — キャンペーン名（UTM）
- `firstUserSourceMedium` — 初回獲得参照元/メディア
- `firstUserDefaultChannelGroup` — 初回獲得チャネル

### デバイス・環境
- `deviceCategory` — デバイス種別（desktop/mobile/tablet）
- `operatingSystem` — OS（iOS/Android/Windows等）
- `browser` — ブラウザ
- `platform` — プラットフォーム（web/android/ios）
- `mobileDeviceModel` — 端末モデル

### ページ・コンテンツ
- `pagePath` — ページパス（/products/123等）
- `pageTitle` — ページタイトル
- `landingPage` — ランディングページ（最初に訪問したページ）
- `pagePathPlusQueryString` — クエリパラメータ付きパス

### ユーザー・地域
- `country` — 国
- `city` — 都市
- `region` — 地域
- `newVsReturning` — 新規/リピーター（new/returning）
- `userAgeBracket` — 年齢層
- `userGender` — 性別

### イベント・コンバージョン
- `eventName` — イベント名
- `isConversionEvent` — コンバージョンイベントかどうか

---

## 選択可能なメトリクス一覧（最大10個まで選択）

### セッション・ユーザー
- `sessions` — セッション数★
- `totalUsers` — 総ユーザー数
- `activeUsers` — アクティブユーザー数
- `newUsers` — 新規ユーザー数★
- `returningUsers` — リピーターユーザー数

### エンゲージメント
- `bounceRate` — 直帰率★
- `engagementRate` — エンゲージメント率
- `engagedSessions` — エンゲージセッション数
- `averageSessionDuration` — 平均セッション時間（秒）★
- `screenPageViews` — ページビュー数
- `screenPageViewsPerSession` — セッションあたりPV数

### コンバージョン・売上
- `conversions` — コンバージョン数★
- `totalRevenue` — 総売上★
- `purchaseRevenue` — 購入売上
- `ecommercePurchases` — 購入件数
- `addToCarts` — カート追加数
- `checkouts` — チェックアウト数
- `cartToViewRate` — カート追加率

### イベント
- `eventCount` — イベント発生数
- `eventCountPerUser` — ユーザーあたりイベント数
