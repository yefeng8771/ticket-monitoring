// v1.5.54 uitest：新字段渲染门/键盘十字线/CSV 新列/机场名拼接/断点合并回归
// 用法：node scripts/uitest_v1554.js（需生产或 demo 实例在线）
const { chromium } = require('playwright');
const fs = require('fs');

const URL = process.env.UITEST_URL || 'http://127.0.0.1:8765/';
const OUT = 'uitest_v1554_result.json';
const results = [];
const errors = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok, detail: detail || '' });
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  — ' + detail : ''));
};

(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1366, height: 900 } });
  pg.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
  pg.on('pageerror', e => errors.push(String(e).slice(0, 200)));

  await pg.goto(URL, { waitUntil: 'domcontentloaded' });
  await pg.waitForTimeout(2500);

  // 1. 首屏渲染与版本
  const ver = await pg.evaluate(() => fetch('/api/state').then(r => r.json()).then(j => j.version));
  check('api version 1.5.54', ver === '1.5.54', 'got ' + ver);

  // 2. 渲染门新键在行数据中存在（旧数据空值不占位）
  const keys = await pg.evaluate(() => fetch('/api/state').then(r => r.json()).then(j => {
    const rows = (j.users && j.users[0] && j.users[0].flights) || [];
    const need = ['planeSize', 'depAirport', 'arrAirport', 'transDepTerminal', 'cabinCode', 'bagState'];
    return { rows: rows.length, ok: rows.length && need.every(k => k in rows[0]) };
  }));
  check('渲染门新键下发', keys.ok, 'rows=' + keys.rows);

  // 3. 明细表渲染零 JS 错 + 次行/空态行：真实点击「明细」导航
  //    （hash 深链在折叠架构下不触发 table()，人肉路径以点击为准）
  const monTab = pg.locator('#tabs span, .tabs .mtab', { hasText: '明细' }).first();
  if (await monTab.count()) { await monTab.click(); await pg.waitForTimeout(1500); }
  const stl = await pg.evaluate(() => ({
    stl: document.querySelectorAll('#ftable .stl').length,
    erow: document.querySelectorAll('#ftable .erow').length,
    rows: document.querySelectorAll('#ftable tbody tr').length
  }));
  check('明细次行渲染（含新字段拼接）', stl.stl > 0, JSON.stringify(stl).slice(0, 120));

  // 4. 机场名+楼号拼接函数（_tt/_apt 单元行为）
  const tt = await pg.evaluate(() => ({
    strip: _apt('虹桥国际机场'), keep: _apt('URC'), pair: _tt('虹桥国际机场', 'T2'),
    termOnly: _tt('', 'T1')
  }));
  check('_apt 剥后缀', tt.strip === '虹桥' && tt.keep === 'URC', JSON.stringify(tt));
  check('_tt 拼接', tt.pair === '虹桥T2' && tt.termOnly === 'T1', JSON.stringify(tt));

  // 5. 键盘步进十字线：聚焦 canvas → ArrowRight → 无异常（HPTS 有数据时画十字线）
  await pg.evaluate(() => { location.hash = '#trend'; });
  await pg.waitForTimeout(1500);
  await pg.focus('#chart');
  for (const key of ['ArrowRight', 'ArrowRight', 'ArrowLeft', 'End', 'Home']) {
    await pg.keyboard.press(key);
    await pg.waitForTimeout(120);
  }
  check('键盘十字线交互无错', errors.filter(e => /drawHover|HPTS|KB_IDX/.test(e)).length === 0);

  // 6. CSV 导出含新列头
  const csvHead = await pg.evaluate(() => {
    // 直接取 expCsv 的 head 数组逻辑等价：从 filteredRows 与函数源码核对
    const src = expCsv.toString();
    return { hasPlane: src.includes("'机型体量'"), hasCabinCode: src.includes("'舱位码'"),
             hasAirport: src.includes("机场/航站楼") };
  });
  check('CSV 新列头', csvHead.hasPlane && csvHead.hasCabinCode && csvHead.hasAirport, JSON.stringify(csvHead));

  // 7. savebar visibility 双态（隐藏不可聚焦）
  const sb = await pg.evaluate(async () => {
    const el = document.querySelector('.savebar');
    if (!el) return { found: false };
    el.classList.add('on');
    await new Promise(r => setTimeout(r, 320));   // 等 .22s 过渡完成
    const visOn = getComputedStyle(el).visibility;
    el.classList.remove('on');
    await new Promise(r => setTimeout(r, 320));
    const visOff = getComputedStyle(el).visibility;
    return { found: true, visOn, visOff };
  });
  check('savebar visibility 双态', sb.found && sb.visOn === 'visible' && sb.visOff === 'hidden', JSON.stringify(sb));

  // 8. .vh 盲文区存在且视觉隐身
  const vh = await pg.evaluate(() => {
    const el = document.getElementById('nrLive');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { w: r.width, h: r.height };
  });
  check('#nrLive 盲文区', vh && vh.w <= 1 && vh.h <= 1, JSON.stringify(vh));

  // 9. 390px 无页面级横向滚动（断点合并回归）
  await pg.setViewportSize({ width: 390, height: 800 });
  await pg.waitForTimeout(800);
  const ovf = await pg.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  check('390px 无横向溢出', !ovf);
  await pg.setViewportSize({ width: 1366, height: 900 });

  // 10. 8 档视口截图（概览/明细）
  await pg.evaluate(() => { location.hash = ''; });
  await pg.waitForTimeout(1200);
  await pg.screenshot({ path: 'audit_shots/v1554_overview_1366.png', fullPage: false });
  await pg.evaluate(() => { location.hash = '#details'; });
  await pg.waitForTimeout(1000);
  await pg.screenshot({ path: 'audit_shots/v1554_details_1366.png', fullPage: false });
  check('截图产出', fs.existsSync('audit_shots/v1554_overview_1366.png'));

  // console 错误总账（过滤 Chrome 扩展噪音与资源 404）
  const jsErrors = errors.filter(e => !/extension|net::ERR_FAILED|favicon/.test(e));
  check('零 JS 错', jsErrors.length === 0, jsErrors.join(' | ').slice(0, 300));

  await b.close();
  fs.writeFileSync(OUT, JSON.stringify({ results, errors }, null, 2));
  const failed = results.filter(r => !r.ok).length;
  console.log('====\nTOTAL ' + results.length + '  FAILED ' + failed);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
