# -*- coding: utf-8 -*-
"""找"把 `>` / `|` / `$(` 塞进 adb shell"的调用点。

为什么需要它（2026-11-04 实测机制）
----------------------------------
从 Python 经 `adb shell` 发出的命令里，**重定向与管道不可靠**。同一个动作
三种写法，只有第三种在设备上真的生效：

| 写法 | 设备上文件内容 |
|---|---|
| `subprocess.run([adb,'-s',S,'shell','sh','-c','echo X > f'])` | **空** |
| 整串交本地 shell | **空** |
| 本地临时文件 → `adb push` → `sh /path/f.sh` | `X` ✅ |

失效方式很坏：**不报错**，只是静默没做成。boot 标记就因此**一直**没写进去，
"本 boot 只做一次全量隐藏"的门槛从未成立，`hide()` 每轮白跑
（denylist 读写 sqlite + 抓 logcat 快照）。修法见 `fingerprint.write_remote`。

**别把这个扫描器报的"0 处"当结论。** 第一版就因为正则写错报了 0，
而 `grep` 找到 17 处 —— 一个说"没问题"的坏工具，比没有工具更危险。
所以这里把判据写成显式的字符串集合，并且**同时输出命中数与总数**，
0 命中时格外可疑。

注意：命中 != 一定要改。有些点是**带读回校验**的（例如 abi-select 表追加，
实测确实写进去了），失败会如实报告而不是静默；有些出现在 `as_root` 里
（脚本被 push 到设备上执行，重定向在**设备侧**解析，是安全的）。
判据是"有没有读回校验"，不是"有没有 > 字符"。

用法：
    python scripts/sweep_adb_redirects.py
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `sh -c` / `su -c` 的形态
CALL = re.compile(r"""["']-c["']""")
# **真正会被本地 shell 抢走的字符**：重定向、管道、命令替换。
#
# 注意 `&&` **不在列**：它只是命令分隔，本身不改变落地位置；
# 把 `test -e X && echo TM_YES` 这类当危险项纯属误报。
# 第一版就是因为把 `&& echo` 算作危险，报了 10 处、其中大半无害 ——
# **一个满是小报告的扫描器最后没人看，比没有扫描器更糟**。
DANGER = (" > ", " >> ", " | ", "$(")
# 纯注释行不参与判定（docstring/注释里写的示例不是调用点）
COMMENT = re.compile(r"^\s*(#|\"\"\"|''')")
# 这些上下文里出现重定向是安全的：脚本已经被 push 到设备上执行
SAFE_HINT = ("as_root(", "as_root(", "base64")


def scan(bases=("core", "crawlers", "scripts")):
    rows = []
    scanned = 0
    for base in bases:
        d0 = os.path.join(ROOT, base)
        if not os.path.isdir(d0):
            continue
        for cur, dirs, files in os.walk(d0):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in sorted(files):
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(cur, fn)
                try:
                    lines = io.open(p, encoding="utf-8").read().splitlines()
                except Exception:
                    continue
                scanned += 1
                for n, line in enumerate(lines):
                    if not CALL.search(line):
                        continue
                    # 只看这条语句自己的后续拼接行（最多 5 行），
                    # 并且跳过纯注释/docstring 行——否则解释性注释会误报
                    body = " ".join(
                        x for x in lines[n:n + 5]
                        if not x.strip().startswith("#")
                        and '"' not in x[:3])
                    bad = [t for t in DANGER if t in body]
                    if not bad:
                        continue
                    in_as_root = "as_root" in body or "write_remote" in body
                    rows.append((os.path.relpath(p, ROOT), n + 1, bad,
                                 in_as_root, lines[n].strip()[:72]))
    return rows, scanned


def main() -> int:
    rows, scanned = scan()
    risky = [r for r in rows if not r[3]]
    safe = [r for r in rows if r[3]]
    print("扫描 %d 个文件，命中 %d 处（其中 %d 处在 as_root/write_remote 里=安全，"
          "%d 处需人工判断）" % (scanned, len(rows), len(safe), len(risky)))
    print()
    for path, ln, bad, _ok, head in risky:
        print("  %s:%d  危险=%s" % (path, ln, bad))
        print("      %s" % head)
    if safe:
        print("\n  （安全：走 as_root/write_remote 的）")
        for path, ln, _b, _ok, head in safe:
            print("    %s:%d  %s" % (path, ln, head))
    if not rows:
        print("\n**0 命中要当心**：先确认正则本身没写错"
              "（第一版就误报过 0，实际 grep 找到 17 处）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
