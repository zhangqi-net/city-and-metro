#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 js/geo_sz.js 渲染成预览图，用于检查地理数据是否正确。"""
import json, os, re, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, '..', 'js', 'geo_sz.js'))
OUT = '/tmp/sz_preview.png'
S = 5          # 每格像素
W, H = 211, 100


def dec(s):
    out = []
    i = 0
    x = y = 0
    n = len(s)
    while i < n:
        r = 0
        sh = 0
        while True:
            b = ord(s[i]) - 63
            i += 1
            r |= (b & 31) << sh
            sh += 5
            if b < 32:
                break
        x += ~(r >> 1) if (r & 1) else (r >> 1)
        r = 0
        sh = 0
        while True:
            b = ord(s[i]) - 63
            i += 1
            r |= (b & 31) << sh
            sh += 5
            if b < 32:
                break
        y += ~(r >> 1) if (r & 1) else (r >> 1)
        out.append((x / 64.0 * S, y / 64.0 * S))
    return out


def main():
    G = json.load(open('/tmp/geo_sz.json', encoding='utf-8'))

    img = Image.new('RGB', (W * S, H * S), (246, 244, 238))
    dr = ImageDraw.Draw(img, 'RGBA')

    # 林地 / 公园
    for key, col in (('woods', (170, 205, 180, 170)), ('parks', (150, 205, 150, 190))):
        for row in G[key]:
            polys = []
            cur = None
            for r in row[1:]:
                pts = dec(r[1:])
                if r[0] == 'o':
                    cur = [pts]
                    polys.append(cur)
                elif cur is not None:
                    cur.append(pts)
            for rings in polys:
                dr.polygon(rings[0], fill=col)
    # 水面
    for row in G['water']:
        if isinstance(row[1], (int, float)):
            continue
        polys = []
        cur = None
        for r in row[1:]:
            pts = dec(r[1:])
            if r[0] == 'o':
                cur = [pts]
                polys.append(cur)
            elif cur is not None:
                cur.append(pts)
        for rings in polys:
            dr.polygon(rings[0], fill=(120, 170, 215))
            for h in rings[1:]:
                dr.polygon(h, fill=(246, 244, 238))
    # 河道
    for row in G['water']:
        if not isinstance(row[1], (int, float)):
            continue
        pts = dec(row[2])
        if len(pts) >= 2:
            dr.line(pts, fill=(120, 170, 215), width=max(1, int(row[1] * S)))
    # 道路（深中通道单独标红，便于核对）
    for row in G['roads']:
        cls = row[1]
        nm = G['names'][row[0]]
        if nm == '深中通道':
            dr.line(dec(row[3]), fill=(200, 30, 90), width=3)
            continue
        col = {4: (250, 200, 120), 3: (252, 226, 176), 2: (238, 232, 220)}.get(cls, (238, 232, 220))
        w = {4: 2, 3: 2, 2: 1}.get(cls, 1)
        dr.line(dec(row[3]), fill=col, width=w)
    # 铁路
    for row in G['rail']:
        dr.line(dec(row[2]), fill=(90, 90, 110), width=1)
    # 行政区界
    for row in G['admin']:
        lvl = row[0]
        col = (200, 90, 90, 200) if lvl == 6 else (200, 90, 90, 70)
        for r in row[2:]:
            if r[0] == 'o':
                dr.line(dec(r[1:]), fill=col, width=2 if lvl == 6 else 1)
    # 地名（只画 rank<=2）
    for p in G['places']:
        if p[3] <= 2:
            dr.ellipse([p[1] * S - 2, p[2] * S - 2, p[1] * S + 2, p[2] * S + 2], fill=(180, 60, 60))

    img.save(OUT)
    print('已保存', OUT, img.size)


if __name__ == '__main__':
    main()
