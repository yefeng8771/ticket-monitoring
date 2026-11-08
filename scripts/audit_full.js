// 全站审计：溢出/遮挡扫描 + 交互遍历 + console 错误 + 全面板截图
const { chromium } = require('playwright');
const fs = require('fs');

const OUT = 'audit_shots';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT);

// 溢出扫描：可见文本元素横向越界 / overflow:hidden 裁切
const SCAN = () => {
  const bad = [];
  const els = document.querySelectorAll('body *');
  for (const el of els) {
    if (!(el instanceof HTMLElement)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!hasText && el.tagName !== 'INPUT' && el.tagName !== 'CANVAS') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    // 横向越界才是遮挡嫌疑（纵向可滚动合法）
    if (r.right > innerWidth + 1 || r.left < -1) {
      bad.push({ t: 'viewport', tag: el.tagName, cls: (el.className + '').slice(0, 40),
        txt: (el.textContent || el.value || '').trim().slice(0, 24),
        rect: [r.left, r.top, r.right, r.bottom].map(Math.round), vw: innerWidth });
      continue;
    }
    let a = el.parentElement;
    while (a && a !== document.body) {
      const acs = getComputedStyle(a);
      if (/(hidden|clip)/.test(acs.overflow + acs.overflowX)) {
        const ar = a.getBoundingClientRect();
        if (r.right > ar.right + 2 || r.bottom > ar.bottom + 2) {
          bad.push({ t: 'clipped', tag: el.tagName, cls: (el.className + '').slice(0, 40),
            txt: (el.textContent || '').trim().slice(0, 24),
            rect: [r.left, r.top, r.right, r.bottom].map(Math.round),
            anc: (a.className + '').slice(0, 30) });
        }
        break;
      }
      a = a.parentElement;
    }
  }
  return bad;
};

(async () => {
  const b = await chromium.launch();
  const report = {};

  for (const [name, url] of [['prod', 'http://127.0.0.1:8765/'], ['demo', 'http://127.0.0.1:8799/']]) {
    const pg = await b.newPage({ viewport: { width: 1512, height: 900 } });
    const cerr = [];
    pg.on('console', m => { if (m.type() === 'error') cerr.push(m.text().slice(0, 200)); });
    pg.on('pageerror', e => cerr.push('PAGEERR ' + ((e.stack || String(e)) + '').slice(0, 300)));
    await pg.goto(url, { waitUntil: 'networkidle' });
    await pg.waitForTimeout(1200);
    report[name] = { console: cerr, overflow: {}, shots: [] };
    for (const th of ['light', 'dark']) {
      await pg.evaluate(t => { localStorage.setItem('jptheme', t); location.reload(); }, th);
      await pg.waitForTimeout(1100);
      const tabs = await pg.locator('.mtab').all();
      for (let i = 0; i < tabs.length; i++) {
        await pg.locator('.mtab').nth(i).click();
        await pg.waitForTimeout(i === 1 ? 900 : 500);
        const tag = await pg.locator('.mtab').nth(i).getAttribute('data-t');
        report[name].shots.push(`${name}-${th}-${tag}.png`);
        await pg.screenshot({ path: `${OUT}/${name}-${th}-${tag}.png`, fullPage: true });
        const ov = await pg.evaluate(SCAN);
        if (ov.length) report[name].overflow[`${th}/${tag}`] = ov;
      }
      if (await pg.locator('#pvBtn').count()) {
        await pg.click('#pvBtn');
        await pg.waitForFunction("document.getElementById('pvMask').classList.contains('on')", { timeout: 40000 }).catch(() => {});
        await pg.waitForTimeout(700);
        await pg.screenshot({ path: `${OUT}/${name}-${th}-preview.png` });
        const ov = await pg.evaluate(SCAN);
        if (ov.length) report[name].overflow[`${th}/preview`] = ov;
        await pg.keyboard.press('Escape');
        await pg.waitForTimeout(300);
      }
      await pg.click('#navCfg'); await pg.waitForTimeout(700);
      for (const p of ['login', 'users', 'globals']) {
        await pg.click(`.cnav[data-p="${p}"]`); await pg.waitForTimeout(500);
        report[name].shots.push(`${name}-${th}-cfg-${p}.png`);
        await pg.screenshot({ path: `${OUT}/${name}-${th}-cfg-${p}.png`, fullPage: true });
        const ov = await pg.evaluate(SCAN);
        if (ov.length) report[name].overflow[`${th}/cfg-${p}`] = ov;
      }
    }
    await pg.close();
  }

  // 交互遍历（demo 实例）
  const pg = await b.newPage({ viewport: { width: 1512, height: 900 } });
  const ierr = [];
  pg.on('pageerror', e => ierr.push('PAGEERR ' + ((e.stack || String(e)) + '').slice(0, 300)));
  await pg.goto('http://127.0.0.1:8799/', { waitUntil: 'networkidle' });
  await pg.waitForTimeout(1000);
  const clicks = [];
  const tryClick = async (sel, label) => {
    const n = await pg.locator(sel).count();
    if (!n) return;
    try { await pg.locator(sel).first().click({ timeout: 2000 }); clicks.push(label + ' ok'); await pg.waitForTimeout(250); }
    catch (e) { clicks.push(label + ' FAIL ' + e.message.slice(0, 60)); }
  };
  for (let i = 0; i < (await pg.locator('.mtab').count()); i++)
    await tryClick(`.mtab >> nth=${i}`, `mtab#${i}`);
  await tryClick('#themeBtn', 'theme');
  await tryClick('#themeBtn', 'theme-back');
  await pg.click('#navCfg'); await pg.waitForTimeout(600);
  await tryClick('.cnav[data-p="users"]', 'cnav-users');
  const grouplabs = await pg.locator('#cfgform .grouplab:visible').count();
  for (let i = 0; i < grouplabs; i++) await tryClick(`#cfgform .grouplab:visible >> nth=${i}`, `grouplab#${i}`);
  for (let i = 0; i < grouplabs; i++) await tryClick(`#cfgform .grouplab:visible >> nth=${i}`, `grouplab#${i}-reopen`);
  for (let i = 0; i < Math.min(await pg.locator('.chhead:visible').count(), 6); i++)
    await tryClick(`.chhead:visible >> nth=${i}`, `chhead#${i}`);
  await tryClick('.cnav[data-p="globals"]', 'cnav-globals');
  for (const id of ['glbRos', 'glbHl', 'glbDbg']) {
    if (await pg.locator('#' + id).count()) {
      await tryClick('#' + id, id + '-on'); await tryClick('#' + id, id + '-off');
    }
  }
  await tryClick('.cnav[data-p="users"]', 'cnav-users2');
  const uh = await pg.locator('.uhead2:visible').count();
  if (uh) { await tryClick('.uhead2:visible >> nth=0', 'ucard-open'); await tryClick('.uhead2:visible >> nth=0', 'ucard-close'); }
  await pg.click('#navMon'); await pg.waitForTimeout(600);
  await tryClick('#pvBtn', 'pv-open');
  await pg.waitForFunction("document.getElementById('pvMask').classList.contains('on')", { timeout: 40000 }).catch(() => {});
  await pg.keyboard.press('Escape'); await pg.waitForTimeout(400);
  const pvClosed = await pg.evaluate("!document.getElementById('pvMask').classList.contains('on')");
  clicks.push('pv-esc-close ' + (pvClosed ? 'ok' : 'FAIL'));
  report.interactive = { clicks: clicks.length, fails: clicks.filter(c => c.includes('FAIL')), console: ierr };
  await pg.close();

  fs.writeFileSync('audit_report.json', JSON.stringify(report, null, 1));
  const ovCount = Object.values(report.prod.overflow).reduce((s, a) => s + a.length, 0)
    + Object.values(report.demo.overflow).reduce((s, a) => s + a.length, 0);
  console.log('OVERFLOW total:', ovCount);
  console.log('PROD console errors:', JSON.stringify(report.prod.console));
  console.log('DEMO console errors:', JSON.stringify(report.demo.console));
  console.log('INTERACT fails:', JSON.stringify(report.interactive.fails), 'clicks:', report.interactive.clicks);
  await b.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
