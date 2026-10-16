# -*- coding: utf-8 -*-
"""LDZOFBB098.WL 断层性质线解析（2026-10-14 产品化入包，K46C001003 裁定链；
2026-10-16 三阶段架构重构——用户裁定评估落地）。

**三阶段架构（2026-10-16 用户裁定：形状+空间组合先行、归属后置）**：
  ① 形状分类：纯内禀（直线/J 钩/缓弯长件），零参照——fam_entry 不再
    触碰断层，#185 案最近股抽签无法在分类阶段发生；
  ② 空间组合：a 对=平行短线对（同向差≤20°、中距≤800m）、b 对=短线杆
    +J 钩头（≤500m）、楔形=共点组合（≤20m，成员先纯最近归属再测
    ∥/斜交）——配对不设蓝族前提（原 blue 闸降为第三阶段的语义赋值闸）；
  ③ 归属+语义赋值：`_strand_cands`（候选股表：垂足投影距升序）+
    `_attr`（多股择优：最近股语义吻合→用之；不吻合而在 prefer_m(300m)
    内有吻合股→择优（#185 案机制根治：弃 88m 非蓝股、取 108m 蓝域股）；
    皆无→存疑登记）。蓝族 rel∈(70,110)°=产状合成点（a/b 对）、
    ∥域≤30°=走滑钩（z 算法旋向）、斜域=存疑不产出。
  产物 schema 不变（synth components/slip rows 同构）——auxchain/gzeeb
  零改动；裁定册两例成为回归锚（#185+#186 应被阶段②自动捕获）。

**定位（2026-10-14 用户定版）**：本层是**断层辅助点/性质点的线状补充载体**——
与点层 LDZOFBB099.WT 同义异载体，补充同一五类合法集（上盘运动方向指示 a/
倾向指示 b/走滑钩·左行/走滑钩·右行/倾角注记）：线层 a 对=双短线、b 对=
杆+箭头头、J 钩（∥域）=走滑钩——合成点注入 auxchain 与点层同权判别、
走滑判定写回 fault_entities 同域聚合。

**形状主轴分类（2026-10-13/14 用户裁定）**：形状自身为第一轴（无参照依赖、
走向交汇区免疫——三阶段架构后真正实现）：
  · 直线族（2 顶点或全转折≤30° 短件）= 产状构件（a 双短线杆 / b 箭杆）
  · J 钩族（|主转折|>30°，实测 133–164° 倒刺回折）= 走滑指示线（∥域）
    或 b 箭头头（斜/⊥域，与杆配对）
  · 缓弯长件（全转折≤30° 且 >500m）= 编图残留物/错误（2026-10-14 用户
    图面核实裁定；不入任何解析池、不删源数据、登记在案）

**配对**：a 对=平行短线对（同向差≤20°、中距≤800m）；b 对=短线杆
+J 钩头（中距≤500m，头形状闸=直线不得充头，#87 案）；裁定配对册
`data/line_aux_pair_overrides_<key>.json` 强制配对（冲突登记不覆盖）。

**共点楔形组合钩（#235+#236 案，用户裁定）**：未配对直线短件端点共点
（≤20m）且一臂∥断层一臂斜交 = 走滑钩拆画——按走滑约定解析。

**走滑解析（2026-10-14 用户裁定定版，逐字规格）**：LDZOFBB098.WL 解析出
的走滑钩**严格按照「从杆臂远离倒刺臂的端点指向接近倒刺臂的端点为运动
方向」**解析断层运动方向和性质——单件钩：杆臂=主转折 vertex 入段（∥ 断层
者为杆，倒刺折于杆末端）；组合钩：∥ 臂为杆、斜交臂为倒刺，运动=杆自由端
→共点端。S=宿主段定向走向、σ=钩盘侧别（S 向左侧 +1）、m_along=杆向沿 S
分量符号、**左行 ⇔ m_along=−σ**。多主转折复杂形→存疑不冒进；宿主归因=
多股择优（≤500m，实体号经 fault_entities 表）。

产物：
  · `_line_aux_synth_<key>.csv`  合成 a/b 点（auxchain 注入消费）
  · `_line_aux_slip_<key>.csv`   逐钩走滑证据 + 逐断层判定

CLI: python -m geosciml4china.calibrate.lineaux --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pyproj

from ..sheets import get_sheet

# —— 形状/配对常量（K46C001003 实证标定；舰队校准待办）——
SHAPE_TURN_DEG = 30.0      # 直线/J 钩 转折分界
COMPANION_LEN_M = 500.0    # 直线族长件→编图残留域
A_PAIR_MAX_M = 800.0       # a 对中距上限
A_PAIR_PARALLEL_DEG = 20.0
B_PAIR_MAX_M = 500.0       # b 对（杆-头）中距上限
COMPOSITE_ORIGIN_M = 20.0  # 组合钩共点容差
SLIP_TURN_DEG = 90.0       # 走滑倒刺回折下限
SLIP_PARALLEL_DEG = 30.0   # 走滑杆 ∥ 断层 容差（物理闸；30°——
                            # 实测极值 #1 为 26°，25° 会误拦裁定态成员）
SLIP_DIST_MAX_M = 500.0    # 宿主归因距离闸
SIDE_NOISE_M = 20.0        # 侧别噪声（贴线不可判）
_CATEGORIES = {"断层性质"}  # 类目词过滤（舰队变体词扩展待办）
_BLUE_LO, _BLUE_HI = 70.0, 110.0   # ⊥域（产状蓝族）


def _az(dx, dy):
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _coords_of(g):
    t = g["type"]
    c = g["coordinates"]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return c
    return []


def _shape(c):
    """形状分类（2026-10-13/14 裁定；10-16 双顶点长度闸修复——#260/000261
    案：2 顶点 1235m 直线原经 nv==2 捷径绕过 500m 长件闸混入直线池，
    与"长件=编图残留"裁定相悖；现 2 顶点同样受 COMPANION_LEN_M 约束）：
    straight / hook / companion。"""
    nv = len(c)
    length = sum(math.hypot(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
                 for i in range(nv - 1))
    if nv == 2:
        return "straight" if length <= COMPANION_LEN_M else "companion"
    turns = []
    for i in range(1, nv - 1):
        a1 = _az(c[i][0] - c[i - 1][0], c[i][1] - c[i - 1][1])
        a2 = _az(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
        turns.append((a2 - a1 + 180) % 360 - 180)
    if any(abs(t) > SHAPE_TURN_DEG for t in turns):
        return "hook"
    return "straight" if length <= COMPANION_LEN_M else "companion"


def _strand_cands(pt, faults, k=6, max_m=2500.0):
    """归属后置·候选股表：全部断层段按垂足投影距升序取前 k（超 max_m 截断）。

    返回 [(dist, seg_idx, S, foot)]——三阶段架构（2026-10-16 用户裁定）
    第二阶段的归属输入：分类（形状+组合）先行、断层参照后置，候选集供
    多股择优（_attr）消除走向交汇区最近股抽签（#185 案根治）。"""
    cands = []
    for si, pp in enumerate(faults):
        best = None  # (dist, S_of_foot_pair, foot_xy)
        for i in range(len(pp) - 1):
            dx = pp[i + 1][0] - pp[i][0]
            dy = pp[i + 1][1] - pp[i][1]
            L2 = dx * dx + dy * dy
            if L2 == 0:
                continue
            t = max(0.0, min(1.0, ((pt[0] - pp[i][0]) * dx
                                   + (pt[1] - pp[i][1]) * dy) / L2))
            fx = pp[i][0] + t * dx
            fy = pp[i][1] + t * dy
            d = math.hypot(pt[0] - fx, pt[1] - fy)
            if best is None or d < best[0]:
                best = (d, _az(dx, dy), (fx, fy))
        if best is not None and best[0] <= max_m:
            cands.append((best[0], si, best[1], best[2]))
    cands.sort(key=lambda z: z[0])
    return cands[:k]


def _attr(cands, a0, family, prefer_m=300.0):
    """归属择优（三阶段架构第三阶段入口）：family ∈ {"blue","par",None}。
    blue=⊥域 rel∈(70,110)（产状蓝族）；par=∥域 rel≤SLIP_PARALLEL_DEG
    （走滑物理闸）；None=纯最近（楔形成员归因等无语义偏好的场景）。
    最近股吻合→(cand,"nearest")；最近股不吻合而在 prefer_m 内有吻合股
    →择优 (cand,"prefer")（#185 案机制）；皆无→(None,"none")（存疑）。"""
    if not cands:
        return None, "none"

    def _rel(S):
        r = (a0 - S) % 180.0
        return min(r, 180.0 - r)

    def _ok(S):
        if family == "blue":
            return 70.0 < _rel(S) < 110.0
        if family == "par":
            return _rel(S) <= SLIP_PARALLEL_DEG
        return True

    if _ok(cands[0][2]):
        return cands[0], "nearest"
    d0 = cands[0][0]
    for c in cands[1:]:
        if c[0] > d0 + prefer_m:
            break
        if _ok(c[2]):
            return c, "prefer"
    return None, "none"


def calibrate_lineaux(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    root = sh.root
    outdir = Path(out_dir) if out_dir else root

    # 幅级形状常量注册册（2026-10-16 舰队校准通道落地——"K46C001003 实证标定；
    # 舰队校准待办"的正式机制化）：data/line_aux_shape_semantics_<key>.json
    # 顶层数值键覆盖模块默认。J44C004003 中刺带案：64° 倒刺走滑钩用户图面
    # 确认（#325/000326）→ slip_turn_deg=60 纳入 61-90° 带；无键幅默认 90 不变。
    _SHAPE_OV = {}
    for _sp in (root / "data" / f"line_aux_shape_semantics_{sheet_key}.json",
                root / f"line_aux_shape_semantics_{sheet_key}.json"):
        if _sp.exists():
            try:
                _SHAPE_OV = json.loads(_sp.read_text(encoding="utf-8"))
            except Exception:
                _SHAPE_OV = {}
            break
    _slip_turn = float(_SHAPE_OV.get("slip_turn_deg", SLIP_TURN_DEG))
    # a 对要素杆长上限（2026-10-16 #260/000261 用户裁定"明显太长不能作 a
    # 要素"机制化）：默认 None 不设限；注册值生效——J44 实证成功 a 件
    # p90=261m/max=278m，注册 300m；双短线=短线对的语义闸
    _a_max = _SHAPE_OV.get("a_elem_max_m")
    _a_max = float(_a_max) if _a_max else None
    if _slip_turn != SLIP_TURN_DEG:
        print(f"幅级形状常量: slip_turn_deg={_slip_turn:.0f}°"
              f"（注册册覆盖默认 {SLIP_TURN_DEG:.0f}°）")

    fp = root / "geojson" / "L0" / "LDZOFBB098.WL.geojson"
    if not fp.exists():
        print(f"无 LDZOFBB098.WL 层——线层解析跳过（{sheet_key}）")
        return {"pairs": 0, "slip": 0, "note": "no_layer"}

    feats = json.load(open(fp, encoding="utf-8"))["features"]
    wl3p = root / "geojson" / "L0" / "LDZOFBA003.WL.geojson"
    faults, tf, inv, epsg = [], None, None, None
    if wl3p.exists():
        wl3 = json.load(open(wl3p, encoding="utf-8"))["features"]
        allx = [c[0] for f in wl3 for p in _coords_of(f["geometry"]) for c in p]
        if allx:
            lon0 = sum(allx) / len(allx)
            epsg = 32600 + int((lon0 + 180) / 6) + 1
            tf = pyproj.Transformer.from_crs(4326, epsg,
                                             always_xy=True).transform
            inv = pyproj.Transformer.from_crs(epsg, 4326,
                                              always_xy=True).transform
            faults = [[tf(x, y) for x, y in part]
                      for f in wl3 for part in _coords_of(f["geometry"])
                      if len(part) >= 2]
    ent_p = root / f"fault_entities_{sheet_key}.csv"
    seg2fid = ({int(r.seg_idx): r.fault_id
                for _, r in pd.read_csv(ent_p).iterrows()}
               if ent_p.exists() else {})

    def nearest_fault(pt):
        """最近断层段：返回 (距离, 段idx, 定向走向S, 垂足)。"""
        best = None
        for si, pp in enumerate(faults):
            for i in range(len(pp) - 1):
                dx = pp[i + 1][0] - pp[i][0]
                dy = pp[i + 1][1] - pp[i][1]
                L2 = dx * dx + dy * dy
                if L2 == 0:
                    continue
                t = max(0.0, min(1.0, ((pt[0] - pp[i][0]) * dx
                                       + (pt[1] - pp[i][1]) * dy) / L2))
                fx = pp[i][0] + t * dx
                fy = pp[i][1] + t * dy
                d = math.hypot(pt[0] - fx, pt[1] - fy)
                if best is None or d < best[0]:
                    best = (d, si, _az(dx, dy), (fx, fy))
        return best

    def side_of(pt, S, foot):
        svx, svy = math.sin(math.radians(S)), math.cos(math.radians(S))
        return 1 if svx * (pt[1] - foot[1]) - svy * (pt[0] - foot[0]) > 0 else -1

    def fam_entry(f):
        # 三阶段架构（2026-10-16 用户裁定）第一阶段：纯形状内禀特征——
        # 不再计算最近断层/rel/蓝族（参照全部后置到第三阶段 _strand_cands
        # + _attr 多股择优），消除 #185 案最近股抽签误拆。
        _parts = _coords_of(f["geometry"])
        if len(_parts) != 1:
            if _parts:
                print(f"⚠ 多部件性质线#{f['properties'].get('_src_id')}: "
                      f"{len(_parts)} 部件——存疑不解析")
            return None
        c = [tf(x, y) for x, y in _parts[0]]
        if len(c) < 2:
            return None
        nv = len(c)
        a0 = _az(c[1][0] - c[0][0], c[1][1] - c[0][1])
        mx = sum(p[0] for p in c) / nv
        my = sum(p[1] for p in c) / nv
        _len = sum(math.hypot(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
                   for i in range(nv - 1))
        return {"id": str(f["properties"].get("_src_id")), "c": c, "nv": nv,
                "shape": _shape(c), "a0": a0, "mid": (mx, my), "len": _len}

    lines = []
    for f in feats:
        if f["properties"].get("CHFCCD") not in _CATEGORIES:
            continue
        e = fam_entry(f)
        if e is not None:
            lines.append(e)
    n_total = len(lines)
    companions = [x for x in lines if x["shape"] == "companion"]
    if companions:
        print(f"编图残留长件（裁定域）: {sorted(x['id'] for x in companions)}"
              f" 不入解析池")
    pool = [x for x in lines if x["shape"] != "companion"]
    shorts = [x for x in pool if x["shape"] == "straight"]
    hooks = [x for x in pool if x["shape"] == "hook"]
    print(f"断层性质线: {n_total}（解析池 {len(pool)}：直线 {len(shorts)} / "
          f"J钩 {len(hooks)}）")

    used = set()
    pairs_a, pairs_b = [], []

    # —— 裁定配对册（2026-10-13/14 用户裁定通道；2026-10-16 优先级提升：
    # 裁定先于自然配对消费构件——J44C004003 #304+#305 案：自然 b 对抢占
    # 后裁定"构件已被占"无法落地；裁定=最高优先，与码义裁定层级同精神）——
    forced_slip = []
    ovr_p = root / "data" / f"line_aux_pair_overrides_{sheet_key}.json"
    if ovr_p.exists():
        ovr = json.loads(ovr_p.read_text(encoding="utf-8"))
        for pk, pe in ovr.get("pairs", {}).items():
            ids = [str(x) for x in pe["members"]]
            # 2026-10-16 裁定复活通道（#232 案）：成员查找扩到全类目线
            # （lines 含 companion——用户裁定可覆盖形状域，长件复活为
            # 合法构件；缺席仍如实告警不执行）
            mems = [next((x for x in lines if x["id"] == i), None) for i in ids]
            if any(m is None for m in mems):
                print(f"⚠ 裁定配对 {pk}: 构件缺席——未执行")
                continue
            d = math.hypot(mems[0]["mid"][0] - mems[1]["mid"][0],
                           mems[0]["mid"][1] - mems[1]["mid"][1])
            role = pe.get("role")
            if role == "a":
                pairs_a.append((mems[0], mems[1], d))
                used.update(ids)
                print(f"裁定配对 {pk}: {'+'.join(ids)} → a 对（{d:.0f}m）")
            elif role == "b":
                # 2026-10-16 J44C004003 #304+#305 案新增：裁定 b 箭头线
                # （members 序：箭杆构件在前——可为 J 钩，其入段即箭杆，
                # 如 钩#304 入段 az170°=箭杆+双倒刺=出段+另边直件#305）
                pairs_b.append((mems[0], mems[1], d))
                used.update(ids)
                print(f"裁定配对 {pk}: {'+'.join(ids)} → b 箭头线"
                      f"（{d:.0f}m，杆件在前）")
            elif role == "slip_hook":
                used.update(ids)
                forced_slip.append((pk, mems, pe))
                print(f"裁定配对 {pk}: {'+'.join(ids)} → 组合走滑钩")

    # —— a 对：平行短线对 ——
    for i, s1 in enumerate(shorts):
        if s1["id"] in used or (_a_max and s1["len"] > _a_max):
            continue
        for s2 in shorts:
            if s2["id"] <= s1["id"] or s2["id"] in used:
                continue
            if _a_max and s2["len"] > _a_max:
                continue
            d = math.hypot(s1["mid"][0] - s2["mid"][0],
                           s1["mid"][1] - s2["mid"][1])
            if d > A_PAIR_MAX_M:
                continue
            dd = abs(s1["a0"] - s2["a0"]) % 180.0
            if min(dd, 180 - dd) > A_PAIR_PARALLEL_DEG:
                continue
            pairs_a.append((s1, s2, d))
            used.add(s1["id"])
            used.add(s2["id"])
            break

    # —— b 对：杆 + J 钩头（全族，最近优先）——
    # 2026-10-16 杆源解耦（#233 存疑根因修复）：杆候选=全部直线形件
    # （含越 500m 残留闸的直线长件——#232/552m 案：b 箭杆不受"短线"语义
    # 约束，质量由中距≤500m+头形状闸+阶段③蓝族归属三重把守；弯曲线长件
    # shape≠straight 仍排除。残留闸只管 a 对/单件走滑的短线语义域）
    _b_shafts = [x for x in lines if x["shape"] == "straight"]
    for s in _b_shafts:
        if s["id"] in used:
            continue
        best = None
        for p in hooks:
            if p["id"] in used:
                continue
            d = math.hypot(s["mid"][0] - p["mid"][0],
                           s["mid"][1] - p["mid"][1])
            if d > B_PAIR_MAX_M:
                continue
            if best is None or d < best[0]:
                best = (d, p)
        if best:
            d, p = best
            pairs_b.append((s, p, d))
            used.add(s["id"])
            used.add(p["id"])

    # （原自然配对后裁定册位置已前移——裁定优先消费构件）

    # —— 共点楔形组合钩探测（#235+#236 案规则化） ——
    free_straights = [x for x in pool
                      if x["shape"] == "straight" and x["id"] not in used]
    compo = []
    for i, s1 in enumerate(free_straights):
        if s1["id"] in used:
            continue
        for s2 in free_straights:
            if s2["id"] <= s1["id"] or s2["id"] in used:
                continue
            best_ep = min(
                math.hypot(e1[0] - e2[0], e1[1] - e2[1])
                for e1 in (s1["c"][0], s1["c"][-1])
                for e2 in (s2["c"][0], s2["c"][-1]))
            if best_ep > COMPOSITE_ORIGIN_M:
                continue
            # 三阶段：成员先归属（纯最近股），再以归属 S 测 ∥/斜交
            a1n, _w1 = _attr(_strand_cands(s1["mid"], faults), s1["a0"], None)
            a2n, _w2 = _attr(_strand_cands(s2["mid"], faults), s2["a0"], None)
            if a1n is None or a2n is None:
                continue
            par1 = min((s1["a0"] - a1n[2]) % 180.0,
                       180 - (s1["a0"] - a1n[2]) % 180.0)
            par2 = min((s2["a0"] - a2n[2]) % 180.0,
                       180 - (s2["a0"] - a2n[2]) % 180.0)
            if not ((par1 <= SLIP_PARALLEL_DEG) != (par2 <= SLIP_PARALLEL_DEG)):
                continue  # 须一臂∥一臂斜
            shaft, barb = (s1, s2) if par1 <= SLIP_PARALLEL_DEG else (s2, s1)
            used.add(s1["id"])
            used.add(s2["id"])
            compo.append((shaft, barb))
            print(f"共点楔形组合钩: 杆#{shaft['id']}+刺#{barb['id']}"
                  f"（端点距 {best_ep:.0f}m）")

    # —— 合成点（三阶段·第三阶段归属：对轴 az 蓝族择优归属）——
    rows = []
    _n_suspect = 0
    for s1, s2, d in pairs_a:
        x = (s1["mid"][0] + s2["mid"][0]) / 2
        y = (s1["mid"][1] + s2["mid"][1]) / 2
        lon, lat = inv(x, y)
        azp = (s1["a0"] + s2["a0"]) / 2.0
        att, how = _attr(_strand_cands((x, y), faults), azp, "blue")
        if att is None:
            _n_suspect += 1
            print(f"⚠ a 对{s1['id']}+{s2['id']}: 蓝族归属失败"
                  f"（最近股 rel∉(70,110)°）——存疑不产出")
            continue
        if how == "prefer":
            print(f"   a 对{s1['id']}+{s2['id']}: 多股择优归属"
                  f"（弃最近非蓝股，取 {att[0]:.0f}m 处蓝域股 #{att[1]}）")
        rows.append(dict(synth_id=900000 + len(rows), role="a", x=x, y=y,
                         lon=round(lon, 7), lat=round(lat, 7), dip_az="",
                         components=f"{s1['id']}+{s2['id']}",
                         pair_span=round(d, 0),
                         dist_fault=round(att[0], 1)))
    for s, p, d in pairs_b:
        x, y = s["mid"]
        att, how = _attr(_strand_cands((x, y), faults), s["a0"], "blue")
        if att is None:
            # 2026-10-16 箭头拓扑回退（#305+#304 / #303+#302 同模双案的用户
            # 裁定规则化）：b 倾向指示箭头=「钩线带杆」——钩入段即箭杆，
            # 配对直件为箭头帽另一边。杆 az 蓝族失败时回退试钩入段 az；
            # 双路皆否才存疑（诚实登记两路 rel）。
            _hx, _hy = p["mid"]
            att2, _how2 = _attr(_strand_cands((_hx, _hy), faults),
                                p["a0"], "blue")
            if att2 is None:
                _n_suspect += 1
                print(f"⚠ b 对{s['id']}+{p['id']}: 蓝族归属失败"
                      f"（杆 {s['a0']:.0f}° / 钩入段 {p['a0']:.0f}° 双路皆否）"
                      f"——存疑不产出")
                continue
            x, y = _hx, _hy
            att, how = att2, _how2
            print(f"   b 对{s['id']}+{p['id']}: 箭头拓扑回退归属"
                  f"（杆 {s['a0']:.0f}° 非蓝 → 钩入段 {p['a0']:.0f}° 蓝域，"
                  f"段{att[1]} {att[0]:.0f}m）")
        lon, lat = inv(x, y)
        dip = _az(x - att[3][0], y - att[3][1])
        rows.append(dict(synth_id=900000 + len(rows), role="b", x=x, y=y,
                         lon=round(lon, 7), lat=round(lat, 7),
                         dip_az=round(dip, 1),
                         components=f"{s['id']}+{p['id']}",
                         pair_span=round(d, 0), dist_fault=round(att[0], 1)))
    synth_p = outdir / f"_line_aux_synth_{sheet_key}.csv"
    if rows:
        pd.DataFrame(rows).to_csv(synth_p, index=False, encoding="utf-8-sig")
        print(f"合成点: {len(rows)}（a {sum(r['role'] == 'a' for r in rows)} / "
              f"b {sum(r['role'] == 'b' for r in rows)}）→ {synth_p.name}")
    elif synth_p.exists():
        synth_p.unlink()
        print("合成点清零（无配对，删陈旧）")

    # —— 走滑解析（2026-10-14 精化约定定版） ——
    slip_rows = []

    def slip_row(single, shaft_a0, tip_a2, mid, seg, S, foot, tag, dist,
                 turn=None):
        sigma = side_of(mid, S, foot)
        m_along = 1 if math.cos(math.radians(shaft_a0 - S)) > 0 else -1
        sense = "左行" if m_along == -sigma else "右行"
        fid = seg2fid.get(seg, "?")
        return {"hook_id": tag, "fault": fid, "seg": seg,
                "strike_S": round(S, 1), "side": sigma,
                "shaft_a0": round(shaft_a0, 1),
                # 真实主转折（2026-10-14 #25 审计案：旧公式
                # tip_a2−shaft_a0+180 为尖向约定残留，倒刺钩误报 ~20°）
                "turn": round(turn, 1) if turn is not None else "",
                "tip_a2": round(tip_a2, 1), "motion_az": round(shaft_a0, 1),
                "motion_along": m_along, "sense": sense,
                # 2026-10-16 P4 微优化：dist 由调用方 nf[0] 传入——
                # 原在此处重算 nearest_fault（每钩一次全幅 O(N×M) 扫描）
                "dist_m": round(dist, 1)}

    for x in pool:
        if x["shape"] != "hook" or x["id"] in used:
            continue
        c = x["c"]
        # 主转折 vertex（多顶点容许，#143 案）
        big = []
        for i in range(1, len(c) - 1):
            a1 = _az(c[i][0] - c[i - 1][0], c[i][1] - c[i - 1][1])
            a2 = _az(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
            big.append((i, (a2 - a1 + 180) % 360 - 180))
        big = [(i, t) for i, t in big if abs(t) > _slip_turn]
        # 2026-10-16 连续顶点聚簇（#325 案）：相邻过闸转折=同一物理弯的
        # 曲线化近似（回折跨多顶点）——聚簇取最大者为唯一主转折；非相邻
        # 多簇仍是真复杂形（多倒刺 S 钩）→存疑不冒进（#143 精神保留）
        if big:
            clusters = [[big[0]]]
            for _it in big[1:]:
                if _it[0] - clusters[-1][-1][0] <= 2:
                    clusters[-1].append(_it)
                else:
                    clusters.append([_it])
            if len(clusters) != 1:
                print(f"⚠ 钩#{x['id']}: 多主转折复杂形——存疑不解析")
                continue
            ib, t = max(clusters[0], key=lambda z: abs(z[1]))
        else:
            continue
        a0 = _az(c[ib][0] - c[ib - 1][0], c[ib][1] - c[ib - 1][1])
        a2 = _az(c[ib + 1][0] - c[ib][0], c[ib + 1][1] - c[ib][1])
        mid = (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))
        # 三阶段：∥ 物理闸由第三阶段多股择优承载（#185 案机制：
        # 最近股不∥ 时在 prefer_m 内找 ∥ 股；皆无→存疑）
        att, how = _attr(_strand_cands(mid, faults, max_m=SLIP_DIST_MAX_M * 2),
                         a0, "par")
        if att is None or att[0] > SLIP_DIST_MAX_M:
            _rel0 = None
            if att is None:
                _c0 = _strand_cands(mid, faults, k=1)
                if _c0:
                    _r = (a0 - _c0[0][2]) % 180.0
                    _rel0 = min(_r, 180.0 - _r)
            print(f"⚠ 钩#{x['id']}: "
                  + (f"宿主超距（>{SLIP_DIST_MAX_M:.0f}m）——存疑"
                     if att is not None else
                     (f"杆斜交断层（最近股 rel={_rel0:.0f}°> "
                      f"{SLIP_PARALLEL_DEG:.0f}°）——存疑不解析"
                      if _rel0 is not None else "无断层候选——存疑"))
                  )
            continue
        if how == "prefer":
            print(f"   钩#{x['id']}: 多股择优归属（弃最近非∥股，"
                  f"取 {att[0]:.0f}m 处∥域股 #{att[1]}）")
        slip_rows.append(slip_row(True, a0, a2, mid, att[1], att[2], att[3],
                                  x["id"], att[0], turn=t))

    for shaft, barb in compo:
        # 运动方向=杆远离倒刺端→接近倒刺端（共点）
        org = min((math.hypot(shaft["c"][0][0] - e[0], shaft["c"][0][1] - e[1]),
                   math.hypot(shaft["c"][-1][0] - e[0], shaft["c"][-1][1] - e[1]),
                   e) for e in (barb["c"][0], barb["c"][-1]))[2]
        free = (shaft["c"][0] if org == shaft["c"][-1] else shaft["c"][-1])
        m_az = _az(org[0] - free[0], org[1] - free[1])
        mid = ((shaft["mid"][0] + barb["mid"][0]) / 2,
               (shaft["mid"][1] + barb["mid"][1]) / 2)
        nf = nearest_fault(mid)
        if nf is None or nf[0] > SLIP_DIST_MAX_M:
            print(f"⚠ 组合钩 {shaft['id']}+{barb['id']}: 宿主超距——存疑")
            continue
        slip_rows.append(slip_row(False, m_az, barb["a0"], mid, nf[1],
                                  nf[2], nf[3], f"{shaft['id']}+{barb['id']}",
                                  nf[0]))

    for pk, mems, pe in forced_slip:
        shaft, barb = mems  # 裁定序：杆在前
        org = min(((math.hypot(shaft["c"][0][0] - e[0], shaft["c"][0][1] - e[1])
                    + math.hypot(shaft["c"][-1][0] - e[0], shaft["c"][-1][1] - e[1]), e)
                   for e in (barb["c"][0], barb["c"][-1])), key=lambda z: z[0])[1]
        free = (shaft["c"][0] if org == shaft["c"][-1] else shaft["c"][-1])
        m_az = _az(org[0] - free[0], org[1] - free[1])
        mid = ((shaft["mid"][0] + barb["mid"][0]) / 2,
               (shaft["mid"][1] + barb["mid"][1]) / 2)
        nf = nearest_fault(mid)
        if nf is None or nf[0] > SLIP_DIST_MAX_M:
            continue
        row = slip_row(False, m_az, barb["a0"], mid, nf[1], nf[2], nf[3],
                       "+".join(m["id"] for m in mems), nf[0])
        exp = pe.get("verdict", "")
        if exp and exp != row["sense"]:
            print(f"⚠ 裁定组合钩 {pk}: 解析「{row['sense']}」≠ 注册期望"
                  f"「{exp}」——冲突登记")
        slip_rows.append(row)

    slip_p = outdir / f"_line_aux_slip_{sheet_key}.csv"
    if slip_rows:
        sdf = pd.DataFrame(slip_rows)
        sdf.to_csv(slip_p, index=False, encoding="utf-8-sig")
        from collections import Counter
        agg = {}
        for f_, g in sdf.groupby("fault"):
            cnt = Counter(g["sense"])
            agg[f_] = ("一致" if len(cnt) == 1 else "**冲突**", dict(cnt))
        n_conf = sum(1 for k, (s_, _) in agg.items() if "冲突" in s_)
        print(f"走滑解析: {len(slip_rows)} 钩 / {len(agg)} 断层"
              f"（冲突 {n_conf}）→ {slip_p.name}")
        for f_, (s_, cnt) in sorted(agg.items()):
            print(f"  {f_}: {cnt} {s_}")
    elif slip_p.exists():
        slip_p.unlink()
        print("走滑解析清零（无钩，删陈旧）")

    return {"total": n_total, "a_pairs": len(pairs_a),
            "b_pairs": len(pairs_b), "slip": len(slip_rows),
            "companions": len(companions)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c lineaux")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    print(calibrate_lineaux(args.sheet, out_dir=args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
