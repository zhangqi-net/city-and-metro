// 方案对比：同一起点跑不同 (ZONE, 早停) 组合，比较耗时与结果指标。
// 用法：node bjdata/compare.js
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

const YEAR = 2026, CYCLES = +(process.env.CYCLES || 3);
const COMBOS = (process.env.COMBOS || '4:0,4:45,6:0,6:45,8:0,8:45').split(',').map(function (s) { return s.split(':').map(Number); });
const WITHNET = !!process.env.WITHNET;   // 是否接入开局既有地铁网（1、2 号线 30 站）

function run(zone, limit) {
  CM.useMap(process.env.MAP || 'bj');
  if (zone) CM.CFG.ZONE = zone;
  if (limit) CM.CFG.roadTreeLimit = limit;
  const city = new CM.City();
  city.generate(19900101, 1990);
  let mi = 0;
  for (let y = 1990; y < YEAR; y++) {
    if (y > 1990) { city.applyReclaim(y); city.applyRoads(y); city.activateLandmarks(y); }
    for (let m = 1; m <= 12; m++) {
      mi++;
      const gr = city.growMonth({ year: y + (m - 1) / 12, monthIndex: mi, zoneAccess: null, cellWalk: null, coverage: 0, econ: null });
      if (gr && gr.streetsChanged) { city.updateStreets(); city.buildGraphs(); }
    }
  }
  city.applyReclaim(YEAR); city.applyRoads(YEAR); city.activateLandmarks(YEAR);
  const model = new CM.Model(city);
  model.setYear(YEAR);
  if (WITHNET) {
    const net = CM.Metro.empty();
    const IN = CM.DATA.initialNetwork;
    for (const L of IN.lines) {
      const lid = CM.Metro.newLine(net, L.name);
      let prev = null;
      for (const st of L.stations) {
        const sid = CM.Metro.addStation(net, st[1], st[2], { size: st[3] || L.size || 'M', type: L.type || 'underground' }, city);
        net.stations[sid].name = st[0];
        if (prev) CM.Metro.addSegment(net, lid, prev, sid, [], L.type || 'underground');
        prev = sid;
      }
    }
    model.setNetwork(CM.Metro.compile(net, city));
  }
  const t0 = Date.now();
  model.solveNow(CYCLES);
  const ms = Date.now() - t0;
  const road = model.road, capF = model.capF || 1, P = model.live.per[0];
  let num = 0, den = 0;
  for (let a = 0; a < road.nA; a++) {
    const v = P.arcVol[a]; if (v <= 0) continue;
    const x = v / (road.arcCap[a] * capF);
    num += v * road.arcLen[a] * Math.min(8, 1 + CM.CFG.road.bprA * x * x * x * x); den += v * road.arcLen[a];
  }
  const D = model.daily || {};
  return {
    zone, limit, ms, Z: model.Z, arc: road.nA,
    cong: den > 0 ? num / den : 0,
    trips: D.trips || 0, vkt: den / 1000, commute: D.commute || 0,
    perIter: ms / (CYCLES * 2 * 4),
  };
}

const base = null;
console.log('ZONE 早停   小区数  弧段   求解' + CYCLES + '轮    单轮迭代   拥堵系数   总出行(万)   车公里(万)   平均通勤(min)');
for (const [z, lim] of COMBOS) {
  const r = run(z, lim);
  console.log(
    String(z).padEnd(4) + String(lim || '-').padEnd(6) +
    String(r.Z).padStart(6) + String(r.arc).padStart(7) +
    (r.ms + 'ms').padStart(10) + (r.perIter.toFixed(0) + 'ms').padStart(11) +
    r.cong.toFixed(3).padStart(11) +
    (r.trips / 1e4).toFixed(1).padStart(12) +
    (r.vkt / 1e4).toFixed(1).padStart(12) +
    (r.commute).toFixed(1).padStart(14));
}
