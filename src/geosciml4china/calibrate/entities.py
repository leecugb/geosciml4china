"""断层实体归组（geosciml4china.calibrate 第 2 域移植，2026-09-29）。

移植自库尔干 _build_fault_entities.py（604 行归组引擎 v1，fault_group_logic.md 实施）：
  L1 命名归组（GZEAB 同名，最强语义）→ L2 端点聚簇直接并链（10m/15°，有向守卫/
  三叉点唯一贯通豁免）→ L3 截断并链（2km/15°/覆盖≥80%/同类，T 触点守卫）→
  L3b 跨段衔接（断口+覆盖判据）→ 属性继承 + 链接级置信（实体=最弱链接，
  named=verified×multi_root / 几何=multi×multi_root / L0=unassessed）。
**aux 写回内置（A1 修复）**：三联体表存在时按 fault_id 聚合 aux_verdict/n_triplets
写回实体表（链阶段对称——英吉沙曾在 aux 审计写回、库尔干从未实现）。

辅助点归属判别建立在断层实体基础上（2026-09-29 用户裁定）：关联 v5/三联体/实体
侧别判别均以实体链为上下文——本模块是四步链第①步，输出即第②③④步的基础。

CLI: python -m geosciml4china.calibrate.entities --sheet <key>
     [--out DIR] [--triplets <csv>] [--triplet-attitude <csv>]
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from pymapgis.semantics import load_source_layer
from pymapgis.rendering.pdf_writer import _unit_age_rank

from ..sheets import get_sheet
from pymapgis.semantics.profile import get_profile


def calibrate_entities(sheet_key: str, out_dir=None,
                       triplets_csv: str | None = None,
                       triplet_attitude_csv: str | None = None) -> dict:
    """执行断层归组，返回统计。out_dir 缺省=图幅 root。"""
    sh = get_sheet(sheet_key)
    _lat0 = float(get_profile(sh.key).center_lat_hint)
    from pathlib import Path as _P
    _outdir = _P(out_dir) if out_dir is not None else sh.root
    _outdir.mkdir(parents=True, exist_ok=True)
    _triplets_csv = triplets_csv
    _attitude_csv = triplet_attitude_csv
    # 实体表文件名按图幅剖面（entities_csv 各幅不同：库尔干 fault_entities.csv /
    # 新幅 fault_entities_<key>.csv——materialize 依此装载）
    _ent_csv = get_profile(sh.key).entities_csv or "fault_entities.csv"
    # 图幅裁定登记册（2026-09-29 泛化优化）：<root>/data/fault_group_overrides_<key>.json
    # （root 兜底）承载 link_block（排除对列表）/l5_merges（人工合并段列表）——
    # 新幅裁定无需改代码。库尔干内建清单与登记册合并生效。
    import json as _json
    _ov = {}
    for _op in (sh.root / "data" / f"fault_group_overrides_{sh.key}.json",
                sh.root / f"fault_group_overrides_{sh.key}.json"):
        if _op.exists():
            _ov = _json.loads(_op.read_text(encoding="utf-8"))
            break
    _EXTRA_BLOCK = {frozenset(pair) for pair in _ov.get("link_block", [])}
    _EXTRA_MERGES = [list(g) for g in _ov.get("l5_merges", [])]

    def _out(name):
        return str(_outdir / name)

    LON_M = 111320.0 * math.cos(math.radians(_lat0))
    LAT_M = 111320.0

    faults = load_source_layer(str(sh.root), "LDZOFBA003.WL", graphic=False)
    sed = load_source_layer(str(sh.root), "LDZOFBB001.WP", graphic=False)
    ice_g = (load_source_layer(str(sh.root), "LDLYAAE002.WP", graphic=False)
             if (sh.root / "LDLYAAE002.WP").exists() or
             (sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson").exists()
             else __import__("geopandas").GeoDataFrame())

    fgeoms = faults.geometry.values
    N = len(fgeoms)
    coords_l = [list(g.coords) for g in fgeoms]
    sed = sed.assign(_age=sed["QDUECC"].map(_unit_age_rank))
    q_polys = [g for g, a in zip(sed.geometry.values, sed["_age"].values)
               if a is not None and a >= 1300]
    ice_u = ice_g.geometry.union_all() if len(ice_g) else None
    q_u = None
    if q_polys:
        from shapely.ops import unary_union
        q_u = unary_union(q_polys)

    parent = list(range(N))


    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x


    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra


    def strike(coords, which, k=3, win_m=None):
        """端部走向：默认固定 k 点（校准行为）；
        win_m 给定米数时用弧长窗口（2026-09-14 审计修复：
        弧长按米制逐段累计（dx·LON_M, dy·LAT_M），窗口端点按弧长**精确插值**
        而非吸附折点——原实现跨度随折点密度漂移 93~980m）。"""
        c = np.array(coords)
        if win_m is not None:
            diffs = np.diff(c, axis=0)
            seg = np.sqrt(((diffs * [LON_M, LAT_M]) ** 2).sum(axis=1))
            cum = np.concatenate([[0], np.cumsum(seg)])
            total = cum[-1]
            w = min(win_m, total * 0.9)
            arc = w if which == 0 else total - w
            j = int(np.searchsorted(cum, arc, side="right")) - 1
            j = max(0, min(j, len(c) - 2))
            t = 0.0 if seg[j] == 0 else (arc - cum[j]) / seg[j]
            p = c[j] * (1 - t) + c[j + 1] * t
            v = (p - c[0]) * [LON_M, LAT_M] if which == 0 \
                else (c[-1] - p) * [LON_M, LAT_M]
            return math.degrees(math.atan2(v[1], v[0]))
        k = min(k, len(c) - 1)
        v = c[k] - c[0] if which == 0 else c[-1] - c[-1 - k]
        return math.degrees(math.atan2(v[1] * LAT_M, v[0] * LON_M))


    def fold_diff(a, b):
        d = abs((a - b) % 180.0)
        return min(d, 180.0 - d)


    def departure(coords, which, k=3):
        """端点 → 体内的**有向**离去方向（度，自 +x 逆时针）。
        与无向走向（fold 180°）互补：用于区分"首尾延续"（两体分居
        接点/断口两侧，离去方向相反）与"同点同向延申的两条断层"
        （离去方向相同——分叉，不得并链，2026-09-14 用户定）。"""
        c = np.array(coords)
        k = min(k, len(c) - 1)
        v = c[k] - c[0] if which == 0 else c[-1 - k] - c[-1]
        return math.degrees(math.atan2(v[1] * LAT_M, v[0] * LON_M))


    def dir_diff(a, b):
        """有向角差，[0,180]。"""
        return abs((a - b + 180.0) % 360.0 - 180.0)


    def is_continuation(ca, wa, cb, wb, slack=150.0):
        """延续判定：两段体内方向在接点两侧反向（≥slack°）。
        同向（<180-slack°）→ 同点同向延申的分叉，不得并链。"""
        return dir_diff(departure(ca, wa), departure(cb, wb)) >= slack


    # ---------- L1 命名归组 ----------
    names = {}
    for i, row in faults.iterrows():
        nm = str(row.get("GZEAB") or "").strip()
        if nm:
            names.setdefault(nm, []).append(i)
    for nm, segs in names.items():
        for s in segs[1:]:
            union(segs[0], s)
    named_segs = {s for segs in names.values() for s in segs}  # L1 段（最强语义，后续规则避让）

    # ---------- 类型兼容规则（2026-09-08 用户定） ----------
    # 01（一般/未细分）与 04（推测）为通用码——与一切类型兼容；
    # 实体 type 展示值中优先级最低（有具体类型时永不被选为展示类型）
    GENERIC_TYPES = {"01", "04"}
    # 具体类型码全表（2026-09-29 英吉沙测试补：03 正/35 推覆/37 活动——
    # 原库尔干表缺此三码致 F056 型 35|02 实体 type 误取；库尔干无此三码→零影响）
    TYPE_PRIORITY = {"05": 50, "07": 50, "16": 50, "18": 50, "28": 50,
                     "31": 50, "41": 50, "02": 50, "03": 50, "35": 50,
                     "37": 50, "01": 10, "04": 10}
    # 具体类型间的跨类型并链许可（除通用码兼容外）：
    # 01↔05 已被通用码规则涵盖（01 通用，与一切兼容）
    TYPE_COMPAT: set = set()


    def type_ok(ta, tb):
        if ta == tb:
            return True
        # 通用码与一切类型兼容
        if ta in GENERIC_TYPES or tb in GENERIC_TYPES:
            return True
        return frozenset({ta, tb}) in TYPE_COMPAT

    # ---------- 端点度计算（供 L2 度约束） ----------
    ep_map = defaultdict(list)  # 网格键 → [(seg, which)]
    GRID = 0.001
    for ci, cs in enumerate(coords_l):
        for w, pt in ((0, cs[0]), (1, cs[-1])):
            key = (round(pt[0] / GRID), round(pt[1] / GRID))
            ep_map[key].append((ci, w))
    degree = {}
    for ci, cs in enumerate(coords_l):
        for w, pt in ((0, cs[0]), (1, cs[-1])):
            cnt = 0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for ci2, w2 in ep_map.get((round(pt[0] / GRID) + dx, round(pt[1] / GRID) + dy), []):
                        if ci2 != ci:
                            p2 = coords_l[ci2][0] if w2 == 0 else coords_l[ci2][-1]
                            if math.hypot((pt[0] - p2[0]) * LON_M, (pt[1] - p2[1]) * LAT_M) <= 10.0:
                                cnt += 1
            degree[(ci, w)] = cnt

    # ---------- L2 直接并链（端点聚簇 + 三叉点共线豁免） ----------
    # 全局链接排除清单（用户裁定，一切规则层不得并链）：
    # 218/216——2026-09-13 裁定交叉断层；2026-09-14 审计证实 218尾 贴于 216 内部
    # （触点距 216首 925m，同向延申的枝状分叉），L3 端点断口曾误桥其"923m 缺口"
    # （实为 216 自身段体）→ 漏洞修复：L3 亦查阅本清单 + T-触点守卫
    LINK_BLOCK = set(_EXTRA_BLOCK)  # 图幅登记册（2026-10-01 泛化：库尔干
    # 内联清单已迁入 fault_group_overrides_kurgan.json——代码零图幅分支）
    import os as _os_g
    if _os_g.environ.get("G4C_NO_MANUAL") == "1" or             _os_g.environ.get("G4C_NO_BLOCK") == "1":  # 泛化探针：空载排除清单
        LINK_BLOCK = set()

    def _interiors_cross(a, b):
        """切截/交叉检测（2026-09-29 泛化优化 G2）：两段几何的内部相交
        （交点≥2 或线段式相交）→ 交叉/切截关系，禁并——208/210（14° 接点
        切截）、6/7、43/61、83/87、240/233 人工裁定排除的几何通则化。"""
        ix = fgeoms[a].intersection(fgeoms[b])
        if ix.is_empty:
            return False
        if ix.geom_type == "Point":
            return False  # 单点=端点相接（贯通候选）
        if ix.geom_type in ("LineString", "MultiLineString"):
            return True   # 线段式相交=穿切
        return len(ix.geoms) >= 2  # MultiPoint≥2=端点之外另有交点

    l2_links = []  # (ci, w, cj, w2)——供"一端一链"端点占用登记
    used_ep = set()  # (seg_idx, which)——一端一链全局占用表（L2→L2c→L3 共用）

    # 2026-09-13 优化（254/267 裁定校准）：端部走向以 200m 弧长窗口为主判定，
    # k=3 固定点兜底（二者任一满足即并链，保证只增并、不拆分已验证组）。
    # 理由：共点接合处的"离去方向"应在统一米制尺度上量取；k=3 实际跨度随
    # 数字化密度浮动（254尾 490m / 267首 611m），会把局部共线（≤300m 走向
    # 完全一致）但 500m 尺度背向弯曲的弧形断层接合误判为斜交。

    # ---------- 端点聚簇：10m 内互达的端点属同一接点 ----------
    ep_par = {}


    def ep_find(x):
        while ep_par.setdefault(x, x) != x:
            ep_par[x] = ep_par[ep_par[x]]
            x = ep_par[x]
        return x


    def ep_union(a, b):
        ra, rb = ep_find(a), ep_find(b)
        if ra != rb:
            ep_par[rb] = ra


    _all_ends = [(ci, w) for ci in range(N) for w in (0, 1)]
    _ep_pt = {(ci, w): (coords_l[ci][0] if w == 0 else coords_l[ci][-1])
              for ci in range(N) for w in (0, 1)}
    for _i in range(len(_all_ends)):
        for _j in range(_i + 1, len(_all_ends)):
            if _all_ends[_i][0] == _all_ends[_j][0]:
                continue
            _p, _q = _ep_pt[_all_ends[_i]], _ep_pt[_all_ends[_j]]
            if math.hypot((_p[0] - _q[0]) * LON_M, (_p[1] - _q[1]) * LAT_M) <= 10.0:
                ep_union(_all_ends[_i], _all_ends[_j])
    ep_clusters = defaultdict(list)
    for _e in _all_ends:
        ep_clusters[ep_find(_e)].append(_e)


    def _pair_ok(e1, e2, metric="any", tol=10.0):
        """两端点走向判定：metric='any' 窗口/k3 任一≤tol（L2 校准行为）；
        metric='win' 仅 200m 窗口（接点共线豁免的统一尺度）。"""
        (c1, w1), (c2, w2) = e1, e2
        dw = fold_diff(strike(coords_l[c1], w1, win_m=200),
                       strike(coords_l[c2], w2, win_m=200))
        if metric == "win":
            return dw <= tol, dw
        dk = fold_diff(strike(coords_l[c1], w1), strike(coords_l[c2], w2))
        return min(dw, dk) <= tol, min(dw, dk)


    for _root, _es in ep_clusters.items():
        if len(_es) < 2:
            continue
        if len(_es) == 2:
            # 经典 L2：两端点互达（等效原度=1），走向差任一尺度 ≤15°
            # （2026-09-14 用户定：10°→15° 放宽，215/216=14.5° 案）
            ok, dw2 = _pair_ok(_es[0], _es[1], metric="any", tol=15.0)
            if ok and _interiors_cross(_es[0][0], _es[1][0]):
                ok = False  # G2 切截/交叉禁并（几何通则）
            if ok and frozenset((_es[0][0], _es[1][0])) in LINK_BLOCK:
                continue  # 用户裁定排除对：一切规则层不得并链
            # 有向守卫（2026-09-14 用户定）：同点同向延申的分叉不并
            if ok and not is_continuation(coords_l[_es[0][0]], _es[0][1],
                                          coords_l[_es[1][0]], _es[1][1]):
                ok = False
            if ok and find(_es[0][0]) != find(_es[1][0]):
                union(_es[0][0], _es[1][0])
                l2_links.append((_es[0][0], _es[0][1], _es[1][0], _es[1][1], dw2))
                used_ep.add(_es[0])
                used_ep.add(_es[1])
            continue
        # 三叉及以上接点（2026-09-13，16/30 裁定校准）：
        # 存在唯一贯通方向时放行共线对——该对走向差（200m 窗口）≤15°
        # （2026-09-21 用户裁定：10°→15° 与 L2 放宽对齐），
        # 且接点上其余端点与二者的走向差均 >15°（防 Y 型歧义）；
        # 每端在同一接点最多配对一次（兼容 X 型双贯通）。
        _matched = set()
        _pairs = []
        for _a in range(len(_es)):
            for _b in range(_a + 1, len(_es)):
                ok, dw = _pair_ok(_es[_a], _es[_b], metric="win", tol=15.0)
                if ok and not _interiors_cross(_es[_a][0], _es[_b][0]):
                    _pairs.append((dw, _es[_a], _es[_b]))  # G2 交叉禁并
        _pairs.sort(key=lambda t: t[0])
        for dw, e1, e2 in _pairs:
            if e1 in _matched or e2 in _matched:
                continue
            ambiguous = False
            for e3 in _es:
                if e3 in (e1, e2):
                    continue
                _, d13 = _pair_ok(e1, e3, metric="win")
                _, d23 = _pair_ok(e2, e3, metric="win")
                if min(d13, d23) <= 15.0:
                    ambiguous = True
                    break
            if ambiguous:
                continue
            # 有向守卫（2026-09-14 用户定）：同点同向延申的分叉不并
            if not is_continuation(coords_l[e1[0]], e1[1], coords_l[e2[0]], e2[1]):
                continue
            if find(e1[0]) == find(e2[0]):
                continue
            union(e1[0], e2[0])
            _matched.add(e1)
            _matched.add(e2)
            l2_links.append((e1[0], e1[1], e2[0], e2[1], dw))
            used_ep.add(e1)
            used_ep.add(e2)

    # ---------- L2c T-共线归并（2026-09-13 用户裁定：整体删除，逻辑简化） ----------
    # 该层曾将"段端点打在另一段内部且方向相近"的段归并（191/194 等），
    # 实践中交叉断层混入风险高（6/7、43/61、83/87 经用户逐一裁定排除），
    # 共线关系改由 L5 人工裁定承载（如 [191,193,194,195]）。
    l2c_links = []  # 已停用，仅保留供审计兼容


    def _touches_interior(b, pt, tol_m=10.0, end_m=50.0):
        """端点 pt 是否打在段 b 的内部（距其两端点 >end_m 的折线 tol_m 内）。"""
        if fgeoms[b].distance(Point(pt)) * LON_M > tol_m:
            return False
        return min(
            math.hypot((pt[0] - coords_l[b][0][0]) * LON_M,
                       (pt[1] - coords_l[b][0][1]) * LAT_M),
            math.hypot((pt[0] - coords_l[b][-1][0]) * LON_M,
                       (pt[1] - coords_l[b][-1][1]) * LAT_M)) > end_m


    # 第三者重叠检测的空间索引（2026-09-14）：bbox 网格预筛，
    # 避免 O(候选×采样×全库) 暴力扫描
    _OV_CELL = 0.005
    _ov_grid = defaultdict(list)
    for _ci in range(N):
        _b = fgeoms[_ci].bounds
        for _gx in range(int(_b[0] / _OV_CELL), int(_b[2] / _OV_CELL) + 1):
            for _gy in range(int(_b[1] / _OV_CELL), int(_b[3] / _OV_CELL) + 1):
                _ov_grid[(_gx, _gy)].append(_ci)


    def _third_overlap(a, b, p1, p2, n=5, tol_m=60.0, frac=0.6):
        """断口连线 ≥frac 采样点落在第三者段体 tol_m 内 → True。"""
        hits = 0
        tol_deg = tol_m / LON_M
        for t in np.linspace(0.1, 0.9, n):
            q = Point(p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
            gx, gy = int(q.x / _OV_CELL), int(q.y / _OV_CELL)
            cands = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cands.update(_ov_grid.get((gx + dx, gy + dy), []))
            for ci in cands:
                if ci in (a, b):
                    continue
                if fgeoms[ci].distance(q) * LON_M <= tol_m:
                    hits += 1
                    break
        return hits >= math.ceil(n * frac)

    # ---------- L3 截断并链 ----------


    def entity_type_of(segs, faults_df, fgeoms_):
        """实体展示类型：具体类型中取链长最长段类型；全为通用码时取 01。"""
        spec = [s for s in segs if str(faults_df.iloc[s]["GZEEB"]) not in GENERIC_TYPES]
        pool = spec if spec else list(segs)
        return max(
            pool,
            key=lambda s: (TYPE_PRIORITY.get(str(faults_df.iloc[s]["GZEEB"]), 30),
                           fgeoms_[s].length),
        ), pool


    def covered_frac(p1, p2, n=7):
        line = LineString([p1, p2])
        hit = 0
        for t in np.linspace(0.08, 0.92, n):
            q = line.interpolate(float(t), normalized=True)
            ok = False
            if q_u is not None and q_u.intersects(q):
                ok = True
            elif ice_u is not None and ice_u.intersects(q):
                ok = True
            if ok:
                hit += 1
        return hit / n


    l3_links = []
    # 一端一链约束（2026-09-13 用户定，严格执行版）：
    # 一个断层段的一端只能链接一条断层，不得同时链接多条。
    # used_ep 全局占用表在 L2/L2c 接受时即登记（见上文），
    # L3 候选全量收集 → 按（档位, 断口距）排序 → 贪心接受，
    # 触及已占用端点者拒绝；接受后立即登记。

    candidates = []  # (tier, gap, a, b, w1, w2, frac)
    for a in range(N):
        for b in range(a + 1, N):
            if find(a) == find(b):
                continue
            if frozenset((a, b)) in LINK_BLOCK:
                continue  # 用户裁定排除对：一切规则层不得并链
            if not type_ok(str(faults.iloc[a]["GZEEB"]), str(faults.iloc[b]["GZEEB"])):
                continue
            if _interiors_cross(a, b):
                continue  # G2 切截/交叉禁并
            best = None
            for w1, p1 in ((0, coords_l[a][0]), (1, coords_l[a][-1])):
                for w2, p2 in ((0, coords_l[b][0]), (1, coords_l[b][-1])):
                    d = math.hypot((p1[0] - p2[0]) * LON_M, (p1[1] - p2[1]) * LAT_M)
                    if best is None or d < best[0]:
                        best = (d, p1, p2, w1, w2)
            gap, p1, p2, w1, w2 = best
            if gap <= 0:
                continue
            # T-触点守卫（2026-09-14，216/218 审计）：
            # 任一端点打在对方内部（>50m 距其端点）时，二者关系属 T 型接触
            # （归 L5 裁定），不构成 L3 断口桥接候选——否则 L3 会把"宿主干
            # 自身段体"误作断口桥接（218尾贴于 216 内部 925m 处案）。
            if _touches_interior(a, p2) or _touches_interior(b, p1):
                continue
            # 第三者重叠守卫（2026-09-14，215/218 审计）：
            # 断口连线 ≥60% 落在第三者段体 60m 内 → "断口"实为另一断层的
            # 段体，不构成可桥接的空地（215尾→218尾 连线全程沿 216 段体案）。
            if _third_overlap(a, b, p1, p2):
                continue
            # 有向守卫（2026-09-14 用户定）：同点同向延申的两条断层不并——
            # 延续要求 a 体在断口后方（dep_a ≈ -gap）且 b 体在断口前方
            # （dep_b ≈ +gap）；二者同向延申为分叉，拒绝。
            if dir_diff(departure(coords_l[a], w1),
                        math.degrees(math.atan2((p1[1] - p2[1]) * LAT_M,
                                                (p1[0] - p2[0]) * LON_M))) > 60.0:
                continue  # a 体伸入断口走廊（同向）
            if dir_diff(departure(coords_l[b], w2),
                        math.degrees(math.atan2((p2[1] - p1[1]) * LAT_M,
                                                (p2[0] - p1[0]) * LON_M))) > 60.0:
                continue  # b 体回折入断口走廊（同向）
            gap_ang = math.degrees(math.atan2((p2[1] - p1[1]) * LAT_M, (p2[0] - p1[0]) * LON_M))
            da = fold_diff(gap_ang, strike(coords_l[a], w1))
            db = fold_diff(gap_ang, strike(coords_l[b], w2))
            # L3 标准/扩展档（扩展：2026-09-08 用户定，走向差 ≤5° 时断口放宽至 4km）
            if gap <= 2000:
                strike_ok = da <= 15.0 and db <= 15.0
            elif gap <= 4000:
                strike_ok = da <= 5.0 and db <= 5.0
            else:
                strike_ok = False
            if strike_ok:
                frac = covered_frac(p1, p2)
                if frac >= 0.8:
                    candidates.append((0, gap, a, b, w1, w2, frac))
                continue
            # L3b 弧形覆盖桥接（2026-09-13，180/184 与 281-288-303-308-309 裁定校准）：
            # 断口近乎全被第四系/冰雪覆盖时，覆盖段内走向不可见，弧形断层允许
            # 两侧走向不延续——走向放宽至 一侧≤15° 且另一侧≤26°，
            # 作为补偿收紧断口至 ≤3km、覆盖 ≥85%（6/7 采样点）。
            # 被否对照组：199/200（覆盖0%）、303/309（覆盖57%）均不触发本规则。
            if gap <= 3000:
                frac = covered_frac(p1, p2)
                if frac >= 0.85 and min(da, db) <= 15.0 and max(da, db) <= 26.0:
                    candidates.append((1, gap, a, b, w1, w2, frac))

    candidates.sort(key=lambda c: (c[0], c[1]))
    for tier, gap, a, b, w1, w2, frac in candidates:
        if find(a) == find(b):
            continue
        if (a, w1) in used_ep or (b, w2) in used_ep:
            continue  # 端点已被更早（更优）链接占用
        union(a, b)
        used_ep.add((a, w1))
        used_ep.add((b, w2))
        l3_links.append((a, b, round(gap), round(frac, 2), "L3" if tier == 0 else "L3b", w1, w2))

    # ---------- L5 人工裁定（规则扩展后重放，2026-09-08） ----------
    # L5 人工裁定合并清单——库尔干专属（段号为其域内索引；新幅空表，
    # 2026-09-29 泛化守卫：新幅的跨段合并裁定另行入册）
    L5_MERGES = ([] if _os_g.environ.get("G4C_NO_MANUAL") == "1"
                 or _os_g.environ.get("G4C_NO_L5") == "1"
                 else _EXTRA_MERGES)  # 图幅登记册（库尔干清单已迁 JSON）
    for grp in L5_MERGES:
        import os
        if os.environ.get("NO_L5") == "1":  # 规则覆盖度自检：NO_L5=1 时跳过人工裁定
            break
        for s in grp[1:]:
            union(grp[0], s)

    # ---------- 归组与属性继承 ----------
    # 一端一链全链路审计（严格执行版）：任何端点在 L2/L2c/L3 链接中
    # 出现次数不得超过 1，发现即报错退出（L1/L5 为实体级语义归并，
    # 不占端点，不在审计范围）。
    from collections import Counter

    _ep_use = Counter()
    for ci, w, cj, w2, _dw2 in l2_links:
        _ep_use[(ci, w)] += 1
        _ep_use[(cj, w2)] += 1
    for a, w, b, he, _dw in l2c_links:
        _ep_use[(a, w)] += 1
        _ep_use[(b, he)] += 1  # T-触点归属的宿主端点同样计入
    for _lnk in l3_links:
        _ep_use[(_lnk[0], _lnk[5])] += 1
        _ep_use[(_lnk[1], _lnk[6])] += 1
    _viol = {e: c for e, c in _ep_use.items() if c > 1}
    if _viol:
        print(f"!! 一端一链审计失败：{len(_viol)} 个端点被多次链接 {_viol}")
        sys.exit(1)
    print(f"一端一链审计通过：L2 {len(l2_links)} 对 + L2c {len(l2c_links)} 对 + "
          f"L3/L3b {len(l3_links)} 对，端点零冲突")

    groups = defaultdict(list)
    for i in range(N):
        groups[find(i)].append(i)


    def total_len(segs):
        return sum(fgeoms[s].length for s in segs)


    entities = []
    for cid, segs in sorted(groups.items(), key=lambda kv: -total_len(kv[1])):
        gtypes = [str(faults.iloc[s]["GZEEB"]) for s in segs]
        main_seg, _ = entity_type_of(segs, faults, fgeoms)
        main_type = str(faults.iloc[main_seg]["GZEEB"])
        nm = next((str(faults.iloc[s]["GZEAB"]).strip() for s in segs
                   if str(faults.iloc[s]["GZEAB"] or "").strip()), "")
        entities.append({
            "segs": segs, "name": nm, "type": main_type,
            "types": "/".join(sorted(set(gtypes))),
            "len_km": total_len(segs) * LON_M / 1000,
            "n": len(segs),
        })

    entities.sort(key=lambda e: -e["len_km"])
    print(f"=== 归组结果：310 段 → {len(entities)} 个断层实体 ===")
    print(f"命名组（L1）: {sum(1 for e in entities if e['name'])}")
    print(f"多段组: {sum(1 for e in entities if e['n'] > 1)}，最大组 {max(e['n'] for e in entities)} 段")
    print(f"L3 截断并链: {len(l3_links)} 对 {l3_links}")
    print()
    print("=== 前 15 大断层实体 ===")
    for k, e in enumerate(entities[:15]):
        print(f"  F{k + 1:03d} {e['name'] or '-':8s} 类型 {e['types']:8s} {e['len_km']:.0f}km {e['n']}段")

    # 验证基准（库尔干专属——本幅裁定样例；新幅跳过，2026-09-29 泛化守卫）
    if sh.key == "kurgan":
        seg_of = {}
        for k, e in enumerate(entities):
            for s in e["segs"]:
                seg_of[s] = k + 1
        print()
        print("=== 验证基准 ===")
        print(f"  seg10/23 同实体: {seg_of.get(10) == seg_of.get(23)}（F{seg_of.get(10):03d}）")
        print(f"  seg168/170 同实体: {seg_of.get(168) == seg_of.get(170)}（F{seg_of.get(168):03d}）")
        for nm in ("F9", "F48", "F50"):
            ids = {seg_of[s] for s in names[nm]}
            print(f"  {nm} 完整不拆: {len(ids) == 1}（{sorted(ids)}）")

    # 输出 fault_entities.csv

    # ---------- 影子置信度（统一框架 S×I×F，2026-09-27 裁定参数；旧列不动） ----------
    # 链接级 C（L2=端点几何×走向两独立根类；L3/L3b=几何×覆盖）；实体级 =
    # 最弱链接继承（命名通道存在时与几何互证升 multi_root）；L5=人工裁定钉顶；
    # L0 孤段 unassessed。证据登记 _fault_entity_links.csv。
    from pymapgis.semantics.confidence import evaluate, fit_from_residual

    _link_bd = {}   # frozenset({a,b}) → ConfBreakdown
    _link_rows = []
    # tol = 2×准入闸：证据零点在准入闸两倍处——合法链（过闸）F≥0.5 落 suspect 以上，
    # 不入 conflict（D7：归组域无 F=0 硬违反；闸内位置是质量梯度非矛盾）。
    for ci, w, cj, w2, dw in l2_links:
        bd = evaluate("multi", "multi_root", fit_from_residual(dw, 30.0),
                      reasons=(f"L2 走向差 {dw:.1f}°/15°",),
                      fit_note=f"res={dw:.2f}° tol=30°(2×闸)")
        _link_bd[frozenset((ci, cj))] = bd
        _link_rows.append({"kind": "L2", "seg_a": ci, "seg_b": cj,
                           "evidence": f"走向差 {dw:.1f}°/15°",
                           "C": bd.C, "band": bd.band})
    for a, b, gap, frac, tier, w1, w2 in l3_links:
        tol = 4000.0 if tier == "L3" else 6000.0
        bd = evaluate("multi", "multi_root", fit_from_residual(gap, tol),
                      reasons=(f"{tier} 断口 {gap:.0f}m/{tol / 2:.0f}m 覆盖 {frac}",),
                      fit_note=f"res={gap:.0f} tol={tol:.0f}(2×闸)")
        _link_bd[frozenset((a, b))] = bd
        _link_rows.append({"kind": tier, "seg_a": a, "seg_b": b,
                           "evidence": f"断口 {gap:.0f}m 覆盖 {frac}",
                           "C": bd.C, "band": bd.band})

    _l5_segs = set()
    for _grp in L5_MERGES:
        _l5_segs.update(_grp)

    _ent_bd = {}
    for k, e in enumerate(entities):
        segs = set(e["segs"])
        if segs & _l5_segs:
            _ent_bd[k] = evaluate("adjudicated", adjudicated=True,
                                  reasons=("L5 人工裁定归并",))
            continue
        links = [bd for p, bd in _link_bd.items() if p <= segs]
        named = bool(e["name"])
        if not links:
            if named:
                _ent_bd[k] = evaluate("verified", "single", 1.0,
                                      reasons=("图面命名（单通道）",))
            else:
                _ent_bd[k] = evaluate("code_read", "single", 1.0,
                                      evaluated=False, reasons=("L0 孤段",))
            continue
        f_min = min(bd.F for bd in links)
        if named:
            _ent_bd[k] = evaluate("verified", "multi_root", f_min,
                                  reasons=(f"命名+{len(links)} 链接互证",),
                                  fit_note=f"weakest F={f_min:.2f}")
        else:
            _ent_bd[k] = evaluate("multi", "multi_root", f_min,
                                  reasons=(f"{len(links)} 几何链接",),
                                  fit_note=f"weakest F={f_min:.2f}")

    _link_df = pd.DataFrame(_link_rows)
    _link_df.to_csv(_out("_fault_entity_links.csv"), index=False, encoding="utf-8-sig")

    with open(_out(_ent_csv), "w", encoding="utf-8-sig") as fh:
        fh.write("seg_idx,fault_id,role,name,type,len_km,method,"
                 "confidence_u,conf_breakdown_u,conf_band_u\n")
        for k, e in enumerate(entities):
            method = "L1" if e["name"] else ("L2" if e["n"] > 1 else "L0")
            bd = _ent_bd[k]
            # breakdown 用分号分隔键值（原生 CSV 写入，避逗号列歧义）
            bd_txt = (f"S={bd.S};I={bd.I};F={bd.F};C={bd.C};src={bd.source_tier};"
                      f"ind={bd.independence};reasons={'|'.join(bd.reasons)}")
            for s in e["segs"]:
                fh.write(f"{s},F{k + 1:03d},main,{e['name']},{e['type']},"
                         f"{e['len_km']:.1f},{method},{bd.C},{bd_txt},{bd.band}\n")
    print(f"输出: {_out(_ent_csv)} + {_out("_fault_entity_links.csv")}")


    # ---------- aux 写回（A1 修复，2026-09-29 链阶段对称统一） ----------
    # 英吉沙链在 aux 审计写回 aux_verdict/n_triplets；库尔干链从未实现——此处
    # 统一内置：三联体表存在时按 fault_id 聚合写回实体表两列。
    _tri_p = sh.root / _triplets_csv if _triplets_csv else None
    _att_p = sh.root / _attitude_csv if _attitude_csv else None
    _ent = pd.read_csv(_out(_ent_csv), dtype=str)
    _nmap = {}
    if _tri_p and _tri_p.exists():
        _tdf = pd.read_csv(_tri_p, dtype=str)
        if "fault_id" in _tdf.columns:
            _nmap = _tdf.groupby("fault_id").size().to_dict()
    _vmap = {}
    if _att_p and _att_p.exists():
        _adf = pd.read_csv(_att_p, dtype=str)
        if "fault_id" in _adf.columns and "verdict" in _adf.columns:
            _vmap = _adf.groupby("fault_id")["verdict"].first().to_dict()
    _ent["aux_verdict"] = [_vmap.get(f, "") for f in _ent["fault_id"]]
    _ent["n_triplets"] = [_nmap.get(f, 0) for f in _ent["fault_id"]]
    _ent.to_csv(_out(_ent_csv), index=False, encoding="utf-8-sig")
    _nv = _ent.loc[_ent["aux_verdict"] != "", "fault_id"].nunique()
    print(f"aux 写回: {_nv} 实体有 verdict / {int(_ent['n_triplets'].astype(int).sum())} 三联体")

    return {
        "entities": len(entities),
        "links": len(_link_df),
        "aux_entities": _nv,
        "n_triplets": int(_ent["n_triplets"].astype(int).sum()),
        "out_dir": str(_outdir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c entities")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None, help="输出目录（缺省=图幅 root）")
    ap.add_argument("--triplets", default=None, help="三联体明细表文件名（写回 n_triplets）")
    ap.add_argument("--triplet-attitude", default=None, help="实体三联体判别表文件名（写回 aux_verdict）")
    args = ap.parse_args()
    stats = calibrate_entities(args.sheet, out_dir=args.out,
                               triplets_csv=args.triplets,
                               triplet_attitude_csv=args.triplet_attitude)
    print("归组完成:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
