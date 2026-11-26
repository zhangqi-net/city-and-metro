#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""西安地图 OSM 抓取：分块从 Overpass 拉取水系/道路/铁路/绿地与地名，支持断点续传。

范围覆盖西安—咸阳都市区（180 x 180 格，每格 250 m，约 45 x 45 km）：
西到咸阳市区 / 咸阳西站，东到纺织城 / 灞河，北到咸阳国际机场（T1-T3 / T5），
南到常宁宫（2 号线南端终点）。旧 120 x 120 格网的 16 块 tile 存的是原始经纬度、
投影在 build_geo.py 阶段才做，重映射 (i+2, j+1) 后原样复用。
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

# 地图范围（西安—咸阳都市区，约 180 x 180 格，每格 250 m）
W, E = 108.6270, 109.1160
S, N = 34.0725, 34.4775

NX, NY = 6, 6
OUT = os.path.dirname(os.path.abspath(__file__))
UA = 'city-metro-map-builder/1.0 (personal non-commercial game map)'

# 本机实测：仅 overpass-api.de 能稳定返回数据；private.coffee 几乎每次读超时（白等 ~80 s），
# 其余镜像直连超时或只含欧洲数据。故只用主镜像 + 短间隔重试，单轮速度提升数倍。
MIRRORS = [
    'https://overpass-api.de/api/interpreter',
]
# 本机 HTTP(S)_PROXY 对 Overpass 会返回 502；实测绕过代理直连可用
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 拆成 3 组小查询：本机到 Overpass 的长连接（>120 s）常被中间设备以 502 掐断，
# 实测单组 30–50 s 成功率高。每组结果单独缓存，失败只需重抓该组。
GROUP_QUERIES = [
  ('road', False, """[out:json][timeout:{to}];(
  way["highway"~"^(motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link|secondary_link)$"]({s},{w},{n},{e});
);out geom;"""),
  ('green', True, """[out:json][timeout:{to}];(
  way["natural"="water"]({s},{w},{n},{e});
  way["waterway"="riverbank"]({s},{w},{n},{e});
  way["landuse"="reservoir"]({s},{w},{n},{e});
  way["waterway"~"^(river|canal|stream)$"]({s},{w},{n},{e});
  way["leisure"~"^(park|garden|nature_reserve)$"]({s},{w},{n},{e});
  way["landuse"~"^(forest|grass|recreation_ground)$"]({s},{w},{n},{e});
  way["natural"="wood"]({s},{w},{n},{e});
);out geom;"""),
  ('rail', True, """[out:json][timeout:{to}];(
  way["railway"~"^(rail|light_rail|subway)$"]({s},{w},{n},{e});
);out geom;"""),
]

ADMIN_QUERY = """[out:json][timeout:180];
rel["boundary"="administrative"]["admin_level"~"^(6|8)$"]({s},{w},{n},{e});
out geom;"""

PLACE_QUERY = """[out:json][timeout:{to}];
node["place"~"^(city|suburb|town|village|quarter|neighbourhood|borough)$"]({s},{w},{n},{e});
out;"""

RAIL_QUERY = """[out:json][timeout:{to}];
way["railway"="station"]({s},{w},{n},{e});
way["aeroway"~"^(aerodrome|runway|terminal)$"]({s},{w},{n},{e});
way["amenity"="university"]({s},{w},{n},{e});
out geom;"""

# 地铁车站节点（含普通铁路站）：用于校准 data_bj.js 站点坐标（范围略大于地图）
METRO_STATION_QUERY = """[out:json][timeout:{to}];
(
  node["railway"="station"]({s},{w},{n},{e});
  node["railway"="halt"]({s},{w},{n},{e});
  node["station"="subway"]({s},{w},{n},{e});
  node["public_transport"="station"]["subway"="yes"]({s},{w},{n},{e});
  node["railway"="subway_entrance"]({s},{w},{n},{e});
);
out;"""

# 一次性补抓：老城（明城墙内）与咸阳市区的 tertiary 干道。
# 引擎 ROAD_CLS 原本只收录 motorway/trunk/primary/secondary，老城东西南北大街、
# 解放路等 OSM 标 tertiary 的主干道整条被过滤掉（对比高德瓦片确认缺失）。
# 单独小 bbox 查询，extract.py 里按名称/范围提升等级，避免全图 tertiary 泛滥。
TERTIARY_QUERY = """[out:json][timeout:{to}];
(
  way["highway"~"^(tertiary|tertiary_link)$"]({s},{w},{n},{e});
);
out geom;"""

# 老城（明城墙）bbox：WGS-84 约 108.918–108.982 E, 34.238–34.292 N
OLDCITY_BBOX = (108.918, 108.982, 34.238, 34.292)   # w, e, s, n
# 咸阳市区 bbox（含秦都区/渭城区核心）
XIANYANG_BBOX = (108.640, 108.775, 34.295, 34.375)
# 机场周边
AIRPORT_BBOX = (108.730, 108.830, 34.415, 34.478)

EXTRA_AREAS = [
    ('oldcity',  OLDCITY_BBOX),
    ('xianyang', XIANYANG_BBOX),
    ('airport',  AIRPORT_BBOX),
]


def post(query, timeout=300, attempts=8):
    body = urllib.parse.urlencode({'data': query}).encode()
    last = None
    # 逐次交替镜像（不并发，避免 429）：主镜像 502 时下一次立刻换备用镜像
    for attempt in range(attempts):
        base = MIRRORS[attempt % len(MIRRORS)]
        req = urllib.request.Request(base, data=body, headers={'User-Agent': UA,
                               'Content-Type': 'application/x-www-form-urlencoded'})
        t0 = time.time()
        try:
            with OPENER.open(req, timeout=timeout) as r:
                raw = r.read()
            d = json.loads(raw)
            if 'elements' in d:
                print('    OK %s  %.1fs  %d 要素  %.1f MB' % (base.split('/')[2], time.time() - t0,
                      len(d['elements']), len(raw) / 1e6), flush=True)
                return d
            last = 'no elements'
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, e)
            print('    ! %s 第%d次失败 %s' % (base.split('/')[2], attempt + 1, last), flush=True)
        # 固定短间隔：原实现 sleep(3*(attempt+1)) 在第 8 次要等 24 s，且交替到超时镜像白等 80 s
        time.sleep(2)
    raise RuntimeError('全部镜像失败：' + str(last))


def main():
    tiles = []
    dx, dy = (E - W) / NX, (N - S) / NY
    for j in range(NY):
        for i in range(NX):
            # (w, s, e, n)：s 为南纬（小），n 为北纬（大）——Overpass 要求 south < north
            tiles.append((i, j, W + i * dx, S + j * dy, W + (i + 1) * dx, S + (j + 1) * dy))
    done = 0
    failed = []
    for (i, j, w, s, e, n) in tiles:
        fn = os.path.join(OUT, 'tile_%d_%d.json' % (i, j))
        gfns = [os.path.join(OUT, 'tile_%d_%d_g%d.json' % (i, j, k))
                for k in range(len(GROUP_QUERIES))]
        # 早期版本直接落完整 tile、没有分片缓存：视为已完成，避免重复抓 3 组
        if (os.path.exists(fn) and os.path.getsize(fn) > 2
                and not any(os.path.exists(g) for g in gfns)):
            done += 1
            continue
        print('[%d,%d] %.4f,%.4f - %.4f,%.4f' % (i, j, w, s, e, n), flush=True)
        ok = True
        for k, (gname, optional, gq) in enumerate(GROUP_QUERIES):
            gfn = gfns[k]
            # 阈值不能太大：可选组失败时写的是 {"elements":[]}（16 B）
            if os.path.exists(gfn) and os.path.getsize(gfn) > 2:
                print('    %s 组已缓存' % gname, flush=True)
                continue
            q = gq.format(s='%.5f' % s, w='%.5f' % w, n='%.5f' % n, e='%.5f' % e, to=120)
            print('    抓取 %s 组...' % gname, flush=True)
            try:
                d = post(q, timeout=200, attempts=3 if optional else 8)
            except Exception as ex:
                if optional:
                    # 不写空缓存：下轮会重抓；成功但确实 0 要素的查询才会落缓存（有效结果）
                    print('    ! %s 组失败，本轮跳过，下轮重试' % gname, flush=True)
                    continue
                else:
                    print('    × %s 组失败，本块留待重跑：%s' % (gname, ex), flush=True)
                    ok = False
                    break
            with open(gfn, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False)
        if not ok:
            failed.append((i, j))
            continue
        # 每轮都重新合并：新补到的组会并入完整 tile，底图逐轮变完整
        merged, seen = [], set()
        for gfn in gfns:
            if not (os.path.exists(gfn) and os.path.getsize(gfn) > 2):
                continue
            with open(gfn, encoding='utf-8') as f:
                d = json.load(f)
            for el in d.get('elements', []):
                key = (el.get('type'), el.get('id'))
                if key not in seen:
                    seen.add(key)
                    merged.append(el)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({'elements': merged}, f, ensure_ascii=False)
        print('    [%d,%d] 合并完成 %d 要素' % (i, j, len(merged)), flush=True)
        done += 1
        time.sleep(1)
    print('地形分块完成 %d/%d' % (done, len(tiles)), flush=True)
    if failed:
        print('失败块（重跑本脚本会继续重试）：%s' % failed, flush=True)
        with open(os.path.join(OUT, 'failed_tiles.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join('%d %d' % t for t in failed))

    fn = os.path.join(OUT, 'admin.json')
    if not (os.path.exists(fn) and os.path.getsize(fn) > 200):
        print('抓取行政区界（admin_level=8）', flush=True)
        d = post(ADMIN_QUERY.format(s='%.5f' % S, w='%.5f' % W, n='%.5f' % N, e='%.5f' % E), timeout=420)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
    else:
        print('行政区界已存在，跳过', flush=True)

    for name, fn, q in (('地名', 'place.json', PLACE_QUERY), ('站场与机场', 'poi.json', RAIL_QUERY),
                        ('车站节点', 'mstations.json', METRO_STATION_QUERY)):
        # 车站节点范围稍大（覆盖地图边缘外的换乘站参考）
        s2, w2, n2, e2 = (S - 0.03, W - 0.03, N + 0.03, E + 0.03) if name == '车站节点' else (S, W, N, E)
        fn = os.path.join(OUT, fn)
        if os.path.exists(fn) and os.path.getsize(fn) > 200:
            print('%s已存在，跳过' % name, flush=True)
            continue
        print('抓取%s' % name, flush=True)
        d = post(q.format(s='%.5f' % s2, w='%.5f' % w2, n='%.5f' % n2, e='%.5f' % e2, to=300), timeout=420)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)

    # 一次性补抓 tertiary 干道（老城 / 咸阳市区 / 机场周边）→ tile_extra_*.json
    for tag, (bw, be, bs, bn) in EXTRA_AREAS:
        fn = os.path.join(OUT, 'tile_extra_%s.json' % tag)
        if os.path.exists(fn) and os.path.getsize(fn) > 2:
            print('tertiary(%s) 已存在，跳过' % tag, flush=True)
            continue
        print('补抓 tertiary 干道：%s' % tag, flush=True)
        q = TERTIARY_QUERY.format(s='%.5f' % bs, w='%.5f' % bw, n='%.5f' % bn, e='%.5f' % be, to=180)
        try:
            d = post(q, timeout=260, attempts=6)
        except Exception as ex:
            print('  ! tertiary(%s) 失败，重跑本脚本续抓：%s' % (tag, ex), flush=True)
            continue
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
    print('全部完成', flush=True)


if __name__ == '__main__':
    main()
