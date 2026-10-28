// 无界面冒烟测试：加载数据与城市模块，生成北京地图并逐年推进，检查区域、人口、地标、道路与任务锚点。
// 用法：node bjdata/smoke.js [目标年份]
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
  'geo_sz.js', 'data_sz.js', 'geo_bj.js', 'data_bj.js', 'maps.js', 'facility.js', 'city.js', 'metro.js', 'sim.js', 'economy.js', 'macro.js'];

for (const f of FILES) {
  const src = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
  try { eval(src); } catch (e) { console.error('加载失败', f, e.message); process.exit(1); }
}

const target = +(process.argv[2] || 2026);
CM.useMap('bj');
const D = CM.DATA;
const t0 = Date.now();
const city = new CM.City();
city.generate(19900101, 1990);
console.log('生成耗时 ' + (Date.now() - t0) + ' ms，格数 ' + city.N);

const P = CM.GEOS.bj.proj;
const gx = (lon) => (lon - P.lon0) * P.kx, gy = (lat) => (P.lat0 - lat) * P.ky;
const where = function (lat, lon) {
  const c = city.cellAt(gx(lon), gy(lat));
  return c < 0 ? '图外' : city.regions[city.region[c]].name;
};

console.log('\n--- 地点归属');
const SPOTS = [['天安门', 39.9087, 116.3975], ['王府井', 39.9150, 116.4110], ['西单', 39.9070, 116.3750],
  ['国贸', 39.9088, 116.4570], ['金融街', 39.9160, 116.3600], ['中关村', 39.9860, 116.3160],
  ['清华', 39.9995, 116.3260], ['北京站', 39.9028, 116.4210], ['北京西站', 39.8948, 116.3220],
  ['北京南站', 39.8650, 116.3780], ['首都机场', 40.0600, 116.5920], ['望京', 39.9960, 116.4700],
  ['亚运村', 40.0000, 116.3990], ['回龙观', 40.0650, 116.3450], ['天通苑', 40.0700, 116.4250],
  ['石景山', 39.9100, 116.2400], ['丰台镇', 39.8630, 116.3100], ['方庄', 39.8760, 116.4430],
  ['酒仙桥', 39.9600, 116.4820], ['香山', 39.9900, 116.1890], ['天坛', 39.8822, 116.4066]];
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
const tot0 = city.totals();
console.log('  1990：人口 ' + Math.round(tot0.pop).toLocaleString() + '，岗位 ' + Math.round(tot0.jobs).toLocaleString());
let land = 0;
for (let c = 0; c < city.N; c++) if (city.landFrac[c] >= 0.5) land++;
console.log('  陆地格 ' + land);
for (let y = 1991; y <= target; y++) {
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
