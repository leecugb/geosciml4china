# 全链范围裁定（2026-09-29，用户裁定）

> 「geosciml4china 的输入是 MapGIS 工程文档（文件夹），它完成对 MapGIS 地质语义的
> 标定、解析，及后续的转换和渲染功能。」

## 架构分层

```
MapGIS 工程文件夹（sheet root）
  │  ① convert_sheet            MapGIS 原生 → geojson/L0（pymapgis，格式层）
  │  ② calibrate_semantics      L0 + 先验/裁定登记 → 标定阶段链 → geojson/L1
  │     （pymapgis 编排器 + geosciml4china.calibrate 标定规则库——渐进迁入）
  │  ③ stylegen / stylegen_fault 语义→样式（DZ/T 0179-2025 色库，包）
  │  ④ build                    L1 → GeoSciML GML + Lite 七视图 + pending（包）
  │  ⑤ verify                   XSD + 业务断言（包）
  │  ⑥ render                   渲染 + L1 镜像核验（包）
```

- **先验库随包**：`data/boundary_contact_priors.json`（新疆区域界线接触关系先验库，
  双料最高知识源主本）迁入包数据 `geosciml4china/data/`；图幅扩展册通道 =
  `<sheet_root>/data/boundary_contact_priors_<key>.json`（裁定追加，合并装载）。
  JWD 冻结侧副本供未迁移脚本消费，切换后单源化（防分叉登记在案）。
- **标定脚本迁移路线**（逐域、影子先行、双幅逐字节复现为准入闸）：
  gzbd（界线，P-GAP-1 急迫）→ gzeeb（断层三维+活动性先验）→ attitudes → fossils →
  aux 链（association/pairs/triplets/entities，库尔干 v5+英吉沙变体归一）。
  未迁移阶段由编排器照旧跑 profile `l1_stages` 列出的既有脚本——全链今天即可跑通。
- **码义随幅**：标定规则入包=规则通用化；图幅特异值（char_dists/remap/豁免集/码义册）
  留在图幅剖面/登记册，规则代码零图幅分支。

## CLI

`g4c pipeline --sheet <key> [--skip-convert] [--skip-calibrate-stages] [--skip-render] [--check-only]`
