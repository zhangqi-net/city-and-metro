#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""填海多边形核对（格坐标版）：覆盖的格子里有多少是现在的陆地，并打印叠加图。"""
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 211, 100

POLYS = {
    '后海 2005': (2005, [[76, 87], [86, 87], [84, 94], [76, 95]]),
    '前海 2014': (2014, [[57, 77], [67, 77], [67, 88], [61, 91], [57, 88]]),
}


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
    # 用 node 打印水陆栅格，得到一个布尔表
    out = subprocess.run(['node', '/tmp/wmap.js', '0', str(W), '0', str(H)], capture_output=True, text=True).stdout
    grid = []
    for line in out.splitlines()[2:]:
        body = line[5:]
        if len(body) != W:
            continue
        grid.append([ch == '#' for ch in body])
    assert len(grid) == H, (len(grid), H)

    for name, (yr, poly) in POLYS.items():
        n = w = 0
        for j in range(H):
            for i in range(W):
                if not inside(i + 0.5, j + 0.5, poly):
                    continue
                n += 1
                if grid[j][i]:
                    w += 1
        print('%-12s 年 %d  格数 %3d  其中现在仍是水面 %d (%.0f%%)' % (name, yr, n, w, 100.0 * w / max(1, n)))

    # 叠加图（每格一个字符）
    print('\n图例： # 海  . 陆  ▓ 该多边形覆盖的陆格  ░ 该多边形覆盖的水格')
    x0, x1, y0, y1 = 40, 95, 55, 100
    print('     ' + ''.join(str((x // 10) % 10) if x % 10 == 0 else ' ' for x in range(x0, x1)))
    print('     ' + ''.join(str(x % 10) for x in range(x0, x1)))
    for j in range(y0, y1):
        line = ''
        for i in range(x0, x1):
            cov = any(inside(i + 0.5, j + 0.5, p) for _, p in POLYS.values())
            line += ('░░' if grid[j][i] else '▓▓') if cov else ('##' if grid[j][i] else '..')
        print('%3d  %s' % (j, line))


if __name__ == '__main__':
    main()
