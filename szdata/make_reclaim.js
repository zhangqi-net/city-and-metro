// 生成填海多边形的辅助脚本：北边贴着 1990 年的岸线（滨海大道 / 前海北界），
// 南边按「现代 OSM 陆地」的实际岸线走，避免手工四边形在图上看成一个方块。
// 用法：node szdata/make_reclaim.js
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

CM.useMap('sz');
const city = new CM.City();
city.generate(19900101, 1990);
const W = city.W;

// 从北界往下，一列一列量出「现代陆地」占到第几行（遇到水就停）
function profile(x0, x1, y0, yMax) {
  const out = [];
  for (let x = x0; x <= x1; x++) {
    let y = y0;
    while (y + 1 <= yMax && city.landMax[(y + 1) * W + x] >= 0.5 && city.landMax[y * W + x] >= 0.5) y++;
    out.push([x, y]);
  }
  return out;
}

function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const d2 = function (p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const L = dx * dx + dy * dy;
    if (!L) return Math.hypot(p[0] - a[0], p[1] - a[1]);
    let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
  };
  let maxd = 0, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) { const d = d2(pts[i], pts[0], pts[pts.length - 1]); if (d > maxd) { maxd = d; idx = i; } }
  if (maxd <= tol) return [pts[0], pts[pts.length - 1]];
  return simplify(pts.slice(0, idx + 1), tol).slice(0, -1).concat(simplify(pts.slice(idx), tol));
}

const JOBS = [
  { id: 'houhai', x0: 74, x1: 92, y0: 87, yMax: 96 },
  { id: 'qianhai', x0: 55, x1: 70, y0: 77, yMax: 92 },
];

for (const job of JOBS) {
  const old = city && CM.DATA.reclaim.find(function (r) { return r.id === job.id; });
  const prof = profile(job.x0, job.x1, job.y0, job.yMax).filter(function (p) { return p[1] > job.y0; });
  if (prof.length < 2) { console.log('// ' + job.id + '：没有可填的海域'); continue; }
  // 南岸从右往左走，北岸从左往右走，合成闭合多边形
  const south = simplify(prof, 0.45);
  const poly = [[job.y0 && prof[0][0], job.y0]];
  for (const p of south) poly.push([p[0], p[1]]);
  poly.push([prof[prof.length - 1][0], job.y0]);
  let area = 0;
  for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; area += a[0] * b[1] - b[0] * a[1]; }
  area = Math.abs(area) / 2;
  const oldArea = Math.abs(old.poly.reduce(function (a, p, i, arr) { const q = arr[(i + 1) % arr.length]; return a + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;
  console.log('\n// ' + old.name + '（' + old.year + '）：' + poly.length + ' 点，约 ' + area.toFixed(1) + ' 格² = ' + (area * 0.0625).toFixed(2) + ' km²（原四边形 ' + oldArea.toFixed(1) + ' 格² = ' + (oldArea * 0.0625).toFixed(2) + ' km²）');
  console.log('    poly: [' + poly.map(function (p) { return '[' + p[0] + ', ' + p[1] + ']'; }).join(', ') + '],');
}
