# 一键装机（Windows）：装依赖 → 装浏览器内核 → 自检并补齐 → 打印下一步
# 用法：右键「使用 PowerShell 运行」，或在 PowerShell 里： .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "===== 机票监控 · 一键装机 =====" -ForegroundColor Cyan

Write-Host "`n[1/4] 检查 Python 版本" -ForegroundColor Yellow
python -c "import sys; assert sys.version_info[:2] >= (3, 11), '需要 Python 3.11+，当前 %s' % sys.version; print('OK', sys.version.split()[0])"

Write-Host "`n[2/4] 安装 Python 依赖" -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "`n[3/4] 安装浏览器内核（约 100–200MB，只需一次）" -ForegroundColor Yellow
python -m playwright install chromium

Write-Host "`n[4/4] 自检并补齐（缺配置会从示例生成，缺目录会建）" -ForegroundColor Yellow
python -m core.setup_check --fix

Write-Host "`n===== 装好了 =====" -ForegroundColor Green
Write-Host "后台运行：  .\start.ps1"
Write-Host "前台运行：  python main.py"
Write-Host "打开界面：  运行后终端会打印 http://127.0.0.1:端口"
Write-Host "想采 App 渠道：先启动 MuMu 模拟器，再跑 python -m core.setup_check 确认「已连到设备」"
