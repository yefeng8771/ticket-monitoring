# -*- coding: utf-8 -*-
"""控制台 README 截图生成（演示模式 + Playwright，JS 错误顺带体检）。

用法：
    python webui.py --demo --port 8799        # 先起演示控制台
    python docs/screenshot.py                 # 截图到 docs/screenshots/

产出：console-light / console-dark / console-preview / console-mobile。
任何 JS console.error / pageerror 都会以非零码退出（发版前兜底）。
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("CONSOLE_URL", "http://127.0.0.1:8799")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")


def main():
    os.makedirs(OUT, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        # 1512 视口布局舒展；device_scale_factor=2 出高清图（GitHub 缩放后依然锐利）
        pg = b.new_page(viewport={"width": 1512, "height": 1042},
                        device_scale_factor=2)
        pg.on("console",
              lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(1500)

        def theme(t):
            pg.evaluate(
                "localStorage.setItem('jptheme','%s');location.reload()" % t)
            pg.wait_for_timeout(1100)

        theme("light")
        pg.screenshot(path=os.path.join(OUT, "console-light.png"))
        # 走势子视图（折线+日历）暗色：覆盖 canvas 暗色渲染。
        # 先切国际长航线片（SHA→伦敦希思罗：长坡缓降+跨天直飞的
        # 国际曲线形态；chip 高亮跟随由 buildChartChips 显式重建）
        pg.click('.mtab[data-t="trend"]')
        pg.wait_for_timeout(700)
        pg.evaluate("""() => {
          const c = [...document.querySelectorAll('#chartRoutes .chip')]
            .find(x => x.textContent.indexOf('上海→伦敦希思罗') >= 0);
          if (c) c.click();
        }""")
        pg.wait_for_timeout(700)
        theme("dark")
        pg.screenshot(path=os.path.join(OUT, "console-dark.png"))
        # 推送预览弹层（暗色下再截一张，覆盖弹层渲染；预览从 demo 库
        # 现渲染，国际达标行随 digest 全量视觉）
        pg.click("#pvBtn")
        pg.wait_for_function(
            "() => {const b = document.querySelector('#pvBody');"
            "return !!b && b.innerText.length > 50;}", timeout=15000)
        pg.locator(".pvcard").screenshot(
            path=os.path.join(OUT, "console-preview.png"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        # K线模式（蜡烛图组件；仍在 LHR 国际长曲线语境）
        pg.click("#mdK")
        pg.wait_for_timeout(600)
        pg.locator("#chartcard").screenshot(
            path=os.path.join(OUT, "console-kline.png"))
        pg.click("#mdLine")
        pg.wait_for_timeout(300)
        # 航班明细子视图（工作台表格）：筛国际航线片（SHA→东京成田——
        # 国际紫标+含税小字+机场对行形态主秀）
        pg.click('.mtab[data-t="details"]')
        pg.wait_for_timeout(400)
        pg.evaluate("""() => {
          const fb = document.querySelector('.fbar');
          if (fb && !fb.classList.contains('open')) togFlt();
          const c = [...document.querySelectorAll('#routechips .chip')]
            .find(x => x.textContent.indexOf('上海→东京成田') >= 0);
          if (c) c.click();
        }""")
        pg.wait_for_timeout(500)
        pg.evaluate("""() => {
          const t=document.getElementById('tablecard');
          if(t)window.scrollTo(0, Math.max(0,
            t.getBoundingClientRect().top + window.scrollY - 150));
        }""")
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, "console-details.png"))
        pg.evaluate("""() => {
          const c = [...document.querySelectorAll('#routechips .chip')]
            .find(x => x.textContent.trim() === '全部航线'
                    || x.textContent.trim() === '全部');
          if (c) c.click();
          const fb = document.querySelector('.fbar');
          if (fb && fb.classList.contains('open')) togFlt();
        }""")
        pg.wait_for_timeout(300)
        # 配置页（面板式设置台：用户与航线面板）
        pg.click("#navCfg")
        pg.wait_for_timeout(900)
        pg.click('#cfgnav .cnav[data-p="users"]')
        pg.wait_for_timeout(700)
        # 展开首个用户卡（r319：特价监控分区随卡展示，呈现面恒最新态）
        pg.evaluate("""() => {
          if (typeof OPEN_USER === 'undefined' || OPEN_USER !== 0) {
            const h = document.querySelector('.uhead2');
            if (h) toggleUser(h);
          }
          // r342：展开首航线呈现「区间+逐日」双通道日期编排
          const rh = document.querySelector('.rline[data-rk] .rhead');
          if (rh && rh.getAttribute('aria-expanded') === 'false') rh.click();
        }""")
        pg.wait_for_timeout(500)
        # r347：视口级最佳构图——日期模式条、已选片、快捷行与保存条同屏
        pg.evaluate("""() => {
          if(typeof CFG!=='undefined'&&CFG[0]&&CFG[0].routes[0]){
            CFG[0].routes[0].alert_direct =
              (Number(CFG[0].routes[0].alert_direct)||0) + 10;
            buildForm();
          }
        }""")
        pg.wait_for_timeout(1300)
        pg.evaluate("""() => {
          const f=document.getElementById('dfrom-0-0'),
                t=document.getElementById('dto-0-0');
          if(f)f.value='2026-11-05';
          if(t)t.value='2026-11-15';
          const d=document.querySelector('.dateSrow');
          if(d)window.scrollTo(0, Math.max(0,
            d.getBoundingClientRect().top + window.scrollY - 260));
        }""")
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, "console-config.png"))
        pg.locator(".dateSrow").first.screenshot(
            path=os.path.join(OUT, "console-date-modes.png"))
        # 城市面板「🌐 国际」页签（地区分组+三路搜索：国际监控能力
        # 的配置面主秀；注入拼音搜索词让搜索框带词出镜）
        pg.evaluate("""() => {
          const inp = [...document.querySelectorAll(
            '#panel-users .ucard input[data-rf], #panel-users .ucard input')]
            .find(i => (i.getAttribute('onfocus') || ''
                        + i.getAttribute('onclick') || '')
                  .indexOf('cityPanel') >= 0
                  || i.classList.contains('cityinput'));
          if (inp) { inp.focus(); inp.click(); }
        }""")
        pg.wait_for_timeout(400)
        pg.evaluate("""() => {
          if (typeof cityPanelTab === 'function') cityPanelTab('intl');
          const si = document.querySelector('#citypanel input[type="text"]');
          if (si) {
            const st = Object.getOwnPropertyDescriptor(
              HTMLInputElement.prototype, 'value').set;
            st.call(si, 'dongjing');
            si.dispatchEvent(new Event('input', {bubbles: true}));
          }
        }""")
        pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(OUT, "console-city-intl.png"),
                      full_page=True)
        pg.evaluate("cityPanelClose&&cityPanelClose()")
        pg.wait_for_timeout(200)
        # 全局配置中心（调度/采集热载 + 启动级只读三组）
        pg.click('#cfgnav .cnav[data-p="globals"]')
        pg.wait_for_timeout(700)
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, "console-globals.png"))
        # 重启与迁移中心（r342）：演示一次未保存路径变更→旧→新+迁移预案
        pg.evaluate("""() => {
          const i = document.getElementById('glbUdd');
          if (i) {
            i.value = 'user_data_migrated';
            i.dispatchEvent(new Event('change', {bubbles: true}));
          }
        }""")
        pg.wait_for_timeout(500)
        pg.evaluate("openRestartCenter && openRestartCenter()")
        pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(OUT, "console-restart.png"))
        pg.evaluate("closeRestartCenter && closeRestartCenter();"
                    "loadCfg && loadCfg()")
        pg.wait_for_timeout(500)
        # 移动端（筛选抽屉 + 首列吸附 + 国际行窄带折行形态）
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.click("#navMon")
        pg.wait_for_timeout(600)
        pg.evaluate("showMonTab('details')")
        pg.wait_for_timeout(500)
        theme("light")
        pg.evaluate("resetFlt()")
        pg.wait_for_timeout(300)
        pg.evaluate("""() => {
          const t=document.getElementById('tablecard');
          if(t)window.scrollTo(0, Math.max(0,
            t.getBoundingClientRect().top + window.scrollY - 120));
        }""")
        pg.wait_for_timeout(350)
        pg.screenshot(path=os.path.join(OUT, "console-mobile.png"))
        # r347：移动筛选抽屉 + 常驻「查看筛选结果」CTA（真实单手出口）
        pg.evaluate("(()=>{const fb=document.querySelector('.fbar');"
                    "if(fb&&!fb.classList.contains('open'))togFlt();})()")
        pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(OUT, "console-mobile-filter.png"))
        pg.evaluate("closeFltShow&&closeFltShow()")
        pg.wait_for_timeout(300)
        b.close()
    if errors:
        print("!! 页面 JS 错误：")
        for e in errors[:10]:
            print("   -", e[:200])
        sys.exit(1)
    print("截图完成（无 JS 错误）：")
    for f in sorted(os.listdir(OUT)):
        print("  ", os.path.join(OUT, f))


if __name__ == "__main__":
    main()
