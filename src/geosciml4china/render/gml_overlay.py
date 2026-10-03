"""GML 语义叠加（geosciml_render，辅助点非实体原则的渲染侧兑现）。

几何一律取 Lite 同 FEATUREID 线（GML posList 为 lat,lon 翻转序，仅取语义）。
movementSense→运动符号；编图矛盾横幅→警示描边。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

GSMLB = "{http://www.opengis.net/gsml/4.1/GeoSciML-Basic}"
GSMLE = "{http://www.opengis.net/gsml/4.1/GeoSciML-Extension}"
GML = "{http://www.opengis.net/gml/3.2}"
XLINK = "{http://www.w3.org/1999/xlink}"

# 语义→蕴含运动性质（2026-10-03 渲染完全基于 geosciml：脱离 MapGIS
# 码系统——标定结构语义 structural_type 直查；活动/推测为其他分层不蕴含）
_IMPLIED_BY_SEM = {"逆断层": "reverse", "推覆体边界": "reverse",
                   "正断层": "normal", "左型走滑断层": "sinistral",
                   "右型走滑断层": "dextral", "走滑断层": None,
                   "复合断层": None}


@dataclass
class OverlayEntry:
    feature_id: str
    movement_sense: str = ""           # normal/reverse/dextral/sinistral/no_movement_sense（首个非空）
    hw_trend: float | None = None      # hangingWallDirection trend（首个）
    azimuth: float | None = None
    dip: float | None = None
    contradiction: bool = False
    description: str = ""
    senses: list = field(default_factory=list)  # 全部 movementSense 词（多块）


def _first_float(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(str(text).split()[0])
    except (ValueError, IndexError):
        return None


def read_gml_overlays(gml_path: str | Path,
                      expected: int | None = None) -> list[OverlayEntry]:
    """解析 ShearDisplacementStructure → OverlayEntry 列表。

    expected: 期望 SDS 数（库尔干 310、英吉沙 289）；None 不闸。
    **闸只在 verify 侧显式给**（渲染侧 None——曾闸崩英吉沙叠加渲染
    且管道 tail 吞掉退出码的教训：长命令管道须 pipefail）。"""
    out: list[OverlayEntry] = []
    root = etree.parse(str(gml_path)).getroot()
    for sds in root.findall(f".//{GSMLB}ShearDisplacementStructure"):
        fid = (sds.get(f"{GML}id") or "")[4:]
        desc_el = sds.find(f"{GML}description")
        desc = desc_el.text or "" if desc_el is not None else ""
        e = OverlayEntry(
            feature_id=fid,
            contradiction="【编图矛盾登记】" in desc,
            description=desc)
        for stsd in sds.findall(f"{GSMLB}stStructureDescription"):
            dv = stsd.find(f"{GSMLE}DisplacementValue")
            if dv is not None:
                ms = dv.find(f"{GSMLE}movementSense")
                if ms is not None:
                    term = (ms.get(f"{XLINK}href") or "").rsplit("/", 1)[-1]
                    if term:
                        e.senses.append(term)
                trend = dv.find(f"{GSMLE}hangingWallDirection//{GSMLB}trend"
                                f"//{GSMLB}lowerValue")
                if trend is not None and e.hw_trend is None:
                    e.hw_trend = _first_float(trend.text)
            po = stsd.find(f".//{GSMLB}GSML_PlanarOrientation")
            if po is not None and e.azimuth is None:
                az = po.find(f"{GSMLB}azimuth//{GSMLB}lowerValue")
                dp = po.find(f"{GSMLB}dip//{GSMLB}lowerValue")
                e.azimuth = _first_float(az.text if az is not None else None)
                e.dip = _first_float(dp.text if dp is not None else None)
        # 段级优先级：走滑钩（段定义性）> 正/逆（b 判别）> 无运动
        for cand in e.senses:
            if cand in ("dextral", "sinistral"):
                e.movement_sense = cand
                break
        if not e.movement_sense:
            for cand in e.senses:
                if cand in ("normal", "reverse"):
                    e.movement_sense = cand
                    break
        if not e.movement_sense and e.senses:
            e.movement_sense = "no_movement_sense"
        out.append(e)
    if expected is not None:
        assert len(out) == expected, f"SDS overlays parsed {len(out)}/{expected}"
    return out


def hw_side(coords, hw_trend: float, lon_m: float, lat_m: float) -> str:
    """上盘侧（trend 方位）相对线方向的左右侧（米制切向）。"""
    import numpy as np
    pts = np.asarray(coords, dtype=float)
    pts = pts * [lon_m, lat_m]
    mid = len(pts) // 2
    t = pts[min(mid + 1, len(pts) - 1)] - pts[max(mid - 1, 0)]
    if not (t ** 2).sum():
        t = pts[-1] - pts[0]
    n_left = (-t[1], t[0])  # 左法线
    rad = math.radians(hw_trend)
    hw = (math.sin(rad), math.cos(rad))
    return "left" if (hw[0] * n_left[0] + hw[1] * n_left[1]) > 0 else "right"


_AUX_RED = (180 / 255.0, 0.0, 0.0)   # pymapgis 辅助点层 (180,0,0)


def draw_strike_slip_end_hooks(ax, coords, sense: str, *,
                               lon_m: float, lat_m: float,
                               meters_per_px: float | None = None,
                               hook_len_px: float = 16.0,
                               barb_len_px: float = 7.0,
                               hook_off_m: float = 130.0,
                               tan_win_m: float = 50.0,
                               color=_AUX_RED, lw: float = 0.4,
                               zorder: int = 20) -> dict:
    """走滑断层端部钩线（2026-09-27 用户定：pymapgis 样式、钩尖对齐线端）。

    样式 = pymapgis render_fault_aux_layer 238/239 钩：主线（lw 0.4、
    16px 经 mpp 换算）+ 钩尖处 ±150° 钩刺（7px），钩刺取背向断层侧。
    布局 = 两条钩线分居断层两端异侧，**钩尖（带刺端）与断层线端点对齐**
    （钩尖 = 端点 + 侧法线×hook_off_m，主线自钩尖沿切向拖入断层跨内）。
    旋向编码（与 draw_strike_slip_arrows 左+t右−t 同约定）：
    dextral→始端右侧（运动 −t）、末端左侧（+t）；sinistral 镜像。
    返回不变量统计（平行偏差/钩尖偏移误差/侧别），供 verify 断言。
    """
    from .fault_measure import _seg_frame_m

    stats = {"hooks": 0, "parallel_max_dev": 0.0, "tip_off_err_max": 0.0,
             "side_violations": 0, "degenerate": 0}
    if not coords or len(coords) < 2 or sense not in ("dextral", "sinistral"):
        return stats
    if meters_per_px is None:
        x0l, x1l = ax.get_xlim()
        try:
            w_px = ax.get_window_extent().width
        except Exception:
            w_px = 0
        if not w_px:
            w_px = ax.figure.get_size_inches()[0] * ax.figure.dpi
        meters_per_px = (x1l - x0l) * lon_m / w_px if w_px else 30.0
    hook_len_m = hook_len_px * meters_per_px
    barb_len_m = barb_len_px * meters_per_px

    cm = [(cx * lon_m, cy * lat_m) for cx, cy in coords]
    total = _seg_frame_m(cm, 0.0)[3]
    if total < 2 * tan_win_m:
        tan_win_m = total / 2.0
    if total < 1e-6:
        stats["degenerate"] += 1
        return stats
    _, t0, n0_left, _ = _seg_frame_m(cm, tan_win_m)
    _, t1, n1_left, _ = _seg_frame_m(cm, total - tan_win_m)

    def to_deg(xm, ym):
        return xm / lon_m, ym / lat_m

    # (端点, 外向切向, 左法线, 期望侧)：dextral 始右末左，sinistral 始左末右
    ends = [(cm[0], (-t0[0], -t0[1]), n0_left,
             "right" if sense == "dextral" else "left"),
            (cm[-1], t1, n1_left,
             "left" if sense == "dextral" else "right")]
    for (exm, eym), (uox, uoy), (nlx, nly), want_side in ends:
        sgn = 1.0 if want_side == "left" else -1.0
        nsx, nsy = nlx * sgn, nly * sgn
        txm, tym = exm + nsx * hook_off_m, eym + nsy * hook_off_m  # 钩尖
        bxm, bym = txm - uox * hook_len_m, tym - uoy * hook_len_m  # 主线尾
        tx_, ty_ = to_deg(txm, tym)
        bx_, by_ = to_deg(bxm, bym)
        ax.plot([bx_, tx_], [by_, ty_], color=color, linewidth=lw,
                zorder=zorder, solid_capstyle="butt")
        # 钩刺：±150° 两候选取背断层（与侧法线点积大）者——pymapgis 同款
        best = None
        for ang in (math.radians(150), math.radians(-150)):
            ca, sa = math.cos(ang), math.sin(ang)
            bxx = uox * ca - uoy * sa
            byy = uox * sa + uoy * ca
            if best is None or bxx * nsx + byy * nsy > best[0]:
                best = (bxx * nsx + byy * nsy, bxx, byy)
        _, bxx, byy = best
        ex_, ey_ = to_deg(txm + bxx * barb_len_m, tym + byy * barb_len_m)
        ax.plot([tx_, ex_], [ty_, ey_], color=color, linewidth=lw,
                zorder=zorder, solid_capstyle="butt")
        stats["hooks"] += 1
        # 不变量：主线∥端切向（夹角≈0）；钩尖偏移=hook_off_m；侧别=期望
        te = t0 if (exm, eym) == cm[0] else t1
        par = abs(uox * te[0] + uoy * te[1])
        dev = math.degrees(math.acos(min(max(par, 0.0), 1.0)))
        stats["parallel_max_dev"] = max(stats["parallel_max_dev"], dev)
        stats["tip_off_err_max"] = max(
            stats["tip_off_err_max"],
            abs(math.hypot(txm - exm, tym - eym) - hook_off_m))
        if not ((sgn > 0) == (want_side == "left")):
            stats["side_violations"] += 1
    return stats


def render_movement_sense_overlay(ax, entries, sds_gdf, *,
                                  lon_m: float, lat_m: float,
                                  meters_per_px: float | None = None,
                                  zorder: int = 20,
                                  draw_marks: bool = False) -> dict:
    """movementSense → 运动符号（delta：base 已有同类装饰则不重复画）。

    桶：一致（码蕴含=sense）/ 新增（码无蕴含）/ 冲突（码蕴含≠sense，
    F019/F050/F067 所在桶，与编图矛盾横幅互证）。
    走滑（dextral/sinistral）= 端部钩线（pymapgis 样式、钩尖对齐线端，
    2026-09-27 用户定），替代早期沿线交替箭头。
    2026-09-28 用户裁定细化：正/逆齿刺标注停用（断层产状测量点体系已
    承担）；走滑旋向指示保留（六类测量模式不含旋向）——draw_marks=False
    时正/逆只入桶不绘制，走滑钩线始终绘制。
    """
    from pymapgis.rendering.symbol_engine import (
        draw_normal_fault_ticks, draw_reverse_fault_teeth)

    geom_by_fid = {str(r["FEATUREID"]): r.geometry for _, r in sds_gdf.iterrows()}
    sem_by_fid = {str(r["FEATUREID"]): str(r.get("structural_type") or "")
                  for _, r in sds_gdf.iterrows()}
    buckets = {"一致": [], "新增": [], "冲突": [], "无运动": 0, "未命中几何": []}
    drawn = 0
    hooks_stats = {"segments": 0, "hooks": 0, "parallel_max_dev": 0.0,
                   "tip_off_err_max": 0.0, "side_violations": 0,
                   "degenerate": 0}
    for e in entries:
        sense = e.movement_sense
        geom = geom_by_fid.get(e.feature_id)
        if geom is None:
            buckets["未命中几何"].append(e.feature_id)
            continue
        if not sense or sense == "no_movement_sense":
            buckets["无运动"] += 1
            continue
        _sem0 = sem_by_fid.get(e.feature_id, "")
        implied = _IMPLIED_BY_SEM.get(_sem0)
        if implied and implied != sense:
            buckets["冲突"].append(e.feature_id)
        elif implied:
            buckets["一致"].append(e.feature_id)
        else:
            buckets["新增"].append(e.feature_id)
        coords = list(geom.coords)
        side = hw_side(coords, e.hw_trend, lon_m, lat_m) if e.hw_trend is not None else "left"
        if sense == "reverse":
            if draw_marks and code != "07":
                draw_reverse_fault_teeth(ax, coords, side=side)
                drawn += 1
        elif sense == "normal":
            if draw_marks:
                draw_normal_fault_ticks(ax, coords, side=side)
                drawn += 1
        elif sense in ("dextral", "sinistral"):
            st = draw_strike_slip_end_hooks(
                ax, coords, sense, lon_m=lon_m, lat_m=lat_m,
                meters_per_px=meters_per_px, zorder=zorder)
            hooks_stats["segments"] += 1
            for k in ("hooks", "degenerate"):
                hooks_stats[k] += st[k]
            for k in ("parallel_max_dev", "tip_off_err_max"):
                hooks_stats[k] = max(hooks_stats[k], st[k])
            hooks_stats["side_violations"] += st["side_violations"]
            drawn += 1
    buckets["drawn"] = drawn
    buckets["hooks"] = hooks_stats
    return buckets


def render_contradiction_overlay(ax, entries, sds_gdf, *,
                                 zorder: int = 30,
                                 color=(0.85, 0.0, 0.85)) -> dict:
    """编图矛盾 7 段：警示描边 + 中点'矛盾'注记。"""
    geom_by_fid = {str(r["FEATUREID"]): r.geometry for _, r in sds_gdf.iterrows()}
    hit, miss = [], []
    for e in entries:
        if not e.contradiction:
            continue
        geom = geom_by_fid.get(e.feature_id)
        if geom is None:
            miss.append(e.feature_id)
            continue
        xs, ys = geom.xy
        ax.plot(xs, ys, color=color, lw=3.0, alpha=0.45, zorder=zorder,
                solid_capstyle="round")
        ax.plot(xs, ys, color="white", lw=0.7, ls=(0, (2, 2)), zorder=zorder + 1)
        mid = geom.interpolate(0.5, normalized=True)
        ax.text(mid.x, mid.y, "矛盾", color=color, fontsize=5, weight="bold",
                ha="center", zorder=zorder + 1,
                bbox=dict(fc="white", ec=color, alpha=0.8, lw=0.5, pad=0.6))
        hit.append(e.feature_id)
    return {"hit": hit, "miss": miss, "expected": 7}
