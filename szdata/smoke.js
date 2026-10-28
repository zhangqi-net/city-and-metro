// 无界面冒烟测试：加载数据与城市模块，生成深圳地图并逐年推进，检查区域、人口、地标、填海、道路与任务锚点。
// 用法：node szdata/smoke.js [目标年份]
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

const noop = function () {};
const ctxStub = new Proxy({}, {
  get(t, k) {
    if (k === 'canvas') return { width: 100, height: 100 };
    if (k in t) return t[k];
    if (k === 'measureText') return () => ({ width: 10 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient' || k === 'createPattern') return () => ({ addColorStop: noop });
    if (k === 'getImageData') return () => ({ data: new Uint8ClampedArray(4) });
    return noop;
  },
  set(t, k, v) { t[k] = v; return true; },
});
const canvasStub = () => ({ width: 100, height: 100, getContext: () => ctxStub, style: {}, addEventListener: noop, removeEventListener: noop });

global.window = global;
global.document = {
  getElementById: () => canvasStub(),
  createElement: () => canvasStub(),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: noop,
  documentElement: { dataset: {}, style: { setProperty: noop }, classList: { add: noop, remove: noop } },
  body: { appendChild: noop, classList: { add: noop, remove: noop } },
};
global.localStorage = { getItem: () => null, setItem: noop, removeItem: noop };
global.matchMedia = () => ({ matches: false, addEventListener: noop });
global.devicePixelRatio = 1;
global.requestAnimationFrame = noop;
global.performance = { now: () => Date.now() };
global.navigator = { userAgent: 'node' };

const CM = {};
global.CM = CM;
window.CM = CM;

const FILES = ['util.js', 'config.js', 'news.js', 'geo_gz.js', 'geo.js', 'data_gz.js', 'data_tutorial.js',
  'geo_hz.js', 'data_hz.js', 'geo_hk.js', 'data_hk.js', 'geo_tk.js', 'data_tk.js', 'geo_tp.js', 'data_tp.js',
  'geo_sz.js', 'data_sz.js', 'maps.js', 'facility.js', 'city.js', 'metro.js', 'sim.js', 'economy.js', 'macro.js'];

for (const f of FILES) {
  const src = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
  try { eval(src); } catch (e) { console.error('加载失败', f, e.message); process.exit(1); }
}

const target = +(process.argv[2] || 2026);
CM.useMap('sz');
const D = CM.DATA;
const t0 = Date.now();
const city = new CM.City();
city.generate(19900101, 1990);
console.log('生成耗时 ' + (Date.now() - t0) + ' ms，格数 ' + city.N);

const P = CM.GEOS.sz.proj;
const gx = (lon) => (lon - P.lon0) * P.kx, gy = (lat) => (P.lat0 - lat) * P.ky;
const where = function (lat, lon) {
  const c = city.cellAt(gx(lon), gy(lat));
  return c < 0 ? '图外' : city.regions[city.region[c]].name;
};

console.log('\n--- 地点归属');
const SPOTS = [['东门', 22.5459, 114.1180], ['华强北', 22.5480, 114.0880], ['福田CBD', 22.5400, 114.0600],
  ['科技园', 22.5400, 113.9500], ['西丽', 22.5850, 113.9500], ['莲塘', 22.5670, 114.1750], ['盐田', 22.5600, 114.2400],
  ['沙头角', 22.5470, 114.2350], ['石岩', 22.6800, 113.9300], ['龙华', 22.6500, 114.0300], ['观澜', 22.7000, 114.0600],
  ['龙岗中心城', 22.7150, 114.2450], ['宝安中心', 22.5700, 113.9050], ['机场T3', 22.6300, 113.8070],
  ['前海', 22.5350, 113.8900], ['后海', 22.5200, 113.9400], ['光明', 22.7350, 113.9300], ['香港元朗', 22.4400, 114.0300],
  ['梧桐山顶', 22.5820, 114.2110], ['羊台山顶', 22.6320, 113.9550]];
for (const s of SPOTS) console.log('  ' + s[0].padEnd(10) + ' → ' + where(s[1], s[2]));

console.log('\n--- 区域');
let bad = 0;
city.regions.forEach(function (r, k) {
  let n = 0, pop = 0;
  for (let c = 0; c < city.N; c++) if (city.region[c] === k) { n++; pop += city.pop[c]; }
  if (!n) bad++;
  console.log('  ' + String(r.name).padEnd(24) + ' open=' + String(r.open).padEnd(5) + ' 格 ' + String(n).padStart(4) + '  人口 ' + Math.round(pop).toLocaleString() + '  中心 (' + (r.cx && r.cx.toFixed(1)) + ',' + (r.cy && r.cy.toFixed(1)) + ')');
});
if (bad) console.log('  ⚠ 有 ' + bad + ' 个区域没有分到格子');

const tot0 = city.totals();
console.log('\n1990：人口 ' + Math.round(tot0.pop).toLocaleString() + '，岗位 ' + Math.round(tot0.jobs).toLocaleString());
let hill = 0, airport = 0, land = 0;
for (let c = 0; c < city.N; c++) { if (city.landFrac[c] >= 0.5) land++; if (city.lu[c] === CM.LU.HILL) hill++; if (city.lu[c] === CM.LU.AIRPORT) airport++; }
console.log('陆地格 ' + land + '，山体格 ' + hill + '，机场格 ' + airport);

// 填海前后
const rcCell = function (id) {
  const r = (D.reclaim || []).find(function (x) { return x.id === id; });
  const p = r.poly, cx = p.reduce(function (a, q) { return a + q[0]; }, 0) / p.length, cy = p.reduce(function (a, q) { return a + q[1]; }, 0) / p.length;
  return city.cellAt(cx, cy);
};
console.log('\n--- 填海（中心格陆水比例，1=全陆地 0=全水面）');
for (const id of ['houhai', 'qianhai']) {
  const r = D.reclaim.find(function (x) { return x.id === id; });
  const c = rcCell(id);
  console.log('  ' + r.name + '（' + r.year + '）1990 年 ' + city.landFrac[c].toFixed(2) + ' → ' + target + ' 年 ' + (target >= r.year ? '1.00（已成陆）' : city.landFrac[c].toFixed(2)));
}

// 深中通道
const sd = city.roadGroups.filter(function (g) { return g.name === '深中通道'; });
console.log('\n深中通道：' + sd.length + ' 组，通车年 ' + (sd.length ? sd[0].year : '-') + '，1990 年已建 ' + city.roadsBuilt[city.roadGroups.indexOf(sd[0])]);

// 任务锚点
console.log('\n--- 任务锚点');
let badAnchor = 0;
for (const t of (D.histTasks || []).concat(D.dynTasks || [])) {
  for (const a of t.anchors || []) {
    const c = city.cellAt(a.x, a.y);
    const rg = c < 0 ? null : city.regions[city.region[c]];
    const ok = c >= 0 && rg && !rg.scenic && rg.open != null;
    if (!ok) { badAnchor++; console.log('  ⚠ ' + t.id + ' / ' + a.name + ' 在 ' + (c < 0 ? '图外' : rg.name) + ' (' + a.x.toFixed(1) + ',' + a.y.toFixed(1) + ')'); }
  }
}
if (!badAnchor) console.log('  全部 ' + (D.histTasks.length + D.dynTasks.length) + ' 个任务的锚点都在可建设区域内');

// 逐年推进
console.log('\n--- 逐年推进');
let lastPop = tot0.pop;
for (let y = 1991; y <= target; y++) {
  city.applyReclaim(y);
  const rch = city.applyRoads(y);
  city.activateLandmarks(y);
  for (let k = 0; k < city.regions.length; k++) {
    const rg = city.regions[k];
    if (city.regionOpen[k] || rg.open == null) continue;
    if (rg.id === 'airport' && !D.airport.buildable) continue;
    if (y >= rg.open) city.openRegion(k, y, 1);
  }
  const built = city.roadsBuilt.reduce(function (a, b) { return a + b; }, 0);
  const lms = city.landmarkOn.reduce(function (a, b) { return a + b; }, 0);
  const ops = city.regionOpen.reduce(function (a, b) { return a + b; }, 0);
  if (y === target || y % 5 === 0 || rch) console.log('  ' + y + '：通车 ' + built + ' / ' + city.roadGroups.length + '，地标 ' + lms + ' / ' + D.landmarks.length + '，开放区域 ' + ops + ' / ' + city.regions.length);
}
const lmOff = D.landmarks.filter(function (l, i) { return !city.landmarkOn[i]; });
if (lmOff.length) console.log('  ⚠ 未落成地标：' + lmOff.map(function (l) { return l.name + '(' + l.year + ')'; }).join('、'));

const act = CM.Fac.list().filter(function (f) { return CM.Fac.active(f, target, city); });
console.log('\n' + target + ' 年运营中的设施 ' + act.length + ' / ' + CM.Fac.list().length);
console.log('  ' + act.map(function (f) { return f.name; }).join('、'));
console.log('\n填海地形版本 ' + Math.max(1, city.terrainYear) + '，水域格 ' + city.landFrac.reduce(function (a, v) { return a + (v < 0.5 ? 1 : 0); }, 0));
