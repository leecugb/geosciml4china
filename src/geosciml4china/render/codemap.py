"""码表反查与派生（geosciml_render）。

渲染纪律：样式推导只认 GeoSciML 产物字段；默认配色=stylegen 语义生成件
（genericSymbolizer≡其 rgb，F1/F9；语义→样式单源，2026-09-27 裁定）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_COLOR_MAPPING = "output/geosciml/kurgan_style_generated.json"
# 2026-09-28（F2）：断层样式单源化——渲染消费 stylegen_fault 生成件
# （词表默认+overrides 裁定层），手工 fault_rendering_styles.json 保留供对账
DEFAULT_FAULT_STYLES = "output/geosciml/kurgan_fault_styles_generated.json"
# SVG 花纹注册表=包数据（DZ/T 0179-2025 标准资产，随包分发）
from ..data import DZT0179_PATTERN_REGISTRY as _SVG_REG
DEFAULT_SVG_REGISTRY = str(_SVG_REG)

# FEATUREID 前缀 → 源文件（F8：OFBB001-004 ↔ 四个面图层文件）
_SRC_FILE_BY_PREFIX = {
    "OFBB001": "LDZOFBB001.WP",
    "OFBB002": "LDZOFBB002.WP",
    "OFBB003": "LDZOFBB003.WP",
    "OFBB004": "LDZOFBB004.WP",
}

# 面图层绘制序（与 render_semantic_map/旧驱动同序：变质→侵入→火山→沉积）
_ZORDER_BY_SRC_FILE = {
    "LDZOFBB004.WP": 1,
    "LDZOFBB003.WP": 2,
    "LDZOFBB002.WP": 3,
    "LDZOFBB001.WP": 4,
}


@dataclass
class UnitEntry:
    norm: str
    raw_code: str          # 含控制符原始码（units 精确键，标注 mathtext 字形）
    src_file: str          # LDZOFBB00X.WP
    rgb: list
    name: str = ""
    pattern_ref: Optional[dict] = None


def build_reverse_unit_map(color_mapping_path: str | Path = DEFAULT_COLOR_MAPPING,
                           ) -> dict[str, UnitEntry]:
    """norm 码 → UnitEntry。norm 全局唯一断言（F9）。"""
    doc = json.loads(Path(color_mapping_path).read_text(encoding="utf-8"))
    out: dict[str, UnitEntry] = {}
    for src_file, layer in (doc.get("polygon_layers") or {}).items():
        for raw_code, u in (layer.get("units") or {}).items():
            norm = u.get("norm")
            if not norm:
                continue
            if norm in out:
                prev = out[norm]
                same = (prev.rgb == list(u.get("rgb") or [])
                        and prev.name == (u.get("name") or "")
                        and prev.pattern_ref == (u.get("pattern_ref") or u.get("pattern")))
                # 同一单元的空白异形码（尾空格变体等，2026-09-29 奥依亚依拉克
                # '→J↓3→k'/'→J↓3→k  ' 首遇）：rgb/name/pattern 全同=无歧义，
                # 合并（首现为准）；任一不同=真语义歧义，维持 F9 硬断言
                if same:
                    continue
                assert False, (f"norm 重名: {norm}（{src_file} 与 "f"{out[norm].src_file}）——rgb/name/pattern 不一致，真歧义交人工裁定")
            out[norm] = UnitEntry(
                norm=norm, raw_code=raw_code, src_file=src_file,
                rgb=list(u.get("rgb") or []), name=u.get("name") or "",
                pattern_ref=u.get("pattern_ref") or u.get("pattern"))
    assert out, f"reverse unit map loaded empty from {color_mapping_path}"
    return out


def feature_id(uri_or_id: str) -> str:
    """identifier.value 末段 / 'sds.<FID>' / 'mf.<FID>' → 裸 FEATUREID。"""
    tail = str(uri_or_id).rsplit("/", 1)[-1]
    for pre in ("sds.", "mf.", "c.", "fol.", "fold.", "gu."):
        if tail.startswith(pre):
            return tail[len(pre):]
    return tail


def src_file_from_feature_id(fid: str) -> Optional[str]:
    """'OFBB001C1A…' → 'LDZOFBB001.WP'（F8 前缀表；无法识别返回 None）。"""
    return _SRC_FILE_BY_PREFIX.get(str(fid)[:7])


def zorder_table() -> dict[str, int]:
    """_src_file → 绘制序（可被 sheet_profile 覆盖的默认值）。"""
    return dict(_ZORDER_BY_SRC_FILE)


def hex_to_rgb(s: str) -> list[int]:
    """'#e5b366' → [229, 179, 102]。"""
    s = str(s).lstrip("#")
    return [int(s[i:i + 2], 16) for i in (0, 2, 4)]
