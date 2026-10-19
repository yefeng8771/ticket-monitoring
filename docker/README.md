# ticket-monitoring Docker 镜像（yefeng8771 fork）

镜像：`ghcr.io/yefeng8771/ticket-monitoring:latest`（另有 `sha-<短提交>` 标签）
架构：`linux/amd64`、`linux/arm64`

## 运行

```bash
docker run -d --name ticket-monitoring \
  -p 8765:8765 \
  -v ticket-data:/app/data \
  --restart unless-stopped \
  ghcr.io/yefeng8771/ticket-monitoring:latest
```

浏览器打开 `http://<宿主机IP>:8765`，在网页 ⚙️ 配置页填航线与钉钉推送，
保存即热生效（零重启）。配置、价格库、日志都落在 `/app/data`（volume 持久化）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `WEB_HOST` | `0.0.0.0` | 控制台监听地址（容器内默认对外；上游默认 `127.0.0.1`） |
| `WEB_PORT` | `8765` | 控制台端口 |
| `DATA_DIR` | `/app/data` | 数据目录（config.yaml / prices.db / logs） |
| `CONFIG_FILE` | `$DATA_DIR/config.yaml` | 配置文件路径（可挂载自己的文件覆盖） |

已有 `config.yaml` 可直接挂载：`-v /path/to/config.yaml:/app/data/config.yaml`。
已显式写在配置文件里的 `web.host`/`web.port` 优先级高于环境变量。

## 说明

- 镜像由 `.github/workflows/docker-build.yml` 自动构建：`main` 分支有代码变更时、
  每天 11:00（CST，紧随上游同步）以及手动触发。
- fork 的上游同步见 `.github/workflows/upstream-sync.yml`（每天 10:00 CST 从
  `dengmeiluan/ticket-monitoring` 合并，冲突按上游为准）。
