# HSAP 车队地图（演示 / T-Box）

## 功能

- 实时查看采集车位置与当前趟次轨迹（**默认高德栅格底图**，国内可访问；可选 `AS_MAP_TILE_PROVIDER=osm`）
- 演示环境默认注入 3 台**长沙**周边假车（湘A），轨迹由贝塞尔曲线密点生成（弯道而非直线折线），后台每 8 秒模拟 T-Box 推进

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `AS_FLEET_MAP_ENABLED` | `1` | 启用车队 API |
| `AS_FLEET_MOCK_SEED` | `1` | 首次启动无车辆时注入演示数据 |
| `AS_FLEET_MOCK_SIMULATE` | `1` | 后台模拟 GPS 推进 |
| `AS_FLEET_SIM_INTERVAL_SEC` | `8` | 模拟间隔秒 |
| `AS_TBOX_INGEST_TOKEN` | `hsap-demo-tbox-token` | T-Box 上报 Token |
| `AS_MAP_TILE_PROVIDER` | `gaode` | 底图：`gaode` / `osm`（国内勿用 osm，易灰屏） |
| `AS_AMAP_KEY` | 空 | 高德 Web JS Key（可选，后续 AMap API） |

## T-Box 与车辆关联（无需页面「新建车辆」）

关联键是 **`device_id`**（入库字段 `tbox_device_id`）：

1. 运维在 T-Box / 采集机配置 HSAP 上报地址与 `X-Tbox-Token`（环境变量 `AS_TBOX_INGEST_TOKEN`）。
2. 终端首次 `POST /api/v1/tbox/gps` 时，若该 `device_id` 不存在，平台**自动创建**车辆记录（可用 body 里的 `plate_no` 填车牌）。
3. 后续同一 `device_id` 的点写入当前 active 行程；`run_signal=end/idle` 时结束行程。

可选 body 字段：`plate_no`、`engineer`、`project`、`batch`、`speed_kmh`、`heading`、`ts`。

Web 页仅用于查看地图、改车牌备注、GPX 补录；**不需要**手工新建车辆。

## T-Box 上报示例

```bash
curl -X POST http://127.0.0.1:8787/api/v1/tbox/gps \
  -H "Content-Type: application/json" \
  -H "X-Tbox-Token: hsap-demo-tbox-token" \
  -d '{"device_id":"TBOX-001","lat":22.72,"lng":114.25,"speed_kmh":40,"run_signal":"active","plate_no":"湘A·采集01"}'
```

## 手动重播种 / 推进

需登录且具备 `write:fleet`（工程师/管理员）：

- `POST /api/v1/fleet/mock/seed` — 仅在无车辆时创建演示数据
- `POST /api/v1/fleet/mock/reseed` — 清空并重新注入长沙演示数据
- `POST /api/v1/fleet/mock/tick` — 手动推进一轮模拟 GPS

切换区域后重新注入：

```bash
curl -X POST http://127.0.0.1:8787/api/v1/fleet/mock/reseed \
  -H "Authorization: Bearer <你的 token>"
```

## Phase 2 API（生产化）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tbox/gps/batch` | 批量上报（最多 100 点），body `{"points":[...]}` |
| GET | `/api/v1/fleet/stream` | SSE 推送 `fleet.gps`（需 Redis + JWT） |
| POST | `/api/v1/fleet/runs/import-csv` | CSV 补录：`lat,lng` 或带表头 `lat,lng,ts`；可选 `project`/`batch` 关联 DMS 批次 |

**超时关趟：** 车辆超过 10 分钟无新 GPS（`RUN_IDLE_TIMEOUT_MIN`）时，`/fleet/live` 与 ingest 前会自动结束 active 行程。

## GPX 轨迹补录

需 `write:fleet`：

```bash
curl -X POST http://127.0.0.1:8787/api/v1/fleet/runs/import-gpx \
  -H "Authorization: Bearer <token>" \
  -F vehicle_id=1 \
  -F file=@track.gpx
```

前端车队页侧栏也可选择车辆上传 `.gpx` 文件。

## 前端

导航 **车队地图**（权限 `read:fleet`），页面每 15 秒轮询 live；选中行程显示里程与里程碑，地图红色点为里程碑。
