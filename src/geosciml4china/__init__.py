"""geosciml4china —— 中国区调图幅 MapGIS→GeoSciML 4.1 转换·样式·渲染·验证包。

子包：
- ``convert``  MapGIS/L1 语义层 → GeoSciML GML + Lite 六视图；
- ``render``   GeoSciML 产物 → DZ/T 0179-2025 样式生成 → 渲染 + 镜像验证；
- ``calibrate`` 九域自支持地质语义标定（gzbd/entities/auxchain/gzeeb/…）。

顶层 API：
- ``onboard(root, key, title=None, code=None)``  零注入接入一步式注册；
- ``pipeline.run_pipeline(key, ...)``            全链编排（CLI g4c pipeline 同源）。

图幅参数：``geosciml4china.sheets``（注册表+用户 TOML+环境变量）；
标准资产：``geosciml4china.data``（XSD/CGI 词表/色库/花纹/ICS，随包分发）。
示例：``examples/``（零注入接入/标定件检查/修改-再转化/GeoSciML 读取）。
"""

__version__ = "0.1.1"

# 顶层 API（模块级导入安全：pipeline/probe 的 pymapgis 依赖均在函数内懒装载，
# PyPI 极简环境下 import geosciml4china 照常可用，仅调用管线函数时自然报错）
from . import pipeline, probe  # noqa: E402
from .probe import onboard  # noqa: E402

__all__ = ["onboard", "pipeline", "probe"]
