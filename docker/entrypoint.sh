#!/usr/bin/env bash
# ticket-monitoring 容器入口：保证配置存在，且控制台在容器网络下可达。
# 上游默认 web.host=127.0.0.1（仅容器内可达），这里在未显式配置时改为 0.0.0.0。
set -euo pipefail

DATA_DIR="${DATA_DIR:-/app/data}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-8765}"
CONFIG_FILE="${CONFIG_FILE:-$DATA_DIR/config.yaml}"

mkdir -p "$DATA_DIR" "$DATA_DIR/logs"

if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<EOF
# ticket-monitoring 容器首次启动自动生成；之后请在网页控制台 ⚙️ 配置页修改（保存即热生效）。
web:
  host: "$WEB_HOST"
  port: $WEB_PORT
output:
  db_path: "$DATA_DIR/prices.db"
  log_path: "$DATA_DIR/logs/monitor.log"
EOF
  echo "[entrypoint] 已生成初始配置: $CONFIG_FILE"
else
  WEB_HOST="$WEB_HOST" WEB_PORT="$WEB_PORT" CONFIG_FILE="$CONFIG_FILE" python3 - <<'PY'
import os, yaml
path = os.environ["CONFIG_FILE"]
with open(path, encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
web = cfg.setdefault("web", {})
# 只补缺失项：用户已显式写的 host/port 保持不动
web.setdefault("host", os.environ["WEB_HOST"])
web.setdefault("port", int(os.environ["WEB_PORT"]))
cfg.setdefault("output", {})
with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, allow_unicode=True)
PY
fi

echo "[entrypoint] 启动监控: python main.py -c $CONFIG_FILE"
exec python /app/main.py -c "$CONFIG_FILE"
