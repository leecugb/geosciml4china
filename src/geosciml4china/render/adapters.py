"""四视图 → 引擎 schema 适配器（pdf_writer 契约，见方案 §适配器映射总表）。

纪律：crs=EPSG:4326 直通不重投影（R15）；geom_type 入口断言（R10）；
计数与命中断言先于渲染（R6 静默跳过防线）。
"""
from __future__ import annotations

import math
from urllib.parse import unquote

import geopandas as gpd
from shapely.geometry import shape

from .codemap import (UnitEntry, feature_id, hex_to_rgb,
                      src_file_from_feature_id)
from .sources import props
from ..convert import model

CRS = "EPSG:4326"


def _frame(rows: list[dict]) -> gpd.GeoDataFrame:
    if not rows:
        # 空帧仍须带 geometry 列（如英吉沙无泥火山）
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=CRS)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)


def adapt_geologic_units(features: list[dict],
                         rmap: dict[str, UnitEntry],
                         zorder_tbl: dict[str, int],
                         ) -> tuple[gpd.GeoDataFrame, dict]:
    """geologic_unit_view → 面层（render_polygon_layer 语义模式契约）。

    specification_uri 末段 norm → 反查表 → QDUECC=raw 原始码（含控制符）、
    _src_file、FEATUREID、zorder 稳定排序；genericSymbolizer==entry.rgb 逐要素断言。
    """
    rows, unmapped, color_bad = [], [], []
    for feat in features:
        p = props(feat)
        spec = str(p.get("specification_uri") or "")
        norm = unquote(spec.rsplit("/", 1)[-1])  # URI 百分编码（希腊字母单元 δ/υ/τα…）
        entry = rmap.get(norm)
        fid = feature_id(p.get("identifier_value") or "")
        if entry is None:
            unmapped.append(norm)
            continue
        sym = p.get("genericSymbolizer")
        if sym and entry.rgb and hex_to_rgb(sym) != list(entry.rgb):
            color_bad.append((norm, sym, entry.rgb))
        src_file = entry.src_file or src_file_from_feature_id(fid)
        rows.append({
            "QDUECC": entry.raw_code,
            "QDUECC_eff": entry.raw_code,
            "_src_file": src_file,
            "FEATUREID": fid,
            "zorder": zorder_tbl.get(src_file, 0),
            "status": "normal",
            "name": p.get("name"),
            "description": p.get("description"),
            "rank": p.get("rank"),
            "geometry": shape(feat["geometry"]),
        })
    gdf = _frame(rows).sort_values("zorder", kind="stable").reset_index(drop=True)
    report = {"count": len(gdf), "unmapped": unmapped,
              "symbolizer_mismatch": color_bad}
    return gdf, report


def adapt_contacts(features: list[dict]) -> tuple[gpd.GeoDataFrame, dict]:
    """contact_view → 界线层（render_line_layer 契约）。2026-10-03 渲染
    完全基于地质语义：出站标定语义标签 sem_label（不再出 GZBD 码）；
    younger_side 结构化贯通（04/24 不整合双线用标定侧；null → 渲染层
    探针回落，与参照管线同链）。"""
    rows, bad_geom = [], []

    def _side(v):
        return v if isinstance(v, str) and v in ("left", "right") else None

    for feat in features:
        p = props(feat)
        geom = shape(feat["geometry"])
        if geom.geom_type != "LineString":
            bad_geom.append(geom.geom_type)
            continue
        sem = str(p.get("genericSymbolizer") or p.get("name") or "")
        rows.append({
            "sem_label": sem,
            "status": "normal",
            "younger_side": _side(p.get("younger_side")),
            "contact_id": feature_id(p.get("identifier_value") or ""),
            "geometry": geom,
        })
    gdf = _frame(rows)
    return gdf, {"count": len(gdf), "bad_geom": bad_geom}


def _clean_name(v) -> str:
    """GZEAB 清洗：None/NaN/'nan' → ''（R4）。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def adapt_shear_structures(features: list[dict]) -> tuple[gpd.GeoDataFrame, dict]:
    """shear_displacement_structure_view → 断层层（render_fault_layer 契约）。"""
    rows, bad_geom = [], []
    for feat in features:
        p = props(feat)
        geom = shape(feat["geometry"])
        if geom.geom_type != "LineString":
            bad_geom.append(geom.geom_type)
            continue
        rows.append({
            # 2026-10-03 渲染完全基于 geosciml：不再出站 MapGIS 码
            # （GZEEB）——样式与旋向归组均按标定语义（structural_type）
            "GZEAB": _clean_name(p.get("name")),
            "FEATUREID": feature_id(p.get("identifier_value") or ""),
            "faultType": p.get("faultType"),
            "description": p.get("description"),
            "evidence_class": str(p.get("evidence_class") or ""),
            "structural_type": str(p.get("structural_type") or ""),
            "geometry": geom,
        })
    gdf = _frame(rows)
    return gdf, {"count": len(gdf), "bad_geom": bad_geom}


def adapt_site_observations(features: list[dict]) -> tuple[gpd.GeoDataFrame, dict]:
    """site_observation_view → 产状层（render_attitude_layer 契约）。

    GZBBAB=symbolRotation（走向，实证 125↔'215∠46'）；
    GZBBAC=(rot+90)%360；GZBBAD=float(observedValue or 0)。
    2026-09-28：sem_type 透传（Pt1 片麻理等宿主裁定语义在渲染层生效）。"""
    rows, bad_val = [], 0
    for feat in features:
        p = props(feat)
        rot = float(p.get("symbolRotation") or 0.0)
        try:
            dip = float(p.get("observedValue") or 0.0)
        except (TypeError, ValueError):
            dip, bad_val = 0.0, bad_val + 1
        rows.append({
            # 2026-10-03 渲染完全基于地质语义：测量契约字段更名（脱离
            # MapGIS 字段名）——GZBBAB→strike_az（走向）、GZBBAC→dip_az
            # （倾向）、GZBBAD→dip（倾角）；渲染器旧名回退保留（遗留）
            "strike_az": rot,
            "dip_az": float((rot + 90.0) % 360.0),
            "dip": dip,
            "GZBBGA": str(p.get("genericSymbolizer") or ""),
            "sem_type": (str(p["sem_type"]) if p.get("sem_type") else None),
            "obs_id": feature_id(p.get("identifier_value") or ""),
            "label": p.get("label"),
            "geometry": shape(feat["geometry"]),
        })
    gdf = _frame(rows)
    return gdf, {"count": len(gdf), "bad_dip": bad_val}


def adapt_specimens(features: list[dict]) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """fossil_specimen_view → 化石层 + 泥火山层（render_fossil_layer /
    render_mudvolcano_layer 契约，2026-09-28 接入——参照 pymapgis 管线）。

    render_fossil_layer 契约列：symbol_no/height/angle + geometry；
    按 specimenType（化石产地/泥火山）拆帧——pdf_writer role 分派
    fossil/mudvol 各自成层（zorder 17）。"""
    rows_f, rows_m = [], []
    for feat in features:
        p = props(feat)
        rec = {
            "symbol_no": int(p.get("symbol_no") or p.get("genericSymbolizer") or 0),
            "height": float(p.get("height") or 2.0),
            "angle": float(p.get("angle") or 0.0),
            "sem_type": p.get("label"),
            "geometry": shape(feat["geometry"]),
        }
        (rows_m if str(p.get("specimenType")) == model.SPECIMEN_KINDS["mudvolcano"]
         else rows_f).append(rec)
    return (_frame(rows_f), _frame(rows_m),
            {"count": len(rows_f) + len(rows_m),
             "fossils": len(rows_f), "mudvolcanoes": len(rows_m)})


def adapt_folds(features: list[dict]) -> tuple[gpd.GeoDataFrame, dict]:
    """fold_view → 褶皱层（render_fold_layer 契约：fold_class 语义 + geometry）。

    2026-10-03 渲染完全基于地质语义：直接消费视图出站的词表裁定语义
    profile（anticline/syncline）——不再读取/解析 GZCE 码。
    """
    rows = []
    for feat in features:
        p = props(feat)
        sem = str(p.get("profile") or p.get("genericSymbolizer") or "")
        rows.append({
            "fold_class": sem if sem in ("syncline", "anticline") else "",
            "name": p.get("label"),
            "geometry": shape(feat["geometry"]),
        })
    return _frame(rows), {"count": len(rows)}


def adapt_water(features: list[dict]) -> tuple[gpd.GeoDataFrame, dict]:
    """waterline_view/waterpoly_view → 水系层（GB 分型 + NAME 注记）。"""
    rows = []
    for feat in features:
        p = props(feat)
        rows.append({
            "GB": str(p.get("GB") or ""),
            "NAME": str(p.get("name") or ""),
            "HYDC": str(p.get("HYDC") or ""),
            "geometry": shape(feat["geometry"]),
        })
    return _frame(rows), {"count": len(rows)}
