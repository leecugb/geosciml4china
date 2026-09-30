"""Lite GeoJSON 装载（json 原生，规避 Fiona 嵌套属性不保，R3）。

Lite 视图坐标为 EPSG:4326 度数、lon/lat 未翻转（RFC7946）——
本层直通，不做任何重投影（R15）。
"""
from __future__ import annotations

import json
from pathlib import Path

VIEWS = (
    "geologic_unit_view",
    "contact_view",
    "shear_displacement_structure_view",
    "site_observation_view",
    "fault_attitude_point_view",   # 第五视图（fault_measure 测量点层）
    "fossil_specimen_view",        # 第六视图（化石/泥火山标本）
    "fold_view",                   # 第七视图（褶皱轴线，2026-09-28 接入）
    # 渲染支撑视图（2026-09-29 十一文件契约补全：水系非 GeoSciML 标准视图，
    # 水系图层地质语义外但属图面组成；L1 直通）
    "waterline_view",
    "waterpoly_view",
)

EXPECTED_COUNT = {
    "geologic_unit_view": 713,
    "contact_view": 1317,
    "shear_displacement_structure_view": 310,
    "site_observation_view": 305,
}


def load_lite_features(lite_dir: str | Path, view: str) -> list[dict]:
    """读取 Lite 视图全部 features。"""
    if view not in VIEWS:
        raise KeyError(f"unknown lite view {view!r}（可选 {VIEWS}）")
    p = Path(lite_dir) / f"{view}.geojson"
    if not p.exists():
        raise FileNotFoundError(p)
    doc = json.loads(p.read_text(encoding="utf-8"))
    feats = doc.get("features") or []
    assert feats, f"lite view loaded empty: {p}"
    return feats


def props(feat: dict) -> dict:
    """扁平化 properties + identifier_value（嵌套 identifier 提取）。"""
    p = dict(feat.get("properties") or {})
    ident = p.pop("identifier", None)
    if isinstance(ident, dict):
        p["identifier_value"] = ident.get("value")
    elif ident is not None:
        p["identifier_value"] = ident
    return p
