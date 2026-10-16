# -*- coding: utf-8 -*-
"""断层辅助点字形几何通道（2026-10-16 PoC 证实后产品化）。

SLIB 破解（pymapgis.slib，1996 符号全索引）使"不看符号码、看字形长
什么样"成为可能——PoC 实证三类注册码几何完全分型：
  1281 = 两条平行纵线（字面双短线）；1894 = T 形（走向纵线+倾向横刺，
方位 ⊥ 对）；1827 = 闭合方块（角砾岩标记）。

本模块：
  glyph_features(geom)   symbol_geometries 输出 → 形状特征量
  classify_glyph(feats)  → double_tick / strike_dip / closed_marker /
                           single_stroke / complex / empty
  load_glyph_classes()   批量解码 {符号码: 类}
  audit_registry()       注册表机器对账（registered family vs glyph
                         class——report-only，矛盾交人工，不自动改册）

auxchain 接线（glyph 兜底）：未注册符号码经字形分类归一 a/b 池——
checks 注记+单列统计+置信降级；幅无 SLIB 时整通道跳过（退化为现行
符号码注册表，同 lineaux 缺席语义）。
"""
import math

CLASS_TO_FAMILY = {"double_tick": "1281", "strike_dip": "1894"}
PERP_LO, PERP_HI = 80.0, 100.0   # ⊥ 对窗口（PoC 实证 90°）
PAR_DEG = 10.0                   # 平行容差


# 走滑钩判窗（168/1630 实证：锐角钩 ~120°、复杂轮廓掉头 164°）
HOOK_TURN_LO, HOOK_TURN_HI = 60.0, 160.0
HOOK_MAX_PTS = 8          # 锐角钩顶点上限（168=4）
COMPLEX_MIN_PTS = 20      # 复杂轮廓顶点下限（1630=176）
COMPLEX_TURN = 150.0      # 复杂轮廓掉头角下限


def glyph_features(geom: dict) -> dict:
    """symbol_geometries 输出 → 形状特征量（几何坐标系无关）。

    2026-10-16 晚扩展：走滑钩两类（hook_glyph/hook_glyph_complex）——
    点层钩符号 168=4 顶点锐角折线（两次 ~120° 弯）、1630=双 88 顶点
    镜像轮廓（164° 掉头）实测定版。max_turn 对全部子路径统计。
    """
    subs = geom.get("subpaths") or []
    circles = geom.get("circles") or []
    strokes = []
    closed_polys = 0
    n_points = 0
    max_turn = 0.0
    same_sign_bend = 0.0
    closed_fill = 0.0
    closed_circ = 0.0
    seen = set()
    dup_pairs = 0
    for sp in subs:
        pts = sp.get("points") or []
        if len(pts) < 2:
            continue
        n_points += len(pts)
        key = tuple((round(x, 3), round(y, 3)) for x, y in pts)
        if key in seen:
            dup_pairs += 1
        seen.add(key)
        segs = []
        for a in range(len(pts) - 1):
            dx = pts[a + 1][0] - pts[a][0]
            dy = pts[a + 1][1] - pts[a][1]
            segs.append(math.degrees(math.atan2(dx, dy)) % 360.0)
        turns = [((segs[k + 1] - segs[k] + 180) % 360) - 180
                 for k in range(len(segs) - 1)]
        for k in range(len(turns) - 1):
            # 同号连弯（C 形钩特征——168 型 turns [-119,-122]；
            # 方块标记为交替号 1827 型 [+126,-126]）
            if (turns[k] * turns[k + 1] > 0
                    and abs(turns[k]) >= HOOK_TURN_LO
                    and abs(turns[k + 1]) >= HOOK_TURN_LO):
                same_sign_bend = max(same_sign_bend,
                                     min(abs(turns[k]), abs(turns[k + 1])))
        for t in turns:
            max_turn = max(max_turn, abs(t))
        closed = sp.get("closed") or (pts[0] == pts[-1])
        if closed:
            closed_polys += 1
            # 闭合多边形填充率（钩 sliver vs 胖标记的区分量——
            # 168 C 钩实测瘦长低填充；1827 方块高填充）
            aa = 0.0
            for k in range(len(pts) - 1):
                aa += pts[k][0] * pts[k + 1][1] - pts[k + 1][0] * pts[k][1]
            area = abs(aa) / 2.0
            xs2 = [q[0] for q in pts]
            ys2 = [q[1] for q in pts]
            bb_area = max((max(xs2) - min(xs2)), 1e-6) *                 max((max(ys2) - min(ys2)), 1e-6)
            # 圆度 P²/A：钩 sliver 瘦高（168 实测 ~35）、胖标记低
            # （方块 ~16）——比填充率更稳的区分量
            per = 0.0
            for k in range(len(pts) - 1):
                per += math.hypot(pts[k + 1][0] - pts[k][0],
                                  pts[k + 1][1] - pts[k][1])
            circ = (per * per / area) if area > 1e-9 else 0.0
            closed_circ = min(closed_circ, circ) if closed_circ and circ                 else (circ or closed_circ)
            closed_fill = min(closed_fill, area / bb_area) if closed_fill                 else area / bb_area
            continue
        dx = pts[-1][0] - pts[0][0]
        dy = pts[-1][1] - pts[0][1]
        strokes.append(math.degrees(math.atan2(dx, dy)) % 180.0)
    bb = geom.get("bbox") or [0, 0, 0, 0]
    w = bb[2] - bb[0]
    h = bb[3] - bb[1]
    return {
        "n_strokes": len(strokes),
        "azimuths": [round(a, 1) for a in strokes],
        "closed_polys": closed_polys + len(circles),
        "n_circles": len(circles),
        "aspect": (max(w, h) / max(min(w, h), 1e-6)) if (w or h) else 0.0,
        "bbox_mm": [round(v, 3) for v in bb],
        "n_points": n_points,
        "max_turn": round(max_turn, 1),
        "same_sign_bend": round(same_sign_bend, 1),
        "closed_fill": round(closed_fill, 3),
        "closed_circ": round(closed_circ, 1),
        "dup_pairs": dup_pairs,
    }


def classify_glyph(f: dict) -> str:
    """规则分类器（PoC 三分型+走滑钩两型定版；复杂形不冒进→complex）。"""
    if f["n_strokes"] == 0 and f["closed_polys"] == 0 and f["max_turn"] == 0:
        return "empty"
    # 复杂轮廓（原 hook_glyph_complex 类——2026-10-16 用户裁定：子图 1630
    # 不是走滑钩；多顶点大角度掉头轮廓不构成钩语义，如实归 complex）
    if f["n_points"] >= COMPLEX_MIN_PTS and f["max_turn"] >= COMPLEX_TURN:
        return "complex"
    # 两笔划分支优先（1894/1281 回归保护：⊥/平行判据先于钩构件）
    if f["n_strokes"] == 2:
        a, b = f["azimuths"][0], f["azimuths"][1]
        dd = abs(a - b) % 180.0
        if PERP_LO <= dd <= PERP_HI:
            return "strike_dip"     # T 形（⊥ 对）
        if dd <= PAR_DEG or dd >= 180.0 - PAR_DEG:
            return "double_tick"    # 平行双短线
        # 钩构件（238/239 型，2026-10-16 用户裁定"配对即钩、两码各居
        # 一侧"）：两笔斜角带（15-85°）或一笔 60-160° 折的扁小符号——
        # ⊥/平行对已在上方分流，斜角带为钩构件独占
        if (15 <= dd <= 85 and f["n_points"] <= 6
                and 0 < f["aspect"] <= 6):
            return "hook_component"
        if f["max_turn"] >= HOOK_TURN_LO and f["n_points"] <= HOOK_MAX_PTS:
            return "hook_component"
        return "complex"
    # 锐角钩·开折线型：少顶点、单弯 60-160°
    if (f["closed_polys"] == 0 and f["n_strokes"] <= 2
            and HOOK_TURN_LO <= f["max_turn"] <= HOOK_TURN_HI
            and f["n_points"] <= HOOK_MAX_PTS):
        return "hook_glyph"
    # 闭合小折角标记（168/1827 同型——单体字形不可分：圆度 20.8/20.9、
    # 同号弯 119/117 双样本等同；168 的"钩"语义来自成对空间结构（auxchain
    # 空间识别，符号列本就仅作佐证）——闭合锐角钩不独立判 hook，
    # 如实归 closed_marker；钩语义交由空间层（准确性优先·两样本过拟合红线）
    if f["n_strokes"] == 0:
        return "closed_marker"
    if f["n_strokes"] == 1:
        if f["closed_polys"]:
            return "closed_marker"
        return "single_stroke"
    return "complex"


def load_glyph_classes(lib, codes):
    """批量解码 {符号码(str): class}（解码失败→"empty"并如实保留）。"""
    from pymapgis.slib import symbol_geometries
    out = {}
    for c in codes:
        try:
            g = symbol_geometries(lib, int(c))
            out[str(c)] = classify_glyph(glyph_features(g))
        except Exception:
            out[str(c)] = "decode_failed"
    return out


def audit_registry(lib, registry: dict) -> list:
    """注册表机器对账：registered role/family vs glyph class。

    report-only——一致性/冲突逐行登记（conflict 交人工裁定，
    不自动改册；与「先验标定·矛盾交人工检核」总纲同构）。
    """
    fam_of = {"1281": "double_tick", "1894": "strike_dip"}  # 正典锚码恒审
    for c, e in registry.items():
        role = str(e.get("role", ""))
        fam = str(e.get("family", ""))
        if role == "tick_variant" and fam == "1281":
            fam_of[str(c)] = "double_tick"
        elif role == "arrow_variant" and fam == "1894":
            fam_of[str(c)] = "strike_dip"
        elif str(c) == "1281":
            fam_of[str(c)] = "double_tick"
        elif str(c) == "1894":
            fam_of[str(c)] = "strike_dip"
    classes = load_glyph_classes(lib, fam_of.keys())
    rows = []
    for c, expect in fam_of.items():
        got = classes.get(c, "decode_failed")
        rows.append({
            "symbol_no": c, "registered_class": expect,
            "glyph_class": got,
            "verdict": ("一致 ✓" if got == expect else
                        ("解码失败（挂账）" if got == "decode_failed"
                         else "冲突！——glyph≠注册（交人工裁定）")),
        })
    return rows
