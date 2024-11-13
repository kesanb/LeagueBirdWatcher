# Pythonの公式イメージを使用
# 既存のDockerfile内容
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 必要なパッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー
COPY Watcher.py .

# アプリケーションを実行
CMD ["python", "Watcher.py"] 
# ヘルスチェックを追加
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ps aux | grep python | grep Watcher.py || exit 1

# 再起動ポリシーを設定
CMD ["python", "Watcher.py"]
