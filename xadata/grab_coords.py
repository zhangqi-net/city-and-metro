#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单独抓取西安地铁车站节点与关键 POI 坐标（WGS-84），输出 xacoords.json 供 data_xa.js 校准。"""
import json, os, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
S, W, N, E = 34.12, 108.77, 34.43, 109.14
B = '%s,%s,%s,%s' % (S, W, N, E)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MIRRORS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.private.coffee/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter']

POI = [
 '钟楼','鼓楼','西安城墙','大雁塔','小雁塔','陕西历史博物馆','大明宫国家遗址公园',
 '兴庆宫公园','曲江池遗址公园','大唐芙蓉园','大唐不夜城','西安世博园','汉城湖',
 '碑林博物馆','西安国际会展中心','西安奥体中心','陕西省体育场','西安北站','西安站',
 '西安咸阳国际机场','西安交通大学','西北工业大学','西安电子科技大学','西北大学',
 '陕西师范大学','长安大学','西安建筑科技大学','西京医院','唐都医院','陕西省人民医院',
 '西安交通大学第一附属医院','赛格国际购物中心','小寨','大唐西市','青龙寺','昆明池',
 '书院门','回民街','西安高新万达广场','大雁塔北广场','西安钟楼','西安鼓楼',
 '西安国际医学中心','西安南站','阿房宫南','创新港','诗经里','秦创原中心',
 '空港新城','秦汉新城','沣东新城','沣西新城','国际港务区','西安电子科技大学长安校区',
 '西北大学长安校区','西安浐灞国家湿地公园','西安半坡博物馆','西安城墙景区','永兴坊',
 '陕西自然博物馆','西安美术馆','西安大剧院','西安城市运动公园','西安植物园',
]

def post(q, timeout=180):
    body = urllib.parse.urlencode({'data': q}).encode()
    for base in MIRRORS:
        for k in range(4):
            try:
                req = urllib.request.Request(base, data=body,
                    headers={'User-Agent':'city-metro-map-builder/1.0',
                             'Content-Type':'application/x-www-form-urlencoded'})
                with OPENER.open(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except Exception as e:
                print('  ! %s %s' % (base.split('/')[2], type(e).__name__), flush=True)
                time.sleep(5 * (k + 1))
    raise RuntimeError('all mirrors failed')

out = {}
# 1) 车站节点
print('抓取车站节点...', flush=True)
q = ('[out:json][timeout:150];('
     'node["railway"="station"](%s);node["railway"="halt"](%s);'
     'node["station"="subway"](%s);node["public_transport"="station"]["subway"="yes"](%s);'
     'node["railway"="subway_entrance"](%s););out;' % (B, B, B, B, B))
d = post(q)
st = {}
for e in d.get('elements', []):
    nm = (e.get('tags') or {}).get('name')
    if nm and nm not in st and e.get('lat') is not None:
        st[nm] = [round(e['lat'], 6), round(e['lon'], 6)]
out['stations'] = st
print('  车站 %d 个' % len(st), flush=True)

# 2) POI（分批）
out['poi'] = {}
for i in range(0, len(POI), 30):
    grp = POI[i:i+30]
    pat = '|'.join(grp)
    q = ('[out:json][timeout:150];('
         'nwr["name"~"^(%s)$"](%s);'
         ');out center;' % (pat, B))
    print('抓取 POI 批次 %d...' % (i//30+1), flush=True)
    try:
        d = post(q)
    except Exception as ex:
        print('  批次失败 %s' % ex, flush=True)
        continue
    for e in d.get('elements', []):
        nm = (e.get('tags') or {}).get('name')
        if not nm or nm in out['poi']:
            continue
        if e.get('lat') is not None:
            out['poi'][nm] = [round(e['lat'],6), round(e['lon'],6), e['type']]
        elif e.get('center'):
            out['poi'][nm] = [round(e['center']['lat'],6), round(e['center']['lon'],6), e['type']]
    print('  累计 %d' % len(out['poi']), flush=True)

with open(os.path.join(HERE, 'xacoords.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('写入 xacoords.json：车站 %d / POI %d' % (len(out['stations']), len(out['poi'])), flush=True)
