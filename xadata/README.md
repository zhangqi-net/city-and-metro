# 西安地图数据流水线（`xadata/`）

生成 `js/geo_xa.js`（底图）与 `js/data_xa.js`（场景规则）的数据来源与复现步骤。
结构沿用 `bjdata/`（北京），参数改为西安。

## 范围与投影

| 项 | 值 |
|---|---|
| 左上原点 | 东经 **108.790°**、北纬 **34.410°** |
| 网格 | `W = 120`、`H = 120`，每格 250 m → 约 30 × 30 km（绕城高速以内） |
| 投影系数 | `kx = 368.05` 格/度（经度，按纬度 34.27° 余弦修正）、`ky = 445.28` 格/度（纬度） |
| 覆盖 | 绕城高速（G3002）以内：西至后卫寨 / 三桥，东至纺织城 / 灞河，北至西安北站 / 未央湖，南至韦曲南 / 航天新城 |
| 图外 | 咸阳机场、西咸新区 / 创新港、临潼秦陵西、高陵昭慧广场、鄠邑户县、常宁宫（任务锚点改用图内方向站点；机场以西北角接驳点近似） |

坐标一律 **WGS-84**（OSM）。国内地图的 GCJ-02 坐标与底图有数百米偏差，禁止照抄。

## 网络说明（重要）

2026-11-19 用户新增本地代理后重新实测，结论更新如下。

### 代理与路径

| 路径 | 说明 |
|---|---|
| `127.0.0.1:55774` | WorkBuddy 沙箱注入的 `HTTP_PROXY` 环境变量；对 Overpass 返回 502，不用 |
| `127.0.0.1:1087` | 系统 HTTP/HTTPS 代理（新增）；**OSM 官方 API 3 s 返回**，Overpass 约 40 s 可用 |
| `127.0.0.1:1080` | SOCKS5 代理（新增）；效果同 1087 |
| 直连 | `ProxyHandler({})` 绕过代理；`overpass-api.de` 约 31 s 可用，最快 |

### 数据源实测（新环境，超时设 78–80 s 避免误判）

| 源 | 直连 | 1087 / SOCKS |
|---|---|---|
| `api.openstreetmap.org/api/0.6/map` | 超时 | **3–20 s 返回完整 OSM XML** |
| `overpass-api.de` | 31 s / 31 要素 | 30–40 s / 31 要素 |
| `overpass.private.coffee` / `kumi.systems` | 78 s 超时 | 78 s 超时 |
| `overpass.osm.ch` | 1 s / 200 但 **0 要素**（仅欧洲） | 非 JSON |
| `www.openstreetmap.net.cn` | 首页 200 | 首页 200 |
| `osm.open.cn` / `overpass.openstreetmap.net.cn` | 502 | 502 |
| `download.geofabrik.de` | 超时 | 超时 |

`www.openstreetmap.net.cn` 是静态介绍站：下载页没有任何真实数据链接，所有 API / 子域名 404 或 502，
`robots.txt` 也只是通用声明，不能作为数据源。

### 两条抓取通道（混合使用）

1. **`fetch_osm.py`（官方 /map，优先）**：走 1087 代理按 4×4 分块拉**全量 OSM 要素**，
   一次请求即含全部道路 / 水系 / 绿地 / 铁路 / 地名，比 Overpass 分组查询更快更全；
   XML 转成 Overpass-like JSON（`way` 带 `geometry`），`extract.py` 可直接消费。
   官方 `/map` 有 **50000 节点上限**，密集城区自动 2×2 细分；累计下载约 88 MB 后会触发
   `You have downloaded too much data. Please try again in N seconds` 下载配额限流，此时切通道 2。
2. **`fetch.py`（Overpass 分组）**：只查目标 tag，按 road / green / rail 三组分别缓存，
   单组 30–80 s、间歇 502 重试一次即过；**不要并发**（实测 6 并发触发 `429`）。用于补齐限流期间未完成的分块。

`slim_tiles.py` 把官方全量 tile（86.7 MB）按 `extract.py` 实际消费的 tag 精简到 15.3 MB，
避免 `json.load` 吃内存；原文件备份到 `backup_overpass/full/`。旧 Overpass 分片归档在 `backup_overpass/shards/`。

其余结论不变：
- `overpass.osm.ch` 只有欧洲数据，已排除。
- 曾测试把正则匹配改为等值索引查询：结果集合完全一致但更慢（94.6 s vs 61.3 s），
  说明瓶颈是服务器排队而非查询写法，故保留正则写法。
- 高德地图 Web 服务 API 无法替代本流水线：它只提供 POI 点位、行政区界 polyline 与路径规划折线，
  **不提供**全量道路网 / 河湖水系 / 公园林地 / 铁路的矢量几何；且 GCJ-02 坐标与本图 WGS-84 冲突。详见 `西安地铁史实.md` 第五节。

## 脚本

| 脚本 | 作用 |
|---|---|
| `fetch.py` | 4×4 分块抓水系/道路/铁路/绿地 → `tile_*.json`；另抓 `admin.json`（区/街道界）、`place.json`（地名）、`poi.json`（站场/机场/大学）、`mstations.json`（车站节点）。支持断点续传，重跑会跳过已存在文件 |
| `fetch_osm.py` | **新通道**：走 1087 代理用官方 `/api/0.6/map` 拉全量 OSM 要素 → `tile_i_j.json`（转 Overpass-like JSON）；超 5 万节点自动细分、断点续传；触发下载配额限流时改用 `fetch.py` 补剩余块 |
| `slim_tiles.py` | 把官方全量 tile 按 `extract.py` 实际消费的 tag 精简（86.7 MB → 15.3 MB），原文件备份到 `backup_overpass/full/` |
| `grab_coords.py` | 单独抓地铁车站节点与关键 POI 坐标 → `xacoords.json`（供 `data_xa.js` 校准） |
| `extract.py` | 合并分块、拼接关系多边形 → `features.json`（与 `szdata/` 同结构） |
| `build_geo.py` | `features.json` → `js/geo_xa.js`（墨卡托近似投影、增量 zigzag 编码、1/64 格精度），同时写 `/tmp/geo_xa.json` 便于预览 |
| `gen_stations.py` | 从 `mstations.json` 按名称查站点经纬度并给出格坐标 |
| `gen_places.py` | 按名称批量查 POI 经纬度 → `places.json` |
| `smoke.js` / `simtest.js` / `prof.js` | 冒烟（区域/锚点/地标）、出行模型推进、分阶段耗时剖析；起始年读地图 `cfg.START.y` |

复现顺序：

```bash
cd xadata
python3 -u fetch_osm.py      # 优先：官方 /map 全量通道（需 1087 代理）
python3 -u fetch.py          # 限流时补齐剩余分块（Overpass 分组）
python3 slim_tiles.py        # 精简全量 tile
python3 extract.py
python3 build_geo.py
node smoke.js
node simtest.js 2026
```

依赖：`python3` + `opencc`（繁转简）+ `shapely`；`node`（测试脚本）。

## 史实与来源

- `西安地铁史实.md`：维基百科《西安地铁》（2026-11-18 `action=raw`）建设简史、路线表、在建规划；西安市统计局 2006 年统计公报。
- 地理数据：© OpenStreetMap 贡献者，ODbL，见 `THIRD_PARTY_NOTICES.txt`。

场景为 **2006-01-01 空网起步**（西安地铁 2006-09-13 才获国家批准、2011-09-16 首条线通车），
地名统一用当前名称；2006 年之后的真实线路不会自动出现，仅通过历史事件与参考任务给出。
人口、就业、造价、票价、设施规模均为**估算**，不代表真实统计。
