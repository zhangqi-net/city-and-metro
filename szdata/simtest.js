// 出行模型冒烟测试：生成 2026 年的深圳，跑一遍出行求解，检查全网拥堵与深中通道的 v/c。
// 用法：node szdata/simtest.js [年份]
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
  'geo_sz.js', 'data_sz.js', 'maps.js', 'facility.js', 'city.js', 'metro.js', 'sim.js', 'economy.js', 'macro.js'];
for (const f of FILES) eval(fs.readFileSync(path.join(ROOT, 'js', f), 'utf8'));

const target = +(process.argv[2] || 2026);
CM.useMap('sz');
const city = new CM.City();
city.generate(19900101, 1990);
// 按月推进到目标年份（与游戏内一致：逐年开路、开区、落成地标，逐月人口与岗位增长）
const t0 = Date.now();
let mi = 0, rebuilt = 0;
for (let y = 1990; y <= target; y++) {
  if (y > 1990) {
    city.applyReclaim(y); city.applyRoads(y); city.activateLandmarks(y);
    for (let k = 0; k < city.regions.length; k++) {
      const rg = city.regions[k];
      if (city.regionOpen[k] || rg.open == null) continue;
      if (rg.id === 'airport' && !CM.DATA.airport.buildable) continue;
      if (y >= rg.open) city.openRegion(k, y, 1);
    }
  }
  if (y === target) break;
  for (let m = 1; m <= 12; m++) {
    mi++;
    const gr = city.growMonth({ year: y + (m - 1) / 12, monthIndex: mi, zoneAccess: null, cellWalk: null, coverage: 0, econ: null });
    if (gr && gr.streetsChanged) { city.updateStreets(); city.buildGraphs(); rebuilt++; }
  }
}
const tot = city.totals();
console.log('推进耗时 ' + (Date.now() - t0) + ' ms，重建路网 ' + rebuilt + ' 次；人口 ' + Math.round(tot.pop).toLocaleString() + '，岗位 ' + Math.round(tot.jobs).toLocaleString());

const model = new CM.Model(city);
model.setYear(target);
const t1 = Date.now();
model.solveNow(2);
const road = model.road, capF = model.capF || 1;
const P = model.live.per[0];
console.log('求解耗时 ' + (Date.now() - t1) + ' ms（推进 ' + (t1 - t0) + ' ms），弧段 ' + road.nA);

let num = 0, den = 0, hot = [];
for (let a = 0; a < road.nA; a++) {
  const v = P.arcVol[a]; if (v <= 0) continue;
  const x = v / (road.arcCap[a] * capF);
  num += v * road.arcLen[a] * Math.min(8, 1 + CM.CFG.road.bprA * x * x * x * x); den += v * road.arcLen[a];
  hot.push([x, a]);
}
console.log('全网车公里加权拥堵系数 ' + (den > 0 ? (num / den).toFixed(3) : '-'));

// 按路名统计 v/c
const nmOf = function (L) { const g = L.name ? city.roadGroups[L.name - 1] : null; return g ? g.name : '(无名)'; };
const byName = new Map();
for (let k = 0; k < road.links.length; k++) {
  const L = road.links[k], nm = nmOf(L);
  if (!['深中通道', '广深沿江高速', '滨海大道', '深南大道', '北环大道'].includes(nm)) continue;
  const a = 2 * k, v = P.arcVol[a], cap = road.arcCap[a] * capF;
  const base = CM.CFG.road.cap[L.cls] * (L.bridge ? 0.75 : 1) * capF;
  const e = byName.get(nm) || { v: 0, cap: 0, n: 0, max: 0, mul: 0, mulN: 0 };
  e.v += v; e.cap += cap; e.n++; e.max = Math.max(e.max, v / cap);
  e.mul += cap / base; e.mulN++;
  byName.set(nm, e);
}
console.log('\n--- 主要道路（工作日平均 v/c，最大值，能力倍数）');
for (const [nm, e] of byName) console.log('  ' + nm.padEnd(8) + ' 弧段 ' + String(e.n).padStart(4) + '  平均 v/c ' + (e.cap > 0 ? (e.v / e.cap).toFixed(2) : '-') + '  最高 ' + e.max.toFixed(2) + '  能力倍数 ' + (e.mul / e.mulN).toFixed(2));

hot.sort(function (p, q) { return q[0] - p[0]; });
console.log('\n--- 最堵的 8 段');
const seen = new Set();
let shown = 0;
for (const [x, a] of hot) {
  const k = a >> 1, L = road.links[k], nm = nmOf(L) + ' #' + k;
  if (seen.has(nm)) continue; seen.add(nm);
  console.log('  ' + (x * 100).toFixed(0).padStart(4) + '%  ' + nm);
  if (++shown >= 8) break;
}
