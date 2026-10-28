// 用 CDP 控制无界面 Chrome：打开游戏、开一局深圳、等画面稳定后截图。
// 用法：node szdata/shoot.js <输出png> [map] [等待毫秒]
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');

const OUT = process.argv[2] || '/tmp/sz_play.png';
const MAP = process.argv[3] || 'sz';
const WAIT = +(process.argv[4] || 12000);
const PORT = 9333;
const URL0 = process.env.PAGE || 'http://127.0.0.1:8779/index.html';

const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
  '--hide-scrollbars', '--window-size=1600,1000', '--remote-debugging-port=' + PORT,
  '--user-data-dir=/tmp/sz_chrome_prof', '--no-first-run', '--no-default-browser-check',
  'about:blank',
], { stdio: 'ignore' });

const get = function (path) {
  return new Promise(function (res, rej) {
    http.get({ host: '127.0.0.1', port: PORT, path: path }, function (r) {
      let b = ''; r.on('data', function (d) { b += d; }); r.on('end', function () { try { res(JSON.parse(b)); } catch (e) { rej(e); } });
    }).on('error', rej);
  });
};
const sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

(async function () {
  let targets = null;
  for (let i = 0; i < 60; i++) {
    try { targets = await get('/json/list'); break; } catch (e) { await sleep(250); }
  }
  if (!targets) throw new Error('Chrome 未就绪');
  const page = targets.find(function (t) { return t.type === 'page'; });
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const waiters = new Map(); const logs = [];
  ws.addEventListener('message', function (ev) {
    const m = JSON.parse(ev.data);
    if (m.id && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); return; }
    if (m.method === 'Runtime.consoleAPICalled') {
      logs.push(m.params.type + ': ' + m.params.args.map(function (a) { return a.value !== undefined ? a.value : (a.description || a.type); }).join(' '));
    }
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      logs.push('EXCEPTION: ' + (d.exception && (d.exception.description || d.exception.value) || d.text));
    }
  });
  const send = function (method, params) {
    return new Promise(function (res) {
      const i = ++id; waiters.set(i, res); ws.send(JSON.stringify({ id: i, method: method, params: params || {} }));
    });
  };
  await new Promise(function (r) { ws.addEventListener('open', r); });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: URL0 });
  await sleep(+(process.env.STARTWAIT || 4000));
  // 可选：按文字点按钮（用于截开始界面的地图选择等），不进入游戏
  if (process.env.CLICK) {
    const q = JSON.stringify(process.env.CLICK);
    const rr = await send('Runtime.evaluate', {
      expression: "(function(){var t=" + q + ";var bs=[].slice.call(document.querySelectorAll('button,a'));" +
        "var b=bs.filter(function(x){return (x.textContent||'').indexOf(t)>=0;})[0];if(!b)return 'none';b.click();return 'clicked';})()",
      returnByValue: true,
    });
    console.log('点击：' + (rr.result && rr.result.result && rr.result.result.value));
    if (process.env.SCROLLTO) {
      const q2 = JSON.stringify(process.env.SCROLLTO);
      await send('Runtime.evaluate', {
        expression: "(function(){var t=" + q2 + ";var els=[].slice.call(document.querySelectorAll('*')).filter(function(x){return x.children.length<6&&(x.textContent||'').indexOf(t)>=0;});" +
          "if(els.length)els[els.length-1].scrollIntoView({block:'center'});return els.length;})()",
        returnByValue: true,
      });
      await sleep(1200);
    }
    await sleep(+(process.env.CLICKWAIT || 2500));
    const shot0 = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(OUT, Buffer.from(shot0.result.data, 'base64'));
    console.log('截图写入 ' + OUT);
    ws.close(); chrome.kill('SIGKILL');
    process.exit(0);
  }
  const r1 = await send('Runtime.evaluate', { expression: "(function(){ if(!window.CM||!CM.newGame) return 'noCM'; CM.newGame({map:'" + MAP + "'}); return 'ok'; })()", returnByValue: true });
  console.log('开新游戏：' + JSON.stringify(r1.result && r1.result.result && r1.result.result.value));
  await sleep(WAIT);
  // 关掉开局简报，进入正常游戏画面
  await send('Runtime.evaluate', { expression: "try{CM.ui.closeScreen();}catch(e){} 1", returnByValue: true });
  await sleep(2500);
  // 可选：相机与视图（CAM=cx,cy,zoom；VIEW=1 表示 2.5D，VIEW=0 表示平面）
  if (process.env.CAM || process.env.VIEW) {
    const [cx, cy, z] = (process.env.CAM || '').split(',').map(Number);
    const expr = "(function(){var c=CM.R.cam;" +
      (process.env.CAM ? ("c.cx=" + cx + ";c.cy=" + cy + ";c.zoom=c.tz=" + z + ";") : "") +
      (process.env.VIEW ? ("c.view=c.t=" + (process.env.VIEW === '0' ? 0 : 1) + ";") : "") +
      "CM.R.invalidate&&CM.R.invalidate();return 1;})()";
    await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    await sleep(3500);
  }
  if (process.env.UNDER) { await send('Runtime.evaluate', { expression: "CM.R.cam.under=CM.R.cam.tu=1;1", returnByValue: true }); await sleep(2500); }
  // 可选：直接把城市地形与路网推到某一年（只用于看画面，不推进模型与账目）
  if (process.env.FORCEYEAR) {
    const y = +process.env.FORCEYEAR;
    const expr = "(function(){var g=CM.game,c=g.city,D=CM.DATA,mi=0;" +
      "for(var yy=1991;yy<=" + y + ";yy++){c.applyReclaim(yy);c.applyRoads(yy);c.activateLandmarks(yy);" +
      "for(var k=0;k<c.regions.length;k++){var rg=c.regions[k];if(c.regionOpen[k]||rg.open==null)continue;" +
      "if(rg.id==='airport'&&!D.airport.buildable)continue;if(yy>=rg.open)c.openRegion(k,yy,1);}" +
      "for(var m=1;m<=12;m++){mi++;c.growMonth({year:yy+(m-1)/12,monthIndex:mi,zoneAccess:null,cellWalk:null,coverage:0,econ:null});}}" +
      "c.updateStreets();c.buildGraphs();g.clock.y=" + y + ";return 1;})()";
    await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    await sleep(4000);
  }
  // 让游戏跑一点时间（按空格开始，等价于 setSpeed）
  await send('Runtime.evaluate', { expression: "if(window.CM&&CM.game){CM.game.setSpeed(1);} 1", returnByValue: true });
  if (process.env.JUMP) {
    const n = +process.env.JUMP;
    await send('Runtime.evaluate', { expression: "CM.game.startJump(" + n + ");1", returnByValue: true });
    for (let i = 0; i < 120; i++) {
      await sleep(1000);
      const st = await send('Runtime.evaluate', { expression: "CM.game&&CM.game.jumping?('jumping '+Math.round(CM.game.jumping.progress*100)+'%'):('done '+CM.game.clock.y+'/'+CM.game.clock.m)", returnByValue: true });
      const v = st.result && st.result.result && st.result.result.value;
      if (i % 5 === 0) console.log('  跳转：' + v);
      if (v && v.indexOf('done') === 0) break;
    }
  }
  await sleep(6000);
  const info = await send('Runtime.evaluate', {
    expression: "(function(){var g=window.CM&&CM.game;if(!g)return 'no game';return JSON.stringify({map:g.mapId,y:g.clock.y,m:g.clock.m,d:g.clock.d,pop:Math.round(g.city.totals().pop),regions:g.city.regions.length,speed:g.speed,fps:Math.round(CM.R.stats.fps||0),zoom:+CM.R.cam.zoom.toFixed(1)});})()",
    returnByValue: true,
  });
  console.log('状态：' + (info.result && info.result.result && info.result.result.value));
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(OUT, Buffer.from(shot.result.data, 'base64'));
  console.log('截图写入 ' + OUT);
  if (logs.length) console.log('页面日志：\n  ' + logs.slice(0, 20).join('\n  '));
  ws.close(); chrome.kill('SIGKILL');
  process.exit(0);
})().catch(function (e) { console.error('失败', e); chrome.kill('SIGKILL'); process.exit(1); });
