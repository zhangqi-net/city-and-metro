#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""西安底图抓取（新代理通道）：OSM 官方 /api/0.6/map 全量要素。

背景：2026-11-19 用户新增本地代理后实测——
  * 直连 api.openstreetmap.org/api/0.6/map 超时；
  * 127.0.0.1:1087（系统 HTTP 代理）与 SOCKS 1080 可在 3–20 s 返回完整 OSM XML；
  * Overpass 分组查询每块需 3 组 x 30–50 s 且常遇 502，官方 /map 一次给全量要素更快更全。

官方 /map 有 50000 节点上限，过密块自动 2x2 细分（最多两层）。
输出：Overpass-like JSON（tile_i_j.json），extract.py 可直接消费；旧 tile 备份到 backup_overpass/。
"""
import os, sys, time, json, subprocess, glob, shutil
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
W, E, S, N = 108.7900, 109.1160, 34.1400, 34.4100
NX = NY = 4
UA = 'city-metro-map-builder/1.0 (personal non-commercial game map)'
URL = 'https://api.openstreetmap.org/api/0.6/map?bbox='
# 走代理的两条实测可用路径；直连超时不再尝试
PATHS = [
    ('1087', ['-x', 'http://127.0.0.1:1087']),
    ('socks', ['--socks5-hostname', '127.0.0.1:1080']),
]
BACKUP = os.path.join(HERE, 'backup_overpass')
TMP = '/tmp/xa_osm'


def fetch_xml(w, s, e, n, dst, timeout=120):
    """下载一个 bbox 的 OSM XML。返回 (成功?, 说明)；TOO_MANY_NODES 表示需要细分。"""
    bbox = '%.6f,%.6f,%.6f,%.6f' % (w, s, e, n)
    last = ''
    for pname, pargs in PATHS:
        cmd = ['curl', '-sS', '-m', str(timeout), '-A', UA, '-o', dst,
               '-w', '%{http_code}|%{time_total}'] + pargs + [URL + bbox]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
            parts = (r.stdout.strip().split('|') + ['?'] * 2)
            code, tt = parts[0], parts[1]
            if code == '200' and os.path.exists(dst) and os.path.getsize(dst) > 2000:
                return True, '%s HTTP200 %.1fs %.1fMB' % (
                    pname, float(tt), os.path.getsize(dst) / 1e6)
            if code == '400':
                return False, 'TOO_MANY_NODES'
            last = '%s HTTP%s %s' % (pname, code, r.stderr.strip()[:50])
        except Exception as ex:
            last = '%s %s: %s' % (pname, type(ex).__name__, str(ex)[:40])
        time.sleep(1)
    return False, last


def xml_to_elements(path):
    """OSM XML -> Overpass-like elements（node + 带 geometry 的 way）。

    relation 由已有 admin.json 单独提供，这里不输出，避免与 extract.py 的
    merge_tiles()（只读 way/node）冲突。
    """
    nodes, ways, out = {}, {}, []
    for _ev, el in ET.iterparse(path, events=('end',)):
        if el.tag == 'node':
            try:
                i = int(el.get('id'))
                lon, lat = float(el.get('lon')), float(el.get('lat'))
                nodes[i] = (lon, lat)
                tg = {t.get('k'): t.get('v') for t in el.findall('tag')}
                if tg:
                    out.append({'type': 'node', 'id': i, 'lon': lon, 'lat': lat, 'tags': tg})
            except Exception:
                pass
            el.clear()
        elif el.tag == 'way':
            try:
                i = int(el.get('id'))
                nd = [int(x.get('ref')) for x in el.findall('nd')]
                tg = {t.get('k'): t.get('v') for t in el.findall('tag')}
                if tg:
                    ways[i] = (nd, tg)
            except Exception:
                pass
            el.clear()
        elif el.tag == 'relation':
            el.clear()
    for i, (nd, tg) in ways.items():
        geom = [{'lon': nodes[n][0], 'lat': nodes[n][1]} for n in nd if n in nodes]
        if len(geom) >= 2:
            out.append({'type': 'way', 'id': i, 'tags': tg, 'geometry': geom})
    return out


def process_tile(i, j):
    done = os.path.join(HERE, '.done_osm_%d_%d' % (i, j))
    if os.path.exists(done):
        return '[%d,%d] 已完成，跳过' % (i, j)
    dx, dy = (E - W) / NX, (N - S) / NY
    boxes = [(W + i * dx, S + j * dy, W + (i + 1) * dx, S + (j + 1) * dy)]
    all_els, seen, ok_any = [], set(), False
    for depth in range(3):
        nxt = []
        for b in boxes:
            tmp = os.path.join(TMP, 'b_%.6f_%.6f.xml' % (b[0], b[1]))
            ok, msg = fetch_xml(*b, dst=tmp)
            if ok:
                els = xml_to_elements(tmp)
                for el in els:
                    k = (el['type'], el['id'])
                    if k not in seen:
                        seen.add(k)
                        all_els.append(el)
                ok_any = True
                print('    [%d,%d] 子块 %.4f,%.4f %s -> %d 要素' % (
                    i, j, b[0], b[1], msg, len(els)), flush=True)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            elif msg == 'TOO_MANY_NODES' and depth < 2:
                mw, ms = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                nxt += [(b[0], b[1], mw, ms), (mw, b[1], b[2], ms),
                        (b[0], ms, mw, b[3]), (mw, ms, b[2], b[3])]
            else:
                print('    [%d,%d] 子块失败：%s' % (i, j, msg), flush=True)
                nxt.append(b)  # 留待下一轮重试
        if not nxt:
            break
        boxes = nxt
        if len(boxes) > 1:
            print('    [%d,%d] 第%d层细分为 %d 子块' % (i, j, depth + 1, len(boxes)), flush=True)
    if not ok_any:
        return '[%d,%d] 全部失败（保留旧 tile）' % (i, j)
    fn = os.path.join(HERE, 'tile_%d_%d.json' % (i, j))
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump({'elements': all_els}, f, ensure_ascii=False)
    with open(done, 'w') as f:
        f.write(str(len(all_els)))
    return '[%d,%d] 完成 %d 要素 -> %s' % (i, j, len(all_els), os.path.basename(fn))


def main():
    os.makedirs(TMP, exist_ok=True)
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP)
        old = glob.glob(os.path.join(HERE, 'tile_*.json'))
        for f in old:
            shutil.copy2(f, BACKUP)
        print('已备份 %d 个旧 Overpass tile 到 backup_overpass/' % len(old), flush=True)
    print('=== 用 OSM 官方 /map + 1087 代理重拉 %d 块 ===' % (NX * NY), flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(process_tile, i, j) for i in range(NX) for j in range(NY)]
        for f in as_completed(futs):
            print(f.result(), flush=True)
    n = len(glob.glob(os.path.join(HERE, '.done_osm_*')))
    print('=== 完成 %d/%d 块，耗时 %.1f 分钟 ===' % (n, NX * NY, (time.time() - t0) / 60), flush=True)
    return 0 if n == NX * NY else 1


if __name__ == '__main__':
    sys.exit(main())
