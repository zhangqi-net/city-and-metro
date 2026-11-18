#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量查询 POI 经纬度（地标、设施、任务锚点），用于校准 js/data_xa.js 的坐标。

用法：
    python3 gen_places.py                     # 用内置的默认清单（地标 + 设施 + 任务锚点）
    python3 gen_places.py 故宫 天坛 中关村     # 指定名称

数据源：OpenStreetMap（WGS-84）。注意：百度/高德等国内地图为 GCJ-02 坐标，与 OSM 相差数百米，
游戏底图是 OSM，因此所有坐标一律以 OSM 为准，不要照抄国内地图的坐标。
结果写入 places.json，供 gen_stations.py / 人工核对复用。
"""
import json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'places.json')
BBOX = (34.12, 108.77, 34.43, 109.14)   # s, w, n, e（绕城高速内，略放宽）
MIRRORS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = 'city-metro-map-builder/1.0 (personal non-commercial game map)'

DEFAULT = [
  # 地标 / 场地
  '钟楼', '鼓楼', '西安城墙', '大雁塔', '小雁塔', '陕西历史博物馆', '兵马俑',
  '大明宫国家遗址公园', '兴庆宫公园', '曲江池遗址公园', '大唐芙蓉园', '大唐不夜城',
  '西安世博园', '西安浐灞国家湿地公园', '昆明池', '汉城湖', '碑林博物馆',
  '西安国际会展中心', '西安奥体中心', '陕西体育场', '西安大剧院',
  '西安北站', '西安站', '西安南站', '西安西站', '咸阳机场', '西安咸阳国际机场',
  '西安交通大学', '西北工业大学', '西安电子科技大学', '西北大学', '陕西师范大学',
  '长安大学', '西安建筑科技大学', '西北政法大学', '西安邮电大学',
  # 医院 / 商圈 / 景区
  '西京医院', '唐都医院', '交大一附院', '陕西省人民医院', '西安市中心医院',
  '钟楼商圈', '小寨', '高新路', '科技路', '唐延路', '锦业路', '高新万达',
  '赛格国际购物中心', '大悦城', '曲江大悦城', '熙地港', '砂之船奥莱',
  '回民街', '书院门', '大皮院', '永兴坊', '大唐西市',
  '高新区', '经开区', '曲江新区', '浐灞生态区', '航天基地', '西咸新区',
  '沣东新城', '沣西新城', '秦汉新城', '空港新城', '国际港务区',
  # 地铁站点（用于任务锚点校准）
  '后卫寨', '纺织城', '北客站', '韦曲南', '鱼化寨', '保税区', '航天新城',
  '常宁宫', '草滩', '创新港', '西安东站', '秦陵西', '贺韶', '机场西',
  '昭慧广场', '井上村', '细柳', '东兆余', '诗经里', '秦创原中心',
  '钟楼', '北大街', '南门', '小寨', '大雁塔', '北池头', '青龙寺',
  '五路口', '玉祥门', '汉城路', '开远门', '劳动路', '安定门', '永宁门',
  '安远门', '龙首原', '大明宫西', '市图书馆', '凤城五路', '行政中心',
  '运动公园', '北苑', '会展中心', '纬一街', '航天城', '凤栖原', '三爻',
  '浐河', '半坡', '长乐坡', '万寿路', '通化门', '康复路', '朝阳门',
  '洒金桥', '莲湖', '枣园', '皂河', '三桥', '沣东自贸园', '上林路',
  '沣河森林公园', '沣西新城', '翱翔小镇', '钓台', '翱翔小镇',
  '桃花潭', '广泰门', '辛家庙', '石家街', '胡家庙', '长乐公园',
  '咸宁路', '延兴门', '青龙寺', '北池头', '大雁塔', '大唐芙蓉园',
  '曲江池西', '金滹沱', '航天大道', '飞天路', '东长安街',
  '丈八一路', '省体育馆', '木塔寺', '甘家寨', '科技路', '西北工业大学',
  '大唐西市', '安定门', '桥梓口', '广济街', '钟楼', '大差市',
  '长乐门', '交通大学·兴庆宫', '咸宁路', '公园南路', '马腾空',
  '田王', '洪庆', '紫霞三路', '凤凰池', '鹦鹉寺公园', '芷阳广场',
  '西工程大·西科大', '华清池', '东三岔', '银桥大道', '秦陵西',
  '空港新城', '艺术中心', '机场西', '秦汉新城', '秦宫', '渭河南',
  '兰池大道', '长陵', '摆旗寨', '石家街', '贺韶', '港务大道',
]


def post(query, timeout=300):
    body = urllib.parse.urlencode({'data': query}).encode()
    last = None
    for base in MIRRORS:
        for attempt in range(4):
            req = urllib.request.Request(base, data=body,
                                         headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'})
            try:
                with OPENER.open(req, timeout=timeout) as r:
                    raw = r.read()
                d = json.loads(raw)
                if 'elements' in d:
                    return d
                last = 'no elements'
            except Exception as e:
                last = '%s: %s' % (type(e).__name__, e)
                time.sleep(5 * (attempt + 1))
    raise RuntimeError('全部镜像失败：%s' % last)


def chunk(lst, n=40):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    names = sys.argv[1:] or DEFAULT
    s, w, n, e = BBOX
    out = {}
    for grp in chunk(names, 40):
        pat = '|'.join(grp)
        q = ('[out:json][timeout:180];\n(\n'
             '  node["name"~"^(%s)$"](%s,%s,%s,%s);\n'
             '  way["name"~"^(%s)$"](%s,%s,%s,%s);\n'
             ');\nout center;' % (pat, s, w, n, e, pat, s, w, n, e))
        d = post(q)
        for el in d.get('elements', []):
            t = el.get('tags') or {}
            nm = t.get('name', '')
            if not nm or nm in out:
                continue
            if el['type'] == 'node':
                out[nm] = [round(el['lat'], 6), round(el['lon'], 6), 'node']
            elif 'center' in el:
                out[nm] = [round(el['center']['lat'], 6), round(el['center']['lon'], 6), 'way']
        print('  查询 %d 个名称，累计命中 %d' % (len(grp), len(out)), flush=True)
        time.sleep(1)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('\n命中 %d / %d，写入 %s' % (len(out), len(names), OUT))
    miss = [x for x in names if x not in out]
    if miss:
        print('未命中（%d）：%s' % (len(miss), '、'.join(miss)))
    # 打印便于复制
    print('\n--- 坐标（纬度, 经度）---')
    for nm in names:
        if nm in out:
            v = out[nm]
            print('%-16s %.6f, %.6f' % (nm, v[0], v[1]))


if __name__ == '__main__':
    main()
