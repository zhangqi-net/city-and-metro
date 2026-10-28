#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 OSM 海岸线生成海面多边形（深圳湾 / 珠江口 / 大鹏湾）。

OSM 里海不是多边形，只有 natural=coastline 线（陆地在左、水在右）。
做法：把海岸线栅格化成屏障，从已知海域种子点做洪水填充得到海面掩膜，
再用 marching squares 提轮廓、简化成多边形。

输出：szdata/sea.json  {"rings": [[[lon,lat],...], ...]}
"""
import json, math, os, sys

import numpy as np
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
LON0, LAT0 = 113.8000, 22.7220
KX, KY = 409.6, 443.0
W, H = 188, 100
LON1 = LON0 + W / KX
LAT1 = LAT0 - H / KY

RES = 8               # 每格再细分 8 份（约 31 m）
DLON = (1.0 / KX) / RES
DLAT = (1.0 / KY) / RES
MARGIN = 0.03         # 度

GX0, GY0 = LON0 - MARGIN, LAT1 - MARGIN
NX = int((LON1 - LON0 + 2 * MARGIN) / DLON) + 2
NY = int((LAT0 - LAT1 + 2 * MARGIN) / DLAT) + 2

# 已知海域种子（经度, 纬度）
SEEDS = [
    (113.930, 22.500),   # 深圳湾内
    (114.300, 22.540),   # 大鹏湾
    (114.280, 22.470),   # 大鹏湾南
]


def grid_of(lon, lat):
    return int((lon - GX0) / DLON), int((lat - GY0) / DLAT)


def ll_of(ix, iy):
    return GX0 + ix * DLON, GY0 + iy * DLAT


def main():
    d = json.load(open(os.path.join(HERE, 'features.json'), encoding='utf-8'))
    coast = d.get('coast') or []
    print('海岸线段:', len(coast))

    barrier = np.zeros((NY, NX), dtype=bool)
    # 栅格化：沿线密集采样，并加粗 1 格，避免斜向漏缝
    for seg in coast:
        pts = seg['pts']
        for (lo1, la1), (lo2, la2) in zip(pts, pts[1:]):
            n = int(max(abs(lo2 - lo1) / DLON, abs(la2 - la1) / DLAT) * 2) + 2
            for k in range(n + 1):
                t = k / n
                lo = lo1 + (lo2 - lo1) * t
                la = la1 + (la2 - la1) * t
                ix, iy = grid_of(lo, la)
                if 0 <= ix < NX and 0 <= iy < NY:
                    barrier[iy, ix] = True
    # 膨胀一格（8 邻域）
    b = barrier.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            b[max(0, dy):NY + min(0, dy), max(0, dx):NX + min(0, dx)] |= \
                barrier[max(0, -dy):NY + min(0, -dy), max(0, -dx):NX + min(0, -dx)]
    barrier = b

    # 洪水填充（BFS）
    from collections import deque
    sea = np.zeros((NY, NX), dtype=bool)
    dq = deque()
    for lo, la in SEEDS:
        ix, iy = grid_of(lo, la)
        if 0 <= ix < NX and 0 <= iy < NY and not barrier[iy, ix] and not sea[iy, ix]:
            sea[iy, ix] = True
            dq.append((ix, iy))

    # 边框种子：南侧全部、东侧全部、西侧低纬（珠江口）；北侧是陆地，不种
    for ix in range(NX):
        if not barrier[0, ix] and not sea[0, ix]:
            sea[0, ix] = True
            dq.append((ix, 0))
    for iy in range(NY):
        if not barrier[iy, NX - 1] and not sea[iy, NX - 1]:
            sea[iy, NX - 1] = True
            dq.append((NX - 1, iy))
        if GY0 + iy * DLAT < 22.62 and not barrier[iy, 0] and not sea[iy, 0]:
            sea[iy, 0] = True
            dq.append((0, iy))

    while dq:
        ix, iy = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jx, jy = ix + dx, iy + dy
            if 0 <= jx < NX and 0 <= jy < NY and not sea[jy, jx] and not barrier[jy, jx]:
                sea[jy, jx] = True
                dq.append((jx, jy))

    frac = sea.mean()
    print('海面占比: %.1f%%  网格 %dx%d' % (frac * 100, NX, NY))
    if frac > 0.75:
        print('⚠️ 海面占比异常，海岸线可能有缺口（洪水泄漏）')

    # 提取轮廓
    contours = measure.find_contours(sea.astype(float), 0.5)
    rings = []
    for c in contours:
        if len(c) < 8:
            continue
        # c: (row, col) → (lon, lat)
        pts = [(GX0 + col * DLON, GY0 + row * DLAT) for row, col in c]
        # 简化为约 0.06 格
        tol = 0.06 / KX
        simp = measure.approximate_polygon(np.array(pts), tolerance=tol)
        if len(simp) < 4:
            continue
        area = 0.0
        for i in range(len(simp) - 1):
            x1, y1 = simp[i]
            x2, y2 = simp[i + 1]
            area += (x1 * y2 - x2 * y1)
        area = abs(area) / 2
        if area < 4e-6:   # 约 0.02 km²
            continue
        rings.append([[round(p[0], 6), round(p[1], 6)] for p in simp])

    rings.sort(key=lambda r: -len(r))
    print('海面多边形:', len(rings), '合计点数:', sum(len(r) for r in rings))
    json.dump({'rings': rings}, open(os.path.join(HERE, 'sea.json'), 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
