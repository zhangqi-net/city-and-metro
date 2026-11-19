#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简官方 /map 通道产出的 tile_*.json。

官方 /map 返回全量 OSM 要素（大量 building / footway / service road），
单块可达 19 MB，16 块合计 88 MB，会让 extract.py 的 json.load 吃内存且变慢。
本脚本按 extract.py 实际消费的 tag 过滤，只保留会被用到的 way 与带 tag 的 node，
把体积压到原来的几十分之一；原文件备份到 backup_overpass/full/。
"""
import glob, json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_overpass', 'full')

ROAD_CLS = {'motorway', 'trunk', 'primary', 'secondary',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link'}
RAIL = {'rail', 'light_rail', 'subway', 'station', 'tram', 'narrow_gauge'}
WATERWAY = {'river', 'canal', 'stream', 'riverbank', 'dock', 'dam'}
NATURAL = {'water', 'wood', 'coastline', 'wetland', 'scrub'}
LANDUSE = {'reservoir', 'forest', 'grass', 'recreation_ground', 'meadow', 'orchard'}
LEISURE = {'park', 'garden', 'nature_reserve'}
AEROWAY = {'runway', 'terminal', 'apron', 'taxiway', 'aerodrome'}


def keep_way(t):
    return (t.get('highway') in ROAD_CLS
            or t.get('railway') in RAIL
            or t.get('waterway') in WATERWAY
            or t.get('natural') in NATURAL
            or t.get('landuse') in LANDUSE
            or t.get('leisure') in LEISURE
            or t.get('aeroway') in AEROWAY
            or t.get('boundary') == 'administrative')


def main():
    os.makedirs(BACKUP, exist_ok=True)
    files = sorted(glob.glob(os.path.join(HERE, 'tile_[0-9]_[0-9].json')))
    total_before = total_after = 0
    for fn in files:
        before = os.path.getsize(fn)
        with open(fn, encoding='utf-8') as f:
            d = json.load(f)
        els = d.get('elements', [])
        kept = [el for el in els
                if (el.get('type') == 'way' and keep_way(el.get('tags') or {}))
                or (el.get('type') == 'node' and el.get('tags'))]
        bk = os.path.join(BACKUP, os.path.basename(fn))
        if not os.path.exists(bk):
            shutil.copy2(fn, bk)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({'elements': kept}, f, ensure_ascii=False)
        after = os.path.getsize(fn)
        total_before += before
        total_after += after
        print('%-18s %6.1f MB -> %5.2f MB  要素 %6d -> %6d' % (
            os.path.basename(fn), before / 1e6, after / 1e6, len(els), len(kept)), flush=True)
    print('合计 %.1f MB -> %.1f MB' % (total_before / 1e6, total_after / 1e6), flush=True)


if __name__ == '__main__':
    main()
