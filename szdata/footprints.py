#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OSM PBF 里量出深圳各地标的真实占地（候选列表版）。

第一遍把建筑的质心、面积、朝向包围盒缓存到 buildings.json（约 1 分钟）；
之后只用缓存做查询，秒出结果。

用法：
  python3 footprints.py            # 查询地标候选（默认半径 300 m，按面积从大到小）
  python3 footprints.py --rebuild  # 重新扫描 PBF
"""
import json, math, os, sys

import numpy as np
import osmium

HERE = os.path.dirname(os.path.abspath(__file__))
PBF = os.path.join(HERE, 'guangdong.osm.pbf')
CACHE = os.path.join(HERE, 'buildings.json')
LON0, LAT0 = 113.7440, 22.7220
KX, KY = 409.6, 443.0
CELL_M = 250.0

LM = [
    ('ba_ab', '宝安机场 A、B 航站楼', 22.6215, 113.8080, ['航站楼', 'A楼', 'B楼']),
    ('ba_t3', '宝安机场 T3 航站楼', 22.6300, 113.8070, ['3号航站楼', 'T3']),
    ('ba_cec2', '深圳国际会展中心', 22.7000, 113.7900, ['会展中心', '国际会展']),
    ('ns_crc', '中国华润大厦', 22.5155, 113.9405, ['华润', '春笋']),
    ('ft_pingan', '平安金融中心', 22.5365, 114.0610, ['平安']),
    ('ft_cec', '深圳会展中心', 22.5340, 114.0570, ['会展']),
    ('ns_szu', '深圳大学', 22.5350, 113.9340, ['深圳大学', '图书馆']),
    ('ns_world', '世界之窗', 22.5390, 113.9750, ['世界之窗']),
    ('ft_bay', '深圳湾体育中心', 22.5155, 113.9479, ['体育中心', '深圳湾']),
    ('lh_rail', '深圳站', 22.5385, 114.1165, ['深圳站', '罗湖']),
    ('lh_east', '深圳东站', 22.5960, 114.1090, ['东站', '布吉']),
    ('lh_north', '深圳北站', 22.6100, 114.0290, ['北站']),
    ('ft_rail', '福田站', 22.5390, 114.0560, ['福田站']),
]


class B(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.items = []

    def way(self, w):
        t = w.tags
        if not (t.get('building') or t.get('aeroway') or t.get('man_made') in ('terminal', 'tower')):
            return
        pts = []
        for n in w.nodes:
            if not n.location.valid():
                continue
            pts.append((n.location.lon, n.location.lat))
        if len(pts) < 3:
            return
        a = np.array(pts)
        if a[:, 0].min() < 113.70 or a[:, 0].max() > 114.30 or a[:, 1].min() < 22.45 or a[:, 1].max() > 22.75:
            return
        x = (a[:, 0] - LON0) * KX * CELL_M
        y = (LAT0 - a[:, 1]) * KY * CELL_M
        if x.max() - x.min() < 8 and y.max() - y.min() < 8:
            return
        cx, cy = float(x.mean()), float(y.mean())
        u = np.stack([x - cx, y - cy], axis=1)
        cov = np.cov(u.T)
        evals, evecs = np.linalg.eigh(cov)
        d = evecs[:, np.argmax(evals)]
        ang = math.degrees(math.atan2(d[1], d[0]))
        r1 = u @ d
        r2 = u @ np.array([-d[1], d[0]])
        wd = float(r1.max() - r1.min())
        dd = float(r2.max() - r2.min())
        ang = ang % 180.0
        if ang > 90:
            ang -= 180.0
        self.items.append([round(cx, 1), round(cy, 1), round(wd), round(dd), round(ang, 1),
                           t.get('name', ''), t.get('building', ''), round(wd * dd / 1e4, 1)])


def build():
    h = B()
    h.apply_file(PBF, locations=True)
    json.dump(h.items, open(CACHE, 'w'), ensure_ascii=False)
    print('缓存 %d 个建筑 → %s' % (len(h.items), CACHE))


def main():
    if '--rebuild' in sys.argv or not os.path.exists(CACHE):
        build()
    data = json.load(open(CACHE))
    for item in LM:
        lid, nm, lat, lon, kws = item
        px, py = (lon - LON0) * KX * CELL_M, (LAT0 - lat) * KY * CELL_M
        hit = []
        for it in data:
            if not it[5]:
                continue
            if any(k in it[5] for k in kws):
                dist = math.hypot(it[0] - px, it[1] - py)
                if dist <= 1500:
                    hit.append((dist, it))
        hit.sort(key=lambda p: -p[1][7])
        print('\n=== %s %s' % (lid, nm))
        if not hit:
            print('   名字里没有 %s 的建筑面' % '/'.join(kws))
        for dist, it in hit[:4]:
            blat, blon = LAT0 - it[1] / (KY * CELL_M), LON0 + it[0] / (KX * CELL_M)
            print('    %4d×%-4d rot %+5.1f°  %7.0f m²  距 %4.0f m  %s (%s)  中心 %.4f,%.4f' % (it[2], it[3], it[4], it[7] * 1e4, dist, it[5], it[6], blat, blon))


if __name__ == '__main__':
    main()
