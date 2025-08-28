# LeagueBirdWatcher
Discord Webhook App for League of Legends

特定の召喚士（友人、お気に入りのストリーマー、プロプレイヤー）の試合をリアルタイムで監視し、Discord通知を送信するアプリケーションです。

## 🚀 主な機能

- **マルチカテゴリ監視**: ストリーマー、友人、スマーフ、トロルの4カテゴリ分類
- **リアルタイム通知**: 試合開始時にDiscord Webhookで通知
- **Northflank最適化**: 無料プラン（512MB RAM, 0.2 vCPU）向けに最適化
- **柔軟な設定**: 必要なカテゴリのみ設定可能
- **メモリ管理**: 定期的なガベージコレクションでメモリリーク防止

## 📋 必要環境

- Python 3.9+
- Docker（Northflankデプロイ時）
- Discord Webhook URL

## ⚙️ 環境変数設定

### 基本設定（必須）
```env
# 少なくとも1つのWebhook URLを設定
DISCORD_WEBHOOK_URL_STREAMER=https://discord.com/api/webhooks/your_streamer_webhook
DISCORD_WEBHOOK_URL_FRIEND=https://discord.com/api/webhooks/your_friend_webhook
DISCORD_WEBHOOK_URL_SMURF=https://discord.com/api/webhooks/your_smurf_webhook
DISCORD_WEBHOOK_URL_TROLL=https://discord.com/api/webhooks/your_troll_webhook
```

### プレイヤー設定（オプション）
```env
# 各カテゴリごとにプレイヤーを設定（nickname:summonername形式）
STREAMER_LIST=ニックネーム1:プレイヤー名1,ニックネーム2:プレイヤー名2
FRIEND_LIST=友人A:summonerA,友人B:summonerB
SMURF_LIST=smurf1:プレイヤーX
TROLL_LIST=troll1:プレイヤーY
```

### 追加設定（オプション）
```env
# HTMLログ保存機能（デバッグ用）
SAVE_HTML_LOG=true

# ログレベル設定
LOG_LEVEL=INFO
```

## 🏗️ Northflankデプロイ

### 1. リポジトリを準備
```bash
git add .
git commit -m "Northflank最適化版"
git push origin main
```

### 2. Northflankでデプロイ
1. Northflankダッシュボードにログイン
2. 新しいプロジェクトを作成
3. Gitリポジトリを接続
4. 環境変数を設定
5. ビルド＆デプロイ

### 3. Northflank設定例
```yaml
# northflank.yaml（オプション）
name: league-bird-watcher
resources:
  cpu: 0.2
  memory: 512MB
env:
  - DISCORD_WEBHOOK_URL_FRIEND=https://discord.com/api/webhooks/...
  - FRIEND_LIST=友人A:summonerA,友人B:summonerB
```

## 🐳 Docker実行

### ローカル実行
```bash
# ビルド
docker build -t league-bird-watcher .

# 実行
docker run -d --env-file .env league-bird-watcher
```

### NorthflankでのDocker実行
```bash
# Northflankでは自動的にビルドされます
# 環境変数をNorthflankダッシュボードで設定
```

## 📊 使用量最適化

Northflank無料プランの制限に合わせて最適化されています：

- **メモリ使用量**: 定期的なガベージコレクション
- **CPU使用量**: 軽量な処理ロジック
- **ネットワーク**: 効率的なリクエスト管理
- **ストレージ**: ログローテーション機能

## 🔧 ログ確認

### Northflankダッシュボード
1. プロジェクトを選択
2. 「Logs」タブをクリック
3. リアルタイムログを確認

### ログレベル
```env
LOG_LEVEL=DEBUG  # 詳細ログ表示
LOG_LEVEL=INFO   # 通常ログ
LOG_LEVEL=ERROR  # エラーのみ
```

## ⚠️ 注意事項

- 全てのログとメッセージが日本語で出力されます
- Northflank無料プランではリソース制限があります
- 過度なリクエストは避けるよう設計されています
- プレイヤー名の変更時は設定の更新が必要です

## 🆘 トラブルシューティング

### よくある問題

1. **Webhook URLが無効**
   - Discord Developer PortalでWebhook URLを確認
   - Northflankの環境変数設定を再確認

2. **プレイヤーが見つからない**
   - プレイヤー名のスペルを確認
   - Porofessor.ggでプレイヤーが存在するかチェック

3. **メモリ不足エラー**
   - 監視対象プレイヤー数を減らす
   - SAVE_HTML_LOGをfalseに設定

### サポート
問題が発生した場合は、ログを確認してエラーメッセージを参照してください。

## 📝 更新履歴

### v2.0.0 (Northflank最適化版)
- Northflank無料プラン向け最適化
- 柔軟なカテゴリ設定
- メモリ管理改善
- コード構造のリファクタリング
- Docker改善

---

**注意**: このアプリケーションはPorofessor.ggのサービスを利用しています。利用規約を確認の上ご使用ください。
