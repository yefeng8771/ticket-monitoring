"""能力降级账本（r1063 T60）：fail-soft 的地方必须**留下可查的证据**。

为什么要有它
------------
"失败就跳过、只写一行日志"在本仓很常见（`except Exception: pass` 几十处）。
问题是：**能力悄悄关掉 ≠ 一切正常**。上轮就是活例子——`geo.fix()` 调错了设备
API，定位固定从来没生效过，只在日志里留过一行 warning，藏了十几轮才被测试撞出来。

约定
----
* 只记**能力级**的降级（"定位没设上""识别后端缺失""UA 与内核不同步"），
  不记单次网络抖动——那会淹没真问题；
* 进程内计数 + 最近一次原因，由 `/api/pacing` 的 `degraded` 段带出去，
  面板上说得出"降级了几类、每类几次、最近为什么"；
* **不改控制流**：调用方照旧 fail-soft，这里只是记账（绝不因为记账失败而报错）。
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_STATE: dict = {}


def note(cap: str, plat: str = "", detail: str = "", *, n: int = 1,
         now: float = None) -> None:
    """记一次能力降级。`cap` 是能力名（英文短横线），`plat` 可选。"""
    key = (str(cap or "").strip(), str(plat or "").strip())
    if not key[0]:
        return
    try:
        add = max(1, int(n or 1))
    except (TypeError, ValueError):
        add = 1
    ts = float(now if now is not None else time.time())
    try:
        with _LOCK:
            rec = _STATE.setdefault(key, {"n": 0, "last": "", "at": 0.0})
            rec["n"] = int(rec.get("n") or 0) + add
            if detail:
                rec["last"] = str(detail)[:160]
            rec["at"] = ts
    except Exception:
        pass                    # 记账失败不许影响调用方


def snapshot() -> dict:
    """按能力聚合：`{cap: {"n": N, "plats": {plat: n}, "last": 原因, "at": ts}}`。"""
    with _LOCK:
        items = [(k, dict(v)) for k, v in _STATE.items()]
    out = {}
    for (cap, plat), rec in items:
        row = out.setdefault(cap, {"n": 0, "plats": {}, "last": "",
                                   "at": 0.0})
        row["n"] += int(rec.get("n") or 0)
        if plat:
            row["plats"][plat] = int(row["plats"].get(plat) or 0) + int(
                rec.get("n") or 0)
        if rec.get("last") and float(rec.get("at") or 0) >= float(
                row.get("at") or 0):
            row["last"] = rec["last"]
            row["at"] = float(rec.get("at") or 0)
    return out


def reset() -> None:
    with _LOCK:
        _STATE.clear()


def total() -> int:
    with _LOCK:
        return sum(int((v or {}).get("n") or 0) for v in _STATE.values())
