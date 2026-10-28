#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从广东省 OSM PBF 中裁剪深圳范围要素，输出 szdata/features.json。

用法：python3 extract.py
依赖：pyosmium
"""
import json, os, sys, time

import osmium

S, W, N, E = 22.4959, 113.7420, 22.7220, 114.2590
# 略微放宽，保证边界处的要素完整
M = 0.02
S2, W2, N2, E2 = S - M, W - M, N + M, E + M

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'features.json')
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guangdong.osm.pbf')


def inbox(lat, lon):
    return S2 <= lat <= N2 and W2 <= lon <= E2


def way_pts(w):
    pts = []
    for n in w.nodes:
        if not n.location.valid():
            continue
        pts.append((round(n.lon, 7), round(n.lat, 7)))
    return pts


def ring_of_way(w):
    p = way_pts(w)
    return p if len(p) >= 4 else None


def main():
    t0 = time.time()
    feats = {k: [] for k in ('water_poly', 'water_line', 'road', 'rail', 'park', 'wood',
                             'admin', 'place', 'coast')}

    # ---------- 节点：地名 ----------
    for n in osmium.FileProcessor(SRC).with_filter(osmium.filter.KeyFilter('place')):
        if not n.is_node() or not n.location.valid():
            continue
        if not inbox(n.location.lat, n.location.lon):
            continue
        t = n.tags
        kind = t.get('place')
        if kind not in ('city', 'suburb', 'town', 'village', 'quarter', 'neighbourhood', 'borough'):
            continue
        if not t.get('name'):
            continue
        rank = {'city': 1, 'borough': 2, 'suburb': 2, 'quarter': 3, 'town': 3,
                'village': 4, 'neighbourhood': 4}.get(kind, 4)
        feats['place'].append({'name': t['name'], 'lon': round(n.location.lon, 6),
                               'lat': round(n.location.lat, 6), 'rank': rank})
    print('地名 %d  (%.1fs)' % (len(feats['place']), time.time() - t0), flush=True)

    # ---------- 线状要素 ----------
    road_cls = {}
    for k in ('motorway', 'trunk', 'motorway_link', 'trunk_link'):
        road_cls[k] = (4, k.endswith('_link'))
    for k in ('primary', 'primary_link'):
        road_cls[k] = (3, k.endswith('_link'))
    for k in ('secondary', 'secondary_link'):
        road_cls[k] = (2, k.endswith('_link'))

    wp = osmium.FileProcessor(SRC).with_locations().with_filter(osmium.filter.KeyFilter('highway', 'railway', 'waterway', 'natural', 'aeroway'))
    cnt = 0
    for w in wp:
        if not w.is_way():
            continue
        t = w.tags
        if not w.nodes:
            continue
        # 先用第一个节点粗筛
        first = w.nodes[0]
        if not first.location.valid():
            continue
        if not inbox(first.location.lat, first.location.lon):
            # 可能是跨界长要素，取整体判断
            pts = way_pts(w)
            if not pts or not any(inbox(la, lo) for lo, la in pts):
                continue
        else:
            pts = way_pts(w)
        if len(pts) < 2:
            continue
        bridge = bool(t.get('bridge')) and t.get('bridge') != 'no'
        tunnel = bool(t.get('tunnel')) and t.get('tunnel') != 'no'
        name = t.get('name', '')

        hw = t.get('highway')
        if hw in road_cls:
            # 深中通道在 OSM 里是 G2518「深岑高速」的东段（深圳侧接线—东人工岛—海底隧道—西人工岛—跨海大桥），
            # 只有跨越伶仃洋这一段（纬度低于 22.62）改名，避免把北边机荷高速的共线段一起改掉
            if name == '深岑高速' and max(p[1] for p in pts) < 22.62:
                name = '深中通道'
            cls, link = road_cls[hw]
            flags = (1 if bridge else 0) | (2 if tunnel else 0) | (4 if link else 0)
            feats['road'].append({'name': name, 'cls': cls, 'flags': flags,
                                  'pts': [[lo, la] for lo, la in pts]})
            cnt += 1
            continue

        rw = t.get('railway')
        if rw == 'rail':
            flags = (1 if bridge else 0) | (2 if tunnel else 0)
            if '高铁' in name or '客运专线' in name or t.get('highspeed') == 'yes':
                flags |= 16
            feats['rail'].append({'name': name, 'flags': flags,
                                  'pts': [[lo, la] for lo, la in pts]})
            continue

        ww = t.get('waterway')
        if ww in ('river', 'canal', 'stream'):
            feats['water_line'].append({'name': name, 'kind': ww,
                                        'pts': [[lo, la] for lo, la in pts]})
            continue

        if t.get('natural') == 'coastline':
            feats['coast'].append({'pts': [[lo, la] for lo, la in pts]})
            continue

    print('道路 %d / 铁路 %d / 河道 %d / 海岸线 %d  (%.1fs)' % (
        len(feats['road']), len(feats['rail']), len(feats['water_line']), len(feats['coast']),
        time.time() - t0), flush=True)

    # ---------- 面状要素（含 multipolygon relation）----------
    water_tags = {('natural', 'water'), ('waterway', 'riverbank'), ('landuse', 'reservoir'),
                  ('natural', 'bay'), ('natural', 'wetland')}
    park_tags = {('leisure', 'park'), ('leisure', 'garden'), ('leisure', 'nature_reserve')}
    wood_tags = {('natural', 'wood'), ('landuse', 'forest')}

    def rings_of_geom(a):
        rings = []
        for o in a.outer_rings():
            p = [(round(n.lon, 7), round(n.lat, 7)) for n in o if n.location.valid()]
            if len(p) >= 4:
                rings.append((True, p))
            try:
                for r in a.inner_rings(o):
                    q = [(round(n.lon, 7), round(n.lat, 7)) for n in r if n.location.valid()]
                    if len(q) >= 4:
                        rings.append((False, q))
            except Exception:
                pass
        return rings

    ap = osmium.FileProcessor(SRC).with_areas()
    n_area = 0
    for a in ap:
        if not a.is_area():
            continue
        t = a.tags
        if not t:
            continue
        n_area += 1
        target = None
        if any(t.get(k) == v for k, v in water_tags):
            target = 'water_poly'
        elif any(t.get(k) == v for k, v in park_tags):
            target = 'park'
        elif any(t.get(k) == v for k, v in wood_tags):
            target = 'wood'
        elif t.get('boundary') == 'administrative' and t.get('admin_level') in ('6', '8'):
            target = 'admin'
        if not target:
            continue
        rings = rings_of_geom(a)
        if not rings:
            continue
        if not any(inbox(la, lo) for _, r in rings for lo, la in r[::max(1, len(r) // 8)]):
            continue
        name = t.get('name', '')
        item = {'name': name,
                'rings': [[('o' if outer else 'i'), [[lo, la] for lo, la in r]] for outer, r in rings]}
        if target == 'admin':
            item['level'] = int(t['admin_level'])
        feats[target].append(item)

    print('扫描 area %d' % n_area, flush=True)
    print('水面 %d / 公园 %d / 林地 %d / 行政区 %d  (%.1fs)' % (
        len(feats['water_poly']), len(feats['park']), len(feats['wood']), len(feats['admin']),
        time.time() - t0), flush=True)

    # 机场：单独存一份，供地标与跑道使用
    aer = []
    for w in osmium.FileProcessor(SRC).with_locations().with_filter(osmium.filter.KeyFilter('aeroway')):
        if not w.is_way():
            continue
        t = w.tags
        if t.get('aeroway') not in ('runway', 'terminal', 'apron', 'taxiway'):
            continue
        pts = way_pts(w)
        if not pts or not any(inbox(la, lo) for lo, la in pts):
            continue
        aer.append({'kind': t['aeroway'], 'ref': t.get('ref', ''), 'name': t.get('name', ''),
                    'pts': [[lo, la] for lo, la in pts]})
    feats['aeroway'] = aer
    print('机场要素 %d' % len(aer), flush=True)

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(feats, f, ensure_ascii=False)
    print('写出 %s  %.1f MB  总耗时 %.1fs' % (OUT, os.path.getsize(OUT) / 1e6, time.time() - t0), flush=True)


if __name__ == '__main__':
    main()
