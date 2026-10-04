# -*- coding: utf-8 -*-
"""走滑钩对空间识别独立审计（2026-10-01 用户指令「审计 geosciml4china 具备
独立识别解析走滑断层辅助点的能力」）。

方法=独立重算：以 shapely 原语重新实现候选池/最近链归属/空间签名（距带
[50,500]m/异侧/垂足纵向≤7km）/贪心配对/旋向 z 符号/区间段号——与生产
_fault_hooks_<key>.csv 逐对对照。共享输入（WT/断层/实体表/归属表），
不共享识别代码路径。

判据：
  ① 候选池=辅助点类别中未被 a/b/注释角色消费的点（符号无关、符号 0 排除）；
  ② 识别零符号依赖（静态行证：识别路径无 238/239/1539/1882/1883 字面量）；
  ③ 逐对双向核验（生产对必独立重现 ∧ 独立对必在生产）；
  ④ 签名不变量：带内/异侧/≤7km；负样本（同侧/超带/超距）不成对；
  ⑤ 区间语义：foot_arc 区间与 segs 段号弧位范围重叠核验；
  ⑥ 旋向与码义互证（16/18 码段：右行/左行与钩旋向一致或如实张力）。
"""
import math
import os

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

# PyPI-minimal 守卫（2026-10-04 CI 泛化：PyPI mapgis2shp 仅含极简读取器，
# semantics 子包未发布——无完整栈环境整文件跳过）
_prof = pytest.importorskip("pymapgis.semantics.profile")
get_profile = _prof.get_profile

# 2026-10-04 用户裁定：审计测试以 jwss/jwsss 为测试项目；import 期
# skipif 标记——无数据机器（CI runner）优雅跳过
SHEETS = [
    pytest.param("jwsss", r"D:\jwsss", 39.5,
                 marks=pytest.mark.skipif(not os.path.isdir(r"D:\jwsss"),
                                          reason="jwsss 数据不在场")),
    pytest.param("jwss", r"D:\jwss", 38.5,
                 marks=pytest.mark.skipif(not os.path.isdir(r"D:\jwss"),
                                          reason="jwss 数据不在场")),
]

BAND = (50.0, 500.0)
MAX_FOOT_SEP = 7000.0
MIN_SIDE_M = 10.0
ASSIGN_WIN = 600.0


def _chain_fold(fl, ent):
    """独立实体链折叠（与判别审计同构的审计自有实现）。"""
    from shapely.geometry import LineString as _LS
    from shapely.ops import unary_union as _uu
    chains = {}
    for fid, sub in ent.groupby("fault_id"):
        idxs = [int(x) for x in sub["seg_idx"]]
        segs = {i: list(fl.geometry[i].coords) for i in idxs}
        if len(segs) == 1:
            chains[fid] = _LS(next(iter(segs.values())))
            continue
        eps = {(i, w): (c[0] if w == 0 else c[-1])
               for i, c in segs.items() for w in (0, 1)}
        used, parts = set(), []
        for (i, w), _p in eps.items():
            if (i, w) in used:
                continue
            used.add((i, 0))
            used.add((i, 1))
            coords = list(segs[i]) if w == 0 else list(reversed(segs[i]))
            cur = (i, 0 if w == 1 else 1)
            while True:
                nxt = None
                for (j, wj), pj in eps.items():
                    if j == cur[0] or (j, wj) in used:
                        continue
                    if (pj[0] - coords[-1][0]) ** 2 + (pj[1] - coords[-1][1]) ** 2 < 1e-8:
                        nxt = (j, wj)
                        break
                if nxt is None:
                    break
                j, wj = nxt
                used.add((j, 0))
                used.add((j, 1))
                cj = list(segs[j]) if wj == 0 else list(reversed(segs[j]))
                d_head = (cj[0][0] - coords[-1][0]) ** 2 + (cj[0][1] - coords[-1][1]) ** 2
                d_tail = (cj[-1][0] - coords[-1][0]) ** 2 + (cj[-1][1] - coords[-1][1]) ** 2
                if d_head > d_tail:
                    cj = list(reversed(cj))
                coords += cj[1:]
                cur = (j, 0 if wj == 1 else 1)
            parts.append(_LS(coords))
        u = _uu(parts) if len(parts) > 1 else parts[0]
        # 独立碎段最小缺口遍历序（发现 C 同口径：弧位基准依赖 part 顺序）
        if u.geom_type == "MultiLineString":
            from shapely.geometry import MultiLineString as _MLS
            _ps = list(u.geoms)
            if len(_ps) > 1:
                def _ends(g_):
                    return g_.coords[0], g_.coords[-1]

                def _d2(c1, c2):
                    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2

                def _greedy(ai, rev0):
                    pool = set(range(len(_ps)))
                    pool.discard(ai)
                    first = _ps[ai]
                    if rev0:
                        first = _LS(list(reversed(first.coords)))
                    order, cur, gap = [(ai, rev0)], first, 0.0
                    while pool:
                        tail = cur.coords[-1]
                        bi = min(pool, key=lambda i: min(
                            _d2(tail, _ends(_ps[i])[0]),
                            _d2(tail, _ends(_ps[i])[1])))
                        pool.discard(bi)
                        h_, t_ = _ends(_ps[bi])
                        if _d2(tail, t_) < _d2(tail, h_):
                            nxt = _LS(list(reversed(_ps[bi].coords)))
                            gap += _d2(tail, t_)
                            order.append((bi, True))
                        else:
                            nxt = _ps[bi]
                            gap += _d2(tail, h_)
                            order.append((bi, False))
                        cur = nxt
                    return order, gap

                best = None
                for _i in range(len(_ps)):
                    for _r in (False, True):
                        cand = _greedy(_i, _r)
                        if best is None or cand[1] < best[1]:
                            best = cand
                _ordered = [_ps[i] if not r
                            else _LS(list(reversed(_ps[i].coords)))
                            for i, r in best[0]]
                u = _MLS(_ordered)
        chains[fid] = u
    return chains


def _arc_dperp(chain, x, y, lon_m, lat_m):
    """独立弧位/垂直距（最近 part + 前置长度，与发现 C 同口径）。"""
    parts = list(chain.geoms) if chain.geom_type == "MultiLineString" else [chain]
    plens = []
    for gp in parts:
        cs = list(gp.coords)
        plens.append(sum(math.hypot((cs[i + 1][0] - cs[i][0]) * lon_m,
                                    (cs[i + 1][1] - cs[i][1]) * lat_m)
                         for i in range(len(cs) - 1)))
    base = [0.0]
    for L in plens:
        base.append(base[-1] + L)
    p = Point(x, y)
    k = min(range(len(parts)), key=lambda i: parts[i].distance(p))
    gp = parts[k]
    s = gp.project(p)
    foot = gp.interpolate(s)
    arc = base[k] + ((s / gp.length) * plens[k] if gp.length else 0.0)
    dperp = math.hypot((foot.x - x) * lon_m, (foot.y - y) * lat_m)
    return arc, dperp, gp, s


def _side(chain, x, y, lon_m, lat_m):
    """独立侧别（切向×点-垂足，米制；|分量|<MIN_SIDE_M 判 0）。"""
    _arc, _dp, gp, s = _arc_dperp(chain, x, y, lon_m, lat_m)
    e = 1e-9
    p1 = gp.interpolate(min(gp.length, s + e))
    p2 = gp.interpolate(max(0.0, s - e))
    foot = gp.interpolate(s)
    cross = ((p1.x - p2.x) * lon_m) * ((y - foot.y) * lat_m) \
        - ((p1.y - p2.y) * lat_m) * ((x - foot.x) * lon_m)
    tlen = math.hypot((p1.x - p2.x) * lon_m, (p1.y - p2.y) * lat_m) or 1e-9
    return 0 if abs(cross) / tlen < MIN_SIDE_M else (1 if cross > 0 else -1)


def _z_of(chain, a_xy, b_xy, lon_m, lat_m):
    """独立旋向 z=T×V（垂足锚定、交换不变）。"""
    from shapely.geometry import Point as _P
    def _foot(p_):
        s = chain.project(p_)
        return chain.interpolate(s)
    c = _foot(_P(*a_xy))
    d = _foot(_P(*b_xy))
    tx = (b_xy[0] - a_xy[0]) * lon_m
    ty = (b_xy[1] - a_xy[1]) * lat_m
    vx = (d.x - c.x) * lon_m
    vy = (d.y - c.y) * lat_m
    return tx * vy - ty * vx


def _independent_identify(key, root, lat):
    """独立重算：返回 {fault_id: [(id1, id2, sense, foot_sep, arcs)]}。"""
    wt = gpd.read_file(root + r"\geojson\L0\LDZOFBB099.WT.geojson")
    fl = gpd.read_file(root + r"/geojson/L1/faults.geojson") \
        .sort_values("_src_id").reset_index(drop=True)
    prof = get_profile(key)
    ent = pd.read_csv(root + "/" + (get_profile(key).entities_csv
                                or "fault_entities.csv"),
                        dtype=str)  # profile 通道（2026-10-05 测试债修复）
    assoc = pd.read_csv(root + f"\\fault_aux_{key}.csv", dtype=str)
    lon_m = 111320.0 * math.cos(math.radians(lat))
    lat_m = 111320.0
    aux = wt[wt["CHFCEC"].astype(str) == str(prof.aux_filter)]
    consumed = set(assoc[assoc["sub_no"].astype(str).isin(["1894", "1281"])]["aux_idx"].astype(int))
    consumed |= set(assoc[assoc["kind"] == "number"]["aux_idx"].astype(int))
    pool = [(int(r["_src_id"]), r.geometry.x, r.geometry.y)
            for _, r in aux.iterrows()
            if int(r["_src_id"]) not in consumed and int(r["symbol_no"]) != 0]
    chains = _chain_fold(fl, ent)
    # 点级最近链归属（600m 窗）
    assign = {}
    for pid, x, y in pool:
        best = min(((ch.distance(Point(x, y)) * lon_m, fid)
                    for fid, ch in chains.items()))
        d, fid = best
        if d <= ASSIGN_WIN:
            assign.setdefault(fid, []).append((pid, x, y))
    out = {}
    for fid, sub in assign.items():
        ch = chains[fid]
        pts = []
        for pid, x, y in sub:
            arc, dperp, _gp, _s = _arc_dperp(ch, x, y, lon_m, lat_m)
            if not (BAND[0] <= dperp <= BAND[1]):
                continue
            sd = _side(ch, x, y, lon_m, lat_m)
            if sd == 0:
                continue
            pts.append((pid, x, y, dperp, arc, sd))
        used = set()
        for i in range(len(pts)):
            if pts[i][0] in used:
                continue
            best = None
            for j in range(len(pts)):
                if j == i or pts[j][0] in used or pts[i][5] == pts[j][5]:
                    continue
                sep = abs(pts[i][4] - pts[j][4])
                if sep > MAX_FOOT_SEP:
                    continue
                if best is None or sep < best[1]:
                    best = (j, sep)
            if best is None:
                continue
            j, sep = best
            z = _z_of(ch, (pts[i][1], pts[i][2]), (pts[j][1], pts[j][2]),
                      lon_m, lat_m)
            sense = "左行" if z > 0 else "右行"
            out.setdefault(fid, []).append(
                (pts[i][0], pts[j][0], sense,
                 round(sep, 0),
                 (round(min(pts[i][4], pts[j][4]), 0),
                  round(max(pts[i][4], pts[j][4]), 0))))
            used.add(pts[i][0])
            used.add(pts[j][0])
    return out, pool


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_hook_identification(key, root, lat):
    prod = pd.read_csv(root + rf"/_fault_hooks_{key}.csv", dtype=str)
    ind, pool = _independent_identify(key, root, lat)
    prod_pairs = {(str(r["fault_id"]), int(r["id1"]), int(r["id2"]))
                  for _, r in prod.iterrows()}
    ind_pairs = set()
    for fid, pairs in ind.items():
        for (i1, i2, sense, sep, arcs) in pairs:
            ind_pairs.add((fid, i1, i2))
    # ③ 双向核验
    assert prod_pairs == ind_pairs, \
        f"配对不一致 {key}: 生产多 {sorted(prod_pairs - ind_pairs)} 独立多 {sorted(ind_pairs - prod_pairs)}"
    # ④ 逐对签名不变量 + 旋向一致
    for _, r in prod.iterrows():
        fid = str(r["fault_id"])
        hit = [p for p in ind.get(fid, [])
               if (p[0], p[1]) == (int(r["id1"]), int(r["id2"]))]
        assert len(hit) == 1
        _p = hit[0]
        assert _p[2] == str(r["sense"]), \
            f"旋向不符 {fid} {r['id1']}/{r['id2']}: 独立 {_p[2]} vs 生产 {r['sense']}"
        assert abs(_p[3] - float(r["foot_sep_m"])) < 5.0, \
            f"垂足间距不符 {fid}: {_p[3]} vs {r['foot_sep_m']}"
        assert abs(_p[4][0] - float(r["foot_arc1_m"])) < 10.0 and \
            abs(_p[4][1] - float(r["foot_arc2_m"])) < 10.0, \
            f"区间弧位不符 {fid}: {_p[4]} vs ({r['foot_arc1_m']},{r['foot_arc2_m']})"
    # ⑤ 区间段号核验（段弧位范围与区间重叠）
    fl = gpd.read_file(root + r"/geojson/L1/faults.geojson") \
        .sort_values("_src_id").reset_index(drop=True)
    ent = pd.read_csv(root + "/" + (get_profile(key).entities_csv
                                or "fault_entities.csv"),
                        dtype=str)  # profile 通道（2026-10-05 测试债修复）
    chains = _chain_fold(fl, ent)
    lon_m = 111320.0 * math.cos(math.radians(lat))
    lat_m = 111320.0
    for _, r in prod.iterrows():
        fid = str(r["fault_id"])
        ch = chains.get(fid)
        assert ch is not None
        lo, hi = float(r["foot_arc1_m"]), float(r["foot_arc2_m"])
        segs = set(map(int, str(r["segs"]).split(","))) if str(r["segs"]).strip() else set()
        assert segs, f"{fid} 区间无段号"
        for sg in segs:
            g = fl.geometry[sg]
            c0, c1 = g.coords[0], g.coords[-1]
            a0, _, _, _ = _arc_dperp(ch, c0[0], c0[1], lon_m, lat_m)
            a1, _, _, _ = _arc_dperp(ch, c1[0], c1[1], lon_m, lat_m)
            s0, s1 = min(a0, a1), max(a0, a1)
            assert s1 > lo and s0 < hi, \
                f"{fid} 段 {sg} 弧位 [{s0:.0f},{s1:.0f}] 不重叠区间 [{lo:.0f},{hi:.0f}]"
    # 负样本：池内无符号 0；同侧/超距不成对（独立实现内禀，此处抽查）
    syms = gpd.read_file(root + r"\geojson\L0\LDZOFBB099.WT.geojson")
    aux = syms[syms["CHFCEC"].astype(str) == str(get_profile(key).aux_filter)]
    for _, r in prod.iterrows():
        for i in (int(r["id1"]), int(r["id2"])):
            row = aux[aux["_src_id"] == i]
            assert len(row) and int(row["symbol_no"].iloc[0]) != 0, \
                f"{fid} 钩对含符号 0 点 {i}"
            assert int(row["symbol_no"].iloc[0]) not in (1281, 1894, 1851), \
                f"{fid} 钩对含 a/b 角色点 {i}"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_hook_identification_static(key, root, lat):
    """静态行证：识别路径零符号字面量依赖（符号无关泛化）。"""
    from pathlib import Path
    src = Path(r"D:\geosciml4china\src\geosciml4china\calibrate\auxchain.py") \
        .read_text(encoding="utf-8")
    # 识别区块（走滑钩空间识别注释至 tdf 初始化）
    i0 = src.index("# 走滑钩对空间识别")
    i1 = src.index("tdf = pd.DataFrame(trip_rows)")
    block = src[i0:i1]
    for literal in ("238", "239", "1539", "1882", "1883"):
        assert literal not in block, f"识别路径含符号字面量 {literal}"
    _aux_src = Path(r"D:\JWD\src\pymapgis\rendering\aux_logic.py")
    if not _aux_src.exists():
        pytest.skip("pymapgis 本地源不在场（CI runner）")
    lib = _aux_src.read_text(encoding="utf-8")
    j0 = lib.index("def identify_strike_slip_hooks")
    j1 = lib.index("def chain_arc_position", j0) if "def chain_arc_position" in lib[j0:] else len(lib)
    for literal in ("238", "239", "1539"):
        assert literal not in lib[j0:j1], f"共享识别函数含符号字面量 {literal}"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_hook_sense_vs_code(key, root, lat):
    """旋向×码义互证：16/18 码段的钩旋向与码义一致或如实张力。"""
    gz = pd.read_csv(root + rf"/_gzeeb_calibration_{key}.csv", dtype=str)
    hooks = pd.read_csv(root + rf"/_fault_hooks_{key}.csv", dtype=str)
    for _, h in hooks.iterrows():
        fid = str(h["fault_id"])
        segs = [int(x) for x in str(h["segs"]).split(",")]
        for sg in segs:
            row = gz[gz["idx"].astype(int) == sg]
            if not len(row):
                continue
            st = str(row.iloc[0]["structural_type"])
            checks = str(row.iloc[0]["checks"])
            if "左型走滑" in st:
                assert h["sense"] == "左行" or "矛盾保留" in checks or "张力" in checks, \
                    f"{fid} seg{sg} 左型码钩旋向 {h['sense']} 未互证未张力"
            elif "右型走滑" in st:
                assert h["sense"] == "右行" or "矛盾保留" in checks or "张力" in checks, \
                    f"{fid} seg{sg} 右型码钩旋向 {h['sense']} 未互证未张力"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_hook_interval_entity_scoping(key, root, lat):
    """实体级不泄漏（用户想法审计核心）：钩对区间覆盖段承载钩证据，
    同实体非覆盖段零承载——「表征某段而非整个实体」。"""
    hooks = pd.read_csv(root + rf"/_fault_hooks_{key}.csv", dtype=str)
    gz = pd.read_csv(root + rf"/_gzeeb_calibration_{key}.csv", dtype=str)
    ent = pd.read_csv(root + "/" + (get_profile(key).entities_csv
                                or "fault_entities.csv"),
                        dtype=str)  # profile 通道（2026-10-05 测试债修复）
    seg2fid = dict(zip(ent["seg_idx"].astype(int), ent["fault_id"].astype(str)))
    n_pairs = 0
    # 实体覆盖并集（多对实体：F002 两对各覆盖一段——证据=全部对的并集）
    cov_of = {}
    for _, h in hooks.iterrows():
        fid = str(h["fault_id"])
        cov = {int(x) for x in str(h["segs"]).split(",") if x.strip()}
        assert cov, f"{fid} 区间无覆盖段"
        entity_segs = {int(sg) for sg, f in seg2fid.items() if f == fid}
        assert cov <= entity_segs, f"{fid} 覆盖段超出实体段集 {cov - entity_segs}"
        cov_of.setdefault(fid, set()).update(cov)
        n_pairs += 1
    for fid, cov in cov_of.items():
        entity_segs = {int(sg) for sg, f in seg2fid.items() if f == fid}
        for sg in entity_segs:
            row = gz[gz["idx"].astype(int) == sg]
            assert len(row), f"{fid} seg{sg} 无标定行"
            has = "钩旋向" in str(row.iloc[0]["checks"])
            assert has == (sg in cov), \
                f"{fid} seg{sg} 钩证据承载 {has} vs 区间覆盖 {sg in cov}"
    # 反向：凡 checks 含钩旋向的段必在某对的覆盖集
    for _, r in gz.iterrows():
        if "钩旋向" in str(r["checks"]):
            sg = int(r["idx"])
            fid = str(r["fault_id"])
            in_cov = any(
                str(h2["fault_id"]) == fid
                and sg in {int(x) for x in str(h2["segs"]).split(",") if x.strip()}
                for _, h2 in hooks.iterrows())
            assert in_cov, f"seg{sg} {fid} 钩证据无对应钩对区间"
    assert n_pairs == len(hooks)


@pytest.mark.parametrize("key,root,lat", [s for s in SHEETS if s[0] != "kurgan"])
def test_hook_slip_lite_scoping(key, root, lat):
    """产品层段级核验：lite SDS 走滑旋向行=恰好覆盖段（语义 id 独立重算）。"""
    import json
    import os
    lp = os.path.join(root, "output", "geosciml", "lite",
                      "shear_displacement_structure_view.geojson")
    if not os.path.exists(lp):
        pytest.skip("lite 未重建")
    d = json.load(open(lp, encoding="utf-8"))
    slip_ids = set()
    for x in d.get("features", []):
        pr = x.get("properties", {})
        if "走滑旋向" in str(pr.get("description", "")):
            slip_ids.add(str(pr["identifier"]["value"]).rstrip("/").split("/")[-1])
    fl = gpd.read_file(root + r"/geojson/L1/faults.geojson")         .sort_values("_src_id").reset_index(drop=True)
    hooks = pd.read_csv(root + rf"/_fault_hooks_{key}.csv", dtype=str)
    # 语义 id 独立重算（审计哲学：不共享生产代码路径）——fault_id.{组内序}
    _ord_of = {}
    for fid, sub in fl.groupby("fault_id", sort=False):
        for i, (_, row) in enumerate(sub.iterrows(), 1):
            _ord_of[int(row["_src_id"])] = (str(fid), i)
    expect = set()
    for _, h in hooks.iterrows():
        for sg in str(h["segs"]).split(","):
            if sg.strip():
                fid, o = _ord_of[int(sg)]
                expect.add(f"{fid}.{o}")
    assert slip_ids == expect, \
        f"lite 走滑旋向行 {sorted(slip_ids)} vs 覆盖段 {sorted(expect)}"
