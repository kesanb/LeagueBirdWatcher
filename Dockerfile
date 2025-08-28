# Pythonの公式イメージを使用（Northflank最適化）
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 必要なシステムパッケージをインストールし、キャッシュをクリア
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pythonパッケージのインストール（キャッシュを無効化）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# アプリケーションのコードをコピー
COPY Watcher.py .

# Northflank向けの最適化設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random

# メモリ最適化のための環境変数
ENV GC_DISABLE=0 \
    PYTHONOPTIMIZE=1

# 非rootユーザーで実行（セキュリティ向上）
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# ヘルスチェックを追加（Northflankの制限に適した間隔）
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# アプリケーションを実行
CMD ["python", "Watcher.py"]