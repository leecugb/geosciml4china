# testdata 项目（geosciml4china 全链测试数据）

**MapGIS 源文件（11 个）**，来自 `D:/testdata` 的 1:25 万测试幅小图幅——
发布目的：作为 geosciml4china 的**全链端到端测试项目**（含 MapGIS→L0
转换步骤，与 `data/jws_l0_geojson/` 的 L0-only 测试用例互补）。
发布批准：数据持有者（用户）2026-10-05。

## 数据画像（L0 普查实测）

| 图层 | 要素数 | 说明 |
|---|---|---|
| LDZOFBB001.WP | 86 面元（含 1 个无代号残余面 row 42） | 沉积岩建造 |
| LDZOFBB002.WP | 7 | 火山岩性岩相 |
| LDZOFBB003.WP | 9 | 侵入岩 |
| LDZOFBB004.WP | 6 | 变质岩建造 |
| LDZOFBA002.WL | 353 界线（含 6 段零长度 GZBD=02） | 地质界线 |
| LDZOFBA003.WL | 52 | 断裂 |
| LDZOFBA016.WT | 23 | 产状 |
| LDZOFBA005.WL | 2 | 褶皱 |
| LDZOFBB099.WT | 208 | 注记（断层辅助点×20：1894×8/1281×4；化石×3） |

单元 21 原码（norm 归一后 20）；中心纬度 39.3N；11 文件 preflight 契约全过
（CORE 缺 0）。

## 注册与运行

profile 键 `td`（pymapgis.semantics.profile.PROFILES 已注册——
aux_filter=断层辅助点、b=1894、零信息接入普查值）。

```toml
[sheets.td]
root = "D:/testdata"   # 或本目录的本地路径
code = "J43T000001"
title = "testdata 项目零信息接入测试"
aux_pairs_csv = "fault_aux_number_1894_pairs.csv"
aux_assoc_csv = "fault_aux_td.csv"
aux_triplets_csv = "_fault_triplets_td.csv"
calibration_csv = "_gzbd_calibration_report.csv"
lite_expect_counts = [107, 143, 52, 23]
```

```bash
g4c pipeline --sheet td     # 全链；verify 期望 29/29（画像已注册于 verify.py EXPECT["td"]）
```

## 测试特性（本数据集刻意覆盖的泛化形态）

- **空码面元**（LDZOFBB001 row 42）——build 空码剔除案例
- **零长度界线**（6 段 GZBD=02）——未标定剔除+mirror 双侧对齐案例
- **小图幅**——端到端运行约 3-5 分钟，适合作为快速全链冒烟
