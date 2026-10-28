#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""features.json → js/geo_bj.js（与 geo_sz.js 同格式：增量 zigzag 编码，1/64 格精度）"""
import json, os, re, sys

import opencc
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.validation import make_valid

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'features.json')
OUT = os.path.abspath(os.path.join(HERE, '..', 'js', 'geo_bj.js'))

# 左上原点（116.160 E, 40.0874 N）；格 250 m；160 x 132 格 = 40 x 33 km
LON0, LAT0 = 116.1600, 40.0874
KX, KY = 341.66, 443.84
W, H = 160, 132

CLIP = box(-2.0, -2.0, W + 2.0, H + 2.0)
T2S = opencc.OpenCC('t2s')

WIDTH = {'river': 0.088, 'canal': 0.048, 'stream': 0.024}

# 铁路启用年份（按名称包含匹配）：高铁按史实年份出现；普速线路均在开局（1990）之前
RAIL_YEAR = [
    ('京广高速铁路', 2012), ('京广高铁', 2012), ('京广客运专线', 2012),
    ('京沪高速铁路', 2011), ('京沪高铁', 2011), ('京沪客运专线', 2011),
    ('京津城际', 2008), ('京雄城际', 2019), ('京张高铁', 2019), ('京张客运专线', 2019),
    ('京哈高铁', 2021), ('京沈客运专线', 2021), ('京沈高铁', 2021),
    ('京九', 1996), ('京通', 1977),
    ('京包', 1909), ('京山', 1897), ('京奉', 1897), ('京广', 1911), ('京承', 1955), ('丰沙', 1955),
]
HSR_KEY = ('高铁', '客运专线', '城际')

CJK = re.compile(r'[\u4e00-\u9fff]')


def clean(name):
    """去拉丁后缀 + 繁转简"""
    if not name:
        return ''
    n = name.strip()
    if CJK.search(n):
        n = re.split(r'\s+(?=[A-Za-z(\uff08])', n)[0]
        n = re.sub(r'[（(][A-Za-z][^）)]*[）)]\s*$', '', n)
    n = n.replace(' - ', '·').strip()
    try:
        n = T2S.convert(n)
    except Exception:
        pass
    return n.strip()


def proj(lon, lat):
    return ((lon - LON0) * KX, (LAT0 - lat) * KY)


def enc(pts):
    out = []
    px = py = 0
    for x, y in pts:
        ix = int(round(x * 64))
        iy = int(round(y * 64))
        for v in (ix - px, iy - py):
            u = (v << 1) ^ (v >> 63)
            while u >= 32:
                out.append(chr((32 | (u & 31)) + 63))
                u >>= 5
            out.append(chr(u + 63))
        px, py = ix, iy
    return ''.join(out)


def dp(pts, tol):
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    t2 = tol * tol
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        best = -1.0
        bi = -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L > 1e-12:
                t = ((px - ax) * dx + (py - ay) * dy) / L
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                qx, qy = ax + dx * t, ay + dy * t
            else:
                qx, qy = ax, ay
            d = (px - qx) ** 2 + (py - qy) ** 2
            if d > best:
                best, bi = d, i
        if best > t2:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [pts[i] for i in range(n) if keep[i]]


class Names:
    def __init__(self):
        self.lst = ['']
        self.idx = {'': 0}

    def __call__(self, s):
        s = s or ''
        if s not in self.idx:
            self.idx[s] = len(self.lst)
            self.lst.append(s)
        return self.idx[s]


def in_view(x, y, m=1.5):
    return -m <= x <= W + m and -m <= y <= H + m


def clip_line(pts):
    runs, cur = [], []
    for x, y in pts:
        if in_view(x, y):
            cur.append((x, y))
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def poly_rows(feature, tol):
    """[['o',pts],['i',pts],…] → 裁剪简化后的 [[(kind, pts)], …]（可能拆成多块）"""
    outers = []
    cur = None
    for kind, pts in feature['rings']:
        g = [proj(lo, la) for lo, la in pts]
        if kind == 'o':
            cur = {'outer': g, 'holes': []}
            outers.append(cur)
        elif cur is not None:
            cur['holes'].append(g)
    rows = []
    for o in outers:
        if len(o['outer']) < 3:
            continue
        try:
            sp = Polygon(o['outer'], [h for h in o['holes'] if len(h) >= 3])
            if not sp.is_valid:
                sp = make_valid(sp)
        except Exception:
            continue
        try:
            sp = sp.intersection(CLIP)
        except Exception:
            continue
        if sp.is_empty:
            continue
        parts = [sp] if sp.geom_type == 'Polygon' else [g for g in getattr(sp, 'geoms', []) if g.geom_type == 'Polygon']
        for p in parts:
            if p.area < 0.02:
                continue
            s = p.simplify(tol, preserve_topology=True)
            if s.is_empty:
                continue
            if s.geom_type == 'MultiPolygon':
                comps = list(s.geoms)
            else:
                comps = [s]
            for c in comps:
                if c.area < 0.02:
                    continue
                ring = dp([(x, y) for x, y in c.exterior.coords], tol)
                if len(ring) < 4:
                    continue
                row = [('o', ring[:-1] if ring[0] == ring[-1] else ring)]
                for ir in c.interiors:
                    h = dp([(x, y) for x, y in ir.coords], tol)
                    if len(h) >= 4:
                        row.append(('i', h[:-1] if h[0] == h[-1] else h))
                rows.append(row)
    return rows


def main():
    d = json.load(open(SRC, encoding='utf-8'))
    names = Names()
    out = {'proj': {'lon0': LON0, 'lat0': LAT0, 'kx': KX, 'ky': KY},
           'water': [], 'roads': [], 'rail': [], 'parks': [], 'reserves': [], 'woods': [],
           'admin': [], 'places': [], 'names': None}

    # ---- 水面 ----
    n_poly = n_line = 0
    for f in d['water_poly']:
        for row in poly_rows(f, 0.06):
            out['water'].append([names(clean(f['name']))] + [k + enc(p) for k, p in row])
            n_poly += 1
    for f in d['water_line']:
        g = [proj(lo, la) for lo, la in f['pts']]
        for run in clip_line(g):
            run = dp(run, 0.08)
            if len(run) >= 2:
                out['water'].append([names(clean(f['name'])), WIDTH.get(f['kind'], 0.05), enc(run)])
                n_line += 1

    # ---- 道路 ----
    nr = 0
    for f in d['road']:
        g = [proj(lo, la) for lo, la in f['pts']]
        for run in clip_line(g):
            run = dp(run, 0.05)
            if len(run) >= 2:
                out['roads'].append([names(clean(f['name'])), f['cls'], f['flags'], enc(run)])
                nr += 1

    # ---- 铁路 ----
    nrail = 0
    for f in d['rail']:
        g = [proj(lo, la) for lo, la in f['pts']]
        year = 0
        nm = clean(f['name'])
        for k, y in RAIL_YEAR:
            if nm and k in nm:
                year = y
                break
        flags = f['flags']
        if any(k in nm for k in HSR_KEY) or year in (2008, 2011, 2012, 2019, 2021):
            flags |= 16
        for run in clip_line(g):
            run = dp(run, 0.06)
            if len(run) >= 2:
                row = [names(nm), flags, enc(run)]
                if year:
                    row.append(year)
                out['rail'].append(row)
                nrail += 1

    # ---- 公园 / 林地 ----
    def polys(key, dst, tol):
        n = 0
        for f in d[key]:
            for row in poly_rows(f, tol):
                dst.append([names(clean(f['name']))] + [k + enc(p) for k, p in row])
                n += 1
        return n

    npark = polys('park', out['parks'], 0.10)
    nwood = polys('wood', out['woods'], 0.16)

    # ---- 行政区 ----
    na = 0
    lv = {}
    for f in d['admin']:
        lv[f['level']] = lv.get(f['level'], 0) + 1
        nm = clean(f['name'])
        if not nm:
            continue
        for row in poly_rows(f, 0.08):
            out['admin'].append([f['level'], names(nm)] + [k + enc(p) for k, p in row])
            na += 1
    print('行政区层级分布:', lv)

    # ---- 地名 ----
    seen = set()
    for p in d['place']:
        x, y = proj(p['lon'], p['lat'])
        nm = clean(p['name'])
        if not in_view(x, y) or not nm or nm in seen:
            continue
        seen.add(nm)
        out['places'].append([nm, round(x, 2), round(y, 2), p['rank']])
    out['places'].sort(key=lambda r: r[3])

    out['names'] = names.lst

    # 预览脚本直接读这一份，避免再解析 JS
    with open('/tmp/geo_bj.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    def js(v):
        return json.dumps(v, ensure_ascii=False, separators=(',', ':'))

    parts = ["'use strict';\n"]
    parts.append('// 由 OpenStreetMap 数据生成（© OpenStreetMap 贡献者，ODbL）。坐标为游戏格（250 m），'
                 '折线为增量编码，1/64 格精度。地名已转为简体中文。\n')
    parts.append('// 覆盖范围：116.160–116.628 E，39.790–40.087 N（160 × 132 格）。生成脚本见 bjdata/。\n')
    parts.append('(function (CM) {\n  (CM.GEOS = CM.GEOS || {}).bj = {\n')
    parts.append('    proj: %s,\n' % js(out['proj']))
    for key in ('water', 'roads', 'rail', 'parks', 'reserves', 'woods', 'admin', 'places'):
        parts.append('    %s: [\n' % key)
        parts.append(',\n'.join('      ' + js(r) for r in out[key]))
        parts.append('\n    ],\n')
    parts.append('    names: %s,\n' % js(out['names']))
    parts.append('  };\n})(window.CM);\n')
    open(OUT, 'w', encoding='utf-8').write(''.join(parts))

    print('水面 %d（多边形 %d / 河道 %d）' % (len(out['water']), n_poly, n_line))
    print('道路 %d / 铁路 %d / 公园 %d / 林地 %d / 行政区 %d / 地名 %d' % (
        nr, nrail, npark, nwood, na, len(out['places'])))
    print('名称 %d 条' % len(out['names']))
    print('输出 %s  %.2f MB' % (OUT, os.path.getsize(OUT) / 1e6))


if __name__ == '__main__':
    main()
