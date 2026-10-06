# geosciml4china 示例

四个可运行示例，按典型工作流排序。全部可用 `python <脚本> --help` 查看参数。

| 脚本 | 内容 | 依赖 |
|------|------|------|
| `01_onboard_and_run.py` | 零注入接入：一步式注册 + 全链（可选渲染） | pymapgis 完整栈 |
| `02_inspect_calibration.py` | 标定件检查：裁决分布/置信带/冲突登记册摘要 | pandas（已标定图幅） |
| `03_modify_reconvert_loop.py` | 修改-再转化回路：编辑映射表 user_semantic → 重跑标定域 | pymapgis 完整栈 |
| `04_read_geosciml.py` | GeoSciML 读取：GML 成员计数/断层类型分布/XSD 校验 | lxml（已构建图幅） |

## codebook（编码-地质语义映射表）

校准完成后管线产出 `codebook_<key>.json`（**这个 JSON 就是 codebook**）：
用户可直接编辑其中任何码的 `user_semantic`/`user_note` 字段（跨轮保留），
然后仅重跑 `g4c build`（无需重跑校准）——后续 GeoSciML 转换建立在
codebook 上（权威序：图幅注册表 > 用户编辑 > 全局先验 > 校准推导）。

```bash
g4c codebook --sheet mykey      # 重新生成 + 摘要
# 编辑 codebook_mykey.json 后：
g4c build --sheet mykey && g4c verify --sheet mykey
```

## 快速开始（零注入接入）

```bash
# CLI 路径
g4c probe --root D:/my-sheet --key mykey --register
g4c pipeline --sheet mykey --accept-portrait

# Python API 等价（见 01_onboard_and_run.py）
python examples/01_onboard_and_run.py --root D:/my-sheet --key mykey
```

## 完整栈要求

标定域与全链需要 pymapgis 完整栈（semantics/rendering 子包，本地安装）；
PyPI 极简环境（仅 mapgis2shp 读取器）可运行 `04_read_geosciml.py` 与
纯逻辑测试。
