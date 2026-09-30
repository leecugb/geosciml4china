# geosciml4china

中国区调图幅 **MapGIS 工程文件夹 → 地质语义标定/解析 → GeoSciML 4.1 转换 → DZ/T 0179-2025 渲染验证** 全链软件包（2026-09-29 全链范围裁定：输入=MapGIS 工程文档文件夹）。

- **标定**（`geosciml4china.calibrate` 渐进迁入 + pymapgis 语义层编排）：先验库驱动（新疆区域界线接触关系先验库=双料最高知识源，随包数据）+ 自支持判别（码义注册表/判据适用域/语义维度三审）；矛盾交人工裁定，永不自动改码。
- **转换**（`geosciml4china.convert`）：六类要素全出站（GeologicUnit / MappedFeature / Contact / ShearDisplacementStructure / Foliation / Fold + 断层产状测量点），全文档过 `geoSciMLExtension.xsd`；Lite 七视图（GeoJSON，含 GeologicSpecimenView 标本视图）。
- **样式**（`geosciml4china.render.stylegen` / `stylegen_fault`）：GeoSciML 地质语义 + DZ/T 0179-2025 统一色库 → 渲染样式文件，图幅特有裁定经 overrides 裁定层固化（生成默认 < 裁定层）。
- **渲染**（`geosciml4china.render`）：薄适配器复用 pymapgis 渲染管线；L1 镜像像素对账；走滑端钩 / 断层产状测量点符号 / 褶皱类型符号 / 编图矛盾警示叠加。
- **验证**（`g4c verify`）：XSD + 29 业务断言 × 三幅实证（库尔干 J43C001002 / 英吉沙 J43C002003 / 奥依亚依拉克 J45C004001）。

## 安装

```bash
pip install -e /d/JWD              # mapgis2shp（pymapgis 语义底座）
pip install -e /d/geosciml4china   # 本包
```

## 图幅项目

一个图幅项目 = 磁盘目录（sheet root），按约定承载 `geojson/L1/`（语义标定层）、
`output/geosciml/`（产出）、`data/` 或根下的图幅级词表映射与裁定层、MapGIS 矢量文件。
包内注册两幅开发图幅（kurgan → D:\JWD；yingjisha → 英吉沙 JWD 目录）。

第三方图幅接入（三选一）：

1. 环境变量：`G4C_ROOT_<KEY>=<图幅根>`；
2. 用户配置 `./geosciml4china.toml` 或 `~/.geosciml4china.toml`：

   ```toml
   [sheets.mysheet]
   root = "/path/to/sheet"
   code = "J43C00XXXX"
   title = "某幅(J43C00XXXX)1:250000建造构造图"
   expected_units = 60
   aux_pairs_csv = "fault_aux_number_XXXX_pairs.csv"
   # …任意 Sheet 字段可覆盖
   ```

3. 代码：`geosciml4china.sheets.register_sheet(Sheet(...))`。

## CLI

```bash
g4c check --sheet kurgan                # 图幅预检：11 文件完整性（规范指定图层，CORE 缺即中止）
g4c pipeline --sheet kurgan             # 全链：MapGIS 文件夹→L0→标定→L1→样式→GML→验证→渲染
g4c sheets                              # 列出已注册图幅与解析后的 root
g4c entities --sheet kurgan             # 断层实体归组（登记册+G2 切截禁并）
g4c auxchain --sheet kurgan             # 辅助点实体链判别（全裁定+最优 1:1 配对）
g4c stylegen --sheet kurgan [--diff]    # 面元样式生成（语义→样式单源）
g4c stylegen-fault --sheet kurgan       # 断层样式生成
g4c build --sheet kurgan [--only gml|lite|pending] [--sample N]
g4c verify --sheet kurgan               # XSD + 业务断言
g4c render --sheet kurgan [--no-overlay] [--check-only]
```

管线序（分步调试时）：**stylegen → build → verify**（render 前 F3 样式动态重生自动兜底；
叠加层=生产默认，`--no-overlay` 关闭）。

## 命名空间闸（A19）

输出标识符当前使用占位域 `geosciml4china.example.org`（`NAMESPACE_FINAL=False`）。
正式域名定后改 `convert/config.py` 单点常量，A19 断言在占位串残留时使构建失败。

## 包数据（随包分发，~4 MB）

GeoSciML 4.1 官方 XSD 树（72 文件，离线校验）· CGI 词表缓存 ·
DZ/T 0179-2025 色库与 SVG 花纹瓦片 · ICS 2020 年代表。
**图幅数据永不入包**（数据权属规避）。

## 许可

Apache-2.0。
