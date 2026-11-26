// 无界面冒烟测试：加载数据与城市模块，生成西安地图并逐年推进，检查区域、人口、地标、道路与任务锚点。
// 用法：node xadata/smoke.js [目标年份]
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
  'geo_sz.js', 'data_sz.js', 'geo_xa.js', 'data_xa.js', 'maps.js', 'facility.js', 'city.js', 'metro.js', 'sim.js', 'economy.js', 'macro.js'];

for (const f of FILES) {
  const src = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
  try { eval(src); } catch (e) { console.error('加载失败', f, e.message); process.exit(1); }
}

const target = +(process.argv[2] || 2026);
CM.useMap('xa');
const D = CM.DATA;
const t0 = Date.now();
const Y0 = (CM.MAPS.xa && CM.MAPS.xa.cfg && CM.MAPS.xa.cfg.START && CM.MAPS.xa.cfg.START.y) || 2006;
const city = new CM.City();
city.generate(Y0 * 10000 + 101, Y0);
console.log('生成耗时 ' + (Date.now() - t0) + ' ms，格数 ' + city.N);

const P = CM.GEOS.xa.proj;
const gx = (lon) => (lon - P.lon0) * P.kx, gy = (lat) => (P.lat0 - lat) * P.ky;
const where = function (lat, lon) {
  const c = city.cellAt(gx(lon), gy(lat));
  return c < 0 ? '图外' : city.regions[city.region[c]].name;
};

console.log('\n--- 地点归属');
const SPOTS = [['钟楼', 34.263, 108.942], ['西安北站', 34.381022, 108.934124], ['纺织城', 34.2300, 109.0590],
  ['后卫寨', 34.3015, 108.8090], ['高新区', 34.2330, 108.8997], ['大雁塔', 34.2247, 108.9592],
  ['韦曲南', 34.1437, 108.9409], ['常宁宫', 34.1115, 108.9335], ['航天城', 34.1440, 109.0080],
  ['咸阳人民路', 34.3315, 108.7088], ['咸阳西站', 34.3320, 108.6573], ['陈杨寨', 34.3120, 108.7020],
  ['沣河森林公园', 34.3187, 108.7480], ['咸阳机场T1-T3', 34.4370, 108.7560], ['机场T5', 34.4523, 108.7800],
  ['汉阳陵', 34.4350, 108.7900], ['秦汉新城', 34.3964, 108.8430], ['摆旗寨', 34.3915, 108.7920],
  ['国际港务区', 34.3624, 109.0343], ['临潼方向（图外）', 34.3670, 109.2200], ['户县方向（图外）', 34.1000, 108.6000]];
for (const s of SPOTS) console.log('  ' + s[0].padEnd(10) + ' → ' + where(s[1], s[2]));

console.log('\n--- 区域');
let bad = 0;
city.regions.forEach(function (r, k) {
  let n = 0, pop = 0;
  for (let c = 0; c < city.N; c++) if (city.region[c] === k) { n++; pop += city.pop[c]; }
  if (!n) bad++;
  console.log('  ' + String(r.name).padEnd(24) + ' open=' + String(r.open == null ? '开局' : r.open).padEnd(5) + ' 格 ' + String(n).padStart(4) + '  人口 ' + Math.round(pop).toLocaleString() + '  中心 (' + (r.cx && r.cx.toFixed(1)) + ',' + (r.cy && r.cy.toFixed(1)) + ')');
});
if (bad) console.log('  ⚠ 有 ' + bad + ' 个区域没有分到格子');

// 任务锚点
console.log('\n--- 任务锚点');
let badAnchor = 0;
for (const t of (D.histTasks || []).concat(D.dynTasks || [])) {
  for (const a of t.anchors || []) {
    const c = city.cellAt(a.x, a.y);
    const rg = c < 0 ? null : city.regions[city.region[c]];
    // 西安为一次性开图：区域无 open 字段即开局开放，锚点只需在图内且非风景区
    const ok = c >= 0 && rg && !rg.scenic;
    if (!ok) { badAnchor++; console.log('  ⚠ ' + t.id + ' / ' + a.name + ' 在 ' + (c < 0 ? '图外' : rg.name) + ' (' + a.x.toFixed(1) + ',' + a.y.toFixed(1) + ')'); }
  }
}
if (!badAnchor) console.log('  全部 ' + (D.histTasks.length + D.dynTasks.length) + ' 个任务的锚点都在可建设区域内');

// 逐年推进
console.log('\n--- 逐年推进');
const tot0 = city.totals();
console.log('  ' + Y0 + '：人口 ' + Math.round(tot0.pop).toLocaleString() + '，岗位 ' + Math.round(tot0.jobs).toLocaleString());
let land = 0;
for (let c = 0; c < city.N; c++) if (city.landFrac[c] >= 0.5) land++;
console.log('  陆地格 ' + land);
for (let y = Y0 + 1; y <= target; y++) {
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
