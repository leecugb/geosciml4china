# 处理域契约（11 文件）逐层对照实证（2026-09-29）

**契约（用户裁定）**：geosciml4china 只处理 11 个 MapGIS 文件——面元×4（LDZOFBB001/002/003/004.WP）、
水系面/线（LDLYAAE002.WP / LDLYAAE001.WL）、地质界线（LDZOFBA002.WL）、褶皱轴（LDZOFBA005.WL）、
断层（LDZOFBA003.WL）、断层辅助点/化石/泥火山（LDZOFBB099.WT 三主题同源）、产状（LDZOFBA016.WT）。
机器可读契约：`geosciml4china/scope.py`（SCOPE_FILES + THEME_SOURCES）。

## 1. L1 主题 ← 源文件溯源（四幅实测）

| L1 主题 | 契约源文件 | 库尔干 | 英吉沙 | 奥依亚依拉克 | 巴什库尔干 |
|---|---|---|---|---|---|
| polygons | BB001-004 | 713（608/10/46/49）✓ | 808（524/1/192/91）✓ | 543（417/–/110/16）✓ | 403（72/–/151/180）✓ |
| waterpoly | LDLYAAE002 | 128 ✓ | 204 ✓ | 80 ✓ | —（本幅无此文件，不入域） |
| waterline | LDLYAAE001 | 1143 ✓ | 1345 ✓ | 516 ✓ | 1 ✓ |
| boundaries | LDZOFBA002 | 2222 ✓ | 2541 ✓ | 1538 ✓ | 1036 ✓ |
| fold | LDZOFBA005 | 4 ✓ | 7 ✓ | 60 ✓ | 10 ✓ |
| faults | LDZOFBA003 | **310 ✓** | **289 ✓**（两幅纯 FBA003 与契约注记一致） | 341 ✓ | 213 ✓ |
| fault_aux | LDZOFBB099 | 299 ✓ | 438 ✓ | 159 ✓ | 38 ✓ |
| fossil | LDZOFBB099 | 27 ✓ | 40 ✓ | 20 ✓ | —（本幅无化石类别） |
| mudvolcano | LDZOFBB099 | 21 ✓（仅库尔干，契约一致） | — | — | — |
| attitude | LDZOFBA016 | 305 ✓ | 165 ✓ | 406 ✓ | 262 ✓ |

注：boundaries/attitude 的 L1 紧凑模式不内化 `_src_file` 列——单源由 materialize 单文件
读取的构造保证 + **L0↔L1 计数对账**（四幅 boundaries/attitude 计数全等：2222/2541/1538/1036
与 305/165/406/262）双重证明。

## 2. 反向核查（契约外文件零进入）

- materialize 全源清单 = BB001-004 + LDLYAAE001/002 + FBA002/003/005/016 + BB099
  ≡ 契约 11 文件，无第十二个；
- 转换（build）只读 L1 主题；stylegen 只读 BB001-004 WP + lite 视图；
- 契约外文件（LFZY 火山/剖面、LZLPGDJ 深部、LYGREBA 遥感推断、LHCPGDAC/LHTQGTA 化探、
  FBA008 同位素、BB008/009/010/011、火山岩性岩相.WP 等）在四幅产品中零出现。

## 3. 发现并修复的契约偏差

**R-W1［已修复］水系双层在 GeoSciML 渲染中缺失。**
契约含水系面（zorder 5）/水系线（zorder 9），但 Lite 视图不含水系（非 GeoSciML 地质要素）
→ 包渲染此前缺水系。修复：lite 新增两个**渲染支撑视图**（`waterline_view`/`waterpoly_view`，
L1 直通、不改几何轴序、明确标注非 GeoSciML 标准视图），map_builder 注册 zorder 5/9，
空主题幅写空集合（巴什库尔干 waterpoly=0）。四幅 lite 重出：既有七视图 14/14 逐字节不变
（库尔干/英吉沙回归），水系新增 1143+128 / 1345+204 / 516+80 / 1+0。

## 4. 结论

11 文件契约成立且全链严格执行：输入侧恰好 11 文件（无越界读取），主题溯源逐层实证，
唯一偏差（水系渲染缺失）已修复并双幅回归无害。
