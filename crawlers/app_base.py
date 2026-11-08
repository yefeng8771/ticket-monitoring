# -*- coding: utf-8 -*-
"""App 渠道基类：不依赖 Playwright，但复用既有账本契约。

为什么另起一个基类而不是继承 BaseCrawler：BaseCrawler 的
`browser()` / `_browser_context()` 全是 Playwright 实现，App 渠道继承
它会把一整套用不上的浏览器路径带进来，且 `fetch` 里误调 `self.browser()`
会静默开一个 Chromium。这里只保留真正共享的部分：

  * `PATH_STATUS` / `path_reset()` / `path_note()` —— 账本字段与
    BaseCrawler **逐键一致**（test_app_crawler_base 钉住），这样探针
    面板、复发账、健康解析都能无差别消费；
  * `safe_fetch()` —— 同签名、同「吞异常返回 []」语义；
  * 日志行 `[<plat>] ...` —— 健康解析的唯一数据源格式。

差异点：`login_url()` 对 App 渠道返回的是**登录入口描述**而非真实 URL
（App 没有可粘贴的登录页），由 webui 走内嵌画面流程。
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from typing import List

from core.models import FlightPrice

# 链路闸门的两件共享件**只认 `crawlers/base.py` 那一份**：等待上限
# （铁律 I6 的数字）与「把 `crawler:` 段包成 `parse_pacing` 认的形状」
# 的包装。抄第二份的后果是改一处忘一处，而这类偏差从界面上看不出来
# （后者的错法正是「配了不生效」）。导入这两个纯常量/纯函数不把浏览器
# 路径带进来——`crawlers/__init__.py` 本来就先导入 `base`。
from .base import PATH_GATE_SLEEP_CAP_S, pacing_cfg_for

# 冻结态用 exe 所在目录：否则 user_data（登录态）会落进 _internal，
# 用户找不到、升级即丢。与 main.py 同源（core.paths.app_root）。
if getattr(sys, "frozen", False):
    from core.paths import app_root as _app_root
    _REPO_ROOT = _app_root()
else:
    _REPO_ROOT = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))


def wait_ready(dev, marker: str, *, exclude=(), frames: int = 14,
               interval: float = 2.5, base_s: float = 90,
               slow_s: float = 150, slow_frame_s: float = 6.0,
               stable: int = 2) -> tuple:
    """等页面就绪：**按帧数预算 + 自适应放宽**，返回 ``(ok, xml, why)``。

    为什么不能只用固定秒数（2026-11-03 实测，14 次「首页未就绪」全是这个）：

    * 空载时一帧 ``uiautomator dump`` ≈2–3s，60s 能取 20 帧；
    * **整机跑着 5 个浏览器渠道时单帧能到 ~20s**，60s 只够 3 帧；
    * 而"连续两帧都是首页"最少要 6 帧（中间任一帧是残留弹层就重置计数）。

    于是慢机上"必然失败"，日志看起来却像"App 打不开"。改成帧数预算后，
    慢机只是等得久一点，不会判错。

    ``marker`` 是就绪标志文案（如「机票查询」）；``exclude`` 里的文案出现
    则视为**未就绪**（如残留的日历弹层标题）。
    """
    ex = tuple(x for x in (exclude or ()) if x)
    deadline = time.time() + float(base_s)
    t0 = time.time()
    hit = 0
    xml = ""
    for i in range(max(2, int(frames))):
        time.sleep(float(interval))
        xml = dev.dump() or ""
        if i == 0 and (time.time() - t0) > float(slow_frame_s):
            # 首帧就慢 → 整机被拖住，放宽总时长（仍然受帧数上限约束）
            deadline = time.time() + float(slow_s)
        ready = (str(marker) in xml) and not any(e in xml for e in ex)
        if ready:
            hit += 1
            if hit >= max(1, int(stable)):
                return True, xml, "ok"
        else:
            hit = 0
        if time.time() > deadline:
            break
    return False, xml, ("未就绪：%d 帧 / 约 %ds 内没等到「%s」"
                        % (i + 1, int(time.time() - t0), marker))


def save_scene(tag: str, xml: str, *, prefix: str = "app", root: str = "",
               limit: int = 150) -> str:
    """把「屏幕上可读的节点」落一份到 ``debug/scene``，返回落盘路径。

    为什么要有这个（2026-11-04）：App 渠道失败时账本只留一行状态
    （`no-list-page` / `无法识别的页面状态`），**看不出当时停在哪一屏**。
    这类"认不出页面"的失败最需要现场，而原来只有 qunar 自己写了一份
    `_save_fail_scene`，其它渠道出问题时**完全没有证据**——
    于是同一个失败连查几轮还在猜。

    真机 dump 常 200KB 不宜整份保存：只留前 ``limit`` 条带
    文案/id/content-desc 的节点（含坐标）。写文件失败不影响采集。

    ``TICKET_SCENE_DIR`` 是测试隔离锚（`tests/conftest.py`）：替身设备
    故意失败时按 CWD 写会把合成现场混进生产 ``debug/scene``（实测踩过）。
    """
    try:
        import os as _os
        import re as _re
        import time as _t
        d = (root or _os.environ.get("TICKET_SCENE_DIR")
             or _os.path.join("debug", "scene"))
        _os.makedirs(d, exist_ok=True)
        p = _os.path.join(d, "%s_%s_%s.txt"
                          % (prefix, _t.strftime("%Y%m%d_%H%M%S"), tag))
        rows = []
        for m in _re.finditer(r"<node\b([^>]*?)/?>", xml or ""):
            seg = m.group(1)
            txt = _re.search(r'text="([^"]*)"', seg)
            rid = _re.search(r'resource-id="([^"]*)"', seg)
            dsc = _re.search(r'content-desc="([^"]*)"', seg)
            bnd = _re.search(
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', seg)
            t = (txt.group(1) if txt else "").strip()
            i_ = (rid.group(1) if rid else "").strip()
            c_ = (dsc.group(1) if dsc else "").strip()
            if not (t or i_ or c_) or not bnd:
                continue
            rows.append("%s | %s | %s | %s,%s,%s,%s"
                        % (i_.split("/")[-1] or c_[:40], t, c_[:60],
                           bnd.group(1), bnd.group(2),
                           bnd.group(3), bnd.group(4)))
            if len(rows) >= max(1, int(limit)):
                break
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
        return p
    except Exception:
        return ""


def dismiss_until_gone(dev, marker: str, *, tries: int = 2,
                       wait_s: float = 1.5) -> tuple:
    """弹层/页面标记还在时按 BACK 尝试关掉：返回 ``(gone, xml)``。

    为什么需要（2026-11-03~04 实测 15 次）：App 里"点日期 → 日历弹层应自己关"，
    但落点偶尔偏到弹层头部，于是弹层不关。原代码**直接判失败放弃**
    （`点了日期但弹层没关` → 明细页没数据 → 整条航线白跑）。
    而这类失败是**可恢复**的：按一次 BACK 关掉弹层，再点一次就成了。

    ``marker`` 是"弹层还在"的标志文案（如 ``Search_Calendar_Dialog``）。
    """
    xml = ""
    for _ in range(max(1, int(tries))):
        try:
            xml = dev.dump() or ""
        except Exception:
            # uiautomator 挂掉时 dump 会抛：不能让它把整条采集带崩
            return False, xml
        if str(marker) not in xml:
            return True, xml
        try:
            dev.keyevent("KEYCODE_BACK")
        except Exception:
            return False, xml
        time.sleep(max(0.2, float(wait_s)))
    try:
        xml = dev.dump() or ""
    except Exception:
        return False, xml
    return (str(marker) not in xml), xml


class AppCrawler:
    """Android App 渠道基类（单设备串行采集）。"""

    name: str = "app_base"
    package: str = ""          # Android 包名
    # 与 BaseCrawler 保持一致（另有 calendar 表达"只出每日最低价"），
    # 并补 App 特有的三类拦路物：广告弹层 / 验证码 / 人脸核验。
    # 它们必须能独立入账——把"被挡住"记成 empty 或 error，等于让账本说谎。
    # 模块里那份"真机格式"的 /proc/cpuinfo（由 scripts/identity_boot_module.py 生成）
    FAKE_CPUINFO = "/data/adb/modules/tm_identity/fake_cpuinfo"
    PATH_STATUS = ("ok", "empty", "login", "blocked", "timeout",
                   "error", "parse_error", "unsupported", "calendar",
                   "soft_reject", "ad", "captcha", "face",
                   # `paced` = 我方主动不发请求（配额让位/节流跳过），
                   # 与浏览器基类同一语义：不算被拒绝，不进爬取率分母
                   "paced")
    # 会话是否可疑（webui 登录卡分层用），实例级每轮复位
    login_suspect: bool = False

    def __init__(self, config: dict, logger: logging.Logger):
        self.config = dict(config or {})
        self.logger = logger
        self.timeout_s = int(self.config.get("action_timeout_s", 60) or 60)
        self.paths: list = []
        self.last_path = ""
        self.last_status = ""
        self.last_error = ""
        self._runtime = None
        # 与浏览器渠道同一条约定：资料目录按仓库根解析，不随 cwd 漂移
        # （登录态快照要落在这里，chdir 后写错位置用户会找不到自己的凭证）。
        # 根目录走唯一口径（config > TM_USER_DATA_DIR > user_data）：
        # 测试里的假渠道曾把快照/账本写进真 user_data（r972）。
        from core.yield_stats import user_data_root
        self.user_data_root = os.path.abspath(
            os.path.join(_REPO_ROOT, user_data_root(self.config)))
        # 登录态快照：进程内只尝试恢复一次（每个渠道各一次）。
        # 只导出不恢复等于白存——用户「登录一次」后换次进程又得重登。
        self._snapshot_restored = False
        # 简易验证码/滑块处理器：**必须在这里挂一次**。
        #
        # 原先只有 `BaseCrawler.__init__` 调 `ensure_slider_handler()`，而
        # AppCrawler 不继承 BaseCrawler（见模块头：只共享账本契约）——
        # 于是 App 渠道**从来没注册过处理器**，`slider.auto` 配什么都没用，
        # 滑块能力在 App 侧等于死的。2026-11-05 实测发现并补上。
        try:
            from crawlers.challenge import ensure_slider_handler
            ensure_slider_handler(
                self.config,
                user_data_dir=self.user_data_root,
                profile=str(getattr(self, "package", "") or ""),
                logger=logger)
        except Exception:
            pass

    # ---------- 登录态快照 ----------
    def _snapshot_manager(self, dev):
        """构造快照管理器；配置关闭或包名为空时返回 None。"""
        android = self.config.get("android") or {}
        if android.get("snapshot") is False:
            return None
        if not self.package:
            return None
        try:
            from core.android.snapshot import SnapshotManager, SnapshotStore
            store = SnapshotStore(
                os.path.join(self.user_data_root, "android_snapshots"))
            return SnapshotManager(dev, store, self.package)
        except Exception:
            return None

    # 登录墙判据（子类覆盖）：默认认手机号表单 + 「立即登录」类文案。
    # 各渠道登录墙形态不同，但「恢复快照后仍在登录页」这件事必须能判出来。
    #
    # r723：**验证码页也是登录墙**。真机实测：输手机号收到短信后，页面变成
    # 「请输入验证码 / 验证码已发送到 +86 199****8573 / 46秒后重发」，
    # 原先两条判据都不匹配 → 登录墙被当成普通页，继续去找城市位，
    # 账本最后记成「选日期失败」/「设到达城市失败」，
    # 用户按提示去查选择器，实际只要重登一次。
    LOGIN_FORM_MARKS = ("请输入手机号", "获取验证码",
                        "请输入验证码", "验证码已发送")

    def is_login_wall(self, xml: str) -> bool:
        """当前页面是不是登录墙（子类可加自己的判据）。"""
        return any(m in (xml or "") for m in self.LOGIN_FORM_MARKS)

    def _clear_blockers(self, dev, xml: str):
        """处理页面拦路物。返回 (xml, Block)。

        策略分级（与 PC/H5 渠道的处置规范一致）：
          * **广告**：只是遮挡 → 自动点关闭，最多两次；关不掉就上报 `ad`，
            让用户看到"被广告挡住"，而不是记成没数据。
          * **验证码**（含滑块/图形点选）：风控已触发，记 `captcha`，
            开干预窗口人工处理。
          * **人脸识别**：生物特征核验，自动化不可行 → 记 `face`，
            明确告知用户必须本人操作，且不会被重试掩盖。
          * **登录**：记 `login`，由内嵌登录画面处理。
        """
        from .app_blockers import (BLOCK_CAPTCHA, BLOCK_FACE, Block,
                                   detect_block)
        from .challenge import ChallengeContext, handle_device

        block = detect_block(xml)
        if block.kind in (BLOCK_CAPTCHA, BLOCK_FACE):
            # 挑战处置接缝：注册了处理器就交给它（解完自行 dump）；
            # 没注册或没接住 → 照现行处置返回给调用方。
            out = handle_device(dev, xml, ChallengeContext(
                plat=self.name, surface="APP", device=dev, crawler=self,
                signal=block))
            if out is not None and out.handled:
                xml = dev.dump()
                if not xml:
                    return "", Block("", "no-ui")
                block = detect_block(xml)
                if block.kind in (BLOCK_CAPTCHA, BLOCK_FACE):
                    return xml, block

        # 降级关闭阶梯（r1063 T65）：广告层不该因为"文案里没写关闭"就整轮停手。
        # 顺序＝从最确定到最粗暴：命中坐标 → BACK → 右上角热区 → 遮罩空白处。
        for _round in range(2):
            block = detect_block(xml)
            if block.kind != "ad":
                return xml, block
            done = ""
            if block.close_xy:
                self.logger.info("[%s] 关闭广告弹层 %s", self.name,
                                 block.close_xy)
                dev.tap(*block.close_xy)
                done = "点关闭钮"
            else:
                # ① BACK：绝大多数营销层都吃返回键（比盲点安全）
                try:
                    dev.keyevent("BACK")
                    done = "BACK 键"
                except Exception:
                    done = ""
                time.sleep(1.2)
                _x1 = dev.dump()
                if _x1 and detect_block(_x1).kind != "ad":
                    xml = _x1
                    done += "（首次生效）"
                    self._note_ad_closed(done)
                    return xml, detect_block(xml)
                # ② 右上角固定热区（图标关闭钮常在这，UI 树里可能没有节点）
                _wh = self._screen_wh(dev)
                if _wh:
                    dev.tap(int(_wh[0] * 0.92), int(_wh[1] * 0.09))
                    done = "右上角热区"
                time.sleep(1.0)
                _x2 = dev.dump()
                if _x2 and detect_block(_x2).kind != "ad":
                    xml = _x2
                    self._note_ad_closed(done)
                    return xml, detect_block(xml)
                # ③ 点遮罩空白（顶部 1/5 处、水平居中）
                if _wh:
                    dev.tap(int(_wh[0] * 0.5), int(_wh[1] * 0.06))
                    done = "点遮罩"
            time.sleep(1.5)
            xml = dev.dump()
            if not xml:
                return "", Block("", "no-ui")
            if detect_block(xml).kind != "ad" and done:
                self._note_ad_closed(done)
                return xml, detect_block(xml)
        # 两轮都没关掉：如实上报（**这次记下试过哪几招**，便于下次改判据）
        return xml, detect_block(xml)

    @staticmethod
    def _screen_wh(dev):
        """(w, h)：真实 API 是 `window_size()`；读不到返回 None（不做猜测）。

        为什么单独一个方法：`dev.screen_size()` **不存在**，而把它写在
        try/except 里被吞掉，会让"右上角热区/点遮罩"两级兜底永久静默失效
        ——这正是 T59 那条教训（fail-soft 必须留证据）。
        """
        for name in ("window_size", "size"):
            fn = getattr(dev, name, None)
            if not callable(fn):
                continue
            try:
                got = fn()
                w, h = int(got[0]), int(got[1])
                if w > 0 and h > 0:
                    return (w, h)
            except Exception:
                continue
        return None

    def _note_ad_closed(self, how: str) -> None:
        """广告关掉了：把"用哪一招"记进路径账（r1063 T65）。

        没有这一行，下次同一个弹层还得重新猜；有了它，账本能回答
        「这家的广告是靠 BACK 关掉的」。
        """
        try:
            self.path_note("app-ad", "closed", detail="广告已关闭：%s" % how)
        except Exception:
            pass

    @staticmethod
    def _looks_blank(xml: str) -> bool:
        """页面是不是还没渲染出来（白屏中间态）。

        真机：force-stop 后立刻发深链，会停在 `TabHomeActivity` 的白屏，
        dump 一个节点都没有，等多久也不自愈。把这种状态当成「已登录」
        会让快照恢复被跳过，整轮跑在空页面上。
        """
        return (xml or "").count("<node") < 6

    def restore_login_snapshot(self, dev) -> bool:
        """首次采集前恢复登录态；返回 True 表示这次真的恢复了。

        - 没有快照、配置关闭、设备不可用，都**静默跳过**（不是错误）；
        - 一个进程内只尝试一次，避免每轮都重启 App 白花时间；
        - 恢复失败要留痕：`snap-restore` 记一条，用户能看到是「恢复失败」
          而不是「明明登录过却还要重登」。

        **设备上已经登录着就绝不恢复**：快照是某一时刻的副本，用完即旧。
        去哪儿的会话凭据还带服务端刷新（真机实测：刚登录完导出快照，
        立刻恢复 → App 回登录墙；不恢复、直接重启 → 登录态正常）。用旧
        副本盖掉设备上更新的会话，等于每次采集都把用户踢下线。
        """
        if self._snapshot_restored:
            return False
        self._snapshot_restored = True
        # 没有快照就没有恢复可谈：**绝不能为此重启 App 去探测页面**。
        # 旧实现先 app_stop + 启动 + 轮询 dump 判断「是否已登录」，再去看
        # 有没有快照——没快照的用户每轮白重启一次 App，而且这次 dump 会
        # 吞掉启动首屏的广告/弹层，后面 `_clear_blockers` 再也看不到它，
        # 广告就那么盖着页面（实测：整轮零数据且看不出原因）。
        try:
            _mgr0 = self._snapshot_manager(dev)
            if _mgr0 is None or not _mgr0.store.exists(self.name):
                return False
        except Exception:
            return False
        # 设备已登录：保持现状，不动它的数据。
        try:
            dev.app_stop(self.package)
            time.sleep(1.5)
            if getattr(self, "home_uri", ""):
                dev.deep_link(self.home_uri)
            else:
                dev.app_start(self.package)
            deadline = time.time() + 30
            xml = ""
            while time.time() < deadline:
                time.sleep(2.5)
                xml = dev.dump() or ""
                if xml and not self._looks_blank(xml):
                    # 登录页是**启动首屏**，不等于未登录（去哪儿实测：
                    # 停在 UCLoginByPhoneActivity 时深链能进首页且是登录态）。
                    # 首屏就是登录墙时再发一次深链，能进首页就算已登录。
                    if self.is_login_wall(xml) and getattr(self, "home_uri", ""):
                        dev.deep_link(self.home_uri)
                        time.sleep(6)
                        xml = dev.dump() or ""
                    break
            if xml and not self._looks_blank(xml) and \
                    not self.is_login_wall(xml):
                self.logger.info("[%s] 设备上已登录，跳过快照恢复", self.name)
                self._app_fresh = True      # 刚冷启过，本轮不必再启一次
                return False
        except Exception:
            pass
        mgr = self._snapshot_manager(dev)
        if mgr is None:
            return False
        try:
            if not mgr.store.exists(self.name):
                return False
            ok, detail = mgr.restore(self.name)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        if ok:
            self.logger.info("[%s] 已恢复登录态快照（%s）", self.name, detail)
            # 恢复了快照但这台设备仍停在登录墙 → 快照**已失效**（会话过期 /
            # 被风控注销）。这跟「恢复失败」是两件事，用户要的处置也不同：
            # 前者该重新登录，后者该查文件。不判这一下，账本只会有
            # 「恢复 ok」+「要求登录」，读者看不出到底哪一步出了问题。
            expired = ""
            try:
                wall = dev.dump() or ""
                if wall and self.is_login_wall(wall):
                    expired = "；快照已失效（仍停在登录墙，需重新登录）"
            except Exception:
                pass
            # r640c：账本契约是「ok 必须带行数」——快照恢复本身不取数，
            # 显式 rows=0 并写明这是登录态恢复、不是一次成功取数，
            # 免得被读成「恢复了快照 = 查到了航班」。
            self.path_note("snap-restore", "ok", rows=0,
                           detail="登录态恢复（非取数）："
                                  + str(detail)[:100] + expired)
            # 恢复里刚 app_start 过，等界面稳定再让调用方继续判断；
            # 否则紧接着的 dump 可能还是旧的（权限框/首页都读不到）。
            #
            # r720：只看「不是登录墙」不够。快照 restore 会**重启 App**，
            # 冷启动到首页面板实测 8–12s；原先这里只 `sleep(2)`，调用方拿到的
            # 是启动首屏（或登录墙之外的白屏中间态），里面没有城市位/搜索面板
            # → `_set_city` 找不到 `atom_flight_tv_dep_city` → 整轮记
            # `set-city-dep`（真机实测三条航线全 0 条，日志却报「设出发城市失败」，
            # 把启动时序问题伪装成城市选择失败）。
            # 这里轮询到「有界面且不是白屏」为止；停在登录墙则如实标注失效。
            deadline = time.time() + 45
            ready = ""
            while time.time() < deadline:
                try:
                    probe = dev.dump() or ""
                except Exception:
                    probe = ""
                if probe and not self._looks_blank(probe):
                    ready = probe
                    break
                time.sleep(2.5)
            if ready and self.is_login_wall(ready):
                expired = "；快照已失效（仍停在登录墙，需重新登录）"
            elif not ready:
                expired = "；快照恢复后界面未就绪（45s 内无可用 dump）"
            self.path_note("snap-restore", "ok", rows=0,
                           detail="登录态恢复（非取数）："
                                  + str(detail)[:100] + expired)
            self._app_fresh = True
            return True
        self.logger.warning("[%s] 登录态快照恢复失败：%s", self.name, detail)
        # 「设备上的登录态比快照新」不是失败，是刻意保留——记成 error 会
        # 让健康卡显示「快照恢复失败」，而实际情况正相反（用户在 App 里
        # 刚登过，恢复才是错的）。这类记录用 skipped 语义单独标注。
        if "比快照新" in str(detail):
            self.path_note("snap-restore", "ok", rows=0,
                           detail="跳过恢复（非失败）：" + str(detail)[:120])
            return False
        self.path_note("snap-restore", "error", detail=str(detail)[:150])
        # 「拿不到 root」这类**环境原因**恢复不了快照时，别把 App 留在半死
        # 状态：设备上本来就是登录着的（快照只是副本）。冷启一次再判——
        # 这一步不改变「恢复失败」的事实（上面已落 error），只保证本轮还能采。
        page = self._cold_start_and_probe(dev)
        if page and not self.is_login_wall(page):
            self.logger.info("[%s] 快照恢复失败但设备仍登录，继续采集", self.name)
        elif page:
            self.login_suspect = True
        return False

    def _cold_start_and_probe(self, dev, wait_s: float = 30) -> str:
        """冷启 App 并等到「有界面」；返回最后一帧 dump（失败返回 ""）。

        与「设备已登录就跳过恢复」那段同律：冷启动到首页要 8–12s，取太早
        会拿到启动首屏/白屏，后面 `_set_city` 会读成「没有城市控件」。
        """
        try:
            dev.app_stop(self.package)
            time.sleep(1.5)
            if getattr(self, "home_uri", ""):
                dev.deep_link(self.home_uri)
            else:
                dev.app_start(self.package)
            deadline = time.time() + wait_s
            page = ""
            while time.time() < deadline:
                time.sleep(2.5)
                page = dev.dump() or ""
                if page and not self._looks_blank(page):
                    return page
            return page
        except Exception:
            return ""

    def _ensure_app_fresh(self, dev) -> bool:
        """每条航线开始前把 App 冷启一次，拿一个确定的起点。

        现场实证（2026-11-01，去哪儿 App）：同一进程里第一条航线
        （19:16 SHA→BKK）成功；后续航线**复用上一轮界面**时开始卡在设城市
        （20:29 `set-city-dep`、20:34 `set-city-arr`），而手动 force-stop
        后同一坐标一次点开——多轮操作留下的广告/动效/子页残留会吞掉点击。
        快照恢复那条路已经冷启过时（`_app_fresh`）不重复启。
        """
        if getattr(self, "_app_fresh", False):
            self._app_fresh = False
            return True
        # keep_alive（默认关）：上一轮成功且 App 已在前台时不再冷启。
        # 冷启本身是一串设备校验 + 首屏风控埋点，频繁冷启更「像自动化」；
        # 但残留界面会吞点击（见上：设城市连续失败），所以默认仍冷启。
        if self._keep_alive() and getattr(self, "_last_round_ok", False):
            try:
                act = str(dev.current_activity() or "")
            except Exception:
                act = ""
            if self.package and act.split("/")[0].strip() == self.package:
                self.logger.info("[%s] 复用前台 App（keep_app_alive）", self.name)
                return True
        page = self._cold_start_and_probe(dev)
        self._app_fresh = False
        return bool(page and not self._looks_blank(page))

    def _dismiss_system_prompts(self, dev) -> int:
        """点掉系统权限弹窗（通知/定位等）。返回处理次数。

        换机、重装、`pm clear` 之后，智行每次启动都可能弹系统级权限框，
        它盖在首页上——采集会读成「首页未就绪 / 页面认不出」，被误判成
        App 改版。这不是风控，可以代点「允许」。

        只看 **activity** 决定要不要介入：不在权限控制器时**不读页面**。
        读页面会消耗调用方的页面序列（实测把广告页吃掉，导致广告关不掉）。
        """
        from .app_zhixing_nav import nodes
        # **权限框**与**首启协议页**分开处理（2026-11-06 补）：
        # `pm clear`/新机后 App 先弹系统权限框，**再**停在启动页要你同意
        # 用户协议（实测携程 `CtripSplashActivity` 的「同意并继续」）。
        # 原来只认 `permission`，于是卡在协议页不动，账本记
        # 「40s 内未到机票表单页」——看起来像渠道坏了，其实只差点一下。
        _PERM_ALLOW = ("允许", "始终允许", "仅在使用中允许", "确定", "知道了")
        _SPLASH_ALLOW = ("同意并继续", "同意", "接受", "跳过", "我知道了")
        handled = 0
        deadline = time.time() + 12
        while time.time() < deadline and handled < 6:
            try:
                act = (dev.current_activity() or "").lower()
            except Exception:
                act = ""
            if "permission" in act:
                allow = _PERM_ALLOW
            elif any(k in act for k in ("splash", "loading", "welcome",
                                        "guide", "agreement", "privacy")):
                allow = _SPLASH_ALLOW
            else:
                return handled
            xml = dev.dump() or ""
            hit = None
            for n in nodes(xml):
                if (n.text or "").strip() in allow:
                    hit = n
                    break
            if hit is None:
                time.sleep(1)
                continue
            self.logger.info("[%s] 关闭系统权限弹窗：%s", self.name, hit.text)
            dev.tap(hit.cx, hit.cy)
            handled += 1
            time.sleep(1.5)
        return handled

    def path_reset(self):
        self.paths = []
        self.last_path = ""
        self.last_status = ""

    def path_note(self, path: str, status: str, rows: int = 0,
                  date: str = "", detail: str = "", ms: int = 0,
                  http_status: int = 0, url: str = ""):
        if status not in self.PATH_STATUS:
            status = "error"
        rec = {"path": str(path), "status": status,
               "rows": int(rows or 0), "date": str(date or ""),
               "detail": str(detail or "")[:160], "ms": int(ms or 0),
               "http": int(http_status or 0),
               "mobile": True}
        if url:
            rec["url"] = str(url)[:500]
        if not hasattr(self, "paths"):
            self.path_reset()
        self.paths.append(rec)
        self.last_path = rec["path"]
        self.last_status = rec["status"]
        return rec

    # ---------- 链路闸门（r1063 T9）：用某个主阶段之前先问一次 ----------
    #
    # **只闸五个主阶段**（通路名与 `core/channels.PATH_CN` 逐字一致）：
    #
    #   ``app-login``     App 登录 / 会话前置
    #   ``app-list``      列表（设航线 → 选日期 → 搜索 → 解析那一整段）
    #   ``app-calendar``  价格日历
    #   ``往返``          往返总价
    #   ``low-fare``      低价机票（发现源）
    #
    # **细段不接闸门**（``app-city*`` / ``app-date`` / ``app-form`` /
    # ``app-search`` / ``app-dump`` / ``app-blocker`` / ``android-*``）：
    # 细段属单次交互内部——它们不是「另一条路」，而是同一条路上的第 3、5、
    # 7 步。停掉一步，拿到的既不是「这条路的空结果」，也不是「另一种口径
    # 的价」，只剩「点了城市、不选日期就搜索」这种半截流程；用户看到的效果
    # 是「我把选日期关了，结果整家一条数据都没有」。所以策略矩阵对细段记
    # ``na``（结构上不适用），**不记** ``n``（未接入的缺陷）：``n`` 会变成
    # 待补的活，``na`` 才说得清这是刻意不闸。
    #
    # **等待一律在设备锁之外**（App 渠道的设备是串行独占的）：五家的
    # ``fetch()`` / ``calendar()`` / ``low_fare()`` 都在
    # ``with rt.device_lock(owner=self.name)`` **之前**问闸门——在锁里等，
    # 排队等锁的其它 App 渠道会全体陪跑，而它们等的是「我们睡觉」。
    # ``path_gate`` 里另有一道兜底（见 `_device_lock_held`），万一将来有人
    # 在锁里问，也不许把采集线程钉在等待上。
    def _pacing_ctx(self):
        """本采集器的节流上下文（懒建一次，之后复用）。

        只承载**链路桶**：渠道级的账 `main.py` 已经为每条查询记过一次
        （`AppCrawler.path_gate` 因此只写 `channel=False`），共用一份实例
        会把同一个请求记两遍。

        配置层由 `pacing_cfg_for` 包一层 `crawler:`：采集器收到的是
        `crawler:` 段（`main.py:1910`），直接递给 `Pacing` 会让这份实例
        永远跑在 `DEFAULTS` 上（`min_gap_s 0`）——「配了不生效」且从数字
        上看不出来。这个包装只认 `crawlers/base.py` 那一份，不在这里抄
        第二遍。主流程/测试要注入时把 `self._pacing` 填上即可。

        **刷新边界（r1063 fix-wave 1 起已接线，与 `crawlers/base.py` 同一份
        事实，别默默不生效）**：热重载时 `main.py::reload_config()` 会遍历
        **已经建过**的采集器实例（含 App 采集器，`rt["pacing"]` 之外这一份
        也算在内）逐份 `refresh()` 这里的私有实例——静默窗 / 错峰 / 并发这三
        条策略是 `parse_pacing` 的产物，不刷它就等于「保存后要等下一轮重建
        实例」。懒建的实例下次构造时自然读到新 cfg。闸门真正用的速率值来自
        **参数层**（`Pacing._rate_limits` 优先 `strategy_params`），本实例
        的 cfg 只在参数层查不到/非法时兜底。 `clear_crawlers()` 重建采集器
        实例时才会重新走这里读 cfg；私有实例不会随热重载 refresh() 之外被替换。

        构造失败是**环境级事实，一次说清就够**：`_pacing_failed` 记住
        「已经说过」，之后每次闸门直接放行、不再重建也不再刷 warning。
        原来失败后存的是 `None`，下一处闸门又见到 `None` → 又重建 → 又
        告警，一次 `fetch()`（登录/列表两段）就能刷 2–3 条同样的日志，
        读起来像「闸门反反复复坏掉」。
        """
        pac = getattr(self, "_pacing", None)
        if pac is not None:
            return pac
        if getattr(self, "_pacing_failed", False):
            return None
        try:
            from core.pacing import Pacing
            pac = Pacing(pacing_cfg_for(self.config))
        except Exception as e:
            # 闸门是采集的必经路径：构造不出来只能放行（并留痕一次），
            # 让它抛异常等于把整家渠道停采。
            pac = None
            self._pacing_failed = True
            log = getattr(self, "logger", None)
            if log is not None:
                log.warning("[%s] 链路闸门不可用（%s）：本轮按放行处理",
                            self.name, e)
        self._pacing = pac
        return pac

    def _device_lock_held(self) -> bool:
        """当前是否正持有设备锁（闸门据此拒绝在锁内睡）。

        判据是运行时的持有者标签 == 本渠道名：App 渠道每轮独占设备，
        「锁上写着我的名字」就等于「这一问是在锁里问的」。拿不到运行时/
        假运行时不提供 `lock_state()` 时按「没持锁」处理（fail-soft：
        这个判断只用来决定要不要等，判不出来时不该把闸门卡死）。
        """
        rt = getattr(self, "_runtime", None)
        fn = getattr(rt, "lock_state", None)
        if not callable(fn):
            return False
        try:
            st = fn() or {}
        except Exception:
            return False
        owner = str(st.get("owner") or "") if isinstance(st, dict) else ""
        return bool(owner) and owner == str(getattr(self, "name", "") or "")

    def path_gate(self, path: str, dim: str = "", *, date: str = "") -> bool:
        """用 `path` 这个阶段之前问一次：能不能用、要不要等。False=跳过它。

        决策顺序与口径全部在 `core.pacing.Pacing.gate_path`（策略停用 →
        熔断 → 限速），这里只做四件事：**封顶等待**、**绝不在设备锁内等**、
        **记 paced 证据**、**只记链路桶**。

        * `allow=False`：只跳过**这一个阶段**，调用点返回该阶段的空结果
          （`[]`），**不记失败**——`paced` 的语义是「我方主动不发请求」，
          记成失败会拉开整家渠道的熔断（那正是本闸门要挡的连坐）。
        * 等待封顶 `PATH_GATE_SLEEP_CAP_S`（铁律 I6）；持有设备锁时**不等**
          （只留一条 warning：限速被跳过的原因必须能事后读出来）。
        * 记账**只写 `渠道|链路` 桶**（`channel=False`），与浏览器端同一
          口径；旧签名（`record` 不吃 `channel=`）时**宁可这条链路不记账**。

        `dim` 是维度段（App 渠道传 `detail` / `calendar` / `round_trip` /
        `low_fare`）：`渠道/维度/链路` 的覆盖要靠它才查得到。
        """
        pac = self._pacing_ctx()
        if pac is None:
            return True
        try:
            allow, wait_s, why = pac.gate_path(self.name, dim, path)
        except Exception as e:
            log = getattr(self, "logger", None)
            if log is not None:
                log.warning("[%s] 链路闸门判定失败（%s）：%s 按放行处理",
                            self.name, e, path)
            return True
        if not allow:
            self.path_note(path, "paced", date=date, detail=why)
            log = getattr(self, "logger", None)
            if log is not None:
                log.info("[%s] 跳过阶段 %s%s：%s", self.name, path,
                         ("（%s）" % date) if date else "", why)
            return False
        try:
            wait = float(wait_s or 0)
        except (TypeError, ValueError):
            wait = 0.0
        if wait > 0:
            if self._device_lock_held():
                # 在锁里睡 = 让排队等设备的其它 App 渠道替我们等。宁可
                # 这一轮少等（限速的「欠账」不补），也不占着设备睡。
                log = getattr(self, "logger", None)
                if log is not None:
                    log.warning("[%s] 阶段 %s 还要等 %.1fs，但此刻正持有设备锁："
                                "跳过等待（不许占着设备睡）", self.name, path, wait)
            else:
                time.sleep(min(wait, PATH_GATE_SLEEP_CAP_S))
        # 只有**这个阶段真的要动一次设备**时才记账，且只记链路桶。
        # 旧签名时不记：退回 `record(plat, path=path)` 会把渠道桶一起写，
        # `per_minute` 当场减半、`min_gap` 当场翻倍。
        try:
            pac.record(self.name, path=path, channel=False)
        except TypeError:
            pass
        except Exception:
            pass
        return True

    # ---------- 运行时 ----------
    def runtime(self):
        if self._runtime is None:
            from core.android.runtime import get_runtime
            self._runtime = get_runtime(self.config, self.logger)
        return self._runtime

    # ---------- 调用入口 ----------
    #: 渠道是否支持往返（App 渠道目前都只做单程）。不支持时**必须显式
    #: unsupported 落账并返回空**——静默忽略 ret_date 会把单程价当成往返
    #: 总价，推送/走势据此报警（浏览器渠道 TRIP 同款口径）。
    supports_round_trip: bool = False

    def safe_fetch(self, from_city: str, to_city: str, dates: List[str],
                   ret_date: str = "") -> List[FlightPrice]:
        self.path_reset()
        self.last_error = ""
        # `login_suspect` 是**本轮观测**，不是终身标记（2026-11-05）。
        # 五个 App 渠道共 21 处只会置 True、没有一处复位，于是第一次登录墙
        # 之后 `_round_signals()["login_wall"]` 永远为真 →
        # `_note_round_risk()` 每轮都记 `note_result(False, device_risk=True)`。
        # 实测同一轮日志既是「抓取完成，得到 1 条记录」又是
        # 「登录连续失败 6 次」；连击数只涨不落，风险分升到 slow，
        # 间隔放大 2.5× 且只跑快层——把本来能出数的渠道压死。
        # 按轮清零后，判据只认本轮证据（本轮的 login 通路/本轮新置的 suspect）。
        self.login_suspect = False
        # 统一策略闸门（与浏览器渠道同一份引擎）：只有 long-term 档会关。
        self.policy_blocked = False
        # 维度（r1063 fix-wave 2）：闸门开关可被 `渠道/维度` 层覆盖，把本次
        # 采集的维度递给它。口径与 `main._dim_of_query()` 同一句（App 渠道
        # 目前不支持往返，真的给了返程日也会在下面被显式落账，但维度仍按
        # 「挂了返程日 = 往返」算，与主扫描一致）。
        if not self._policy_gate(
                dim="round_trip" if str(ret_date or "").strip() else "detail"):
            return []
        try:
            if ret_date and not self.supports_round_trip:
                self.logger.warning(
                    "[%s] 往返明细暂不支持（返程 %s），未发起单程查询",
                    self.name, ret_date)
                self.path_note("TRIP", "unsupported",
                               detail="往返明细暂不支持，未发起单程查询")
                return []
            self.logger.info("[%s] 开始抓取 %s->%s 日期=%s",
                             self.name, from_city, to_city, dates)
            results = self.fetch(from_city, to_city, dates,
                                 ret_date=ret_date) or []
            if not results and not self.paths:
                # **归因缺口**：既没出数、又一条通路都没记。
                # 这时 `statuses_ok([])` 返回空 path，账本只能落成 `unknown`
                # —— 实测 app_qunar 攒了 35 条这样的记录，报表上看得见
                # "失败"，却完全看不出卡在哪一步，和真风控混在一起无从分辨。
                # 所以这里必须显式留痕：**允许说不出原因，不允许什么都不说**。
                self.path_note(
                    "app-silent", "error",
                    detail=self.last_error or "fetch 返回空且未记录任何通路")
            self.logger.info("[%s] 抓取完成，得到 %d 条记录",
                             self.name, len(results))
            self._last_round_ok = bool(results)
            return results
        except Exception as e:  # 设备掉线/解析失败都走这里
            self._last_round_ok = False
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.warning("[%s] 抓取失败: %s", self.name, self.last_error)
            if not any(p.get("status") == "error" for p in self.paths):
                self.path_note("app-error", "error", detail=self.last_error)
            return []
        finally:
            # 登录账本与风险评分：**只记账、不改流程**（异常全吞）。
            # 「连续登录失败后还按 30 分钟节奏重试」本身就是撞库特征，
            # 是「越重登越登不上」的机制，所以必须跨进程记住连击数。
            self._note_round_risk()
            # 爬取率账本：与浏览器渠道同一口径（rows>0 才算 ok），
            # 这样两端的成功率可以在同一张表里比。
            self._note_round_yield()
            self._policy_note_round()

    # ---------- 统一策略 ----------
    def _policy_engine(self):
        """策略引擎（与 BaseCrawler 同一个 `core/policy.py`，判据不漂移）。"""
        eng = getattr(self, "_policy_eng", None)
        if eng is not None:
            return eng
        try:
            from core.policy import default_engine
            cfg = getattr(self, "config", None)
            self._policy_eng = default_engine(
                cfg if isinstance(cfg, dict) else {},
                repo_root=_REPO_ROOT,
                profile=str(getattr(self, "profile_name", "") or self.name))
        except Exception:
            self._policy_eng = None
        return self._policy_eng

    def _policy_enabled(self, dim: str = "") -> bool:
        """``crawler.policy_gate`` 总开关（与浏览器渠道同一把，默认开）。

        用 ``getattr`` 取 config：单测里常用 ``__new__`` 造桩对象，没有走
        ``__init__`` 就没有 config——这里不能因此抛异常（fail-soft 是本仓库
        对这类辅助方法的一贯约定）。

        与浏览器侧 ``BaseCrawler._policy_enabled`` 同一口径：**现读参数层**
        （``switch_on("policy_gate.enabled")``），``self.config`` 只作读不到时
        的兜底——它是构造时注入的冷冻配置，``reload_config()`` 不重建采集器，
        拿它判开关等于「保存后要重启才生效」（复核 2026-11-06 Important）。

        ``dim``（r1063 fix-wave 2）：``渠道/维度`` 层写的
        ``policy_gate.enabled: false`` 要能让这个采集器看到；缺省空串 = 只看
        渠道层，与迁移前逐位相同。
        """
        cfg = getattr(self, "config", None)
        raw = cfg.get("policy_gate") if isinstance(cfg, dict) else None
        try:
            from core.pacing import _flag
            from core.strategy_params import switch_on
            return switch_on("policy_gate.enabled",
                             plat=str(getattr(self, "name", "") or ""),
                             dim=str(dim or ""), fallback=_flag(raw, True))
        except Exception:            # 参数层不可用：按本实例配置（旧行为）
            if isinstance(raw, str):
                return raw.strip().lower() not in ("0", "false", "no", "off", "")
            return True if raw is None else bool(raw)

    def _policy_gate(self, dim: str = "") -> bool:
        """采集入口闸门。App 端补两条浏览器端没有的信号：

        * 设备/隐藏自检分（来自 `runtime.status()` 的最近一次硬化报告）；
        * 上一轮是否停在登录墙/验证码（`login_suspect` + 本轮账本）。

        没有这些信号时 score 达不到 human/rotate 档，因此**默认全放行**，
        既有的「登录墙照记照跑」语义不变。

        `dim` 原样递给 `_policy_enabled()`（维度级覆盖要用它）。
        """
        if not self._policy_enabled(dim=dim):
            return True
        eng = self._policy_engine()
        if eng is None:
            return True
        ident = self._identity_scores()
        try:
            pol = eng.decide(self.name, two_way=False,
                             captcha=bool(self.login_suspect), **ident)
        except Exception:
            return True
        self.last_policy = pol.as_dict()
        if pol.allow:
            return True
        self.policy_blocked = True
        log = getattr(self, "logger", None)
        if log is not None:
            log.warning(
                "[%s] 策略暂停本轮（%s，%ds 后可试）：%s", self.name, pol.state,
                pol.wait_s(), "／".join(pol.reasons)[:200])
        return False

    def _identity_scores(self) -> dict:
        """从 runtime 的硬化报告里取身份/隐藏自检分（取不到就不传）。"""
        out = {}
        try:
            rt = self.runtime()
            st = rt.status() if rt is not None else {}
            ip = (st.get("identity") or {}).get("audit") or {}
            if isinstance(ip.get("score"), (int, float)):
                out["identity_score"] = ip["score"]
            sp = ((st.get("stealth") or {}).get("detect") or {})
            if isinstance(sp.get("score"), (int, float)):
                out["stealth_score"] = sp["score"]
        except Exception:
            pass
        return out

    def _policy_note_round(self) -> None:
        """把本轮事实喂回策略层（推进状态机）。全吞异常，绝不改流程。"""
        eng = self._policy_engine()
        if eng is None:
            return
        try:
            statuses = [p.get("status") for p in (self.paths or [])]
            eng.decide(self.name, two_way=False,
                       captcha=any(s in ("captcha", "face") for s in statuses),
                       login_wall=("login" in statuses) or self.login_suspect,
                       soft=("soft_reject" in statuses),
                       **self._identity_scores())
            self._policy_cache = None
        except Exception:
            pass

    def _note_round_yield(self) -> dict:
        try:
            from core.yield_stats import (default_ledger, statuses_ok,
                                          is_paced, user_data_root)
            cfg = getattr(self, "config", None) or {}
            # 与浏览器渠道同一口径（config > TM_USER_DATA_DIR > user_data）
            root = user_data_root(cfg)
            profile = str(getattr(self, "profile_name", "") or self.name)
            led = default_ledger(os.path.join(_REPO_ROOT, root), profile)
            # 主动让位（配额/节流）**不算样本**：既不是成功也不是失败。
            # 记进去会把"我方克制"读成"渠道不行"。
            if is_paced(self.paths):
                return {"ok": None, "rows": 0, "path": "paced", "skipped": True}
            ok, rows, path = statuses_ok(self.paths)
            if not ok and getattr(self, "_last_round_ok", False):
                ok, rows = True, rows or 1
                path = path or (self.last_path or "unknown")
            # 顺便记下主通路的**状态**：账本只累加 ok/fail 的话，
            # "确实没票(empty)"、"解析失败(error)"、"登录墙(login)"
            # 会混成一个 fail 数字，处置方向完全不同（2026-11-05）。
            _st = next((str(r.get("status") or "") for r in (self.paths or [])
                        if str(r.get("path") or "") == path), "")
            led.note(self.name, path or "unknown", ok, rows=rows, status=_st)
            return {"ok": ok, "rows": rows, "path": path}
        except Exception:
            return {}

    # ---------- 登录账本 / 风险评分 ----------
    def _ledger(self):
        """登录账本（懒加载；user_data 找不到/写入失败都当没有）。"""
        led = getattr(self, "_login_ledger", None)
        if led is not None:
            return led
        try:
            from core.riskscore import default_ledger
            from core.yield_stats import user_data_root
            root = user_data_root(self.config)
            # AppCrawler 没有 profile_name（那是浏览器基类的），用 getattr 取：
            # 直接 self.profile_name 会抛 AttributeError，被这里吞掉后账本
            # 静默失效——正是「记了但没记上」那类最难查的坑。
            profile = str(getattr(self, "profile_name", "") or self.name)
            self._login_ledger = default_ledger(os.path.join(
                _REPO_ROOT, root), profile)
        except Exception:
            self._login_ledger = None
        return self._login_ledger

    def _round_signals(self) -> dict:
        """从本轮账本里抽风控信号（全部是**已发生的事实**）。"""
        statuses = [p.get("status") for p in (self.paths or [])]
        return {
            "login_wall": ("login" in statuses) or bool(self.login_suspect),
            "captcha": any(s in ("captcha", "face") for s in statuses),
            "soft": "soft_reject" in statuses,
            "blocked": "blocked" in statuses,
        }

    def _note_round_risk(self) -> dict:
        """把本轮结果写进登录账本，并按风险分给出「下一步该怎么办」。

        App 渠道没有 HTTP 状态码，403/429 那一路信号取不到；这里只喂
        能观测到的三类：登录墙、验证码/人脸、软拒。**不喂猜测值**。
        """
        try:
            sig = self._round_signals()
            led = self._ledger()
            if led is None:
                return {}
            # **只记「登录相关」的结果**。这里不是「每轮成功/失败」的计数器：
            # 超时、解析失败、真无票都跟登录无关，若也记成失败，几轮之后
            # 退避会涨到 2 小时，把用户正常的重登窗口一起堵死。
            login_hit = bool(sig["login_wall"] or sig["captcha"])
            if login_hit:
                led.note_result(self.name, False, device_risk=True)
            elif getattr(self, "_last_round_ok", False):
                led.note_result(self.name, True)
            else:
                return {}      # 与登录无关的失败：不给账本添噪声
            from core.riskscore import assess
            got = assess(self.name, ledger=led,
                         captcha=sig["captcha"], login_wall=sig["login_wall"],
                         soft=sig["soft"], blocked=sig["blocked"])
            if got.get("level") not in ("calm",):
                self.logger.warning(
                    "[%s] 风控评分 %.0f（%s）：%s；建议 %s",
                    self.name, got.get("score", 0), got.get("level"),
                    got.get("advice", {}).get("text", ""),
                    "／".join(got.get("reasons") or [])[:200])
            return got
        except Exception:
            return {}

    def _keep_alive(self) -> bool:
        """是否复用「上一轮就在前台」的 App（``android.keep_app_alive``）。

        默认关：仓库里已实证「复用上一轮界面」会让后续航线卡在设城市
        （残留广告/子页吞点击），所以冷启是更稳的默认。开着它的唯一理由
        是**降低 App 冷启次数**（每次冷启都会重跑设备校验与首屏风控埋点），
        换来的是偶发点不动的风险——由操作员按现场权衡。
        """
        try:
            return bool((self.config.get("android") or {}).get(
                "keep_app_alive", False))
        except Exception:
            return False

    # ---------- 航线 / 城市名 / 逐日期记账（所有 App 渠道同一套语义） ----------
    #
    # 这三件事曾各自写在单个渠道里：城市名映射只在智行有一份、去哪儿另抄
    # 12 条别名表；「航线未变就跳过重设」只有智行有；逐日期记账两个渠道
    # 各写一遍，措辞与 empty 判据还不一致。新增渠道必然再抄一遍——所以
    # 收进基类，子类只实现 `read_route` 这一个「从屏幕读事实」的钩子。

    @staticmethod
    def _city_name(code: str) -> str:
        """三字码 → App 里显示的中文城市名（全渠道单源）。

        配置里常用机场码（PEK/NRT），而 App 的城市是城市级（北京/东京）；
        先过项目的 airport_city_code 归一，再取中文名。查不到就原样
        传下去——宁可让它显式失败，也不要瞎猜一个城市。
        """
        try:
            from core.citydata import CODE_NAME
        except Exception:
            return code
        c = (code or "").upper()
        try:
            from core.intl import airport_city_code
            c = (airport_city_code(c) or c).upper()
        except Exception:
            pass
        nm = CODE_NAME.get(c) or ""
        if not nm:
            # 国际城市（NRT/PVG 之类）不在国内表里：走 core.intl 的城市名表，
            # 浏览器渠道用的是同一张表（PC/H5 已覆盖国际，App 必须同名）。
            try:
                from core.intl import city_name_of
                nm = city_name_of(c) or ""
                if nm == c:          # 查不到时它会原样返回，别当成真名
                    nm = ""
            except Exception:
                nm = ""
        for suf in ("市", "自治州", "地区"):
            nm = nm.replace(suf, "")
        return nm or code

    def read_route(self, dev):
        """App 当前停留的航线 (出发名, 到达名)；读不出返回 None。

        子类实现。判据必须是**屏幕上的字**，不是记忆：App 可能被用户手动
        改过、被系统回收后恢复成别的航线；只有屏幕才是事实。
        """
        return None

    def _route_unchanged(self, dev, from_city: str, to_city: str) -> bool:
        """App 当前是否已停在目标航线上（按界面文案判，不靠记忆）。"""
        try:
            cur = self.read_route(dev)
        except Exception:
            return False        # 判不了就当「需要重设」，宁慢勿错
        if not cur:
            return False
        return cur == (self._city_name(from_city), self._city_name(to_city))

    def note_date(self, date: str, got, why: str, ms: int = 0,
                  url: str = "", path: str = "航班明细"):
        """逐日期记账的**单源**：ok / empty / timeout 的判据与措辞只在这里。
        `empty` 只允许表示「列表页确实打开且该日无航班」；其余一律
        timeout 并写明卡点——「没采到」不等于「没票」，这是账本红线。
        各 App 渠道传同一种 reason 词汇，健康卡/节流才读得懂同一件事。
        """
        if got:
            return self.path_note(path, "ok", rows=len(got), date=date,
                                  detail="%d 条真实航班/时刻/价格" % len(got),
                                  ms=ms, url=url)
        if why == "empty":
            return self.path_note(path, "empty", date=date,
                                  detail="列表已打开，该日无可售航班")
        if why == "login":
            return self.path_note(path, "login", date=date,
                                  detail="该日被要求登录")
        return self.path_note(path, "timeout", date=date,
                              detail="未取到可用结果：%s" % (why or "unknown"))

    #: App 渠道的**日期视野**（天）。各家日历/明细只支持近未来：
    #: 携程/飞猪/智行的价格日历都是 ~62 天（`calendar(days=62)` 也是这个量级），
    #: 明细更短。超过视野的日期在 App 里**永远不可能出数**，但每条要白耗
    #: 100–150 秒设备时间。实测（2026-11-05）：生产对
    #: `SHA→HAK 2027-01-29`（85 天）与 `HAK→SHA 2027-02-14`（101 天）
    #: 都派了 App 渠道，三个 App 渠道各耗 ~150s，单设备被白占十来分钟。
    date_horizon_days = 62

    def reject_far_dates(self, dates) -> bool:
        """日期超出 App 视野时写 `unsupported` 并返回 True（调用方直接返回空）。

        与"没抓到"要分开：这是**能力边界**，不是失败。如实记 `unsupported`
        才能让账本不把它算成渠道质量问题（否则会误伤爬取率统计）。
        """
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        end = today + _td(days=int(self.date_horizon_days or 90))
        far = []
        for s in dates or []:
            try:
                dd = _d.fromisoformat(str(s))
            except (TypeError, ValueError):
                continue
            if dd > end:
                far.append(str(s))
        if not far:
            return False
        self.path_note(
            "app-date", "unsupported",
            detail="日期超出 App 视野（%d 天内，最远 %s），交浏览器"
                   % (int(self.date_horizon_days or 90), far[0]))
        return True

    def date_guard(self, date: str, fn, *args, _default=None, **kwargs):
        """**单日隔离**：某一天抛异常只死这一天，不许拖垮整段。

        为什么需要：App 渠道的日期循环原本是

            for date in dates:
                got = self._one_date(dev, ..., date)   # ← 一抛异常，整个 fetch 结束
                if got: out.append(got)

        ``_one_date`` 里任何一处异常（设备掉线、uiautomator 卡死、弹层没关掉、
        解析越界）都会让**后面所有日期**一起丢掉——账本上表现为整条航线
        「timeout」，而实际可能只有 1 天有问题。按日期隔离之后，失败被压缩成
        「这一天没采到」，其余日期照常出数，爬取率按天而不是按航线计。

        ``_default``：返回多值元组的渠道（如智行返回 ``(rows, blocked)``）
        传它自己的空值，保持调用方解包不变。

        记账口径沿用 ``note_date``：异常日一律记 timeout 并写明卡点，
        **绝不记 empty**（"没采到" ≠ "没票"，这是账本红线）。
        """
        t0 = time.time()
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            why = "%s: %s" % (type(e).__name__, str(e)[:100])
            self.logger.warning("[%s] 日期 %s 单独失败（其余日期继续）：%s",
                                self.name, date, why)
            self.note_date(date, [], why, ms=int((time.time() - t0) * 1000))
            # 单值渠道拿 []（与 _one_date 的空值同形）；元组渠道传自己的空值。
            return [] if _default is None else _default

    # ---------- 子类必须实现 ----------
    def fetch(self, from_city: str, to_city: str, dates: List[str],
              ret_date: str = "") -> List[FlightPrice]:
        raise NotImplementedError

    def login_url(self) -> str:
        """App 渠道返回登录入口描述（无真实 URL）。"""
        raise NotImplementedError

    # ---------- 自愈：App 卡死（ANR） ----------
    def diagnose_anr(self, dev) -> str:
        """读 ANR 现场，返回一句可读结论（读不到返回空串）。

        实测两类原因，处置完全不同：
          * **动态 so 与设备 ABI 不匹配**：`/data/anr/*` 主线程 Blocked 在
            `Runtime.load0`，等 `DynamicSoManager` 下载/加载锁；而设备是
            x86_64、so 是 arm64（去哪儿 `libbnfacesdk.so` 实测）。这类是
            **环境缺陷**，重启也只会再撞一次，必须换 32/64 位匹配的包或
            让该模块不加载；采集端能做的是如实上报，不是无限重试。
          * **临时卡顿**：重启通常能恢复。
        """
        try:
            # **整条脚本作为单个 argv 传给 `adb shell`，不套 `sh -c`**。
            # 实测（2026-11-04）：`_sh("shell","sh","-c", "<带 $() 与 | 的脚本>")`
            # 这种三段 argv 写法**恒返回空串**——adb 把 argv 用空格拼成一条命令
            # 送进设备 shell，`$(...)` 被外层 shell 先展开、`;` 把命令切断，
            # 内层只剩 `sh -c f=...`，于是永远读不到 ANR 内容。
            # 这个诊断是"渠道为什么卡住"的唯一线索，静默为空 = 白丢线索。
            # 同一条脚本作为**单个 argv** 送过去就正常返回（已对照实测）。
            out = dev._sh(
                "shell",
                "f=$(ls -t /data/anr/ 2>/dev/null | head -1); "
                '[ -n "$f" ] && head -40 "/data/anr/$f"',
                timeout=30) or ""
        except Exception:
            return ""
        if not out:
            return ""
        for line in out.splitlines():
            if "is not responding" in line or "isn't responding" in line:
                return line.strip()[:160]
        return ""

    def prepare_device(self, dev) -> None:
        """设备就绪后的**统一前置**：竖屏 → 登录态 → 权限框 → ANR → props 重清。

        三个 App 渠道共用同一条前置顺序（不要各写一份）：快照恢复会重启
        App，而重启后最容易撞上「没有响应」死锁（实证：主线程等 so 下载
        锁）。放在这里，任何渠道第一轮都不会因为卡死白跑。
        """
        # 先锁竖屏：坐标/滑动按 900×1600 写，横屏会让整轮点不动
        # （2026-11-01 现场：accelerometer_rotation=1，App 转成 1600×900，
        # 首页控件都在却怎么点都打不开城市页，账本记 set-city-dep）
        try:
            dev.lock_portrait()
        except Exception:
            pass
        self.restore_login_snapshot(dev)
        self._dismiss_system_prompts(dev)
        self._ensure_own_app(dev)
        self.recover_anr(dev, wait_s=30)
        self._refresh_vendor_props(dev)
        # 定位（r1063 T45）：模拟器重启/被回收后 GPS 会回到出厂点（加州），
        # 一家上海出发的 App 读到设备在加州，是比 UA 更硬的矛盾。
        self.ensure_geo(dev)
        self.ensure_proc_cpuinfo(dev)

    def ensure_proc_cpuinfo(self, dev) -> None:
        """确认 /proc/cpuinfo 不是宿主 Intel；缺了就通过 MuMu root shell 重挂。

        背景见文件头：KSU service.sh 的 bind-mount 落不到全局 ns，手动从
        `MuMuManager sh` 挂才生效。App 每次启动前校验一次最可靠，且开销只有
        一次 `head -3`（挂上之后就一直满足条件，不会重复挂）。
        """
        try:
            out = str(dev._sh("shell", "head", "-3", "/proc/cpuinfo") or "")
        except Exception:
            return
        if "CPU implementer" in out:      # 已经是 ARM 视图
            return
        if "Intel" not in out and "GenuineIntel" not in out:
            return                        # 认不出，不擅自改
        if not getattr(dev, "mumu_available", lambda: False)():
            return
        cmd = ('chcon u:object_r:proc_cpuinfo:s0 %s 2>/dev/null; '
               'chmod 644 %s 2>/dev/null; mount --bind %s /proc/cpuinfo'
               % (self.FAKE_CPUINFO, self.FAKE_CPUINFO, self.FAKE_CPUINFO))
        try:
            dev.mumu_sh(cmd)
            self.logger.info("[%s] 已把 /proc/cpuinfo 换成真机视图（隐藏宿主 CPU）",
                             self.name)
        except Exception:
            pass

    def ensure_geo(self, dev) -> None:
        """把模拟器定位钉到配置坐标（r1063 T45）。**幂等、失败不阻断采集。**

        为什么每次开查前都要打：模拟器重启、被系统回收、切前台应用都可能把
        GPS 复位到出厂点（Google 总部，加州）。而「IP 在上海、时区上海、GPS 在
        加州」是风控里最便宜的一条矛盾——比 UA 写得花不花哨危险得多。

        坐标读 `android.geo`（缺省 = 上海浦东世博片区）；`enabled: false` 不动设备。
        """
        try:
            from core.android import geo as _geo
            rep = _geo.fix(dev, getattr(self, "config", None),
                           logger=getattr(self, "logger", None))
        except Exception as e:
            try:
                self.logger.warning("[定位] 固定失败（不阻断采集）：%s",
                                    str(e)[:80])
            except Exception:
                pass
            return
        if rep.get("ok"):
            self._geo_pinned = rep

    def _refresh_vendor_props(self, dev) -> None:
        """开查前把厂商 props 再清一遍（廉价：1 条 getprop）。

        为什么必须挂在「每次查询前」而不是只在硬化时做一次
        ---------------------------------------------------
        MuMu 的 `nemuinit` 守护进程会在**几分钟内**把 `nemud.*` 与那批
        随机名 `*nemu=1` 属性写回来（实测：清完归零 → 7 分钟后 57 行）。
        而硬化按 `boot_id` 每 boot 只跑一次、采集一轮约 30 分钟 ——
        也就是说**绝大部分时间里 App 看到的都是裸露的模拟器标记**。

        2026-11-05 实测：手动 `resetprop --delete` 掉 3 条随机名
        `*nemu=1` 与 8 条 `nemud.*` 之后，自检从 92 → **88/88（上限）**，
        泄漏项只剩 ABI（走 MuMu 官方 per-app 表，不归本层）。

        放在这个位置的理由：App 渠道是唯一读 `android.os.Build` /
        设备 props 做风控判定的通路（PC/H5 走浏览器指纹那一套），
        所以清在 App 启动前，命中面正好覆盖。

        fail-soft：设备读不到 / 没有 resetprop，一律跳过，绝不阻断采集。
        """
        fn = getattr(self, "_stealth_refresh", None)
        if fn is None:
            # 延迟导入，避免 core → crawlers 的反向依赖在模块加载期成环
            from core.android import stealth as _stealth

            def fn(dev):
                return _stealth.refresh(dev, getattr(self, "config", None),
                                        getattr(self, "logger", None))
        try:
            rep = fn(dev) or {}
        except Exception:
            return
        deleted = rep.get("deleted") or []
        if deleted:
            try:
                self.logger.info(
                    "[%s] 开查前重清厂商 props %d 条（nemuinit 会周期性写回）",
                    self.name, len(deleted))
            except Exception:
                pass

    def _ensure_own_app(self, dev) -> bool:
        """确保前台是自家 App；不是就切回来（真返回 True 表示切过）。

        实测（2026-11-02）：同一台模拟器先跑去哪儿、再跑智行时，后者的
        `prepare_device` 没做任何前台校验——智行顺着**去哪儿**的首页去解析，
        dump 里全是 `com.Qunar:id/...`，账本还记成「页面选择不覆盖」。
        开错 App 与「页面没数据」在账本上长得一样，只能靠这里先纠正。
        """
        if not self.package:
            return False
        try:
            act = str(dev.current_activity() or "")
        except Exception:
            return False       # 读不到就不动手（可能只是 adb 慢）
        cur = act.split("/")[0].strip()
        if not cur or cur == self.package:
            return False
        self.logger.warning("[%s] 前台是 %s，先切回 %s（上一渠道未退出）",
                            self.name, cur, self.package)
        try:
            dev.app_start(self.package)
        except Exception as e:
            self.logger.warning("[%s] 切回 %s 失败：%s", self.name,
                                self.package, e)
            return False
        time.sleep(2.5)
        try:
            after = str(dev.current_activity() or "").split("/")[0].strip()
        except Exception:
            after = ""
        if after and after != self.package:
            self.logger.warning("[%s] 已启动 %s，但前台仍是 %s",
                                self.name, self.package, after)
            return False
        return True

    def recover_anr(self, dev, attempts: int = 1, wait_s: int = 45,
                    restart_after: bool = True) -> bool:
        """处理系统「没有响应」对话框；恢复成功返回 True。

        ANR 由 App 自身造成（实证：主线程 Blocked 在 Runtime.load0，等
        DynamicSoManager 下载 so 时持有的锁），与我们的点击无关，但**会一直
        挡着**——不处理就是整轮「打不开首页」。

        实测：点「等待」后 **186s 依然卡着**（死锁不会自己解开），所以
        「等待」只能当第一手；等不回来就必须 force-stop 冷启动。点
        「关闭应用」等同于重启，但由系统杀进程更不可控，因此自己 stop。
        """
        from .app_blockers import BLOCK_ANR, _ANR_WAIT, detect_block
        # **不 dump 就不可能有 ANR**：dump 会消耗调用方的页面序列（实测
        # 把广告页吃掉，导致关不掉广告）。所以先用 activity 粗筛——ANR
        # 对话框挂在 Dispatcher/启动页上，正常业务页面不会。只有像 ANR
        # 时才读页面做精确判定。
        try:
            act = (dev.current_activity() or "").lower()
        except Exception:
            # 读不到当前 Activity = 无法判断有没有 ANR。此时**不能**下探
            # `dump()`：dump 会消耗调用方的页面序列（实测把广告页吃掉，
            # 于是关不掉广告、整轮白跑）。判不了就不动手。
            return True
        if act and ("dispatcher" not in act and "splash" not in act
                    and "launcher" not in act):
            return True
        xml = dev.dump() or ""
        if not xml or detect_block(xml).kind != BLOCK_ANR:
            return True
        xy = None
        for m in re.finditer(
                r'<node[^>]*?text="([^"]*)"[^>]*?bounds='
                r'"\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            if m.group(1).strip() in _ANR_WAIT:
                xy = ((int(m.group(2)) + int(m.group(4))) // 2,
                      (int(m.group(3)) + int(m.group(5))) // 2)
                break
        if xy is not None:
            self.logger.warning("[%s] App 无响应，先点「等待」（最多等 %ds）",
                                self.name, wait_s)
            dev.tap(*xy)
            end = time.time() + wait_s
            while time.time() < end:
                time.sleep(4)
                xml = dev.dump() or ""
                if xml and detect_block(xml).kind != BLOCK_ANR:
                    return True
        if not restart_after or not self.package:
            return False
        # 死锁等不回来：自己重启（不点「关闭应用」，避免系统侧不可控杀进程）
        why = self.diagnose_anr(dev)
        self.logger.warning("[%s] App 卡死未恢复，重启 App%s", self.name,
                            ("（现场：%s）" % why) if why else "")
        self._anr_reason = why
        dev.app_stop(self.package)
        time.sleep(2)
        ok = dev.deep_link(getattr(self, "home_uri", "") or "") \
            if getattr(self, "home_uri", "") else False
        if not ok:
            ok = dev.app_start(self.package)
        if not ok:
            return False
        end = time.time() + 90
        while time.time() < end:
            time.sleep(4)
            xml = dev.dump() or ""
            if xml and detect_block(xml).kind != BLOCK_ANR:
                return True
        return False
