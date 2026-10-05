"""Map IR 装配（geosciml_render）。

层名纪律：boundary|LDZOFBA002.WL / fault|LDZOFBA003.WL 派发从 layer.name
切 "|" 尾段（pdf_writer.py:2737-2742），命名不可改（R8）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# pymapgis 完整地质栈导入懒化（2026-10-04 CI 泛化：PyPI mapgis2shp 仅含
# 极简读取器——rendering/semantics 子包未发布；模块级导入移入函数体，
# 使本包在 PyPI-minimal 环境 import 安全；注解经 future 懒求值不受影响）
from . import adapters, sources
from .codemap import DEFAULT_COLOR_MAPPING, build_reverse_unit_map, zorder_table

_LAYER_TABLE = [
    ("waterpoly_view", "waterpoly|LDLYAAE002.WP", "waterpoly", 5),
    ("waterline_view", "waterline|LDLYAAE001.WL", "waterline", 9),
    ("geologic_unit_view", "polygon|merged", "polygon", 2),
    ("contact_view", "boundary|LDZOFBA002.WL", "boundary", 10),
    ("shear_displacement_structure_view", "fault|LDZOFBA003.WL", "fault", 15),
    ("site_observation_view", "attitude|LDZOFBA016.WT", "attitude", 18),
    # 2026-09-28 接入（参照 pymapgis 管线）：
    # 化石/泥火山=第六视图拆两帧（role fossil/mudvol 各自分派）；褶皱=第七视图
    ("fossil_specimen_view", "fossil|specimen", "fossil", 17),
    ("fold_view", "fold|LDZOFBA005.WL", "fold", 14),
]


# 比例尺锚定（2026-10-05 用户裁定「样式尺寸保持固定」）：画布随图幅范围
# 等比伸缩，mpp 恒定 = 1:25 万图面每像素地面米（250000×0.0254/dpi）——
# 点尺寸样式/花纹瓦片（SVG_TILE_SCALE 地面米锚）/mpp 换算叠加符号全部获得
# 跨幅一致的真实地面尺寸；消除小图幅（testdata 41×42 km）因固定画布被
# 3.4× 放大后点尺寸样式相对变细小的缺陷。figsize 显式传入时保持旧行为。
_MAP_SCALE_DENOM = 250000.0


def _scale_anchored_figsize(bbox: tuple[float, float, float, float],
                            dpi: int) -> tuple[float, float]:
    """bbox(度) → (fig_w_in, fig_h_in)：每像素地面米恒定（1:25 万）。
    与 dpi 无关的物理图面尺寸；dpi 只决定像素数。"""
    import math
    minx, miny, maxx, maxy = bbox
    lat0 = (miny + maxy) / 2.0
    lon_m = 111320.0 * math.cos(math.radians(lat0))
    lat_m = 111320.0
    mpp = _MAP_SCALE_DENOM * 0.0254 / dpi  # 地面米/px
    return ((maxx - minx) * lon_m / (mpp * dpi),
            (maxy - miny) * lat_m / (mpp * dpi))


def build_geosciml_map(
    lite_dir: str | Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    bbox_margin_frac: float = 0.05,
    crop_outliers: bool = True,
    figsize: tuple[float, float] | None = None,
    dpi: int = 200,
    color_mapping_path: str | Path | None = DEFAULT_COLOR_MAPPING,
    title: str | None = None,
    zorder_tbl: dict | None = None,
) -> tuple[Map, dict]:
    """Lite 四视图 → (Map IR, 适配报告)。"""
    from pymapgis.rendering import Layer, Map
    if not color_mapping_path:
        raise ValueError("color_mapping_path 必须显式传入（泛化 2026-10-02：无库尔干默认）")
    rmap = build_reverse_unit_map(color_mapping_path)
    ztbl = zorder_tbl or zorder_table()
    # 泛化（2026-10-02 审计）：标题经参数传入（注册表 SHEET_TITLE）
    m = Map(title=title or "GeoSciML (Lite)",
            figsize=figsize if figsize is not None else (24.0, 16.0), dpi=dpi)
    report: dict = {"layers": {}}
    bounds = []
    for view, lname, role, z in _LAYER_TABLE:
        feats = sources.load_lite_features(lite_dir, view)
        if view == "geologic_unit_view":
            gdf, rep = adapters.adapt_geologic_units(feats, rmap, ztbl)
        elif view == "contact_view":
            gdf, rep = adapters.adapt_contacts(feats)
        elif view == "shear_displacement_structure_view":
            gdf, rep = adapters.adapt_shear_structures(feats)
        elif view == "fossil_specimen_view":
            gdf, gdf_m, rep = adapters.adapt_specimens(feats)
            rep["loaded"] = len(feats)
            report["layers"][view] = rep
            m.add_layer(Layer(name="fossil|specimen", geodataframe=gdf,
                              zorder=17, role="fossil"))
            if len(gdf_m):
                m.add_layer(Layer(name="mudvolcano|specimen",
                                  geodataframe=gdf_m,
                                  zorder=17, role="mudvolcano"))
            bounds.append(gdf.total_bounds)
            if len(gdf_m):
                bounds.append(gdf_m.total_bounds)
            continue
        elif view == "fold_view":
            gdf, rep = adapters.adapt_folds(feats)
        elif view in ("waterline_view", "waterpoly_view"):
            gdf, rep = adapters.adapt_water(feats)
        else:
            gdf, rep = adapters.adapt_site_observations(feats)
        rep["loaded"] = len(feats)
        report["layers"][view] = rep
        if not len(feats):
            continue  # 空层（本幅无该水系主题）——不入图不参 bbox
        m.add_layer(Layer(name=lname, geodataframe=gdf, zorder=z, role=role))
        bounds.append(gdf.total_bounds)
    B = np.array(bounds)
    if bbox is None:
        # 分位数裁剪（2026-10-05 用户裁定 A 方案）：孤立远点（切块/编图
        # 残迹，如 testdata 的 2 个远西要素）不撑图框——按全要素 bounds
        # 的 1-99 分位取有效范围；crop_outliers=False 时保持全要素包络
        if crop_outliers and len(m.layers):
            _lo_x, _lo_y, _hi_x, _hi_y = [], [], [], []
            for _layer in m.layers:
                if _layer.geodataframe is None or not len(_layer.geodataframe):
                    continue
                _b = _layer.geodataframe.geometry.bounds
                _lo_x += _b["minx"].tolist()
                _lo_y += _b["miny"].tolist()
                _hi_x += _b["maxx"].tolist()
                _hi_y += _b["maxy"].tolist()
            if _lo_x:
                minx = float(np.percentile(_lo_x, 1))
                miny = float(np.percentile(_lo_y, 1))
                maxx = float(np.percentile(_hi_x, 99))
                maxy = float(np.percentile(_hi_y, 99))
            else:
                minx, miny, maxx, maxy = B[:, 0].min(), B[:, 1].min(),                     B[:, 2].max(), B[:, 3].max()
        else:
            minx, miny = B[:, 0].min(), B[:, 1].min()
            maxx, maxy = B[:, 2].max(), B[:, 3].max()
        dx = (maxx - minx) * bbox_margin_frac
        dy = (maxy - miny) * bbox_margin_frac
        bbox = (minx - dx, miny - dy, maxx + dx, maxy + dy)
    if figsize is None:
        # 比例尺锚定画布（样式尺寸跨幅固定）——figsize 显式传入时保持旧行为
        m.figsize = _scale_anchored_figsize(bbox, dpi)
    m.bbox = bbox
    return m, report
