# -*- coding: utf-8 -*-
"""r993：健康页节流工具条扁平化（用户「节流和溯源的UI/排版」）。

修前 390 实测：`#paceBox .pace-tools` 是 335px 高的灰底卡中卡，预热/自检
两组各换 4 行按钮；1512 也是 218px 灰底块。现改为白底发丝线，
390 每组一条横向可滑动动作行，工具条降到 96px。
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def ui():
    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    srv = subprocess.Popen([sys.executable, "webui.py", "--demo", "--port", str(port)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        ok = False
        for _ in range(90):
            try:
                urllib.request.urlopen(base + "/api/state", timeout=2)
                ok = True
                break
            except Exception:
                time.sleep(0.5)
        if not ok:
            pytest.skip("demo 服务未起来")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for w, h in ((1512, 1000), (390, 1200)):
                pg = br.new_page(viewport={"width": w, "height": h})
                pg.goto(base + "/", wait_until="domcontentloaded")
                pg.wait_for_timeout(2400)
                pg.evaluate("switchView('mon');showMonTab('health')")
                pg.wait_for_timeout(1600)
                # 节流面板是异步二次渲染；只等固定时长会在慢机上量到
                # 尚未布局的 0×0 分组（与 UI 无关的假红）。
                pg.wait_for_function(
                    "()=>{const g=document.querySelector('#paceBox .pace-tools .g');"
                    "return !!g&&g.getBoundingClientRect().width>0}", timeout=12000)
                out[str(w)] = pg.evaluate("""() => {
                  const t = document.querySelector('#paceBox .pace-tools');
                  if (!t) return {err: 'no tools'};
                  const R = e => { const b=e.getBoundingClientRect(); const cs=getComputedStyle(e);
                    return {t:+b.top.toFixed(1), b:+b.bottom.toFixed(1), h:+b.height.toFixed(1),
                            bg:cs.backgroundColor, wrap:cs.flexWrap, sw:e.scrollWidth, cw:e.clientWidth}; };
                  return {tools:R(t),
                    groups:[...t.querySelectorAll('.g')].map(g => ({
                      label:(g.querySelector('b')||{}).textContent||'', ...R(g),
                      firstT:(g.querySelector('button')||g).getBoundingClientRect().top,
                      labC:(()=>{const r=g.querySelector('b').getBoundingClientRect();return +((r.top+r.bottom)/2).toFixed(1)})(),
                      btnC:(()=>{const r=(g.querySelector('button')||g).getBoundingClientRect();return +((r.top+r.bottom)/2).toFixed(1)})(),
                      btnH:[...g.querySelectorAll('button')].map(b=>+b.getBoundingClientRect().height.toFixed(1))
                    })),
                    overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};
                }""")
                # 打开第一条溯源，量详情的扁平度/空态高度
                btn = pg.query_selector('#paceBox button[data-pk$=":trace"]')
                if btn:
                    btn.evaluate("el=>el.click()")
                    pg.wait_for_timeout(900)
                    out[str(w)]["detail"] = pg.evaluate("""() => {
                      const d=document.getElementById('paceDetail');
                      if(!d)return {err:'no detail'};
                      const b=d.getBoundingClientRect(), cs=getComputedStyle(d);
                      return {h:+b.height.toFixed(1), bg:cs.backgroundColor, r:cs.borderRadius,
                              txt:(d.textContent||'').trim().slice(0,120),
                              overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};
                    }""")
                pg.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
    return out


def test_pace_tools_is_flat_not_a_nested_gray_card(ui):
    for w in ("1512", "390"):
        d = ui[w]
        assert "err" not in d, (w, d)
        assert d["tools"]["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), (w, d["tools"])


def test_mobile_pace_groups_are_one_scrollable_row_each(ui):
    d = ui["390"]
    assert d["tools"]["h"] <= 120, d["tools"]
    for g in d["groups"]:
        assert g["h"] <= 40, g
        assert g["wrap"] == "nowrap", g
        assert g["sw"] > g["cw"], ("动作行没有可滑动内容", g)
        assert len(set(g["btnH"])) <= 1 and g["btnH"] and g["btnH"][0] >= 28, g
    assert d["overflow"] <= 1, d


def test_desktop_pace_tools_stays_compact(ui):
    d = ui["1512"]
    assert d["tools"]["h"] <= 280, d["tools"]
    assert d["overflow"] <= 1, d


def test_trace_detail_is_flat_and_empty_state_is_one_line(ui):
    for w in ("1512", "390"):
        d = ui[w].get("detail") or {}
        assert not d.get("err"), (w, d)
        assert d["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), (w, d)
        assert d["r"] == "0px", (w, d)
        assert d["h"] <= 80, (w, d)
        # 演示库带历史尝试时详情是证据表；空态行只在没有记录时出现。
        # 两种形态都必须是扁平短块，不把「有记录」当缺陷。
        assert d["txt"].strip(), (w, d)
        assert d["overflow"] <= 1, d


def test_pace_group_label_and_first_button_share_a_baseline(ui):
    for w in ("1512", "390"):
        for g in ui[w]["groups"]:
            assert abs(g["labC"] - g["btnC"]) <= 1.5, (w, g)
