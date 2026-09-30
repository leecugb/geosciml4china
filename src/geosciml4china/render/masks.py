"""已知差异掩膜（几何→像素）。

**教训（2026-09-27 排查）**：掩膜仿射不得用"等比满幅"公式手算——
render_map_to_pdf 的实际出图变换是**各向异性**的（x/y 缩放不同，
由 matplotlib equal-aspect 在内容驱动下的真实布局决定），手算公式
会系统性偏置数十至数百像素。掩膜仿射必须**从实际渲染的 ax.transData
捕获**（run_mirror 经 savefig 探针捕获矩阵）。
"""
from __future__ import annotations

import numpy as np


class RenderTransform:
    """从实际渲染捕获的数据→像素变换（含 dpi 换算与 y 翻转）。"""

    def __init__(self, trans_data, fig_dpi: float, out_dpi: float,
                 out_shape: tuple[int, int]):
        """trans_data: matplotlib Affine2D（fig_dpi 显示坐标系）；
        out_shape: (H, W) 输出图像尺寸。"""
        self._m = trans_data
        self.k = out_dpi / fig_dpi
        self.H = out_shape[0]

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        px, py = self._m.transform((x, y))
        return px * self.k, (self.H / self.k - py) * self.k


def affine_for(bbox, width: int, height: int):
    """旧等比满幅仿射（**已证伪，仅留作对照/调试**）。"""
    minx, miny, maxx, maxy = bbox
    dw, dh = maxx - minx, maxy - miny
    scale = min(width / dw, height / dh)
    x0 = (width - dw * scale) / 2.0
    y0 = (height - dh * scale) / 2.0
    return scale, x0, y0, minx, maxy


def to_px(x, y, aff):
    scale, x0, y0, minx, maxy = aff
    return x0 + (x - minx) * scale, y0 + (maxy - y) * scale


def _mask_line(geom, width_px: float, to_px_fn, shape_wh: tuple[int, int]) -> np.ndarray:
    """线缓冲掩膜（像素近似：沿线每 ~1px 采样、圆盘半径 width_px/2+1）。"""
    H, W = shape_wh
    mask = np.zeros((H, W), dtype=bool)
    length = geom.length
    if length <= 0:
        return mask
    r = max(int(round(width_px / 2.0)) + 1, 1)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    disk = xx * xx + yy * yy <= r * r
    n = max(int(length * 4000), 2)
    for i in range(n + 1):
        p = geom.interpolate(i / n, normalized=True)
        px, py = to_px_fn(p.x, p.y)
        cx, cy = int(round(px)), int(round(py))
        x1, x2 = max(cx - r, 0), min(cx + r + 1, W)
        y1, y2 = max(cy - r, 0), min(cy + r + 1, H)
        if x1 >= x2 or y1 >= y2:
            continue
        sub = disk[(y1 - cy + r):(y2 - cy + r), (x1 - cx + r):(x2 - cx + r)]
        mask[y1:y2, x1:x2] |= sub
    return mask


def _mask_point(x: float, y: float, half_px: int, to_px_fn, shape_wh) -> np.ndarray:
    H, W = shape_wh
    mask = np.zeros((H, W), dtype=bool)
    px, py = to_px_fn(x, y)
    cx, cy = int(round(px)), int(round(py))
    x1, x2 = max(cx - half_px, 0), min(cx + half_px + 1, W)
    y1, y2 = max(cy - half_px, 0), min(cy + half_px + 1, H)
    mask[y1:y2, x1:x2] = True
    return mask


def build_masks(l1_boundaries_gdf, l1_attitude_gdf, to_px_fn, shape_wh,
                line_width_px: float = 3.0, point_half_px: int = 22):
    """M1=81 冰雪界线（312 条）、M2=status=excluded 段（1 条）、M3=片麻理 4 点。

    to_px_fn: RenderTransform（从实际渲染捕获），保证掩膜与出图同变换。
    """
    gz = l1_boundaries_gdf["GZBD_eff"].astype(str).str.replace(".0", "", regex=False).str.zfill(2)
    m1 = np.zeros(shape_wh, dtype=bool)
    for g in l1_boundaries_gdf[gz == "81"].geometry:
        m1 |= _mask_line(g, line_width_px, to_px_fn, shape_wh)
    m2 = np.zeros(shape_wh, dtype=bool)
    exc = l1_boundaries_gdf[l1_boundaries_gdf["status"].astype(str) == "excluded"]
    for g in exc.geometry:
        m2 |= _mask_line(g, line_width_px, to_px_fn, shape_wh)
    m3 = np.zeros(shape_wh, dtype=bool)
    gns = l1_attitude_gdf[l1_attitude_gdf["sem_type"].astype(str) == "片麻理产状"]
    for g in gns.geometry:
        m3 |= _mask_point(g.x, g.y, point_half_px, to_px_fn, shape_wh)
    return [("M1_冰雪81层", m1), ("M2_excluded段", m2), ("M3_片麻理符号", m3)]
