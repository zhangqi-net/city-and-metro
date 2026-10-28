#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 mstations.json（OSM 车站节点）查询站点经纬度，输出 data_bj.js 可用的 st()/anchor() 片段。

用法：
    python3 gen_stations.py            列出全部车站（供人工核对）
    python3 gen_stations.py 苹果园 古城 ...   按给定站名输出 JS 行
坐标来源：OpenStreetMap（© OpenStreetMap 贡献者，ODbL）。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'mstations.json')

# 新投影（与 build_geo.py 一致），输出时一并给出格坐标便于核对
LON0, LAT0, KX, KY = 116.0400, 40.1600, 341.66, 443.84


def load():
    if not os.path.exists(SRC):
        print('缺少 %s，先跑 fetch.py（会抓取车站节点）' % SRC, file=sys.stderr)
        return {}
    with open(SRC, encoding='utf-8') as f:
        d = json.load(f)
    out = {}
    for el in d.get('elements', []):
        if el.get('type') != 'node':
            continue
        nm = (el.get('tags') or {}).get('name', '')
        if not nm:
            continue
        # 同名取第一个（后续同名多为出入口，坐标相近）
        if nm not in out:
            out[nm] = (round(el['lat'], 6), round(el['lon'], 6))
    return out


def gr(lat, lon):
    return round((lon - LON0) * KX, 1), round((LAT0 - lat) * KY, 1)


def find(st, n):
    """站名模糊匹配：原文 / 带“站” / 去“站”"""
    for cand in (n, n + '站', n[:-1] if n.endswith('站') else n):
        if cand in st:
            return cand, st[cand]
    return None, None


def main():
    st = load()
    names = sys.argv[1:]
    if not names:
        print('共 %d 个车站节点。示例：苹果园、西直门、回龙观…' % len(st))
        if st:
            for k in sorted(st):
                la, lo = st[k]
                x, y = gr(la, lo)
                print('%s\t%.6f, %.6f\t格 (%.1f, %.1f)' % (k, la, lo, x, y))
        return
    missing = []
    for n in names:
        key, v = find(st, n)
        if not v:
            missing.append(n)
            print('!! 未找到：%s' % n)
            continue
        la, lo = v
        x, y = gr(la, lo)
        print("%-14s %.6f, %.6f   格 (%.1f, %.1f)%s" % (n, la, lo, x, y, '' if key == n else '  [OSM 名：%s]' % key))
    if missing:
        print('\n缺失 %d 个：%s' % (len(missing), '、'.join(missing)), file=sys.stderr)


if __name__ == '__main__':
    main()
