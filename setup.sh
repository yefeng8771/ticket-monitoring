#!/usr/bin/env bash
# 一键装机（Linux / macOS）：装依赖 → 装浏览器内核 → 自检并补齐 → 打印下一步
# 用法：bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "===== 机票监控 · 一键装机 ====="

echo
echo "[1/4] 检查 Python 版本"
python3 - <<'PY'
import sys
assert sys.version_info[:2] >= (3, 11), "需要 Python 3.11+，当前 %s" % sys.version
print("OK", sys.version.split()[0])
PY

echo
echo "[2/4] 安装 Python 依赖"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo
echo "[3/4] 安装浏览器内核（约 100–200MB，只需一次）"
python3 -m playwright install chromium

echo
echo "[4/4] 自检并补齐（缺配置会从示例生成，缺目录会建）"
python3 -m core.setup_check --fix

echo
echo "===== 装好了 ====="
echo "前台运行：  python3 main.py"
echo "打开界面：  运行后终端会打印 http://127.0.0.1:端口"
echo "想采 App 渠道：先启动模拟器，再跑 python3 -m core.setup_check 确认「已连到设备」"
