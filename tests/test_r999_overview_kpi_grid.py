# -*- coding: utf-8 -*-
"""r999：桌面概览每组直飞/中转 KPI 从竖排五行改为两列，减少右半列空白。"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_css_scopes_overview_kpi_grid():
    with open(os.path.join(ROOT, "webui.py"), encoding="utf-8") as f:
        src = f.read()
    assert "#montab-overview .dgroup .kpi{display:grid;" in src
    assert 'grid-template-areas:"lab lab" "num note" "bar flight"' in src


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


def test_rendered_overview_kpi_is_two_column_on_desktop():
    import pytest
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        pytest.skip("playwright 缺失")
    with sync_playwright() as pw:
        if not os.path.exists(pw.chromium.executable_path):
            pytest.skip("chromium 二进制缺失")
    out = {}
    srv, base = _boot()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            try:
                for w in (1512, 390):
                    pg = b.new_page(viewport={"width": w, "height": 1000})
                    pg.goto(base)
                    pg.wait_for_function(
                        "typeof S!=='undefined'&&S&&S.users", timeout=30000)
                    pg.evaluate("()=>{switchView('mon');showMonTab('overview')}")
                    pg.wait_for_timeout(1500)
                    out[w] = pg.evaluate(r"""()=>{
                      const g=document.querySelector('#montab-overview .dgroup .grid');
                      const k=g.querySelector('.kpi');
                      const R=e=>e.getBoundingClientRect();
                      const by={}; for(const e of k.children)
                        by[e.className.split(' ').filter(Boolean).pop()||'x']=R(e);
                      return {disp:getComputedStyle(k).display,
                        kpiH:+R(k).height.toFixed(0),groupH:+R(g).height.toFixed(0),
                        numR:+by.num.right.toFixed(0),noteL:+by.muted?.left?.toFixed?.(0)||0,
                        overflow:document.documentElement.scrollWidth
                          -document.documentElement.clientWidth};}""")
                    pg.close()
            finally:
                b.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=8)
        except Exception:
            srv.kill()
    d = out[1512]
    assert d["disp"] == "grid", d
    assert d["kpiH"] <= 120, d
    assert d["overflow"] <= 0, d
    assert out[390]["disp"] == "block", out[390]
    assert out[390]["kpiH"] <= 140, out[390]
