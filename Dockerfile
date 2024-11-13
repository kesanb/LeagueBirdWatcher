# 既存のDockerfile内容
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY Watcher.py .

# ヘルスチェックを追加
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ps aux | grep python | grep Watcher.py || exit 1

# 再起動ポリシーを設定
CMD ["python", "Watcher.py"]
