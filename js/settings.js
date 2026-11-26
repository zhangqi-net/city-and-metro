'use strict';
// 设置：只保留常用项（主题、界面大小、地图标注、交通动画、声音与三路音量、自动保存），保存在本地；变化时立即生效并通知各模块
(function (CM) {
  const KEY = 'cm1.settings';
  const DEF = {
    theme: 'auto',        // light | dark | auto（跟随系统）
    uiScale: 1,           // 界面大小
    labels: 'all',        // 地图标注：all 全部 | stations 仅车站 | none 关闭
    agents: true,         // 车辆、行人与列车动画
    sound: true, volume: 0.6,   // 总开关与总音量
    trainVol: 0.7, ambVol: 0.6, // 列车音效、城市环境音（v2.0）
    autosave: true,
    amapTiles: true,      // 高德栅格瓦片背景层（仅带 amap 标记的地图，需联网）
    amapStyle: 'road',    // road | satellite
    amapClear: true,      // 清晰底图：瓦片生效时去掉半透明自绘地面蒙版
  };
  let cur = Object.assign({}, DEF);
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (s) {
      for (const k in DEF) if (s[k] !== undefined) cur[k] = s[k];
      // 旧版的两个标注开关合并为一项
      if (s.labels === undefined && (s.stationLabels === false || s.mapLabels === false)) cur.labels = s.stationLabels === false ? 'none' : 'stations';
    } else {
      const t = localStorage.getItem('cm1.theme'); if (t === 'light' || t === 'dark') cur.theme = t;
      const so = JSON.parse(localStorage.getItem('cm1.sound') || 'null'); if (so) { cur.sound = so.enabled !== false; if (isFinite(so.volume)) cur.volume = so.volume; }
    }
  } catch (e) { /* 存储不可用时使用默认值 */ }
  // URL 参数临时覆盖（不写回本地存档）：?amap=0 关闭瓦片，?amapStyle=satellite 切卫星图
  try {
    const q = new URLSearchParams(location.search);
    if (q.has('amap')) cur.amapTiles = q.get('amap') !== '0';
    if (q.has('amapStyle')) cur.amapStyle = q.get('amapStyle') === 'satellite' ? 'satellite' : 'road';
    if (q.has('amapGround')) cur.amapClear = q.get('amapGround') !== 'blend';
  } catch (e) { /* ignore */ }
  const subs = [];
  function save() { try { localStorage.setItem(KEY, JSON.stringify(cur)); } catch (e) { /* ignore */ } }
  const mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const mqRM = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  const Settings = {
    DEF: DEF,
    get: function (k) { return cur[k]; },
    all: function () { return Object.assign({}, cur); },
    set: function (k, v) {
      if (cur[k] === v) return;
      cur[k] = v; save();
      Settings.apply(k);
      for (const f of subs) { try { f(k, v); } catch (e) { console.error(e); } }
    },
    reset: function () {
      cur = Object.assign({}, DEF); save();
      Settings.apply();
      for (const k of Object.keys(DEF)) for (const f of subs) { try { f(k, cur[k]); } catch (e) { console.error(e); } }
    },
    on: function (fn) { subs.push(fn); },
    // 系统“减少动态效果”偏好（不再单独设置）
    reducedMotion: function () { return !!(mqRM && mqRM.matches); },
    resolvedTheme: function () { return cur.theme === 'auto' ? (mq && mq.matches ? 'dark' : 'light') : cur.theme; },
    apply: function (k) {
      const root = document.documentElement;
      if (!k || k === 'theme') { if (CM.setTheme) CM.setTheme(Settings.resolvedTheme()); else root.dataset.theme = Settings.resolvedTheme(); }
      if (!k || k === 'uiScale') root.style.setProperty('--uiz', String(cur.uiScale));
      if (!k || k === 'sound' || k === 'volume') { if (CM.Sound) { CM.Sound.setEnabled(cur.sound); CM.Sound.setVolume(cur.volume); } }
      if (CM.Sound && (!k || k === 'trainVol')) CM.Sound.setTrainVolume(cur.trainVol);
      if (CM.Sound && (!k || k === 'ambVol')) CM.Sound.setAmbVolume(cur.ambVol);
      if (CM.R && (!k || k === 'labels' || k === 'agents')) { CM.R.labelsOn = cur.labels !== 'none'; CM.R.mapLabelsOn = cur.labels === 'all'; CM.R.agentsOn = cur.agents; }
      if (CM.AmapTiles && (!k || k === 'amapTiles' || k === 'amapStyle' || k === 'theme')) {
        CM.AmapTiles.setEnabled(cur.amapTiles);
        CM.AmapTiles.setStyle(cur.amapStyle);
        CM.AmapTiles.onTheme(Settings.resolvedTheme() === 'dark');
      }
    },
  };
  if (mq && mq.addEventListener) mq.addEventListener('change', function () { if (cur.theme === 'auto') Settings.apply('theme'); });
  CM.Settings = Settings;
})(window.CM);
