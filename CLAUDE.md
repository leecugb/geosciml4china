# geosciml4china 项目指引

中国区调图幅 MapGIS→GeoSciML 4.1 转换·DZ/T 0179-2025 语义样式·渲染·验证包。

## 单源纪律（2026-09-28 起）

- **本包是唯一正典源**。D:\JWD 下的 `geosciml/` 与 `geosciml_render/` 是冻结历史副本，
  禁止再编辑；JWD 驱动脚本（build_geosciml.py 等）切换前仍消费冻结副本。
- 产出文件（style JSON 等）内嵌元数据串仍含旧包名（`geosciml_render/stylegen.py` 等）——
  为保双幅逐字节一致刻意保留，更名须同步重生成并对账。

## 布局

```
src/geosciml4china/
  sheets.py    图幅注册表（唯一图幅参数源；env G4C_ROOT_<KEY> > *.toml > 包内默认）
  data.py      包数据 accessor（XSD 树/CGI 词表/DZ-T 色库+SVG 花纹/ICS，~4MB 随包分发）
  cli.py       g4c 入口（sheets/data/stylegen/stylegen-fault/build/verify/render）
  convert/     MapGIS·L1 → GeoSciML GML + Lite 六视图（含 build.py/verify.py 驱动）
  render/      语义→样式（stylegen/stylegen_fault）→ 渲染 + L1 镜像核验
tests/         冒烟（28 项；图幅数据缺失机器自动跳过图幅用例）
```

## 关键契约

- `convert.config`：消费方读模块常量（`config.GML_OUT` 等），`init_sheet(key)` 切换图幅；
  常量来自 sheets 注册表，包内零路径硬编码。
- 图幅项目 = 磁盘目录：`geojson/L1/` + `output/geosciml/` + `data/或根下的裁定层/登记册`。
- 管线序：**stylegen → build → verify**；render 前 F3 样式动态重生自动兜底。
- 命名空间占位 `geosciml4china.example.org`（NAMESPACE_FINAL=False；A19 闸控替换，单点 config）。
- 产出 GML/lite 必须保持可复算：任何改动后跑 `g4c build --sheet kurgan|yingjisha` +
  `g4c verify` 双幅全绿，并与基线对 sha256。

## 环境

- Python：`C:\ProgramData\anaconda3\python.exe`（PATH 上的 python 是 Store 占位 stub）。
- 依赖：`mapgis2shp>=2.2.1`（import 名 pymapgis；本地 editable：pip install -e /d/JWD）。
- Windows 控制台 GBK：用户可见输出避免 ✓/✗ 等字形（或 PYTHONIOENCODING=utf-8）。
