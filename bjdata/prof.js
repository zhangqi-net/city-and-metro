// 性能剖析：定位月度推进的耗时分布。用法：node bjdata/prof.js [地图id] [目标年份]
// 例：node bjdata/prof.js bj 2026 / node bjdata/prof.js sz 2026
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
  getElementById: () => canvasStub(), createElement: () => canvasStub(),
  querySelector: () => null, querySelectorAll: () => [], addEventListener: noop,
  documentElement: { dataset: {}, style: { setProperty: noop }, classList: { add: noop, remove: noop } },
  body: { appendChild: noop, classList: { add: noop, remove: noop } },
};
global.localStorage = { getItem: () => null, setItem: noop, removeItem: noop };
global.matchMedia = () => ({ matches: false, addEventListener: noop });
global.devicePixelRatio = 1;
global.requestAnimationFrame = noop;
global.performance = { now: () => Date.now() };
global.navigator = { userAgent: 'node' };

const CM = {}; global.CM = CM; window.CM = CM;
const FILES = ['util.js', 'config.js', 'news.js', 'geo_gz.js', 'geo.js', 'data_gz.js', 'data_tutorial.js',
  'geo_hz.js', 'data_hz.js', 'geo_hk.js', 'data_hk.js', 'geo_tk.js', 'data_tk.js', 'geo_tp.js', 'data_tp.js',
  'geo_sz.js', 'data_sz.js', 'geo_bj.js', 'data_bj.js', 'maps.js', 'facility.js', 'city.js', 'metro.js', 'sim.js', 'economy.js', 'macro.js'];
for (const f of FILES) eval(fs.readFileSync(path.join(ROOT, 'js', f), 'utf8'));

const MAP = process.argv[2] || 'bj';
const target = +(process.argv[3] || 2026);
CM.useMap(MAP);
if (+process.argv[4]) CM.CFG.ZONE = +process.argv[4];
if (+process.argv[5]) CM.CFG.roadTreeLimit = +process.argv[5];
const CFG = CM.CFG;
console.log('=== 地图 ' + MAP + '  格 ' + CFG.W + 'x' + CFG.H + ' = ' + (CFG.W * CFG.H) + '  ZONE=' + CFG.ZONE + ' ===');

function ms(fn) { const t = process.hrtime.bigint(); const r = fn(); return [Number(process.hrtime.bigint() - t) / 1e6, r]; }

let t = 0;
const Y0 = (CM.MAPS[MAP] && CM.MAPS[MAP].cfg && CM.MAPS[MAP].cfg.START && CM.MAPS[MAP].cfg.START.y) || 1990;
const city = new CM.City();
let d, r;
[d] = ms(() => city.generate(Y0 * 10000 + 101, Y0));
console.log('generate            ' + d.toFixed(0).padStart(7) + ' ms');
console.log('  车行 links=' + city.car.links.length + ' 弧段=' + city.car.nA + ' 节点=' + city.car.nN +
  '  步行节点=' + city.walk.start.length + ' 步行弧=' + city.walk.to.length +
  '  道路组=' + city.roadGroups.length + '  区域=' + city.regions.length);

// 推进到目标年（不计时，只计时最后一年每月）
let mi = 0;
for (let y = Y0; y < target; y++) {
  if (y > Y0) { city.applyReclaim(y); city.applyRoads(y); city.activateLandmarks(y); }
  for (let m = 1; m <= 12; m++) {
    mi++;
    const gr = city.growMonth({ year: y + (m - 1) / 12, monthIndex: mi, zoneAccess: null, cellWalk: null, coverage: 0, econ: null });
    if (gr && gr.streetsChanged) { city.updateStreets(); city.buildGraphs(); }
  }
}
city.applyReclaim(target); city.applyRoads(target); city.activateLandmarks(target);
console.log('推进到 ' + target + '：人口 ' + Math.round(city.totals().pop).toLocaleString());

// ---- 单月各阶段计时 ----
const model = new CM.Model(city);
console.log('new Model           ' + (d = (() => { const a = process.hrtime.bigint(); model.setYear(target); return Number(process.hrtime.bigint() - a) / 1e6; })()).toFixed(0).padStart(7) + ' ms (setYear)');

[d] = ms(() => city.growMonth({ year: target, monthIndex: mi + 1, zoneAccess: null, cellWalk: null, coverage: 0, econ: null }));
console.log('growMonth           ' + d.toFixed(1).padStart(7) + ' ms');
[d] = ms(() => { city.updateStreets(); });
console.log('updateStreets       ' + d.toFixed(1).padStart(7) + ' ms');
[d] = ms(() => { city.buildGraphs(); });
console.log('buildGraphs         ' + d.toFixed(1).padStart(7) + ' ms  (仅在街道/道路变化时)');

const emptyNet = { stations: [], lines: [], segs: [] };
let C;
[d, C] = ms(() => CM.Metro.compile(emptyNet, city));
console.log('M.compile           ' + d.toFixed(1).padStart(7) + ' ms');

const steps = [];
function step(name, fn) { const [dd] = ms(fn); steps.push([name, dd]); console.log(name.padEnd(20) + dd.toFixed(1).padStart(7) + ' ms'); }

step('buildZones', () => model.buildZones());
const g = model.buildDemandGen();
(function drain() { const [dd] = ms(() => { let n = 0; while (!g.next().done && n++ < 100000); }); console.log('buildDemandGen'.padEnd(20) + dd.toFixed(1).padStart(7) + ' ms'); })();
step('syncRoad', () => { model.roadVer = -1; model.syncRoad(); });
step('computeArcZones', () => model.computeArcZones());
step('prepareRoad', () => model.prepareRoad());
step('computeAccess', () => model.computeAccess(C));
step('buildMetro', () => model.buildMetro(C));
step('setNetwork', () => model.setNetwork(C, true));

// 单次 iterate 计时（1 个时段）
(function () {
  const P0 = model.live.per[0];
  P0.iters = 1;   // 跳过 fullSkim 分支
  const g1 = model.iterate(model.net, P0, 0, {});
  let n = 0; const t0 = process.hrtime.bigint();
  while (!g1.next().done && n++ < 1e6);
  console.log('iterate(单时段,非fullSkim) ' + (Number(process.hrtime.bigint() - t0) / 1e6).toFixed(0).padStart(6) + ' ms   Z=' + model.Z + ' 弧段=' + model.road.nA + ' 节点=' + model.road.nN);
  P0.iters = 0;
  const g2 = model.iterate(model.net, P0, 0, { fullSkim: true });
  n = 0; const t1 = process.hrtime.bigint();
  while (!g2.next().done && n++ < 1e6);
  console.log('iterate(单时段,fullSkim)   ' + (Number(process.hrtime.bigint() - t1) / 1e6).toFixed(0).padStart(6) + ' ms');
})();

// 求解：一次完整 solveNow
let solved;
if (!process.env.QUICK) {
  [d] = ms(() => { model.solveNow(2); solved = true; });
  console.log('solveNow(2 cycles)  ' + d.toFixed(0).padStart(7) + ' ms');
}
if (process.env.SOLVE1) {
  [d] = ms(() => model.solveNow(1));
  const road = model.road, capF = model.capF || 1, P = model.live.per[0];
  let num = 0, den = 0, vol = 0;
  for (let a = 0; a < road.nA; a++) {
    const v = P.arcVol[a]; if (v <= 0) continue;
    const x = v / (road.arcCap[a] * capF);
    num += v * road.arcLen[a] * Math.min(8, 1 + CM.CFG.road.bprA * x * x * x * x); den += v * road.arcLen[a]; vol += v;
  }
  const D0 = model.daily || {};
  console.log('RESULT solveNow(1)=' + d.toFixed(0) + 'ms Z=' + model.Z + ' 拥堵=' + (den > 0 ? (num / den).toFixed(3) : '-') +
    ' 车公里=' + Math.round(den / 1000).toLocaleString() + ' 总出行=' + Math.round(D0.trips || 0).toLocaleString() +
    ' 覆盖=' + ((D0.coverage || 0) * 100).toFixed(1) + '%');
}

// 单独测一次 iterate 与一个 cycle
const P = model.live.per[0];
console.log('  per 数 ' + model.live.per.length + '  弧段 ' + model.road.nA);

// 再跑一个月（无路网变化）看重复成本
[d] = ms(() => { const gg = model.refreshCityGen(C); while (!gg.next().done); });
console.log('refreshCityGen      ' + d.toFixed(0).padStart(7) + ' ms');
[d] = ms(() => model.solveNow(2));
console.log('solveNow 第2次      ' + d.toFixed(0).padStart(7) + ' ms');
