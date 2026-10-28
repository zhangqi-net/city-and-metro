#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""北京地图 OSM 抓取：分块从 Overpass 拉取水系/道路/铁路/绿地与地名，支持断点续传。

范围 160 x 132 格，每格 250 m（40 x 33 km）：西到石景山，东到首都机场，北到北五环外（含机场），南到南四环。
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

# 地图范围（160 x 132 格，每格 250 m）
W, E = 116.1600, 116.6283
S, N = 39.7900, 40.0874

NX, NY = 6, 4
OUT = os.path.dirname(os.path.abspath(__file__))
UA = 'city-metro-map-builder/1.0 (personal non-commercial game map)'

MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]

QUERY = """[out:json][timeout:{to}];
(
  way["natural"="water"]({s},{w},{n},{e});
  way["waterway"="riverbank"]({s},{w},{n},{e});
  way["landuse"="reservoir"]({s},{w},{n},{e});
  way["waterway"~"^(river|canal|stream)$"]({s},{w},{n},{e});
  way["highway"~"^(motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link|secondary_link)$"]({s},{w},{n},{e});
  way["railway"~"^(rail|light_rail|subway)$"]({s},{w},{n},{e});
  way["leisure"~"^(park|garden|nature_reserve)$"]({s},{w},{n},{e});
  way["landuse"~"^(forest|grass|recreation_ground)$"]({s},{w},{n},{e});
  way["natural"="wood"]({s},{w},{n},{e});
);
out geom;"""

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


def post(query, timeout=300):
    body = urllib.parse.urlencode({'data': query}).encode()
    last = None
    for base in MIRRORS:
        for attempt in range(4):
            req = urllib.request.Request(base, data=body, headers={'User-Agent': UA,
                                       'Content-Type': 'application/x-www-form-urlencoded'})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
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
                time.sleep(8 * (attempt + 1))
    raise RuntimeError('全部镜像失败：' + str(last))


def main():
    tiles = []
    dx, dy = (E - W) / NX, (N - S) / NY
    for j in range(NY):
        for i in range(NX):
            # (w, s, e, n)：s 为南纬（小），n 为北纬（大）——Overpass 要求 south < north
            tiles.append((i, j, W + i * dx, S + j * dy, W + (i + 1) * dx, S + (j + 1) * dy))
    done = 0
    for (i, j, w, s, e, n) in tiles:
        fn = os.path.join(OUT, 'tile_%d_%d.json' % (i, j))
        if os.path.exists(fn) and os.path.getsize(fn) > 200:
            print('[%d,%d] 已存在，跳过' % (i, j), flush=True)
            done += 1
            continue
        q = QUERY.format(s='%.5f' % s, w='%.5f' % w, n='%.5f' % n, e='%.5f' % e, to=180)
        print('[%d,%d] %.4f,%.4f - %.4f,%.4f' % (i, j, w, s, e, n), flush=True)
        d = post(q)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        done += 1
        time.sleep(2)
    print('地形分块完成 %d/%d' % (done, len(tiles)), flush=True)

    fn = os.path.join(OUT, 'admin.json')
    if not (os.path.exists(fn) and os.path.getsize(fn) > 200):
        print('抓取行政区界（admin_level=8）', flush=True)
        d = post(ADMIN_QUERY.format(s='%.5f' % S, w='%.5f' % W, n='%.5f' % N, e='%.5f' % E), timeout=420)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
    else:
        print('行政区界已存在，跳过', flush=True)

    for name, fn, q in (('地名', 'place.json', PLACE_QUERY), ('站场与机场', 'poi.json', RAIL_QUERY)):
        fn = os.path.join(OUT, fn)
        if os.path.exists(fn) and os.path.getsize(fn) > 200:
            print('%s已存在，跳过' % name, flush=True)
            continue
        print('抓取%s' % name, flush=True)
        d = post(q.format(s='%.5f' % S, w='%.5f' % W, n='%.5f' % N, e='%.5f' % E, to=180), timeout=420)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
    print('全部完成', flush=True)


if __name__ == '__main__':
    main()
