"""包数据访问（importlib.resources）。

随包分发的标准资产（与图幅数据正交——图幅数据永不入包）：

- ``geosciml_xsd/``            GeoSciML 4.1 官方 XSD 树（72 文件，离线校验）
- ``cgi_vocab_terms.json``     CGI 词表术语缓存（SPARQL 抓取快照）
- ``cgi_vocabs_current/``      当前用 CGI 词表 JSON（simplelithology/foliationtype…）
- ``dzt0179_color_library.json``  DZ/T 0179-2025 地质图用色标准色库
- ``dzt0179_patterns/``        DZ/T 0179 花纹 SVG 瓦片 + 注册表
- ``ics_2020_eras.json``       ICS 2020 国际年代地层表

注意：本包按文件系统安装形态（pip install / pip install -e）设计，
``files()`` 直接返回真实路径；不支持 zip 内运行（XSD 校验器需要真实目录）。
"""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_PKG = "geosciml4china"


def data_path(rel: str = "") -> Path:
    """包数据根/子路径的真实文件系统路径。"""
    base = files(_PKG) / "data"
    p = base if not rel else base.joinpath(*rel.split("/"))
    return Path(str(p))


def xsd_root() -> Path:
    """GeoSciML XSD 树根（离线校验；不存在则 FileNotFoundError）。"""
    p = data_path("geosciml_xsd")
    if not p.is_dir():
        raise FileNotFoundError(f"GeoSciML XSD tree missing from package data: {p}")
    return p


DZT0179_COLOR_LIBRARY = data_path("dzt0179_color_library.json")
DZT0179_PATTERN_REGISTRY = data_path("dzt0179_patterns/patterns.json")
CGI_TERMS = data_path("cgi_vocab_terms.json")
CGI_VOCABS_DIR = data_path("cgi_vocabs_current")
ICS_ERAS = data_path("ics_2020_eras.json")
