# 深圳地图的生成脚本

`js/geo_sz.js` 与 `js/data_sz.js` 里的地理部分由这里的脚本生成；年代表（区域开放、道路通车、地标落成、人口与造价）是人工整理的数据，写在 `js/data_sz.js` 里。

坐标约定：格 250 m，左上角原点 `lon0 = 113.744, lat0 = 22.722`，`kx = 409.6, ky = 443.0`，地图 `W = 212, H = 100`（W、H 必须是 `CFG.ZONE = 4` 的整数倍）。

## 重新生成

```bash
python3 fetch.py        # 下载广东省 OSM PBF（约 1.6 GB，可跳过：自行准备 guangdong.osm.pbf）
python3 extract.py      # 裁剪深圳范围 → features.json；顺带把 G2518 深岑高速的东段改名为「深中通道」
python3 make_sea.py     # 由海岸线洪水填充生成海面多边形 → sea.json
python3 build_geo.py    # 投影、简化、编码 → ../js/geo_sz.js
```

依赖：`pyosmium`、`numpy`、`scikit-image`、`opencc`。

## 验证脚本（不需要浏览器）

```bash
node smoke.js 2026      # 生成地图、区域统计、填海前后、深中通道、任务锚点、逐年推进
node simtest.js 2026    # 按月推进人口 → 建出行模型 → 全网拥堵与主要道路 v/c
```

## 截图脚本（需要本机 Chrome）

```bash
node shoot.js out.png sz 12000               # 开局截图
CAM=134,77,13 VIEW=1 node shoot.js out.png   # 指定镜头与视图（0 = 平面，1 = 2.5D）
FORCEYEAR=2026 node shoot.js out.png         # 直接把地形与人口推到 2026 年
```

原始 PBF 与 `features.json` 体积过大，已在 `szdata/.gitignore` 中排除；`shots/` 同理。
