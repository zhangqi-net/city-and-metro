# 北京地图的生成脚本

`js/geo_bj.js` 与 `js/data_bj.js` 里的地理部分由这里的脚本生成；年代表（区域开放、道路通车、地标落成、人口与造价）是人工整理的数据，写在 `js/data_bj.js` 里。

坐标约定：格 250 m，左上角原点 `lon0 = 116.160, lat0 = 40.0874`，`kx = 341.66, ky = 443.84`，地图 `W = 160, H = 132`（W、H 必须是 `CFG.ZONE = 4` 的整数倍）。

## 重新生成

```bash
python3 fetch.py        # 分块从 Overpass 抓取水系/道路/铁路/绿地 + 行政区界/地名/站场（约 25 分钟，支持断点续传）
python3 extract.py      # 合并分块、拼接关系多边形 → features.json
python3 build_geo.py    # 投影、简化、编码 → ../js/geo_bj.js
```

依赖：`shapely`、`opencc`（`pip3 install opencc-python-reimplemented`）。

北京是内陆城市，没有海岸线，因此不需要 `make_sea.py`；河流与湖泊直接由 OSM 的 `natural=water` / `waterway` 要素得到。

## 验证脚本（不需要浏览器）

```bash
node smoke.js 2026      # 生成地图、区域统计、逐年推进、任务锚点检查
node simtest.js 2026    # 按月推进人口 → 建出行模型 → 全网拥堵与主要道路 v/c
```

## 来源与日期

- 地理：OpenStreetMap（© OpenStreetMap 贡献者，ODbL），按 250 m 网格投影，地名转简体。
- 开局既有地铁：1 号线苹果园—复兴门 12 站（1971 通车）、2 号线环线 18 站（1984 开通西北段、1987-12 成环）。
- 区域开放年份、道路通车年份、地标落成年份、车站与机场启停年份为史实参考（位置与范围近似）。
- 人口就业分布、增长曲线、造价、票价与设施规模为估算；2026 年 10 月之后为模拟。
