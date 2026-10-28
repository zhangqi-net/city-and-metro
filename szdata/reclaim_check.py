#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""填海多边形核对：把候选多边形画在预览图上，并统计多边形内的“现代水面”占比。
占比越高说明多边形压到了现在的海面（说明范围画大了）；理想值是接近 0（现在全是陆地）。
"""
import json, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
S = 5
W, H = 211, 100
LON0, LAT0, KX, KY = 113.744, 22.722, 409.6, 443.0

# 候选填海多边形（经纬度）
POLYS = {
    '蛇口·赤湾 1984': (1984, [(113.882, 22.496), (113.925, 22.496), (113.930, 22.508), (113.918, 22.517), (113.895, 22.517), (113.884, 22.508)]),
    '后海 2005': (2005, [(113.928, 22.508), (113.962, 22.508), (113.966, 22.520), (113.940, 22.524), (113.928, 22.520)]),
    '前海 2015': (2015, [(113.868, 22.520), (113.905, 22.518), (113.912, 22.545), (113.885, 22.558), (113.866, 22.545)]),
    '大铲湾 2008': (2008, [(113.850, 22.556), (113.882, 22.552), (113.890, 22.578), (113.862, 22.592), (113.848, 22.578)]),
    '盐田港 1990': (1990, [(114.238, 22.562), (114.268, 22.566), (114.272, 22.582), (114.244, 22.586)]),
    '深圳湾超级总部 2018': (2018, [(113.960, 22.512), (113.984, 22.512), (113.988, 22.522), (113.962, 22.522)]),
}


def grid(lo, la):
    return ((lo - LON0) * KX, (LAT0 - la) * KY)


def inside(px, py, pts):
    n = len(pts)
    c = False
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1):
            c = not c
    return c


def main():
    im = Image.open('/tmp/sz_preview.png').convert('RGB')
    P = im.load()
    dr = ImageDraw.Draw(im, 'RGBA')
    f = ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc', 14)
    print('%-24s %6s %6s' % ('多边形', '水面%', '格数'))
    for name, (yr, poly) in POLYS.items():
        pts = [grid(lo, la) for lo, la in poly]
        # 只在图上画多边形覆盖的格
        n = w = 0
        x0 = int(min(p[0] for p in pts)); x1 = int(max(p[0] for p in pts)) + 1
        y0 = int(min(p[1] for p in pts)); y1 = int(max(p[1] for p in pts)) + 1
        for gy in range(max(0, y0), min(H, y1)):
            for gx in range(max(0, x0), min(W, x1)):
                if not inside(gx + 0.5, gy + 0.5, pts):
                    continue
                wc = 0
                for yy in range(gy * S, gy * S + S):
                    for xx in range(gx * S, gx * S + S):
                        r, g, b = P[xx, yy]
                        if b > r + 30 and b > 170:
                            wc += 1
                n += 1
                if wc >= 13:
                    w += 1
                dr.rectangle([gx * S, gy * S, gx * S + S - 1, gy * S + S - 1], fill=(255, 0, 120, 150))
        print('%-24s %5.0f%% %6d' % (name, 100.0 * w / max(1, n), n))
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        dr.text((cx * S - 20, cy * S), name, font=f, fill=(90, 0, 40))
        dr.line([(p[0] * S, p[1] * S) for p in pts] + [(pts[0][0] * S, pts[0][1] * S)], fill=(255, 0, 120), width=2)
    im.save('/tmp/reclaim_check.png')
    print('已保存 /tmp/reclaim_check.png')


if __name__ == '__main__':
    main()
