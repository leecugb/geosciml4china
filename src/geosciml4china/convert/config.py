"""GeoSciML conversion pipeline configuration (sheet-registry driven).

消费契约（自 J43C001002 库尔干幅管线起未变）：各模块以 `config.X` 读取
模块常量；`init_sheet(key)` 在 build/verify 入口切换图幅参数集（重指向
模块常量）。本实现自 **geosciml4china.sheets 注册表**取图幅参数——
包内零路径硬编码（图幅 root 由注册条目/用户 TOML/环境变量解析），
标准资产（XSD/CGI 词表/ICS 年代表）走 **geosciml4china.data 包数据**。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..data import CGI_TERMS as _PKG_CGI_TERMS
from ..data import CGI_VOCABS_DIR as _PKG_CGI_VOCABS
from ..data import ICS_ERAS as _PKG_ICS_ERAS
from ..data import xsd_root as _pkg_xsd_root
from ..sheets import get_sheet

# --- Identity（命名空间恒量；正式域名替换的唯一闸） ---------------------------
CODE_SPACE = "http://www.ietf.org/rfc/rfc2616"
NIL_URI = "http://www.opengis.net/def/nil/OGC/0/unknown"
# When a final public namespace is assigned, set NAMESPACE_FINAL=True and
# replace NAMESPACE_PLACEHOLDER — assertion A19 fails the build while the
# placeholder string is still present anywhere in the output.
NAMESPACE_FINAL = False
NAMESPACE_PLACEHOLDER = "geosciml4china.example.org"

MAPPING_FRAME_TERM = "surface_geology"
MAPPING_FRAME_URI = (
    "http://resource.geosciml.org/classifier/cgi/mappingframe/surface_geology"
)

# --- CGI URI helpers ---------------------------------------------------------
CGI_CLASSIFIER = "http://resource.geosciml.org/classifier/cgi"
CGI_ICS = "http://resource.geosciml.org/classifier/ics/ischart"
INSPIRE_FOLD_URI = "http://inspire.ec.europa.eu/codelist/FoldProfileTypeValue"

PRECISION = 14  # decimal places emitted for coordinates

# --- 包数据（图幅无关标准资产，常量化不随 init_sheet 变化） -------------------
ICS_ERAS = _PKG_ICS_ERAS
CGI_TERMS = _PKG_CGI_TERMS
SIMPLE_LITHOLOGY = _PKG_CGI_VOCABS / "simplelithology.json"
FOLIATIONTYPE = _PKG_CGI_VOCABS / "foliationtype.json"

XSD_CANDIDATES = [
    _pkg_xsd_root(),
    Path(os.environ.get("GSML_XSD_ROOT", "")) if os.environ.get("GSML_XSD_ROOT") else None,
    Path(os.environ.get("TEMP", "")) / "gsml_xsd" / "xsd_tree",
]


def _bind(sheet_key: str) -> dict:
    """注册表 → 模块常量绑定表（init_sheet 与模块初始化共用）。"""
    sh = get_sheet(sheet_key)
    return {
        "SHEET": sh.code,
        "SHEET_KEY": sh.key,
        "SHEET_TITLE": sh.title,
        "BASE_URI": sh.base_uri or f"https://{NAMESPACE_PLACEHOLDER}/{sh.code}/",
        "SCALE_DENOMINATOR": sh.SCALE_DENOMINATOR,
        "GEOJSON_L1": sh.geojson_l1,
        "SHEET_ROOT": sh.root,
        "DATA": sh.root / "data",
        "OUT_DIR": sh.out_dir,
        "LITE_OUT": sh.lite_out,
        "GML_OUT": sh.gml_out,
        "PENDING_OUT": sh.pending_out,
        "REPORT_OUT": sh.report_out,
        "VOCAB_MAPPING": sh.vocab_mapping,
        # 单元配色=stylegen 语义生成件（DZ/T 0179-2025 色库+overrides 裁定层）——
        # 管线序：g4c stylegen --sheet <key> 先于本管线运行
        "UNIT_COLOR_MAPPING": sh.style_generated,
        "UNIT_TO_ICS": sh.unit_to_ics,
        "AGE_TABLE_CSV": sh.age_table_csv,
        "AUX_PAIRS_CSV": sh.aux_pairs,
        "AUX_ASSOC_CSV": sh.aux_assoc,
        "AUX_TRIPLETS_CSV": sh.aux_triplets,
        "AUX_SEMANTICS_JSON": sh.aux_semantics_json,  # 编图矛盾登记册
        "CONFLICTS_CSV": sh.root / f"_gzeeb_conflicts_{sh.key}.csv",  # 段级横幅源（2026-10-02）
        # 断裂接触活动候选册（2026-10-02 活动断层审计 A7：双册消费——
        # 断裂接触层独有实体的候选经此到达 build 横幅）
        "CONTACT_CONFLICTS_CSV": sh.root / f"_fault_contact_activity_conflicts_{sh.key}.csv",
        "CALIBRATION_CSV": sh.calibration,            # 界线标定报告（关系装配源）
        "EXPECTED_UNITS": sh.expected_units,          # 色库单元数断言
        # 面图层文件分布断言（装载期漂移闸）
        "EXPECTED_POLYGON_DIST": sh.expected_polygon_dist,
    }


def init_sheet(sheet: str = "kurgan") -> None:
    """在 build/verify 入口切换图幅参数集（重指向模块常量）。"""
    for k, v in _bind(sheet).items():
        globals()[k] = v


# 模块初始化：默认图幅 kurgan（开发默认；Path 绑定不触盘，未安装图幅数据的
# 机器上 import 安全，仅在实际读文件时失败）。
init_sheet("kurgan")
