# -*- coding: utf-8 -*-
"""断层产状测量点符号渲染（2026-09-27 用户方案，裁定级）。

数据源：fault_attitude_point_view.geojson（第五视图，点位=b 到所属段的垂足）。
方案（用户 2026-09-27 定）：
- 仅倾向模式：测量点沿 dip_az 拉箭头线；
- 倾向-倾角（无 a）：箭头线 + 箭头线右侧倾角注释（随箭头旋转、字体不旋转）；
- a-b-a/a-b 逆：箭头线 +（有倾角时）右侧注释 + 测量点沿断层两侧一定距离处
  放置上盘运动双短线，**双短线与 b 箭头分居断层两侧**；
- a-b-a/a-b 正：同上，**双短线与 b 箭头位于断层同侧**。

样式基准（2026-09-27 用户定）：倾向指示箭头与上盘运动双短线样式
**参照 pymapgis 渲染管线** `pdf_writer.render_fault_aux_layer`：
- 箭头 = 主线（lw=0.4、butt 端）+ 端部燕尾双折（±150°、barb_len_px），
  尺寸按像素定义（arrow_len_px=16、barb_len_px=7）经 meters_per_px 换算；
- 双短线 = 固定「=」字形（fontsize=6，rotation=锚点处图面法线角、
  rotation_mode="anchor"、ha="left" 自断层向目标侧延展）；
- 倾角注释 = 右侧智能偏移（margin 100m + 文字盒投影）、ha/va=center、3.5pt；
- 颜色 (180,0,0)、zorder=16——与 pymapgis 辅助点层一致。

双短线与断层垂直=视觉硬不变量（aux-pair-orthogonality-invariant）——
显示空间（度制等比图面）构造切向/法线，绘制后逐点校验并回传统计。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

RED = tuple(v / 255.0 for v in (180, 0, 0))   # pymapgis 辅助点层 (180,0,0)


def load_measure_points(lite_dir: str | Path) -> list[dict]:
    """fault_attitude_point_view.geojson → [{x, y, az, dip, mode, sds_uri}]

    2026-10-02 语义 id 裁定：视图 identifier 不再承载 aux_idx（图元 id
    不入产品）——原 aux_idx 解析删除（下游绘制未消费该字段）。
    """
    p = Path(lite_dir) / "fault_attitude_point_view.geojson"
    if not p.exists():
        return []
    doc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for ft in doc.get("features", []):
        pr = ft["properties"]
        x, y = ft["geometry"]["coordinates"][:2]
        dip_txt = pr.get("observedValue")
        dip = None
        try:
            dip = float(dip_txt) if dip_txt not in (None, "", "unknown") else None
        except (TypeError, ValueError):
            dip = None
        out.append({
            "x": x, "y": y,
            "az": float(pr.get("symbolRotation") or 0.0),
            "dip": dip,
            "mode": pr.get("description") or "",
            "sds_uri": pr.get("featureOfInterest_uri"),
        })
    return out


def classify_mode(desc: str) -> str:
    """模式标签 → dip_only / full / reverse / normal / none。
    none=存疑等无运动指示（2026-09-29 修：原兜底 normal 使「点近线侧别
    不可判」存疑组误画正断层双短线）。"""
    if "仅倾向" in desc:
        return "dip_only"
    if "倾向-倾角" in desc:
        return "full"
    if "逆断层" in desc:
        return "reverse"
    if "正断层" in desc:
        return "normal"
    return "none"


def _seg_frame_m(coords_m, s_m: float):
    """米空间折线上弧长 s_m 处的 (点, 单位切向, 左单位法线, 总弧长)。"""
    n = len(coords_m)
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + math.hypot(coords_m[i][0] - coords_m[i - 1][0],
                                        coords_m[i][1] - coords_m[i - 1][1]))
    total = acc[-1]
    s_m = min(max(s_m, 0.0), total)
    j = 0
    while j < n - 2 and acc[j + 1] < s_m:
        j += 1
    span = acc[j + 1] - acc[j] or 1e-9
    t = (s_m - acc[j]) / span
    px = coords_m[j][0] + (coords_m[j + 1][0] - coords_m[j][0]) * t
    py = coords_m[j][1] + (coords_m[j + 1][1] - coords_m[j][1]) * t
    tx = (coords_m[j + 1][0] - coords_m[j][0]) / span
    ty = (coords_m[j + 1][1] - coords_m[j][1]) / span
    return (px, py), (tx, ty), (-ty, tx), total


def draw_fault_measure_points(ax, points, sds_gdf, *, lon_m: float, lat_m: float,
                              meters_per_px: float | None = None,
                              arrow_len_px: float = 16.0,
                              barb_len_px: float = 7.0,
                              tick_along_m: float = 700.0,
                              dip_fontsize: float = 3.5,
                              eq_fontsize: float = 6.0,
                              color=RED, zorder: int = 16) -> dict:
    """按用户方案绘制全部测量点；返回逐模式计数+不变量校验统计。

    样式 100% 对齐 pymapgis render_fault_aux_layer（箭头=主线+燕尾、
    双短线=「=」字形、注释=右侧智能偏移）；尺寸按像素经 meters_per_px
    换算（区分经/纬每度米数，与 pdf_writer 同一做法）。
    sds_gdf: 断层层（度几何，FEATUREID 键）。"""
    counts = {"dip_only": 0, "full": 0, "reverse": 0, "normal": 0,
              "none": 0,  # 存疑组：箭头保留、无运动双短线
              "arrows": 0, "dip_texts": 0, "ticks": 0, "seg_missing": 0,
              "tick_ortho_max_dev": 0.0, "side_violations": 0}
    seg_by_srcid = {}
    for _, r in sds_gdf.iterrows():
        fid = r.get("FEATUREID")
        if fid is not None:
            seg_by_srcid[str(fid)] = r.geometry

    # 像素长度 → 地面米（优先调用方按最终图幅几何算好的值；缺省按当前轴估计，
    # 与 pdf_writer L1155-1165 同一回退链）
    if meters_per_px is None:
        x0l, x1l = ax.get_xlim()
        try:
            w_px = ax.get_window_extent().width
        except Exception:
            w_px = 0
        if not w_px:
            w_px = ax.figure.get_size_inches()[0] * ax.figure.dpi
        meters_per_px = (x1l - x0l) * lon_m / w_px if w_px else 30.0
    arrow_len_m = arrow_len_px * meters_per_px
    barb_len_m = barb_len_px * meters_per_px

    def to_m(x, y):
        return x * lon_m, y * lat_m

    def to_deg(xm, ym):
        return xm / lon_m, ym / lat_m

    for p in points:
        mode = classify_mode(p["mode"])
        counts[mode] += 1
        x0m, y0m = to_m(p["x"], p["y"])
        rad = math.radians(p["az"])
        dx, dy = math.sin(rad), math.cos(rad)
        # ① 箭头线（全部模式；pymapgis 样式：主线 lw=0.4 + 端部燕尾 ±150°）
        x0, y0 = p["x"], p["y"]
        exm, eym = x0m + dx * arrow_len_m, y0m + dy * arrow_len_m
        ex, ey = to_deg(exm, eym)
        ax.plot([x0, ex], [y0, ey], color=color, linewidth=0.4,
                zorder=zorder, solid_capstyle="butt")
        for ang in (math.radians(150), math.radians(-150)):
            ca, sa = math.cos(ang), math.sin(ang)
            bx_m = dx * ca - dy * sa
            by_m = dx * sa + dy * ca
            bx_, by_ = to_deg(exm + bx_m * barb_len_m, eym + by_m * barb_len_m)
            ax.plot([ex, bx_], [ey, by_], color=color, linewidth=0.4,
                    zorder=zorder, solid_capstyle="butt")
        counts["arrows"] += 1
        # ② 倾角注释（full 恒有；reverse/normal 有数值时有）——pymapgis 右侧
        # 智能偏移（margin + 文字盒投影）、随箭头旋转而字体水平
        if p["dip"] is not None and mode != "dip_only":
            rx, ry = dy, -dx  # 顺 dip 右手侧（米制单位向量）
            txt = str(int(float(p["dip"])))
            w_m = max(len(txt), 1) * 180.0    # 3.5pt 数字宽 ≈180m/字
            h_m = 310.0                       # 3.5pt 字高 ≈310m
            margin_m = 100.0
            off_m = (margin_m + (w_m / 2) * abs(rx) + (h_m / 2) * abs(ry))
            t_m = arrow_len_m / 2.0
            tx_, ty_ = to_deg(x0m + dx * t_m + rx * off_m,
                              y0m + dy * t_m + ry * off_m)
            ax.text(tx_, ty_, txt, color=color, fontsize=dip_fontsize,
                    rotation=0, ha="center", va="center", zorder=zorder + 1)
            counts["dip_texts"] += 1
        # ③ 逆/正：断层两侧一定距离处放置双短线（pymapgis 样式：「=」字形）
        if mode in ("reverse", "normal"):
            srcid = str(p["sds_uri"]).rsplit("/", 1)[-1]
            seg = seg_by_srcid.get(srcid)
            if seg is None:
                counts["seg_missing"] += 1
                continue
            coords_m = [to_m(cx, cy) for cx, cy in seg.coords]
            # 垂足弧长（米空间最近点参数搜索）
            best_s, best_d = 0.0, 1e18
            total_len = _seg_frame_m(coords_m, 0.0)[3]
            for k in range(101):
                s_k = total_len * k / 100.0
                (px, py), _, _, _ = _seg_frame_m(coords_m, s_k)
                d = math.hypot(px - x0m, py - y0m)
                if d < best_d:
                    best_s, best_d = s_k, d
            _, (tx, ty), (nx, ny), _ = _seg_frame_m(coords_m, best_s)
            dip_left = (dx * nx + dy * ny) > 0
            want_left = dip_left if mode == "normal" else not dip_left
            for sgn in (-1.0, 1.0):
                s = best_s + sgn * tick_along_m
                (bx0, by0), (ttx, tty), (tnx, tny), _ = _seg_frame_m(coords_m, s)
                side_sign = 1.0 if want_left else -1.0
                nx_s, ny_s = tnx * side_sign, tny * side_sign
                # 「=」自段上锚点沿图面法线向目标侧延展（笔画⊥断层）
                ang_eq = math.degrees(math.atan2(ny_s / lat_m, nx_s / lon_m))
                bx_, by_ = to_deg(bx0, by0)
                ax.text(bx_, by_, "=", fontsize=eq_fontsize, color=color,
                        rotation=ang_eq, rotation_mode="anchor",
                        ha="left", va="center", zorder=zorder)
                counts["ticks"] += 1
                # 不变量校验：法线⊥切向夹角≈90°；绘制侧别=期望侧别
                dot = abs(nx_s * ttx + ny_s * tty)
                dev = abs(90.0 - math.degrees(math.acos(min(max(dot, 0.0), 1.0))))
                counts["tick_ortho_max_dev"] = max(counts["tick_ortho_max_dev"], dev)
                # 侧别实证：法线·dip 方向——normal 应同侧(>0)、reverse 应异侧(<0)
                side_dot = nx_s * dx + ny_s * dy
                if (mode == "normal" and side_dot <= 0) or \
                   (mode == "reverse" and side_dot >= 0):
                    counts["side_violations"] += 1
    return counts
