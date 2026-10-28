#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量查询 POI 经纬度（地标、设施、任务锚点），用于校准 js/data_bj.js 的坐标。

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
BBOX = (39.66, 116.01, 40.19, 116.77)   # s, w, n, e
MIRRORS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']
UA = 'city-metro-map-builder/1.0 (personal non-commercial game map)'

DEFAULT = [
  # 地标
  '天安门', '故宫博物院', '故宫', '天坛公园', '天坛', '颐和园', '人民大会堂', '民族文化宫',
  '北京电报大楼', '北京站', '工人体育场', '首都体育馆', '民族饭店', '国贸', '京广中心',
  '中央电视台', '中信大厦', '中国尊', '恒基中心', '东方广场', '中华世纪坛', '中央电视塔',
  '国家大剧院', '国家体育场', '国家游泳中心', '北京西站', '北京南站', '北京朝阳站',
  '首都国际机场', '清华大学', '北京大学', '中国人民大学', '北京师范大学',
  '北京航空航天大学', '北京理工大学', '北京邮电大学', '北京交通大学', '中国农业大学',
  '中央民族大学',
  # 设施
  '北京北站', '北京东站', '南苑机场', '北京协和医院', '首都医科大学附属北京同仁医院', '同仁医院',
  '宣武医院', '北京大学第三医院', '北医三院', '北京友谊医院', '友谊医院', '首都医科大学附属北京朝阳医院',
  '朝阳医院', '北京天坛医院', '天坛医院', '北京大学人民医院', '北京安贞医院', '安贞医院',
  '北京积水潭医院', '积水潭医院', '王府井', '西单', '前门大街', '隆福寺', '赛特购物中心',
  '燕莎友谊商城', '蓝岛大厦', '双安商场', '北海公园', '景山公园', '恭王府', '玉渊潭公园',
  '紫竹院公园', '陶然亭公园', '朝阳公园', '龙潭公园', '奥林匹克森林公园', '香山公园',
  '五棵松体育馆', '中国国际展览中心', '北京展览馆', '全国农业展览馆', '雍和宫',
  # 任务锚点 / 地铁换乘站
  '东单', '西单', '建国门', '复兴门', '广渠门', '双井', '西直门', '回龙观', '东直门',
  '天通苑北', '天通苑', '天通苑南', '立水桥', '霍营', '北苑', '望京西', '望京', '西二旗',
  '上地', '五道口', '知春路', '大钟寺', '龙泽', '生命科学园', '沙河', '沙河高教园',
  '四惠', '四惠东', '高碑店', '双桥', '管庄', '通州北苑', '果园', '九棵树', '梨园', '土桥',
  '宋家庄', '肖村', '小红门', '旧宫', '亦庄桥', '亦庄文化园', '万源街', '次渠', '荣京东街',
  '中关村', '学院路', '北太平庄', '亚运村', '安定门', '金融街', '三元桥', '巴沟',
  '劲松', '安河桥北', '公益西桥', '新宫', '后沙峪', '南法信', '顺义', '俸伯',
  '海淀五路居', '慈寿寺', '花园桥', '白石桥南', '车公庄西', '平安里', '北海北', '南锣鼓巷',
  '东四', '东大桥', '金台路', '十里堡', '青年路', '常营', '草房', '北运河西', '郝家府', '潞城',
  '张郭庄', '园博园', '大瓦窑', '郭庄子', '西局', '七里庄', '十里河', '草桥', '牡丹园',
  '北土城', '安贞门', '惠新西街南口', '芍药居', '太阳宫', '亮马桥', '农业展览馆', '团结湖',
  '呼家楼', '金台夕照', '大望路', '永安里', '国贸', '王府井', '天安门东', '天安门西',
  '木樨地', '南礼士路', '长椿街', '宣武门', '菜市口', '陶然亭', '马家堡', '角门西',
  '西苑', '圆明园', '海淀黄庄', '人民大学', '魏公村', '国家图书馆', '动物园', '新街口', '西四',
  '灵境胡同', '菜市口', '北京南站', '大屯路东', '北苑路北', '惠新西街北口', '磁器口',
  '广渠门内', '广渠门外', '九龙山', '大郊亭', '七里庄', '郭公庄', '良乡大学城西',
]


def post(query, timeout=300):
    body = urllib.parse.urlencode({'data': query}).encode()
    last = None
    for base in MIRRORS:
        for attempt in range(3):
            req = urllib.request.Request(base, data=body,
                                         headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
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
