# yefeng8771 fork: ticket-monitoring Docker 镜像
# 自动构建见 .github/workflows/docker-build.yml → ghcr.io/yefeng8771/ticket-monitoring
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATA_DIR=/app/data \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8765

WORKDIR /app

# Playwright chromium 系统依赖 + 推送报表 PNG 的中文字体
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

RUN chmod +x docker/entrypoint.sh

EXPOSE 8765
VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${WEB_PORT:-8765}/" >/dev/null || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
