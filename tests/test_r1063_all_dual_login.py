# -*- coding: utf-8 -*-
"""r1063 T177-T179：**所有浏览器渠道统一 PC+H5 双端登录**（跟飞猪一样）。

用户原话：「我说的是为什么不同时要求双端登录，跟飞猪一样！」

真因（前端写死了分组表，后端早就有 `*_h5` 槽位）：
```js
const order=['ctrip','qunar','fliggy','fliggy_h5','tongcheng','tuniu'];
{key:'ctrip',     tag:'全端',    slots:[by.ctrip]}
{key:'tongcheng', tag:'全端',    slots:[by.tongcheng]}
{key:'tuniu',     tag:'全端',    slots:[by.tuniu]}
{key:'fliggy',    tag:'PC / H5', slots:[by.fliggy,by.fliggy_h5]}   ← 只有飞猪
```

本次三件事：
1. `order` / `reqs` 补 `ctrip_h5` / `tongcheng_h5` / `tuniu_h5`；
2. 三家 card 改 `tag:'PC / H5'` + 两槽；双端弹窗从"飞猪专用"泛化为
   `lgOpenDual(plat)`（`LG_DUAL` 表 + `lgFliggyModalHTML` 保留为别名）；
3. `_login_state_view` 里"按槽位自己算状态"的分支从 `fliggy_h5` 泛化到
   **所有独立端槽位**（`key != meta["plat"]`）——此前其余 `_h5` 抄渠道级状态，
   于是没登录也显示「会话有效·明细可用」（假可用）。

配套：继承 PC 会话到 H5 改成**配置开关**（`web.login_inherit_pc_session`，
默认 false）——继承来的只是 PC 域 cookie，与"两端要分别登录"矛盾。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _w():
    return io.open(os.path.join(ROOT, "webui.py"), encoding="utf-8").read()


def test_all_vendors_are_dual_in_the_card_table():
    w = _w()
    for vendor in ("ctrip", "tongcheng", "tuniu"):
        assert "slots:[by.%s,by.%s_h5]" % (vendor, vendor) in w, \
            "%s 没做成双端（用户明确要求跟飞猪一样）" % vendor
    i = w.index("const order=['ctrip'")
    seg = w[i:i + 200]
    for k in ("ctrip_h5", "tongcheng_h5", "tuniu_h5"):
        assert k in seg, "order 里缺 %s" % k


def test_dual_modal_is_generic():
    """双端弹窗不许再写死飞猪：要有 LG_DUAL 表与 lgOpenDual(plat)。"""
    w = _w()
    assert "const LG_DUAL={" in w
    assert "function lgOpenDual(plat){" in w
    assert "function lgFliggyModalHTML(){return lgDualModalHTML('fliggy')}" in w
    # 卡片按钮按渠道传参，而不是固定开飞猪
    assert "lgOpenDual('${he(p)}')" in w


def test_h5_slots_report_their_own_state():
    """独立端槽位必须按自己的 profile 算状态（否则假可用）。"""
    w = _w()
    i = w.index("for key in LOGIN_SLOT_ORDER:")
    seg = w[i:i + 900]
    assert 'if key != meta.get("plat"):' in seg, \
        "只有 fliggy_h5 走独立分支的话，其余 _h5 会抄渠道状态（假可用）"


def test_inheritance_is_opt_in():
    src = io.open(os.path.join(ROOT, "core", "login_slots.py"),
                  encoding="utf-8").read()
    assert "login_inherit_pc_session" in src
    i = src.index("login_inherit_pc_session")
    seg = src[max(0, i - 300):i + 300]
    assert "False" in seg, "继承必须默认关闭"
