'use strict';
// 高德栅格瓦片背景层（免 Key 公开 XYZ 端点）
//
// 作用：把高德地图的栅格瓦片作为**视觉底图**画在游戏自绘地面之下。
// 这只是一层图片，不参与任何玩法计算 —— geo_*.js 的矢量几何（水系 / 道路 / 铁路 /
// 绿地 / 行政区）仍由 city.js 栅格化成掩膜、建路网拓扑、匹配区域，一行都没替换。
//
// 关键实现：
//  1. 游戏用「格网等距近似投影」(proj.kx/ky)，高德瓦片用 Web Mercator + GCJ-02。
//     因此先把 WGS-84 世界坐标转到 GCJ-02（国测局偏移算法，与 TeslaMate 中文版
//     install-coord-functions.sql 同源），再算墨卡托全局像素。
//  2. 屏幕 CSS 像素 <-> 墨卡托像素用一个仿射变换拟合（取屏幕左上/右上/左下三点）。
//     30 km 的地图范围内 Mercator 的非线性误差远小于 1 像素，可忽略。
//     一次 setTransform 后即可按墨卡托坐标直接 drawImage，天然支持平移与缩放。
//  3. 瓦片异步加载、LRU 缓存、失败自动换 CDN 子域重试；整批失败时判定为离线，
//     自绘地面自动恢复不透明（不会出现白屏），并每 20 s 重试一次。
//  4. 等距视图（cam.view=1）与地下视图在 render.js 里通过 alpha 淡出，避免透视错乱。
//
// 端点实测（2026-11-24）：wprd01..04 / webst01..04 均返回 image/png(jpeg)，
// 且带 access-control-allow-origin: * ，所以 Image.crossOrigin='anonymous' 后
// canvas.toDataURL() 不会被污染，PNG 导出不受影响。
//
// 注意：这些是地图前端使用的公开端点，不在高德官方 Web 服务 API 文档内；
// 在线实时加载、不落地存储、不二次分发。用于个人研究/本地游玩；若公开发布请自行
// 评估高德服务条款 7.3（禁止缓存、下载、截图、制作衍生品）。
(function (CM) {
  'use strict';
  const TILE = 256;
  const MIN_Z = 3, MAX_Z = 18;
  const MAX_TILES = 120;          // 单帧最多请求的瓦片数，防止极端缩放打爆网络
  const CACHE_MAX = 400;
  const FADE_SPEED = 6;           // 瓦片淡入 / 自绘地面淡出速度
  const RETRY_MS = 20000;

  let enabled = true, style = 'road', night = false;
  let proj = null;                // { lon0, lat0, kx, ky }
  let mapId = null;
  let fade = 0, degraded = false, lastRetry = 0;
  const cache = new Map();        // key -> { img, state, tries, host, used }
  let seq = 0;

  // ---------------- WGS-84 -> GCJ-02（国测局偏移 / eviltransform） ----------------
  function outOfChina(lat, lon) {
    return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
  }
  function transLat(x, y) {
    let r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    r += (20 * Math.sin(y * Math.PI) + 40 * Math.sin(y / 3 * Math.PI)) * 2 / 3;
    r += (160 * Math.sin(y / 12 * Math.PI) + 320 * Math.sin(y * Math.PI / 30)) * 2 / 3;
    return r;
  }
  function transLon(x, y) {
    let r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    r += (20 * Math.sin(x * Math.PI) + 40 * Math.sin(x / 3 * Math.PI)) * 2 / 3;
    r += (150 * Math.sin(x / 12 * Math.PI) + 300 * Math.sin(x / 30 * Math.PI)) * 2 / 3;
    return r;
  }
  function wgs2gcj(lat, lon) {
    if (outOfChina(lat, lon)) return [lat, lon];
    const a = 6378245.0, ee = 0.00669342162296594323;
    let dLat = transLat(lon - 105, lat - 35), dLon = transLon(lon - 105, lat - 35);
    const rad = lat / 180 * Math.PI;
    let magic = Math.sin(rad); magic = 1 - ee * magic * magic;
    const sq = Math.sqrt(magic);
    dLat = dLat * 180 / ((a * (1 - ee)) / (magic * sq) * Math.PI);
    dLon = dLon * 180 / (a / sq * Math.cos(rad) * Math.PI);
    return [lat + dLat, lon + dLon];
  }

  // ---------------- Web Mercator ----------------
  function merc(lon, lat, z) {
    const s = TILE * Math.pow(2, z);
    let sn = Math.sin(lat * Math.PI / 180);
    sn = Math.max(-0.9999, Math.min(0.9999, sn));
    return [(lon + 180) / 360 * s, (0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI)) * s];
  }
  // 屏幕像素 -> 世界格 -> WGS-84 -> GCJ-02 -> 墨卡托全局像素
  function screenToMerc(R, sx, sy, z) {
    const w = R.unproject(sx, sy);
    const lon = proj.lon0 + w.x / proj.kx;
    const lat = proj.lat0 - w.y / proj.ky;
    const g = wgs2gcj(lat, lon);
    return merc(g[1], g[0], z);
  }
  // 选 z：让 256 px 瓦片按接近 1:1 的屏幕像素显示，最清晰且瓦片数可控
  function pickZoom(R) {
    const a = screenToMerc(R, 0, 0, 14), b = screenToMerc(R, R.w, 0, 14);
    const s14 = Math.abs(b[0] - a[0]) / Math.max(1, R.w);
    if (!(s14 > 0) || !isFinite(s14)) return 14;
    const z = 14 - Math.log(s14) / Math.LN2;
    return Math.max(MIN_Z, Math.min(MAX_Z, Math.round(z)));
  }
  // 用三点拟合屏幕 <-> 墨卡托的仿射变换
  function affine(R, z) {
    const m00 = screenToMerc(R, 0, 0, z);
    const m10 = screenToMerc(R, R.w, 0, z);
    const m01 = screenToMerc(R, 0, R.h, z);
    const W = Math.max(1, R.w), H = Math.max(1, R.h);
    const A = (m10[0] - m00[0]) / W, B = (m01[0] - m00[0]) / H, C0 = m00[0];
    const D = (m10[1] - m00[1]) / W, E = (m01[1] - m00[1]) / H, F0 = m00[1];
    const det = A * E - B * D;
    if (!isFinite(det) || Math.abs(det) < 1e-12) return null;
    return {
      s2m: { A: A, B: B, C: C0, D: D, E: E, F: F0 },
      // merc -> screen：sx = a*mx + b*my + c, sy = d*mx + e*my + f
      m2s: { a: E / det, b: -B / det, c: (-E * C0 + B * F0) / det,
             d: -D / det, e: A / det, f: (D * C0 - A * F0) / det },
    };
  }
  function mercAtScreen(af, sx, sy) {
    const p = af.s2m;
    return [p.A * sx + p.B * sy + p.C, p.D * sx + p.E * sy + p.F];
  }

  // ---------------- 瓦片 URL 与缓存 ----------------
  function urlFor(x, y, z, host) {
    const n = (host % 4) + 1;
    if (style === 'satellite')
      return 'https://webst0' + n + '.is.autonavi.com/appmaptile?style=6&x=' + x + '&y=' + y + '&z=' + z;
    return 'https://wprd0' + n + '.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x=' + x + '&y=' + y + '&z=' + z;
  }
  function get(x, y, z) {
    const key = style + ':' + z + ':' + x + ':' + y;
    let e = cache.get(key);
    if (e) { e.used = ++seq; return e; }
    const img = new Image();
    img.crossOrigin = 'anonymous';       // 端点返回 ACAO:*，避免污染画布导致 PNG 导出失败
    e = { img: img, state: 0, host: (x + y) % 4, tries: 0, used: ++seq };
    cache.set(key, e);
    img.onload = function () { e.state = 1; e.used = ++seq; };
    img.onerror = function () {
      e.tries++;
      if (e.tries < 3) { e.host = (e.host + 1) % 4; img.src = urlFor(x, y, z, e.host); }
      else e.state = 2;
    };
    img.src = urlFor(x, y, z, e.host);
    return e;
  }
  function trim() {
    if (cache.size <= CACHE_MAX) return;
    const arr = Array.from(cache.entries()).sort(function (a, b) { return a[1].used - b[1].used; });
    for (let i = 0; i < arr.length - CACHE_MAX; i++) cache.delete(arr[i][0]);
  }
  function reset() { cache.clear(); degraded = false; fade = 0; }

  function fadeOut(R) {
    fade = Math.max(0, fade - Math.min(1, (R.dt || 0.016) * FADE_SPEED));
    return fade;
  }

  // ---------------- 绘制 ----------------
  // maxAlpha 由 render.js 传入：(1 - 等距过渡) * (1 - 地下过渡)
  // 返回实际生效的 alpha；render.js 据此把自绘地面降到 TILE_GROUND_ALPHA
  function draw(ctx, R, maxAlpha) {
    if (CM.mapId !== mapId) {
      mapId = CM.mapId;
      const G = CM.GEO;
      proj = G && G.proj && isFinite(G.proj.kx) && isFinite(G.proj.ky) ? G.proj : null;
      fade = 0; degraded = false;
    }
    if (!enabled || !R.amapTheme || !R.game || R.game.preview || !proj || maxAlpha <= 0.01) return fadeOut(R);
    if (degraded && Date.now() - lastRetry > RETRY_MS) { reset(); lastRetry = Date.now(); }

    const z = pickZoom(R), af = affine(R, z);
    if (!af) return fadeOut(R);
    const pts = [mercAtScreen(af, 0, 0), mercAtScreen(af, R.w, 0),
                 mercAtScreen(af, 0, R.h), mercAtScreen(af, R.w, R.h)];
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
    const tx0 = Math.floor(x0 / TILE) - 1, tx1 = Math.floor(x1 / TILE) + 1;
    const ty0 = Math.floor(y0 / TILE) - 1, ty1 = Math.floor(y1 / TILE) + 1;
    if ((tx1 - tx0 + 1) * (ty1 - ty0 + 1) > MAX_TILES) return fadeOut(R);

    const max = Math.pow(2, z), list = [];
    let any = false, loading = 0, failed = 0;
    for (let ty = ty0; ty <= ty1; ty++) for (let tx = tx0; tx <= tx1; tx++) {
      if (tx < 0 || ty < 0 || tx >= max || ty >= max) continue;
      const e = get(tx, ty, z);
      if (e.state === 1) any = true; else if (e.state === 2) failed++; else loading++;
      list.push([tx, ty, e]);
    }
    trim();
    if (!any && list.length && !loading && failed === list.length) {
      degraded = true; lastRetry = Date.now();     // 整批失败：判定离线，交给自绘底图兜底
    }

    const target = any ? maxAlpha : 0;
    fade += (target - fade) * Math.min(1, (R.dt || 0.016) * FADE_SPEED);
    if (fade < 0.015) return 0;

    ctx.save();
    const dpr = R.dpr || 1, m = af.m2s;
    ctx.setTransform(dpr * m.a, dpr * m.d, dpr * m.b, dpr * m.e, dpr * m.c, dpr * m.f);
    ctx.globalAlpha = fade;
    ctx.imageSmoothingEnabled = true;
    const useFilter = night && ('filter' in ctx);
    if (useFilter) ctx.filter = 'brightness(0.58) saturate(0.72) contrast(1.06)';
    for (let i = 0; i < list.length; i++) {
      const it = list[i];
      if (it[2].state !== 1) continue;
      try { ctx.drawImage(it[2].img, it[0] * TILE, it[1] * TILE, TILE, TILE); } catch (err) { /* 忽略单块解码失败 */ }
    }
    if (useFilter) ctx.filter = 'none';
    else if (night) {   // 不支持 filter 时退化为叠一层深蓝
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.globalAlpha = fade * 0.42; ctx.fillStyle = '#0a1422'; ctx.fillRect(0, 0, R.w, R.h);
    }
    ctx.restore();
    return fade;
  }

  CM.AmapTiles = {
    setEnabled: function (v) { enabled = !!v; if (!enabled) fade = 0; },
    setStyle: function (s) { const v = s === 'satellite' ? 'satellite' : 'road'; if (v !== style) { style = v; cache.clear(); fade = 0; } },
    onTheme: function (n) { night = !!n; },
    active: function () { return enabled && !degraded && !!proj; },
    status: function () { return !enabled ? '已关闭' : degraded ? '离线（已回退自绘底图）' : !proj ? '该地图无投影参数' : '在线 · ' + (style === 'satellite' ? '卫星' : '道路'); },
    reset: reset,
    draw: draw,
    // 供 Node 侧单测（不依赖 DOM）
    _test: { wgs2gcj: wgs2gcj, merc: merc, pickZoom: pickZoom, affine: affine, mercAtScreen: mercAtScreen, setProj: function (p) { proj = p; }, screenToMerc: screenToMerc },
  };
})(typeof window !== 'undefined' ? window.CM : (globalThis.CM = globalThis.CM || {}));
