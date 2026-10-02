# jws L0 GeoJSON（库尔干幅 J43C001002 全管线测试副本）

本目录为 **jws 测试幅**（库尔干幅 J43C001002 副本，全管线测试）的 **L0 级
GeoJSON**——geosciml4china 解析链的 11 文件完整性契约（preflight CORE+
CONDITIONAL）对应的转换产物。

## 管线位置

```
MapGIS 6.x 矢量（.WL/.WT/.WP）
  → convert（MapGIS → L0 GeoJSON，EPSG:4326）
  → 自支持地质语义判别解析（六标定域）
  → L1 语义 GeoJSON
  → GeoSciML（GML + lite 视图）
  → 语义渲染
```

本目录 = 上述链第一步的输出（L0）。

## 文件清单（11 文件契约）

| 文件 | 要素 | 契约 |
|---|---|---|
| LDLYAAE001.WL.geojson | 水系（线） | CONDITIONAL 1143 |
| LDLYAAE002.WP.geojson | 水系（面） | CONDITIONAL 128 |
| LDZOFBA002.WL.geojson | 地质界线 | CORE 2222 |
| LDZOFBA003.WL.geojson | 断层线 | CORE 310 |
| LDZOFBA005.WL.geojson | 褶皱线 | CONDITIONAL 4 |
| LDZOFBA016.WT.geojson | 产状要素 | CORE 305 |
| LDZOFBB001.WP.geojson | 地层 | CORE 608 |
| LDZOFBB002.WP.geojson | 火山岩 | CONDITIONAL 10 |
| LDZOFBB003.WP.geojson | 侵入岩 | CONDITIONAL 46 |
| LDZOFBB004.WP.geojson | 变质岩 | CONDITIONAL 49 |
| LDZOFBB099.WT.geojson | 注记（含断层辅助点） | CORE 2024 |

## 备注

- 坐标系：EPSG:4326（WGS84 经纬度）；
- 数据源：库尔干幅（J43C001002）1:25 万建造构造图 MapGIS 工程副本；
- 生成工具：`pymapgis` Reader（geosciml4china 管线 preflight→convert）；
- L1 语义层与 GeoSciML 产物不在此目录（解析输出见对应图幅项目根）。
