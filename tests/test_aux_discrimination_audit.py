# -*- coding: utf-8 -*-
"""断层辅助点判别逻辑执行审计（2026-09-29 用户指令；2026-09-29 晚升级实体链版）。

方法=独立重算：以 shapely 原语重新实现实体链折叠/归属距离/弧长/侧别/带标记/
判别链，与校准产出逐组对照——共享结论不共享代码路径。
基准（用户裁定链）：四步（实体归组/b-a 归属 a 依附 b/注释 1:1/三联体判别）
+ 距离四闸（孤儿 2×char_b/配对 2km/臂长 4km/侧别 20m/a-b 200m/中位距离带——
b -20%/+40%、a -35%/+75%（2026-09-30 系列裁定））
+ 同侧正异侧逆 + 存疑交人工零改码。
"""
import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString as _LS, MultiLineString as _MLS, Point as _Pt
from shapely.ops import transform as _stf, unary_union as _uu

SHEETS = [
    ("aoyiyayilake", r"D:\J45C004001新疆奥依亚依拉克\J45C004001\MAPGIS\JWD", 36.5),
    ("bashkurgan", r"D:\ts\JWD", 39.5),
]
NOISE_SIDE = 20.0
MIN_AB = 200.0
BAND_FRAC = 0.2        # （保留名）
B_BAND_LO_FRAC = 0.61  # b(1894) 带下限（2026-09-30 裁定，b1722 案：度量归真后 -60%→-61%）
B_BAND_HI_FRAC = 0.4   # b(1894) 带上限 +40%（2026-09-30 裁定，b1745 案）
A_BAND_LO_FRAC = 0.35  # a(1281) 带下限 -35%（2026-09-30 裁定，a1849 案）
A_BAND_HI_FRAC = 0.75  # a(1281) 带上限（2026-09-30 裁定：+50%→+75%，a1742 案）
B_SECOND_HI = 0.5      # 二次判别带 b 上限（2026-09-30 裁定，b1714 案）
ARM_MAX = 4000.0


def _band_limits(sn, med):
    if str(sn) == "1281":
        return (med * (1 - A_BAND_LO_FRAC), med * (1 + A_BAND_HI_FRAC))
    return (med * (1 - B_BAND_LO_FRAC), med * (1 + B_BAND_HI_FRAC))


def _geo(root):
    wt = gpd.read_file(root + r"\geojson\L0\LDZOFBB099.WT.geojson")
    fl = gpd.read_file(root + r"\geojson\L1\faults.geojson").sort_values("_src_id")
    return wt, fl.reset_index(drop=True)


def _chain_fold(fl, ent):
    """独立实体链折叠（审计自己的实现）：端点邻接拼接、必要时反向。"""
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
            used.add((i, 0))  # 段级双端点消耗（C-① 镜像）
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
        if u.geom_type == "MultiLineString":
            u = _MLS(_order_parts(list(u.geoms)))  # C-②b 镜像：构建时一次排序
        chains[fid] = u
    return chains


def _part_len_m(part, LON_M, LAT_M):
    cs = list(part.coords)
    return sum(math.hypot((cs[i + 1][0] - cs[i][0]) * LON_M,
                          (cs[i + 1][1] - cs[i][1]) * LAT_M)
               for i in range(len(cs) - 1))


def _order_parts(parts):
    """MultiLineString 碎段排成最小缺口遍历序（发现 C-②b：union 输出序
    任意，碎段线性参考须按物理邻接定向——F029 案 seg170 尾≈seg168 首
    ~450m 数字化缺口，乱序致弧距虚增 15km）。
    实现：端点坐标一次性缓存为浮点元组（枚举期不触 shapely 坐标序列）；
    N≤40 全锚点×双朝向贪心取总缺口最小者；N>40 端点极径启发
    （最远端点对即遍历两端）单锚贪心——F002 型 207 碎段实体由 229s 降至毫秒级。"""
    if len(parts) <= 1:
        return parts
    _LS2 = _LS
    E = [(p_.coords[0], p_.coords[-1]) for p_ in parts]

    def _d2(c1, c2):
        return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2

    def _greedy(ai, rev0):
        pool = set(range(len(parts)))
        pool.discard(ai)
        order = [(ai, rev0)]
        tail = E[ai][0] if rev0 else E[ai][1]
        gap = 0.0
        while pool:
            bi = min(pool, key=lambda i: min(_d2(tail, E[i][0]),
                                             _d2(tail, E[i][1])))
            pool.discard(bi)
            if _d2(tail, E[bi][1]) < _d2(tail, E[bi][0]):
                order.append((bi, True))
                gap += _d2(tail, E[bi][1])
                tail = E[bi][0]
            else:
                order.append((bi, False))
                gap += _d2(tail, E[bi][0])
                tail = E[bi][1]
        return order, gap

    if len(parts) <= 40:
        best = None
        for i in range(len(parts)):
            for rev in (False, True):
                cand = _greedy(i, rev)
                if best is None or cand[1] < best[1]:
                    best = cand
        order = best[0]
    else:
        # 端点极径启发：最远端点对所在 part 即遍历两端
        ends = [(i, w) for i in range(len(parts)) for w in (0, 1)]
        i0, w0 = max(ends, key=lambda x: max(_d2(E[x[0]][x[1]], E[j][w])
                                             for j in range(len(parts)) for w in (0, 1)))
        order = _greedy(i0, w0 == 1)[0]
    return [_LS2(list(reversed(parts[i].coords))) if r else parts[i]
            for i, r in order]
def _arc_and_side(geom, pt, LON_M, LAT_M):
    # MultiLineString：最近 part 段内弧位 + 前置 part 长度，不跨跳（C-② 镜像）
    if geom.geom_type == "MultiLineString":
        parts = list(geom.geoms)  # 构建时已排序（C-②b 镜像）
        k = min(range(len(parts)), key=lambda i: parts[i].distance(pt))
        s_pre = sum(_part_len_m(pp, LON_M, LAT_M) for pp in parts[:k])
        s_in, side, dperp = _arc_and_side(parts[k], pt, LON_M, LAT_M)
        return s_pre + s_in, side, dperp
    n = 400
    pts = [geom.interpolate(i / n, normalized=True) for i in range(n + 1)]
    best = min(range(n + 1), key=lambda i:
               ((pts[i].x - pt.x) * LON_M) ** 2 + ((pts[i].y - pt.y) * LAT_M) ** 2)
    s = 0.0
    for i in range(best):
        s += math.hypot((pts[i + 1].x - pts[i].x) * LON_M,
                        (pts[i + 1].y - pts[i].y) * LAT_M)
    d = geom.project(pt)
    e = 1e-9
    p1 = geom.interpolate(min(geom.length, d + e))
    p2 = geom.interpolate(max(0.0, d - e))
    tx = (p1.x - p2.x) * LON_M
    ty = (p1.y - p2.y) * LAT_M
    px = (pt.x - geom.interpolate(d).x) * LON_M
    py = (pt.y - geom.interpolate(d).y) * LAT_M
    cross = tx * py - ty * px
    return s, (1 if cross > 0 else -1), math.hypot(px, py)


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_assoc_distance_and_band(key, root, lat):
    wt, fl = _geo(root)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    assoc = pd.read_csv(root + f"\\fault_aux_{key}.csv", dtype=str)
    ent = pd.read_csv(root + f"\\fault_entities_{key}.csv", dtype=str)
    chains = _chain_fold(fl, ent)
    # 发现 A 镜像：米制链（逐轴缩放）上重算归属距离
    chains_m = {f: _stf(lambda x, y: (x * LON_M, y * LAT_M), c)
                for f, c in chains.items()}
    dists = {c: [] for c in ("1894", "1281")}
    for _, r in assoc.iterrows():
        if r["kind"] != "symbol" or r["dist_m"] is None or pd.isna(r["dist_m"]):
            continue
        pt = wt.iloc[int(r["aux_idx"])].geometry
        ch = chains_m.get(r["fault_id"])
        assert ch is not None
        d_min = ch.distance(_Pt(pt.x * LON_M, pt.y * LAT_M))
        assert abs(d_min - float(r["dist_m"])) < 1.0, \
            f"归属非最近链 aux={r['aux_idx']}: 记录 {r['dist_m']} vs 重算 {d_min:.1f}"
        sn = str(r["sub_no"])
        if sn in dists:
            dists[sn].append(d_min)
    med = {c: sorted(v)[len(v) // 2] for c, v in dists.items() if v}
    for _, r in assoc.iterrows():
        if r["kind"] != "symbol" or r["dist_m"] is None or pd.isna(r["dist_m"]):
            continue
        sn = str(r["sub_no"])
        if sn not in med:
            continue
        d = float(r["dist_m"])
        lo, hi = _band_limits(sn, med[sn])
        out = d < lo or d > hi
        got = str(r.get("dist_band_ok") or "")
        assert (got == "out") == out, \
            f"带标记不符 aux={r['aux_idx']} sn={sn} d={d:.1f} med={med[sn]:.1f} 标记={got!r}"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_triplet_discrimination(key, root, lat):
    wt, fl = _geo(root)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    tri = pd.read_csv(root + f"\\_fault_triplets_{key}.csv", dtype=str)
    assoc = pd.read_csv(root + f"\\fault_aux_{key}.csv", dtype=str)
    ent = pd.read_csv(root + f"\\fault_entities_{key}.csv", dtype=str)
    chains = _chain_fold(fl, ent)
    dists = {c: [] for c in ("1894", "1281")}
    for _, r in assoc.iterrows():
        if r["kind"] == "symbol" and r["dist_m"] is not None and not pd.isna(r["dist_m"]):
            sn = str(r["sub_no"])
            if sn in dists:
                dists[sn].append(float(r["dist_m"]))
    med = {c: sorted(v)[len(v) // 2] for c, v in dists.items() if v}
    band = {c: _band_limits(c, m) for c, m in med.items()}

    def band_ok(aid, sn):
        arow = assoc[assoc["aux_idx"] == str(aid)]
        if not len(arow):
            return True
        d = arow.iloc[0]["dist_m"]
        if d is None or pd.isna(d):
            return True
        d = float(d)
        return band[str(sn)][0] <= d <= band[str(sn)][1]

    for _, t in tri.iterrows():
        fid = t["fault_id"]
        b_id = int(t["a1894"])
        a_ids = [int(x) for x in str(t["a1281"]).split("/")]
        if str(t.get("src") or "") == "second_pass":
            # 二次判别组：b 放宽至二次带（≥首判下限、≤(1+B_SECOND_HI)×中位），
            # a 伙伴仍须首判带内
            _bd = float(assoc[assoc["aux_idx"] == str(b_id)].iloc[0]["dist_m"])
            _sp_ok = (band["1894"][0] <= _bd
                      <= med["1894"] * (1 + B_SECOND_HI)) if "1894" in band else True
            _members_ok = _sp_ok and all(band_ok(x, "1281") for x in a_ids)
        else:
            _members_ok = all(band_ok(x, "1894" if x == b_id else "1281")
                              for x in [b_id] + a_ids)
        if not _members_ok:
            exp = "存疑（距离偏离中位数距离带）"
        else:
            g = chains[fid]
            b = wt.iloc[b_id].geometry
            dab = min(math.hypot((wt.iloc[x].geometry.x - b.x) * LON_M,
                                 (wt.iloc[x].geometry.y - b.y) * LAT_M) for x in a_ids)
            if dab < MIN_AB:
                exp = "存疑（a-b 间距过近，几何退化）"
            else:
                sides = []
                for x in [b_id] + a_ids:
                    _, side, dperp = _arc_and_side(g, wt.iloc[x].geometry, LON_M, LAT_M)
                    sides.append(None if dperp < NOISE_SIDE else side)
                if any(s_ is None for s_ in sides):
                    exp = "存疑（点近线，侧别不可判）"
                else:
                    s94, sa = sides[0], set(sides[1:])
                    if len(sa) > 1:
                        exp = "存疑（1281自身异侧）"
                    else:
                        exp = "正断层产状点" if s94 in sa else "逆断层产状点"
        assert exp == t["verdict"], \
            f"判别不符 b{b_id} {fid}: 基线={t['verdict']} vs 重算={exp}"


@pytest.mark.parametrize("key,root,lat", [SHEETS[0]])
def test_pairs_constraints(key, root, lat):
    pairs = pd.read_csv(root + r"\fault_aux_number_1894_pairs.csv", dtype=str)
    assert pairs["idx1894"].nunique() == len(pairs), "共享 b（1:1 违反）"
    assert pairs["num_idx"].nunique() == len(pairs), "共享注释（1:1 违反）"
    assoc = pd.read_csv(root + rf"\fault_aux_{key}.csv", dtype=str)

    def _n(v):
        s = str(v).strip()
        return None if s in ("", "nan", "None") else float(s)
    # 双通道一致性（2026-10-02 b1778/b1699 案）：assoc.dip 必须镜像最终
    # pairs 表——配对是倾角唯一来源，旧实现双通道漂移致同一注释倾角
    # 在 GML 双发（b1699 经 pairs、b1778 经 assoc 残留）
    adip = {int(r2["aux_idx"]): _n(r2.get("dip")) for _, r2 in assoc.iterrows()}
    pb = set(int(x) for x in pairs["idx1894"])
    for _, r in pairs.iterrows():
        b = int(r["idx1894"])
        assert adip.get(b) == _n(r["dip"]), \
            f"assoc.dip 与 pairs 不一致 b{b}: assoc={adip.get(b)} vs pairs={_n(r['dip'])}"
    stray = [b for b, v in adip.items() if b not in pb and v is not None]
    assert not stray, f"未配对 b 残留 assoc.dip: {stray}"
    wt, _fl = _geo(root)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    for _, r in pairs.iterrows():
        g1 = wt.iloc[int(r["num_idx"])].geometry
        g2 = wt.iloc[int(r["idx1894"])].geometry
        d = math.hypot((g1.x - g2.x) * LON_M, (g1.y - g2.y) * LAT_M)
        assert d <= 2000.0, f"配对超 2km n{r['num_idx']}-b{r['idx1894']}: {d:.0f}m"


# ---- 2026-09-29 新裁定审计（非法 a-b-a 禁止 / 歧义降信 / 重归属资格） ----

@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_illegal_aba_prohibited(key, root, lat):
    """非法 a-b-a（两 a 异侧）必须禁止成组：产物中零非法行+审查册在册。"""
    tri = pd.read_csv(root + rf"\_fault_triplets_{key}.csv", dtype=str)
    for _, r in tri.iterrows():
        if r["form"] != "a-b-a":
            continue
        sides = [float(x) for x in str(r["sides_1281"]).split("/")
                 if str(x).strip() not in ("nan", "None", "")]
        assert len(sides) != 2 or sides[0] == sides[1], \
            f"非法 a-b-a 漏禁 b{r['a1894']} {r['fault_id']}: sides={r['sides_1281']}"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_reattribution_eligibility(key, root, lat):
    """重归属资格：仅低置信度（n_chains_band≥2）孤立点；非低置信度零调整。"""
    assoc = pd.read_csv(root + rf"\fault_aux_{key}.csv", dtype=str)
    reatt = assoc[assoc["method"] == "reattributed"]
    for _, r in reatt.iterrows():
        n = pd.to_numeric(r["n_chains_band"], errors="coerce")
        basis = str(r.get("reattrib_basis") or "")
        assert basis in ("ambig", "outband"), \
             f" basis={basis!r} n={n}"

@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_ambiguity_notes_on_triplets(key, root, lat):
    """歧义降信注记：含歧义成员的三联体须带注记；注记与成员歧义一致。"""
    assoc = pd.read_csv(root + rf"\fault_aux_{key}.csv", dtype=str)
    ambig = set(assoc[pd.to_numeric(assoc["n_chains_band"], errors="coerce")
                      .fillna(0) >= 2]["aux_idx"].astype(int))
    tri = pd.read_csv(root + rf"\_fault_triplets_{key}.csv", dtype=str)
    for _, r in tri.iterrows():
        members = {int(r["a1894"])} | {int(x) for x in str(r["a1281"]).split("/")}
        has_ambig = bool(members & ambig)
        if has_ambig:
            assert "歧义降信" in str(r["gzeeb_check"]), \
                f"歧义成员未注记 b{r['a1894']} {r['fault_id']}"


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_reattributed_patterns_valid(key, root, lat):
    """重归属组的判别可复现：正=全同侧于 b、逆=全异侧于 b；零混侧。"""
    wt, fl = _geo(root)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    tri = pd.read_csv(root + rf"\_fault_triplets_{key}.csv", dtype=str)
    ent = pd.read_csv(root + rf"\fault_entities_{key}.csv", dtype=str)
    chains = _chain_fold(fl, ent)
    for _, r in tri.iterrows():
        if "reattributed" not in str(r["src"]):
            continue
        b_id = int(r["a1894"])
        a_ids = [int(x) for x in str(r["a1281"]).split("/")]
        s94 = int(float(r["side_1894"]))
        for x in a_ids:
            _, side, dperp = _arc_and_side(chains[r["fault_id"]],
                                           wt.iloc[x].geometry, LON_M, LAT_M)
            assert side is not None
            assert side == s94 if "正" in r["verdict"] else side != s94, \
                f"重归属判别不可复现 b{b_id} {r['fault_id']}"


# ---- 距离判据严格实行审计（中位距离带/孤儿闸/带外禁止；2026-09-30 非对称带） ----

@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_distance_criteria_strict(key, root, lat):
    """a/b 与所属断层距离判据严格实行（独立重算）：
    ① 带=逐类中位带（b -20%/+40%；a -35%/+75%）；② 带外成员禁止成组；
    ③ 超 2×中位=孤儿排除；④ 重归属行终态带内+资格来源合法。"""
    wt, fl = _geo(root)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    assoc = pd.read_csv(root + rf"\fault_aux_{key}.csv", dtype=str)
    tri = pd.read_csv(root + rf"\_fault_triplets_{key}.csv", dtype=str)

    # ① 带独立重算（总体=符号行全量，与 auxchain 口径一致）
    band, _med = {}, {}
    for sn in ("1894", "1281"):
        ds = sorted(float(x) for x in assoc[(assoc["kind"] == "symbol")
                                            & (assoc["sub_no"].astype(str) == sn)
                                            & assoc["dist_m"].notna()]["dist_m"])
        if ds:
            med_any = sorted(ds)[len(ds) // 2]
            band[sn] = _band_limits(sn, med_any)
            _med[sn] = med_any
    for _, r in assoc.iterrows():
        if r["kind"] != "symbol" or pd.isna(r["dist_m"]):
            continue
        sn = str(r["sub_no"])
        if sn not in band:
            continue
        d = float(r["dist_m"])
        out = d < band[sn][0] or d > band[sn][1]
        got = str(r.get("dist_band_ok") or "")
        assert (got == "out") == out, \
            f"带标记不符 aux={r['aux_idx']} d={d:.1f} 带={band[sn]} 标={got!r}"

    # ② 带外成员禁止成组：产物三联体任一行所有成员带内
    #    （second_pass 组例外：b 允许首判带外但须在二次带内——b1714 案裁定；
    #     a 伙伴一律首判带内）
    bmap = assoc.set_index(assoc["aux_idx"].astype(int))["dist_band_ok"].to_dict()
    dmap = assoc.set_index(assoc["aux_idx"].astype(int))["dist_m"].to_dict()
    for _, t in tri.iterrows():
        sp = str(t.get("src") or "") == "second_pass"
        b_id = int(t["a1894"])
        members = [b_id] + [int(x) for x in str(t["a1281"]).split("/")]
        for m in members:
            mark = str(bmap.get(m) or "")
            if sp and m == b_id:
                d = float(dmap[m])
                assert band["1894"][0] <= d <= _med["1894"] * (1 + B_SECOND_HI), \
                    f"二次判别 b 超二次带 b{m} d={d:.1f}"
                continue
            assert mark != "out", \
                f"带外成员成组 b{t['a1894']} {t['fault_id']} 成员 {m}"

    # ③ 孤儿闸：超 2×中位者 status_note=orphan 且不参组（前向：标记者必超闸）
    orphan_marks = assoc[assoc["status_note"].astype(str) == "orphan"]
    for _, r in orphan_marks.iterrows():
        sn = str(r["sub_no"])
        med = _med[sn]  # 中位数显式携带（a/b 下限系数不同，不可反推）
        assert float(r["dist_m"]) > 2 * med, \
            f"孤儿标记未超闸 aux={r['aux_idx']} d={r['dist_m']} med={med:.0f}"
    # 孤儿不参组
    orphan_ids = set(orphan_marks["aux_idx"].astype(int))
    for _, t in tri.iterrows():
        members = {int(t["a1894"])} | {int(x) for x in str(t["a1281"]).split("/")}
        assert not (members & orphan_ids), f"孤儿参组 {t['a1894']}"
    # 反向：超闸者必标记孤儿
    for sn, (lo, hi) in band.items():
        med = _med[sn]  # 显式中位数（a/b 下限系数不同）
        far = assoc[(assoc["sub_no"].astype(str) == sn)
                    & (pd.to_numeric(assoc["dist_m"], errors="coerce") > 2 * med)]
        for _, r in far.iterrows():
            assert str(r["status_note"]) == "orphan", \
                f"超孤儿闸未标记 aux={r['aux_idx']} d={r['dist_m']} med={med:.0f}"

    # ④ 重归属行终态：带内（dist_band_ok≠out）+ 资格来源合法
    reatt = assoc[assoc["method"] == "reattributed"]
    for _, r in reatt.iterrows():
        assert str(r.get("dist_band_ok") or "") != "out", \
            f"重归属后仍带外 aux={r['aux_idx']}"
        assert str(r.get("reattrib_basis") or "") in ("ambig", "outband"), \
            f"资格来源非法 aux={r['aux_idx']}"
