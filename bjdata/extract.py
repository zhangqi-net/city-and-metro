#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tile_*.json + admin.json + place.json + poi.json（Overpass 原始输出）→ features.json。

与深圳 szdata/features.json 同一结构：water_poly / water_line / road / rail / park / wood /
admin / place / aeroway / coast，供 build_geo.py 消费。
Overpass 关系多边形的 outer/inner ways 在此拼接成环。
"""
import glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'features.json')

# 与 fetch.py 一致
W, E = 116.1600, 116.6283
S, N = 39.7900, 40.0874
M = 0.02
S2, W2, N2, E2 = S - M, W - M, N + M, E + M


def inbox(lat, lon):
    return S2 <= lat <= N2 and W2 <= lon <= E2


def load(name):
    fn = os.path.join(HERE, name)
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return json.load(f)
    return {'elements': []}


def merge_tiles():
    """合并分块（按 type+id 去重）。"""
    ways, nodes = {}, {}
    for fn in sorted(glob.glob(os.path.join(HERE, 'tile_*.json'))):
        with open(fn, encoding='utf-8') as f:
            d = json.load(f)
        for el in d.get('elements', []):
            k = (el['type'], el['id'])
            if el['type'] == 'way':
                ways[k] = el
            elif el['type'] == 'node':
                nodes[k] = el
    return list(ways.values()), list(nodes.values())


ROAD_CLS = {}
for k in ('motorway', 'trunk', 'motorway_link', 'trunk_link'):
    ROAD_CLS[k] = (4, k.endswith('_link'))
for k in ('primary', 'primary_link'):
    ROAD_CLS[k] = (3, k.endswith('_link'))
for k in ('secondary', 'secondary_link'):
    ROAD_CLS[k] = (2, k.endswith('_link'))

WATER_TAGS = {('natural', 'water'), ('waterway', 'riverbank'), ('landuse', 'reservoir')}
PARK_TAGS = {('leisure', 'park'), ('leisure', 'garden'), ('leisure', 'nature_reserve')}
WOOD_TAGS = {('natural', 'wood'), ('landuse', 'forest'), ('landuse', 'grass'), ('landuse', 'recreation_ground')}


def ring_of_way_geom(el):
    """way（含 geometry）→ [(lon, lat), ...]"""
    g = el.get('geometry') or []
    return [(round(p['lon'], 7), round(p['lat'], 7)) for p in g if p is not None]


def build_rings(polylines):
    """把一组折线（原地消费）拼成若干条环/长折线；返回 pts 列表。"""
    segs = [list(p) for p in polylines if len(p) >= 2]
    res = []
    guard = 0
    while segs and guard < len(polylines) + 4:
        guard += 1
        ring = segs.pop(0)
        changed = True
        while changed and segs:
            changed = False
            for i, s in enumerate(segs):
                if ring[-1] == s[0]:
                    ring = ring + s[1:]
                elif ring[-1] == s[-1]:
                    ring = ring + list(reversed(s))[1:]
                elif ring[0] == s[-1]:
                    ring = s + ring[1:]
                elif ring[0] == s[0]:
                    ring = list(reversed(s)) + ring[1:]
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if len(ring) >= 4:
            if ring[0] != ring[-1]:
                ring = ring + [ring[0]]
            res.append(ring)
    return res


def rings_of_relation(rel):
    """relation（out geom）→ [('o', pts) / ('i', pts), ...]"""
    outers, inners = [], []
    for mem in rel.get('members', []):
        if mem.get('type') != 'way' or 'geometry' not in mem:
            continue
        pts = [(round(p['lon'], 7), round(p['lat'], 7)) for p in mem['geometry'] if p is not None]
        if len(pts) < 2:
            continue
        (inners if mem.get('role') == 'inner' else outers).append(pts)
    rings = []
    # 先取自身闭合的 way，再把剩下的段拼接成环
    for p in outers:
        if len(p) >= 4 and p[0] == p[-1]:
            rings.append(('o', p))
    for r in build_rings([p for p in outers if not (len(p) >= 4 and p[0] == p[-1])]):
        rings.append(('o', r))
    for p in inners:
        if len(p) >= 4 and p[0] == p[-1]:
            rings.append(('i', p))
    for r in build_rings([p for p in inners if not (len(p) >= 4 and p[0] == p[-1])]):
        rings.append(('i', r))
    return rings


def has_tag(t, tagset):
    return any(t.get(k) == v for k, v in tagset)


def main():
    ways, nodes = merge_tiles()
    print('合并分块：way %d / node %d' % (len(ways), len(nodes)), flush=True)

    feats = {k: [] for k in ('water_poly', 'water_line', 'road', 'rail', 'park', 'wood',
                             'admin', 'place', 'aeroway', 'coast')}

    # ---------- 线状：way ----------
    for el in ways:
        t = el.get('tags') or {}
        pts = ring_of_way_geom(el)
        if len(pts) < 2:
            continue
        if not any(inbox(la, lo) for lo, la in pts):
            continue
        bridge = bool(t.get('bridge')) and t.get('bridge') != 'no'
        tunnel = bool(t.get('tunnel')) and t.get('tunnel') != 'no'
        name = t.get('name', '')

        hw = t.get('highway')
        if hw in ROAD_CLS:
            cls, link = ROAD_CLS[hw]
            flags = (1 if bridge else 0) | (2 if tunnel else 0) | (4 if link else 0)
            feats['road'].append({'name': name, 'cls': cls, 'flags': flags, 'pts': pts})
            continue

        rw = t.get('railway')
        if rw == 'rail':
            flags = (1 if bridge else 0) | (2 if tunnel else 0)
            if '高铁' in name or '客运专线' in name or '城际' in name or t.get('highspeed') == 'yes':
                flags |= 16
            feats['rail'].append({'name': name, 'flags': flags, 'pts': pts})
            continue

        ww = t.get('waterway')
        if ww in ('river', 'canal', 'stream'):
            feats['water_line'].append({'name': name, 'kind': ww, 'pts': pts})
            continue

        aw = t.get('aeroway')
        if aw in ('runway', 'terminal', 'apron', 'taxiway'):
            feats['aeroway'].append({'kind': aw, 'ref': t.get('ref', ''), 'name': name, 'pts': pts})

    print('way 线要素：道路 %d / 铁路 %d / 河道 %d / 机场 %d' % (
        len(feats['road']), len(feats['rail']), len(feats['water_line']), len(feats['aeroway'])), flush=True)

    # ---------- 面状：闭合 way ----------
    for el in ways:
        t = el.get('tags') or {}
        pts = ring_of_way_geom(el)
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        if not any(inbox(la, lo) for lo, la in pts[::max(1, len(pts) // 8)]):
            continue
        name = t.get('name', '')
        rings = [('o', pts)]
        target = None
        if has_tag(t, WATER_TAGS):
            target = 'water_poly'
        elif has_tag(t, PARK_TAGS):
            target = 'park'
        elif has_tag(t, WOOD_TAGS):
            target = 'wood'
        elif t.get('boundary') == 'administrative' and t.get('admin_level') in ('6', '8'):
            target = 'admin'
        if target:
            item = {'name': name, 'rings': rings}
            if target == 'admin':
                item['level'] = int(t['admin_level'])
            feats[target].append(item)

    print('闭合 way：水面 %d / 公园 %d / 林地 %d / 行政区 %d' % (
        len(feats['water_poly']), len(feats['park']), len(feats['wood']), len(feats['admin'])), flush=True)

    # ---------- relation 多边形（admin + 大水面/公园） ----------
    for fn in ('admin.json', 'admin6.json'):
        adm = load(fn)
        for el in adm.get('elements', []):
            if el.get('type') != 'relation':
                continue
            t = el.get('tags') or {}
            if t.get('boundary') != 'administrative' or t.get('admin_level') not in ('6', '8'):
                continue
            rings = rings_of_relation(el)
            if not rings:
                continue
            if not any(inbox(la, lo) for _, r in rings for lo, la in r[::max(1, len(r) // 8)]):
                continue
            feats['admin'].append({'name': t.get('name', ''), 'level': int(t['admin_level']), 'rings': rings})

    print('含关系后：行政区 %d' % len(feats['admin']), flush=True)

    # ---------- 地名节点 ----------
    pl = load('place.json')
    for el in pl.get('elements', []):
        if el.get('type') != 'node':
            continue
        t = el.get('tags') or {}
        kind = t.get('place')
        if kind not in ('city', 'suburb', 'town', 'village', 'quarter', 'neighbourhood', 'borough'):
            continue
        if not t.get('name'):
            continue
        la, lo = el['lat'], el['lon']
        if not inbox(la, lo):
            continue
        rank = {'city': 1, 'borough': 2, 'suburb': 2, 'quarter': 3, 'town': 3,
                'village': 4, 'neighbourhood': 4}.get(kind, 4)
        feats['place'].append({'name': t['name'], 'lon': round(lo, 6), 'lat': round(la, 6), 'rank': rank})
    print('地名 %d' % len(feats['place']), flush=True)

    # ---------- 站场 / 大学 / 机场 ----------
    for fn in ('poi.json', 'poi2.json'):
        poi = load(fn)
        for el in poi.get('elements', []):
            t = el.get('tags') or {}
            pts = ring_of_way_geom(el)
            if not pts and el.get('type') == 'node':
                pts = [(round(el['lon'], 7), round(el['lat'], 7))]
            if len(pts) < 1:
                continue
            if t.get('railway') == 'station' and t.get('name'):
                feats['place'].append({'name': t['name'], 'lon': round(pts[0][0], 6),
                                       'lat': round(pts[0][1], 6), 'rank': 3})
            if t.get('amenity') == 'university' and t.get('name'):
                feats['aeroway'].append({'kind': 'university', 'ref': '', 'name': t['name'], 'pts': pts})
            aw = t.get('aeroway')
            if aw in ('runway', 'terminal', 'apron', 'taxiway'):
                feats['aeroway'].append({'kind': aw, 'ref': t.get('ref', ''), 'name': t.get('name', ''), 'pts': pts})

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(feats, f, ensure_ascii=False)
    print('写出 %s  %.1f MB' % (OUT, os.path.getsize(OUT) / 1e6), flush=True)


if __name__ == '__main__':
    main()
