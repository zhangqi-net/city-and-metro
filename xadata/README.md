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

本机 `HTTP_PROXY`/`HTTPS_PROXY` 对 Overpass 返回 502，
所有抓取脚本用 `urllib.request.build_opener(ProxyHandler({}))` **绕过代理直连**。

- `overpass.osm.ch` 响应快但**只有欧洲数据**（北京 bbox 查询同样返回 0 要素），已排除。
- `overpass-api.de` 直连可用，单块约 60–180 s，间歇 502。
- `overpass.private.coffee` 实测可用（约 79 s 响应，返回真实西安数据），作为备用。
- `kumi.systems` / `osm.jp` / `openstreetmap.ru` / `nchc.org.tw` 直连超时或域名不可达，不用。
- `fetch.py` 按「8 次重试 × 2 镜像逐次交替」容错；**不要并发**抓取，实测 6 并发会触发 `429 Too Many Requests`。
- 曾测试把正则匹配改为等值索引查询：结果集合完全一致，但耗时反而更慢（94.6 s vs 61.3 s），
  说明瓶颈是服务器排队而非查询写法，故保留原正则写法。
- 高德地图 Web 服务 API 无法替代本流水线：它只提供 POI 点位、行政区界 polyline 与路径规划折线，
  **不提供**全量道路网 / 河湖水系 / 公园林地 / 铁路的矢量几何；且 GCJ-02 坐标与本图 WGS-84 冲突。详见 `西安地铁史实.md` 第五节。

## 脚本

| 脚本 | 作用 |
|---|---|
| `fetch.py` | 4×4 分块抓水系/道路/铁路/绿地 → `tile_*.json`；另抓 `admin.json`（区/街道界）、`place.json`（地名）、`poi.json`（站场/机场/大学）、`mstations.json`（车站节点）。支持断点续传，重跑会跳过已存在文件 |
| `grab_coords.py` | 单独抓地铁车站节点与关键 POI 坐标 → `xacoords.json`（供 `data_xa.js` 校准） |
| `extract.py` | 合并分块、拼接关系多边形 → `features.json`（与 `szdata/` 同结构） |
| `build_geo.py` | `features.json` → `js/geo_xa.js`（墨卡托近似投影、增量 zigzag 编码、1/64 格精度），同时写 `/tmp/geo_xa.json` 便于预览 |
| `gen_stations.py` | 从 `mstations.json` 按名称查站点经纬度并给出格坐标 |
| `gen_places.py` | 按名称批量查 POI 经纬度 → `places.json` |
| `smoke.js` / `simtest.js` / `prof.js` | 冒烟（区域/锚点/地标）、出行模型推进、分阶段耗时剖析；起始年读地图 `cfg.START.y` |

复现顺序：

```bash
cd xadata
python3 -u fetch.py          # 断点续传，失败块重跑即可
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
