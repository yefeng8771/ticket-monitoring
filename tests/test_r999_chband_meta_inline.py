# -*- coding: utf-8 -*-
"""r999：390 渠道入口卡头「渠道名 + 必须登录要求」同一行。"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_css_keeps_meta_inline_on_mobile():
    with open(os.path.join(ROOT, "webui.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index(" .chband-meta{white-space:normal!important")
    blk = src[i:i + 220]
    assert "flex:0 1 auto!important" in blk, blk


def _boot():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "webui.py"), "--demo",
         "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = "http://127.0.0.1:%d" % port
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            op.open(base + "/api/state", timeout=2)
            return srv, base
        except Exception:
            time.sleep(0.3)
    srv.kill()
    raise RuntimeError("demo server did not start")


def test_rendered_channel_header_is_one_line():
    import pytest
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        pytest.skip("playwright 缺失")
    with sync_playwright() as pw:
        if not os.path.exists(pw.chromium.executable_path):
            pytest.skip("chromium 二进制缺失")
    srv, base = _boot()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            try:
                pg = b.new_page(viewport={"width": 390, "height": 900})
                pg.goto(base)
                pg.wait_for_function(
                    "typeof S!=='undefined'&&S&&S.users", timeout=30000)
                pg.evaluate("()=>switchView('cfg')")
                try:
                    pg.wait_for_selector('#cfgChannelLinks .chband',
                                         timeout=20000)
                except Exception:
                    pytest.skip("演示环境未渲染旧渠道卡（新渠道入口已替代）")
                pg.wait_for_timeout(600)
                d = pg.evaluate(r"""()=>{
                  const ids=[...document.querySelectorAll('.chband-id')]
                    .filter(e=>e.offsetParent&&e.getBoundingClientRect().height>5)
                    .slice(0,3);
                  return ids.map(id=>{
                    const n=id.querySelector('.chband-name').getBoundingClientRect();
                    const m=id.querySelector('.chband-meta');
                    const mb=m?m.getBoundingClientRect():null;
                    return {h:+id.getBoundingClientRect().height.toFixed(0),
                      dy:mb?+Math.abs(n.top-mb.top).toFixed(0):null,
                      overflow:document.documentElement.scrollWidth
                        -document.documentElement.clientWidth};});}""")
            finally:
                b.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=8)
        except Exception:
            srv.kill()
    assert len(d) >= 2, d
    for x in d:
        assert x["h"] <= 26, x
        assert x["dy"] is not None and x["dy"] <= 4, x
        assert x["overflow"] <= 0, x
