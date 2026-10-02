# -*- coding: utf-8 -*-
"""断层辅助点实体链判别（geosciml4china.calibrate 第 1.5 域，2026-09-29 泛化优化）。

**实体基础原则（用户裁定）**：辅助点归属判别建立在断层实体基础上——b/a 归属、
弧长、三联体均以实体链（而非单段）为上下文：跨段三元组恢复成组、fault_id 取
实体号（F%03d）、实体级 aux 汇总随之可写回。

判别链（全部裁定在案）：
  · b/a 归属：实体链折线上最近点（米制）→ 弧长 s、垂直距、侧别（<20m 噪声→None）
  · 距离带：逐类（1894/1281）中位带（下限统一 -20%；上限 a(1281)+75%/
    b(1894)+40%，2026-09-30 系列裁定——a1739/a1742/b1745 三案）
  · 注释配对：注释依附 b、1:1、≤2km（共享库 pair_dip_annotations；本幅无倾角
    注释类别→跳过，倾角留空——不继承 GZECE，用户裁定）
  · 三联体：链弧长上 b 上下游最近 a（臂长≤4km）→ 判别序：带外→存疑 /
    a-b<200m→存疑 / 侧别 None→存疑 / 1281 异侧→存疑 / 同侧=正、异侧=逆
  · GZEEB 互验（05/07→逆期望）：互证/冲突如实登记；存疑入审查册——零自动改码
  · 孤立的 a 无意义（不成组不入运动语义）

CLI: python -m geosciml4china.calibrate.auxchain --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import transform as _st, unary_union

from pymapgis.rendering.aux_logic import (chain_arc_position,
                                     identify_strike_slip_hooks,
                                     pair_dip_annotations)
from pymapgis.semantics.profile import get_profile

from ..sheets import get_sheet
from .registry import load_gzeeb_semantics, reverse_codes

SIDE_NOISE_M = 20.0      # 侧别噪声阈值（点垂直距<20m 侧别不可判）
MIN_AB_M = 200.0         # a-b 最小间距（符号重叠级）
BAND_FRAC = 0.2          # （保留名）b(1894) 带下限基准
B_BAND_LO_FRAC = 0.61    # b(1894) 带下限（2026-09-30 用户裁定，b1722 案）：
                         # 初始 -60%（失真中位口径）；发现 A 度量归真后中位数
                         # 225.5→276.2，b1722（109.4m）被顶出 1.1m——同日裁定
                         # 「b1722 不能出带」兑现为 -61%（107.7m，真值口径）
A_BAND_LO_FRAC = 0.35    # a(1281) 带下限 -35%（2026-09-30 用户裁定，a1849 案：
                         # 68.8m 段内垂直足、侧别有效，下限侧首个合法化案例；
                         # 取 -35%（62.5m）兼容发现 A 修复后真值 79.6m 双口径同带籍）
B_BAND_HI_FRAC = 0.4     # b(1894) 带上限 +40%（2026-09-30 用户裁定，b1745 案：
                         # 夹缝点——F052 80.3m 太近带外、F129 291.3m 擦边带外；
                         # 取 +40%（315.7m）兼容发现 A 修复后真值 305.3m 双口径同带籍）
A_BAND_HI_FRAC = 0.75    # a(1281) 带上限（下限维持 -20%）：
                         # 2026-09-30 +50%（a1739 案：唯一非孤儿链带外 a 合法化）→
                         # 2026-09-30 +75%（a1742 案：跨段三元组成员 153.2m 合法化；
                         # 选 +75% 非最小拟合 +60%——兼容发现 A 度量修复后真值
                         # 167.9m，两种口径同带籍）
B_SECOND_HI_FRAC = 0.5   # 二次判别带 b(1894) 上限（2026-09-30 用户裁定，
                         # b1714 案）：孤立 b（本链带外超上限、非孤儿、臂内有
                         # 带内 a）允许二次判别——上限上调至 (1+本值)×中位；
                         # 下限不动、孤儿闸（>2×中位）不动；a 伙伴仍须首判带内
ARM_MAX_M = 4000.0       # 三联体臂长上限
PAIR_MAX_M = 2000.0      # 注释配对硬约束
EXPECT_REVERSE = {}   # GZEEB 逆断层期望码——注册表驱动（2026-10-01 泛化）：
                     # 语义∈{逆断层,推覆体边界}的码，装载期自注册表推导；
                     # 2026-10-02 泛化审计：按 sheet key 缓存（原全局单值
                     # 同进程先后跑两幅会串码）


def _band_limits(sub_no: str, med: float) -> tuple[float, float]:
    """逐类距离带（2026-09-30 非对称带系列裁定）：a(1281)=下限
    (1−A_BAND_LO_FRAC)/上限 (1+A_BAND_HI_FRAC)；b(1894)=±BAND_FRAC 下限/
    (1+B_BAND_HI_FRAC) 上限。"""
    if str(sub_no) == "1281":
        return (med * (1 - A_BAND_LO_FRAC), med * (1 + A_BAND_HI_FRAC))
    return (med * (1 - B_BAND_LO_FRAC), med * (1 + B_BAND_HI_FRAC))


def _chain_of(seg_geoms: list, seg_idx: list[int]) -> LineString | None:
    """实体段集 → 链折线（端点相接拼接、必要时反向；单段=自身）。"""
    segs = {i: list(g.coords) for i, g in zip(seg_idx, seg_geoms)}
    if len(segs) == 1:
        return LineString(next(iter(segs.values())))
    eps = {}
    for i, c in segs.items():
        eps[(i, 0)] = c[0]
        eps[(i, 1)] = c[-1]
    used = set()
    chains = []
    for (i, w), p in eps.items():
        if (i, w) in used:
            continue
        used.add((i, 0))  # 段级双端点消耗（发现 C-① 定版恢复）
        used.add((i, 1))
        coords = list(segs[i]) if w == 0 else list(reversed(segs[i]))
        cur_i, cur_w = i, (0 if w == 1 else 1)
        while True:
            nxt = None
            for (j, wj), pj in eps.items():
                if j == cur_i or (j, wj) in used:
                    continue
                if math.hypot(pj[0] - coords[-1][0], pj[1] - coords[-1][1]) < 1e-4:
                    nxt = (j, wj)
                    break
            if nxt is None:
                break
            j, wj = nxt
            used.add((j, 0))
            used.add((j, 1))
            cj = list(segs[j]) if wj == 0 else list(reversed(segs[j]))
            if math.hypot((cj[0][0] - coords[-1][0]), (cj[0][1] - coords[-1][1])) > \
               math.hypot((cj[-1][0] - coords[-1][0]), (cj[-1][1] - coords[-1][1])):
                cj = list(reversed(cj))
            coords += cj[1:]
            cur_i, cur_w = j, (0 if wj == 1 else 1)
        chains.append(LineString(coords))
    u = unary_union(chains) if len(chains) > 1 else chains[0]
    if u.geom_type == "MultiLineString":
        # 碎段最小缺口遍历序在链构建时一次完成（发现 C-②b；_arc_side 不再重复排序）
        u = MultiLineString(_order_parts(list(u.geoms)))
    return u


def _part_len_m(part: LineString, LON_M: float, LAT_M: float) -> float:
    """单 part 逐轴米制长度。"""
    cs = list(part.coords)
    return sum(math.hypot((cs[i + 1][0] - cs[i][0]) * LON_M,
                          (cs[i + 1][1] - cs[i][1]) * LAT_M)
               for i in range(len(cs) - 1))


def _order_parts(parts: list) -> list:
    """MultiLineString 碎段排成最小缺口遍历序（发现 C-②b：union 输出序
    任意，碎段线性参考须按物理邻接定向——F029 案 seg170 尾≈seg168 首
    ~450m 数字化缺口，乱序致弧距虚增 15km）。
    实现：端点坐标一次性缓存为浮点元组（枚举期不触 shapely 坐标序列）；
    N≤40 全锚点×双朝向贪心取总缺口最小者；N>40 端点极径启发
    （最远端点对即遍历两端）单锚贪心——F002 型 207 碎段实体由 229s 降至毫秒级。"""
    if len(parts) <= 1:
        return parts
    from shapely.geometry import LineString as _LS2
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
def _arc_side(chain: LineString, pt, LON_M: float, LAT_M: float):
    """点 → 链折线（米制）弧长/侧别/垂直距（细采样独立实现）。
    MultiLineString：取最近 part 段内弧位 + 前置 part 真实长度累加——
    碎段间不跨跳累加（发现 C-② 修复，2026-09-30：union 碎化链上
    采样跳变曾致弧长虚增 ~2×，a1917/b1868 假 37km 弧距案）。"""
    if chain.geom_type == "MultiLineString":
        parts = list(chain.geoms)  # 构建时已排最小缺口遍历序（C-②b）
        k = min(range(len(parts)), key=lambda i: parts[i].distance(pt))
        s_pre = sum(_part_len_m(pp, LON_M, LAT_M) for pp in parts[:k])
        s_in, side, dperp = _arc_side(parts[k], pt, LON_M, LAT_M)
        return s_pre + s_in, side, dperp
    n = 400
    pts = [chain.interpolate(i / n, normalized=True) for i in range(n + 1)]
    best = min(range(n + 1), key=lambda i:
               ((pts[i].x - pt.x) * LON_M) ** 2 + ((pts[i].y - pt.y) * LAT_M) ** 2)
    s = 0.0
    for i in range(best):
        s += math.hypot((pts[i + 1].x - pts[i].x) * LON_M,
                        (pts[i + 1].y - pts[i].y) * LAT_M)
    d = chain.project(pt)
    e = 1e-9
    p1 = chain.interpolate(min(chain.length, d + e))
    p2 = chain.interpolate(max(0.0, d - e))
    tx = (p1.x - p2.x) * LON_M
    ty = (p1.y - p2.y) * LAT_M
    px = (pt.x - chain.interpolate(d).x) * LON_M
    py = (pt.y - chain.interpolate(d).y) * LAT_M
    cross = tx * py - ty * px
    dperp = math.hypot(px, py)
    side = None if dperp < SIDE_NOISE_M else (1 if cross > 0 else -1)
    return s, side, dperp


def calibrate_auxchain(sheet_key: str, out_dir=None) -> dict:
    global EXPECT_REVERSE
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
    if EXPECT_REVERSE.get(sh.key) is None:
        # 注册表驱动（2026-10-01 泛化）：逆期望码=语义∈{逆断层,推覆体边界}
        # 的码——推覆=逆冲分量，aux 组期望逆判（库尔干 05/07、英吉沙 05/35）
        import re as _re

        def _nsem(x):
            return _re.sub(r"[（(].*?[)）]", "", str(x)).strip()

        _gsem, _ = load_gzeeb_semantics(sh.root, sh.key)
        EXPECT_REVERSE[sh.key] = reverse_codes(_gsem, _nsem)
        print(f"GZEEB 逆期望码集（注册表驱动）: {sorted(EXPECT_REVERSE[sh.key])}")
    lat = float(prof.center_lat_hint)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    outdir = Path(out_dir) if out_dir else sh.root
    outdir.mkdir(parents=True, exist_ok=True)

    wt = gpd.read_file(sh.root / "geojson" / "L0" / "LDZOFBB099.WT.geojson")
    fl = gpd.read_file(sh.root / "geojson" / "L1" / "faults.geojson").sort_values("_src_id")
    fl = fl.reset_index(drop=True)
    ent_csv = sh.root / (prof.entities_csv or "fault_entities.csv")
    ent = pd.read_csv(ent_csv, dtype=str)

    chains = {}
    for fid, sub in ent.groupby("fault_id"):
        idxs = [int(x) for x in sub["seg_idx"]]
        ch = _chain_of([fl.geometry[i] for i in idxs], idxs)
        if ch is not None:
            chains[fid] = ch
    print(f"实体链: {len(chains)}（实体 {ent['fault_id'].nunique()}）")
    # 发现 A 修复（2026-09-30 用户裁定）：归属/带/重归属距离一律逐轴米制
    # （原 ch.distance(pt)*LON_M 纬度向 ×0.77 压缩各向异性失真——a1690
    # 61.9m 伪带外 vs 真值 77.5m 案）。度制链仍供 _arc_side（内部逐轴）。
    _scale = lambda g: _st(lambda x, y: (x * LON_M, y * LAT_M), g)
    chains_m = {fid: _scale(ch) for fid, ch in chains.items()}
    fl_m = fl.geometry.apply(_scale)

    def _pm(pt):
        return Point(pt.x * LON_M, pt.y * LAT_M)

    aux_cat = wt[wt["CHFCEC"].astype(str) == prof.aux_filter]
    # 异常册装载（2026-10-02 泛化修复——jws 全管线测试暴露）：图幅裁定
    # confirmed_error 点（1700/1701 弃对剔除等）不参与判别/配对/钩识别
    _anom_ids = set()
    if prof.anomaly_csv:
        _anom_p = sh.root / prof.anomaly_csv
        if _anom_p.exists():
            _adf = pd.read_csv(_anom_p, dtype=str)
            if "aux_idx" in _adf.columns:
                _anom_ids = {int(x) for x in _adf["aux_idx"]}
    aux_cat = aux_cat[~aux_cat["_src_id"].astype(int).isin(_anom_ids)]
    if _anom_ids:
        print(f"异常册排除: {len(_anom_ids)} 点（confirmed_error 裁定）")

    rows = []
    for _, r in aux_cat.iterrows():
        idx = int(r["_src_id"])
        sn = int(r["symbol_no"])
        pt = r.geometry
        best = None
        pt_m = _pm(pt)
        for fid, ch in chains_m.items():
            dm = ch.distance(pt_m)
            if best is None or dm < best[0]:
                best = (dm, fid)
        dm, fid = best
        ch = chains[fid]
        s_, side, dperp = _arc_side(ch, pt, LON_M, LAT_M)
        _seg = int(fl_m.distance(pt_m).idxmin())  # b 最近段（build 键接/互验用）
        _ang = float(r["angle"]) if str(r["angle"]).strip() else None
        rows.append({
            "aux_idx": idx, "kind": "symbol",
            "sub_no": (1894 if sn == int(prof.b_symbol_raw) else sn),
            "angle": _ang, "dip": None, "fault_id": fid, "seg_idx": _seg,
            # b 符号归一 1894（build 平面装配键；英吉沙 1851 正典化同构）
            "sub_no_raw": sn,
            "dist_m": round(dm, 1), "arc_s": round(s_, 0),
            "side": side, "dperp_m": round(dperp, 1),
            "method": "chain_nearest", "in_band": None,
            "n_chains_band": None,  # 带内链数（归属歧义，裁定 2026-09-29）
            # 倾向方位（P-AUX-REMAP 裁定公式按幅：dip_az=(360−angle+offset)%360；
            # offset=剖面 b_dip_offset_deg——库尔干 0（⊥ 验证在案）、英吉沙 180）
            "dip_az": (round((360.0 - _ang + float(prof.b_dip_offset_deg)) % 360.0, 1)
                       if _ang is not None else None),
        })
    assoc = pd.DataFrame(rows).sort_values("aux_idx")

    band, _med_of = {}, {}
    for sn in ("1894", "1281"):
        ds = [float(x) for x in assoc[assoc["sub_no"] == int(sn)]["dist_m"]]
        if not ds:
            continue
        med = sorted(ds)[len(ds) // 2]
        band[sn] = _band_limits(sn, med)
        _med_of[sn] = med
        print(f"距离带 {sn}: 中位 {med:.1f}m 带 [{band[sn][0]:.0f},{band[sn][1]:.0f}]")
    assoc["dist_band_ok"] = [
        "" if (str(sn) not in band or (r_.dist_m is not None and
                                       band[str(sn)][0] <= float(r_.dist_m) <= band[str(sn)][1]))
        else "out"
        for sn, r_ in zip(assoc["sub_no"], assoc.itertuples(index=False))]
    n_out = int((assoc["dist_band_ok"] == "out").sum())
    print(f"带外点: {n_out}（审查登记）")
    # 孤儿闸（2026-09-29 严格化补）：距链超 2×中位=太远排除（异常册，
    # 不归属不参与三联体）——与逐段基线 orphan 闸同口径
    assoc["status_note"] = ""
    _n_orphan = 0
    for _idx in assoc[assoc["kind"] == "symbol"].index:
        _sn = str(int(assoc.at[_idx, "sub_no"]))
        _d = assoc.at[_idx, "dist_m"]
        if _sn not in band or _d is None or str(_d).strip() in ("", "nan"):
            continue
        if float(_d) > 2 * _med_of[_sn]:
            assoc.at[_idx, "status_note"] = "orphan"
            _n_orphan += 1
    if _n_orphan:
        print(f"孤儿闸排除（>2×中位）: {_n_orphan} 点")
    # 归属歧义（2026-09-29 用户裁定）：a 点距离≥2 条断层均在带内→归属置信度降低
    _n_ambig = _n_ambig_b = 0
    for _idx in assoc[assoc["sub_no"].isin([1281, 1894])].index:
        _sn = str(int(assoc.at[_idx, "sub_no"]))
        _pt = wt.iloc[int(assoc.at[_idx, "aux_idx"])].geometry
        if _sn not in band:
            continue
        _lo, _hi = band[_sn]
        _pt_m = _pm(_pt)
        _n = sum(1 for _ch in chains_m.values()
                 if _lo <= _ch.distance(_pt_m) <= _hi)
        assoc.at[_idx, "n_chains_band"] = _n
        if _n >= 2:
            if _sn == "1281":
                _n_ambig += 1
            else:
                _n_ambig_b += 1
    print(f"a 归属歧义（≥2 链带内）: {_n_ambig} 点 / b: {_n_ambig_b} 点（置信度降低）")

    review = []  # 审查册提前初始化（中位数优先/配对隔离共用，2026-10-02）
    # 中位数最近优先（2026-10-02 用户裁定「接受中位数最近≠纯最近规则」）：
    # 带内多链归属时，取距离最接近类中位数的链（ID201 冻结原则「候选竞争
    # 接近平均距离优先，非单纯最近段」恢复）；纯最近链仅当中位数最近时保持。
    # 改属者 method=median_pref + 审查册留痕；后续判别/重归属基于新归属。
    # 交互裁定（2026-10-02 用户「a1690 不能回 F089，维持现状」）：本规则为
    # 归属倾向（先执行）；重归属组寻为后置覆盖（组优先）——a1690 型
    # 「组寻覆盖归属倾向」合法，维持现状时序。
    _n_med = 0
    for _idx in assoc[assoc["kind"] == "symbol"].index:
        _sn = str(int(assoc.at[_idx, "sub_no"]))
        if _sn not in band:
            continue
        _pt = wt.iloc[int(assoc.at[_idx, "aux_idx"])].geometry
        _pt_m = _pm(_pt)
        _lo, _hi = band[_sn]
        _med = _med_of[_sn]
        _cands = []
        for _fid in chains_m:
            _d = chains_m[_fid].distance(_pt_m)
            if _lo <= _d <= _hi:
                _cands.append((abs(_d - _med), _d, _fid))
        if len(_cands) < 2:
            continue
        _cands.sort()
        if _cands[0][2] == assoc.at[_idx, "fault_id"]:
            continue  # 纯最近=中位数最近者保持
        _old_fid = assoc.at[_idx, "fault_id"]
        _fid = _cands[0][2]
        _dm = _cands[0][1]
        _s_, _side_, _dp = _arc_side(chains[_fid], _pt, LON_M, LAT_M)
        assoc.at[_idx, "fault_id"] = _fid
        assoc.at[_idx, "dist_m"] = round(_dm, 1)
        assoc.at[_idx, "arc_s"] = round(_s_, 0)
        assoc.at[_idx, "side"] = int(_side_) if _side_ is not None else None
        assoc.at[_idx, "dist_band_ok"] = ""
        assoc.at[_idx, "method"] = "median_pref"
        # 段索引必须落在新归属实体内（2026-10-02 b1718 案：中位数改属
        # 跨断层——b1718 全局最近段 23 属 F052 而归属 F071，build 按段
        # 键接把平面挂到 F052，GML 与判别矛盾）；取新实体段集中最近者。
        # 初始 chain_nearest 无此问题（最近段必属最近链，数学保证）。
        assoc.at[_idx, "seg_idx"] = min(
            (int(_sg) for _sg in ent[ent["fault_id"] == _fid]["seg_idx"]),
            key=lambda _sg: fl_m.iloc[_sg].distance(_pt_m))
        review.append({"aux_idx": int(assoc.at[_idx, "aux_idx"]), "sub_no": int(_sn),
                       "note": f"中位数最近优先：{_old_fid}@{float(assoc.at[_idx, 'dist_m']) - _dm + _dm:.0f}m"
                               f" 改属 {_fid}（距中位 {abs(_dm - _med):.0f}m 更近）"})
        _n_med += 1
    if _n_med:
        print(f"中位数最近优先: {_n_med} 点改属（带内多链取距中位数最近者）")

    # 倾角注释类别按幅探测（英吉沙=产状注释；库尔干/奥依亚依拉克=断层注释；
    # 巴什库尔干均无→跳过，倾角留空）
    _num_cls = "断层注释" if (wt["CHFCEC"].astype(str) == "断层注释").any() else         ("产状注释" if (wt["CHFCEC"].astype(str) == "产状注释").any() else "")
    num_cat = wt[wt["CHFCEC"].astype(str) == _num_cls] if _num_cls else         wt.iloc[0:0]
    # 库尔干式注释：断层辅助点类内部文本行（symbol_no=0，CHFCED 为倾角数字）
    _aux_text = aux_cat[(aux_cat["symbol_no"].astype(int) == 0)
                        & (aux_cat["CHFCED"].astype(str).str.strip() != "")]
    num_cat = pd.concat([num_cat, _aux_text])
    pairs_rows, anomalies = [], []
    if len(num_cat):
        b_pts = {}
        _fid_int = {fid: k for k, fid in enumerate(chains)}
        for _, r in assoc[assoc["sub_no"] == 1894].iterrows():
            pt = wt.iloc[int(r["aux_idx"])].geometry
            b_pts[int(r["aux_idx"])] = (pt.x, pt.y,
                                         _fid_int.get(r["fault_id"], 0))
        nums = []
        for _, r in num_cat.iterrows():
            m = re.fullmatch(r"(\d+(?:\.\d+)?)°?", str(r["CHFCED"]).strip())
            if not m:
                # 噪声收紧（2026-09-29）：仅登记 b 点 2km 内的不可解析注释——
                # 英吉沙产状注释类含大量非断层倾角注记，远场者非配对候选
                if any(math.hypot((r.geometry.x - bx) * LON_M,
                                  (r.geometry.y - by) * LAT_M) <= PAIR_MAX_M
                       for bx, by, _fid_i in b_pts.values()):
                    anomalies.append({"aux_idx": int(r["_src_id"]), "kind": "number",
                                      "reason": f"倾角文本不可解析: {str(r['CHFCED'])!r}"})
                continue
            nums.append({"aux_idx": int(r["_src_id"]), "x": r.geometry.x,
                         "y": r.geometry.y, "dip": float(m.group(1))})
        out = pair_dip_annotations(nums, b_pts, LON_M, LAT_M, max_pair_m=PAIR_MAX_M)
        for p in out:
            if p.get("anomaly"):
                anomalies.append({"aux_idx": p["aux_idx"], "kind": "number",
                                  "reason": f"配对异常: {p.get('anomaly')}"})
                continue
            bidx = int(p["paired_b"])
            pairs_rows.append({
                "num_idx": p["aux_idx"], "dip": p.get("dip"),
                "seg_num": "", "idx1894": bidx, "seg_1894": "",
                "dist_m": p["dist_m"], "same_seg": "",
            })
            assoc.loc[assoc["aux_idx"] == bidx, "dip"] = p.get("dip")
    if pairs_rows:
        _pdf = pd.DataFrame(pairs_rows).sort_values("num_idx")
        # 最优 1:1 指派（2026-09-29 b110/b109 案）：全候选矩阵（2km 内
        # 所有 b×注释）建簇后求最小总距配对——原库贪婪序依赖致次优
        # （18°→b109 922m 而 22° 仅 633m；交换后总距 1502→1267m）。
        # 簇≤8 节点穷举全局最优；更大簇保留库配对（贪婪）。
        from itertools import permutations as _perm
        _b_rows = assoc[assoc["sub_no"] == 1894]
        _b_pos = {int(r_.aux_idx): wt.iloc[int(r_.aux_idx)].geometry
                  for r_ in _b_rows.itertuples(index=False)}
        _n_all = pd.DataFrame(nums)
        _n_pos = {int(r_.aux_idx): wt.iloc[int(r_.aux_idx)].geometry
                  for r_ in _n_all.itertuples(index=False)}
        # 2km 内候选边 → 连通簇
        _par = {}
        def _fnd(x):
            while _par[x] != x:
                _par[x] = _par[_par[x]]
                x = _par[x]
            return x
        for _b_, _bg in _b_pos.items():
            _par[("b", _b_)] = ("b", _b_)
        for _n_, _ng in _n_pos.items():
            _par[("n", _n_)] = ("n", _n_)
        for _b_, _bg in _b_pos.items():
            for _n_, _ng in _n_pos.items():
                _d = math.hypot((_bg.x - _ng.x) * LON_M, (_bg.y - _ng.y) * LAT_M)
                if _d <= PAIR_MAX_M:
                    _par[_fnd(("b", _b_))] = _fnd(("n", _n_))
        _clusters = {}
        for _k in _par:
            _clusters.setdefault(_fnd(_k), []).append(_k)
        _newpairs, _nswap = {}, 0
        _pairs_orig = {int(r_.idx1894): (int(r_.num_idx), float(r_.dist_m))
                       for r_ in pd.DataFrame(pairs_rows).itertuples(index=False)}
        for _comp in _clusters.values():
            _bs = sorted(k[1] for k in _comp if k[0] == "b")
            _ns = sorted(k[1] for k in _comp if k[0] == "n")
            if not _bs or not _ns:
                continue
            if len(_bs) + len(_ns) > 8:
                for _b_ in _bs:  # 大簇保留库配对
                    if _b_ in _pairs_orig:
                        _newpairs[_b_] = _pairs_orig[_b_]
                continue
            _nmap = {(_b_, _n_): math.hypot(
                (_b_pos[_b_].x - _n_pos[_n_].x) * LON_M,
                (_b_pos[_b_].y - _n_pos[_n_].y) * LAT_M)
                for _b_ in _bs for _n_ in _ns
                if math.hypot((_b_pos[_b_].x - _n_pos[_n_].x) * LON_M,
                              (_b_pos[_b_].y - _n_pos[_n_].y) * LAT_M) <= PAIR_MAX_M}
            # 审计捕获（n421 2262m 案）：候选矩阵必须 ≤2km 硬约束过滤——
            # 簇经 ≤2km 边连通，但簇内点对可能 >2km（传递连通）；
            # 原实现簇内无过滤，超闸配对混入指派
            # b 子集 × 注释排列全局最小总距（2026-10-02 b1778/b1699 案）：
            # 原实现 b 固定取排序前 _m 个——簇内 b 多于注释时（2b:1n），
            # 较近候选（b1778←1754 368m）从未进入搜索空间，客观选中下标
            # 较小者（b1699←1754 699m）；子集选择必须入优化变量
            from itertools import combinations as _comb
            _best = None
            _m = min(len(_bs), len(_ns))
            for _bsub in _comb(_bs, _m):
                for _p in _perm(_ns, _m):
                    if any((_bsub[i], _p[i]) not in _nmap for i in range(_m)):
                        continue  # 超闸边不可用
                    _c = sum(_nmap[(_bsub[i], _p[i])] for i in range(_m))
                    if _best is None or _c < _best[0]:
                        _best = (_c, _bsub, _p)
            if _best is not None:
                _, _bsub, _p = _best
                for _i, _b_ in enumerate(_bsub):
                    _newpairs[_b_] = (_p[_i], round(_nmap[(_b_, _p[_i])], 1))
        for _b_, (_n_new, _d_new) in _newpairs.items():
            _n_old, _d_old = _pairs_orig.get(_b_, (None, None))
            if _n_old is not None and _n_old != _n_new:
                _nswap += 1
                anomalies.append({"aux_idx": _n_old, "kind": "number",
                                  "reason": f"最优指派交换: b{_b_} 注释 {_n_old}→{_n_new}"
                                            f"（{_d_old:.0f}m→{_d_new:.0f}m）"})
        if _nswap:
            print(f"最优 1:1 指派: {_nswap} 处交换（最小总距）")
        _pdf = pd.DataFrame([
            {"num_idx": _n_, "dip": None, "seg_num": "", "idx1894": _b_,
             "seg_1894": "", "dist_m": _d_, "same_seg": ""}
            for _b_, (_n_, _d_) in sorted(_newpairs.items())])
        _dipmap = {int(_n_["aux_idx"]): _n_["dip"] for _n_ in nums}
        _pdf["dip"] = [_dipmap.get(int(x), None) for x in _pdf["num_idx"]]
        # 1:1 硬约束后置强制（2026-09-29）：共享 b 保留最近注释、其余隔离
        # 登记（库尔干先例：共享 b 隔离交裁定；此处远者剔除+注记）
        _dupb = _pdf[_pdf.duplicated("idx1894", keep=False)]
        if len(_dupb):
            _keep = _pdf.groupby("idx1894", sort=False)["dist_m"].apply(
                lambda x: x.astype(float).idxmin()).values
            _drop = _dupb[~_dupb.index.isin(_keep)]
            for _, _dr in _drop.iterrows():
                anomalies.append({"aux_idx": int(_dr["num_idx"]),
                                  "kind": "number",
                                  "reason": f"共享 b{_dr['idx1894']} 隔离："
                                            f"距 {_dr['dist_m']}m 较远剔除"})
            _pdf = _pdf[~_pdf.index.isin(_drop.index)]
            print(f"1:1 后置强制: 共享 b {_dupb['idx1894'].nunique()} 例"
                  f"（剔除 {len(_drop)} 条远注释）")
        # 丢对审计（2026-10-02 b1778/b1699 案）：库配对有对而最终指派无的
        # b——原实现只审计交换（遍历 _newpairs），丢对分支无声漏记
        _pdf_b = set(_pdf["idx1894"].astype(int))
        _n_drop = 0
        for _b_, (_n_old, _d_old) in _pairs_orig.items():
            if _b_ in _pdf_b:
                continue
            _n_new_b = next((int(r_.idx1894) for r_ in
                             _pdf[_pdf["num_idx"] == _n_old].itertuples(index=False)
                             if int(r_.idx1894) != _b_), None)
            _n_drop += 1
            anomalies.append({"aux_idx": _b_, "kind": "symbol",
                              "reason": f"最优指派移除配对: b{_b_} 原注释 {_n_old}"
                                        f"（{_d_old:.0f}m）"
                                        + (f"——注释改配 b{_n_new_b}" if _n_new_b else "")})
        if _n_drop:
            print(f"最优 1:1 指派: {_n_drop} 处移除（b 多于注释簇，注释改配较近 b）")
        # assoc.dip 统一写回（2026-10-02 b1778/b1699 案）：1:1 以最终指派
        # （_pdf）为唯一权威——原实现库配对写 assoc、最优指派只写 pairs 表，
        # build 双通道读出同一注释倾角（b1699 经 pairs、b1778 经 assoc 残留）
        for _r_ in _pdf.itertuples(index=False):
            assoc.loc[assoc["aux_idx"] == int(_r_.idx1894), "dip"] = (
                float(_r_.dip) if _r_.dip is not None else None)
        for _b_ in set(_pairs_orig) - _pdf_b:
            assoc.loc[assoc["aux_idx"] == _b_, "dip"] = None
        _pdf.to_csv(outdir / f"fault_aux_number_{prof.b_symbol_raw}_pairs.csv",
                    index=False, encoding="utf-8-sig")
    print(f"配对: {len(pairs_rows)} 注释 / b 覆盖 "
          f"{assoc['dip'].notna().sum()}/{int((assoc['sub_no'] == 1894).sum())}")

    bsub = assoc[(assoc["sub_no"] == 1894)
                 & (assoc["status_note"].astype(str) != "orphan")]
    asub = assoc[(assoc["sub_no"] == 1281)
                 & (assoc["status_note"].astype(str) != "orphan")]
    seg_gzeeb = {i: str(fl.iloc[i].get("GZEEB") or "").zfill(2) for i in range(len(fl))}
    trip_rows = []  # review 已提前初始化（中位数优先块）
    for fid, grp in bsub.groupby("fault_id"):
        agrp = asub[asub["fault_id"] == fid]
        if not len(agrp):
            continue
        for _, b in grp.iterrows():
            b_id = int(b["aux_idx"])
            up = [a for a in agrp.itertuples(index=False)
                  if a.arc_s < b["arc_s"] and b["arc_s"] - a.arc_s <= ARM_MAX_M]
            dn = [a for a in agrp.itertuples(index=False)
                  if a.arc_s > b["arc_s"] and a.arc_s - b["arc_s"] <= ARM_MAX_M]
            arms = []
            if up:
                arms.append(min(up, key=lambda a: b["arc_s"] - a.arc_s))
            if dn:
                arms.append(min(dn, key=lambda a: a.arc_s - b["arc_s"]))
            if not arms:
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 臂长内无 1281（独立箭头）"})
                continue

            def _band_ok(row):
                sn = str(int(row.sub_no))
                return sn not in band or (band[sn][0] <= float(row.dist_m) <= band[sn][1])
            # a-b-a 合法硬约束（2026-09-29 用户终版）：两 a 必同侧——异侧两 a
            # 为**非法模式，禁止成组**（不构成有效地质语义）；只登记审查册，
            # b 落无运动模式。此闸先于一切判别序（带外短路也不放行）。
            _sl = [a.side for a in arms]
            if (len(arms) == 2 and _sl[0] is not None and _sl[1] is not None
                    and _sl[0] != _sl[1]):
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 非法 a-b-a（两 a 异侧 "
                                       f"{_sl[0]}/{_sl[1]}）已禁止——不构成地质语义"})
                continue
            if not _band_ok(b):
                # b 带外：整组禁止（2026-09-29 严格化）——不发射、只登记审查
                # （带外归属者可经重归属移至带内合法链；无合法去处者留审查）
                _bad = [b_id] + [int(a_.aux_idx) for a_ in arms
                                 if not _band_ok(a_)]
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 带外成员 {_bad}（距离偏离"
                                       f"中位数距离带）禁止成组"})
                continue
            _out_a = [a_ for a_ in arms if not _band_ok(a_)]
            if _out_a:
                # 主路 a-b 降级（2026-09-30 用户裁定，b1847 案）：a-b-a 候选含
                # 带外 a→剔除带外成员、降级 a-b——原生带内 b 就近认领伙伴
                # （a-b 模式空间紧邻原则），免于流入重归属阶段被远端低置信
                # b 抢占（b1962–a1850 3754m 跨距抢占 vs b1847–a1850 858m 紧邻）
                _keep = [a_ for a_ in arms if _band_ok(a_)]
                if not _keep:
                    review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                                   "note": f"{fid} 带外成员 {[int(a_.aux_idx) for a_ in arms]}"
                                           f"（距离偏离中位数距离带）禁止成组"})
                    continue
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 带外 a {[int(x.aux_idx) for x in _out_a]}"
                                       f" 剔除→降级 a-b 成组（空间紧邻原则）"})
                arms = _keep
            gpt = wt.iloc[b_id].geometry
            dab = min(math.hypot((wt.iloc[int(a.aux_idx)].geometry.x - gpt.x) * LON_M,
                                 (wt.iloc[int(a.aux_idx)].geometry.y - gpt.y) * LAT_M)
                      for a in arms)
            if dab < MIN_AB_M:
                v = "存疑（a-b 间距过近，几何退化）"
            elif b["side"] is None or any(a.side is None for a in arms):
                v = "存疑（点近线，侧别不可判）"
            else:
                sa = {a.side for a in arms}
                if b["side"] in sa:
                    v = "正断层产状点"
                else:
                    v = "逆断层产状点"
            _ambig = [int(a_.aux_idx) for a_ in arms
                      if (len(assoc[assoc["aux_idx"] == int(a_.aux_idx)])
                          and int(assoc[assoc["aux_idx"] == int(a_.aux_idx)]
                                  ["n_chains_band"].iloc[0]) >= 2)]
            _bambig = (len(assoc[assoc["aux_idx"] == b_id])
                       and int(assoc[assoc["aux_idx"] == b_id]
                               ["n_chains_band"].iloc[0]) >= 2)
            seg_of_b = int(b["seg_idx"])
            gtype = seg_gzeeb[seg_of_b]
            chk = ""
            if not v.startswith("存疑"):
                exp = "逆断层产状点" if gtype in EXPECT_REVERSE[sh.key] else ""
                if exp:
                    chk = "互证" if v == exp else "冲突"
                    if chk == "冲突":
                        review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                                       "note": f"GZEEB={gtype} 互验冲突（判别={v}）"})
            trip_rows.append({
                "fault_id": fid, "src": "chain_extracted",
                "a1281": "/".join(str(int(a.aux_idx)) for a in arms),
                "a1894": b_id,
                "sides_1281": "/".join(str(a.side) for a in arms),
                "side_1894": b["side"],
                "span_m": round(max([a.arc_s for a in arms] + [b["arc_s"]])
                                - min([a.arc_s for a in arms] + [b["arc_s"]])),
                "verdict": v,
                "form": "a-b-a" if len(arms) == 2 else "a-b",
                "gzeeb_check": chk + ("；a 归属歧义降信" if _ambig else "")
                + ("；b 归属歧义降信" if _bambig else "")
                + ("；带外成员剔除降级" if _out_a else ""),
            })
    # 二次判别（2026-09-30 用户裁定，b1714 案）：孤立的 b——本链带外
    # （超上限）、非孤儿、臂内有首判带内 a——允许上调距离上限至
    # (1+B_SECOND_HI_FRAC)×中位二次判别；判别序与主路一致（a-b-a 同侧
    # 合法闸/a-b≥200m/侧别噪声/同侧正异侧逆/GZEEB 互验）；发射组
    # src=second_pass 挂「二次判别带宽」注记；下限与孤儿闸不动
    _sp_hi = {sn: m * (1 + B_SECOND_HI_FRAC) for sn, m in _med_of.items()}
    _n_sp = 0
    for fid, grp in bsub.groupby("fault_id"):
        agrp = asub[asub["fault_id"] == fid]
        if not len(agrp) or "1894" not in band:
            continue
        for _, b in grp.iterrows():
            b_id = int(b["aux_idx"])
            if str(b["dist_band_ok"]) != "out":
                continue  # 仅首判带外 b
            _dm = float(b["dist_m"])
            if not (band["1894"][0] <= _dm <= _sp_hi["1894"]):
                continue  # 太近（下限不动）或超二次上限/孤儿——不救
            up = [a_ for a_ in agrp.itertuples(index=False)
                  if a_.arc_s < b["arc_s"] and b["arc_s"] - a_.arc_s <= ARM_MAX_M
                  and str(a_.dist_band_ok) != "out"]
            dn = [a_ for a_ in agrp.itertuples(index=False)
                  if a_.arc_s > b["arc_s"] and a_.arc_s - b["arc_s"] <= ARM_MAX_M
                  and str(a_.dist_band_ok) != "out"]
            arms = []
            if up:
                arms.append(min(up, key=lambda a_: b["arc_s"] - a_.arc_s))
            if dn:
                arms.append(min(dn, key=lambda a_: a_.arc_s - b["arc_s"]))
            if not arms:
                continue  # 无带内 a 伙伴——独立箭头（审查册已在主路登记）
            _sl = [a_.side for a_ in arms]
            if (len(arms) == 2 and _sl[0] is not None and _sl[1] is not None
                    and _sl[0] != _sl[1]):
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 非法 a-b-a（两 a 异侧 "
                                       f"{_sl[0]}/{_sl[1]}）二次判别同禁——不构成地质语义"})
                continue
            gpt = wt.iloc[b_id].geometry
            dab = min(math.hypot((wt.iloc[int(a_.aux_idx)].geometry.x - gpt.x) * LON_M,
                                 (wt.iloc[int(a_.aux_idx)].geometry.y - gpt.y) * LAT_M)
                      for a_ in arms)
            if dab < MIN_AB_M:
                v = "存疑（a-b 间距过近，几何退化）"
            elif b["side"] is None or any(a_.side is None for a_ in arms):
                v = "存疑（点近线，侧别不可判）"
            else:
                sa = {a_.side for a_ in arms}
                v = "正断层产状点" if b["side"] in sa else "逆断层产状点"
            _ambig = [int(a_.aux_idx) for a_ in arms
                      if (len(assoc[assoc["aux_idx"] == int(a_.aux_idx)])
                          and int(assoc[assoc["aux_idx"] == int(a_.aux_idx)]
                                  ["n_chains_band"].iloc[0]) >= 2)]
            _bambig = (len(assoc[assoc["aux_idx"] == b_id])
                       and int(assoc[assoc["aux_idx"] == b_id]
                               ["n_chains_band"].iloc[0]) >= 2)
            seg_of_b = int(b["seg_idx"])
            gtype = seg_gzeeb[seg_of_b]
            chk = ""
            if not v.startswith("存疑"):
                exp = "逆断层产状点" if gtype in EXPECT_REVERSE[sh.key] else ""
                if exp:
                    chk = "互证" if v == exp else "冲突"
                    if chk == "冲突":
                        review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                                       "note": f"GZEEB={gtype} 互验冲突（判别={v}）"})
            trip_rows.append({
                "fault_id": fid, "src": "second_pass",
                "a1281": "/".join(str(int(a_.aux_idx)) for a_ in arms),
                "a1894": b_id,
                "sides_1281": "/".join(str(a_.side) for a_ in arms),
                "side_1894": b["side"],
                "span_m": round(max([a_.arc_s for a_ in arms] + [b["arc_s"]])
                                - min([a_.arc_s for a_ in arms] + [b["arc_s"]])),
                "verdict": v,
                "form": "a-b-a" if len(arms) == 2 else "a-b",
                "gzeeb_check": (chk + ("；a 归属歧义降信" if _ambig else "")
                                + ("；b 归属歧义降信" if _bambig else "")
                                + "；二次判别带宽").lstrip("；"),
            })
            review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                           "note": f"{fid} b{b_id} 二次判别成组（b 上限放宽至 "
                                   f"+{int(B_SECOND_HI_FRAC*100)}%×中位，{_dm:.0f}m 入带）"})
            _n_sp += 1
    if _n_sp:
        print(f"二次判别: {_n_sp} 组成组（b 上限 +{int(B_SECOND_HI_FRAC*100)}%×中位）")
    # 孤立 a 重归属（2026-09-29 用户裁定收窄）：**仅低置信度**（归属歧义，
    # n_chains_band≥2）的孤立 a 允许在周边带内链上寻求 a-b-a/a-b 模式——
    # 命中则重归属并成组（method=reattributed）；明确归属的孤立 a 不调整
    _members = set()
    for _t in trip_rows:
        _members.add(int(_t["a1894"]))
        for _x in str(_t["a1281"]).split("/"):
            _members.add(int(_x))
    _iso_a = asub[~asub["aux_idx"].astype(int).isin(_members)]
    # 带外归属 a 豁免孤立闸（存疑组不验证归属，b109 案对偶）
    _outband_a_ids = set(asub[asub["dist_band_ok"].astype(str) == "out"]
                         ["aux_idx"].astype(int))
    _reatt = 0
    for _, _ar in asub[asub["aux_idx"].astype(int)
                       .isin(set(_iso_a["aux_idx"].astype(int)) | _outband_a_ids)].iterrows():
        _aid = int(_ar["aux_idx"])
        # 重归属资格（2026-09-29 用户裁定+分析补充）：低置信度孤立 a——
        # n_chains_band≥2（归属歧义降信）或当前归属带外（归属本不合法，
        # b109 案：最近链带外 69m、邻链带内带 a98）才有资格；
        # 带内且唯一归属的孤立 a 不调整
        _outband_a = str(_ar["dist_band_ok"]) == "out"
        if (int(_ar["n_chains_band"] or 0) < 2 and not _outband_a):
            continue
        _apt = wt.iloc[_aid].geometry
        _old_fid = _ar["fault_id"]
        if "1281" not in band:
            continue
        _lo, _hi = band["1281"]
        _apt_m = _pm(_apt)
        for _fid, _ch in chains.items():
            if _fid == _old_fid:
                continue
            _dm = chains_m[_fid].distance(_apt_m)
            if not (_lo <= _dm <= _hi):
                continue  # 带内约束（合法范围）
            _s_a, _side_a, _dp = _arc_side(_ch, _apt, LON_M, LAT_M)
            # 伙伴带内硬闸（2026-09-30 裁定）：重归属组全员带内——候选 b 与
            # 伙伴 a 均须带内（带外禁止成组对重归属组同样适用，a1690/a1688 案）
            _cand = [x for x in bsub[bsub["fault_id"] == _fid].itertuples(index=False)
                     if abs(x.arc_s - _s_a) <= ARM_MAX_M
                     and str(x.dist_band_ok) != "out"]
            if not _cand:
                continue
            _b = min(_cand, key=lambda x: abs(x.arc_s - _s_a))
            _brow = bsub[bsub["aux_idx"] == int(_b.aux_idx)].iloc[0]
            _other = [x for x in asub[(asub["fault_id"] == _fid)
                                      & (asub["aux_idx"].astype(int) != _aid)].itertuples(index=False)
                      if abs(x.arc_s - _b.arc_s) <= ARM_MAX_M
                      and (x.arc_s < _b.arc_s) != (_s_a < _b.arc_s)
                      and str(x.dist_band_ok) != "out"]
            _arm_side = _side_a
            _all_sides = [int(_arm_side)] + [int(x.side) for x in _other]
            if any(s_ == 0 for s_ in _all_sides):
                continue  # 侧别 None 跳过（近线不可判）
            _s94 = int(_brow["side"])
            if _s94 == 0:
                continue
            if all(s_ == _s94 for s_ in _all_sides):
                _v = "正断层产状点"
            elif all(s_ != _s94 for s_ in _all_sides):
                _v = "逆断层产状点"
            else:
                continue  # 混侧不成组
            # 接受重归属；旧存疑行移除
            trip_rows[:] = [x for x in trip_rows
                            if str(_aid) not in str(x["a1281"]).split("/")
                            or not x["verdict"].startswith("存疑")]
            assoc.loc[assoc["aux_idx"] == _aid, "fault_id"] = _fid
            # seg_idx 随重归属刷新（2026-10-02 修复：build 按 seg 键接——
            # 不刷新则测量符号/平面挂旧断层，b1711 案：标定 F089 而产品 F006）
            _new_seg = min((int(_sg) for _sg in
                            ent[ent["fault_id"] == _fid]["seg_idx"]),
                           key=lambda _s: fl.geometry[_s].distance(_apt))
            assoc.loc[assoc["aux_idx"] == _aid, "seg_idx"] = _new_seg
            assoc.loc[assoc["aux_idx"] == _aid, "arc_s"] = round(_s_a, 0)
            assoc.loc[assoc["aux_idx"] == _aid, "side"] = int(_arm_side)
            assoc.loc[assoc["aux_idx"] == _aid, "dist_m"] = round(_dm, 1)
            _alo, _ahi = band["1281"]
            assoc.loc[assoc["aux_idx"] == _aid, "dist_band_ok"] = (
                "" if _alo <= _dm <= _ahi else "out")
            assoc.loc[assoc["aux_idx"] == _aid, "method"] = "reattributed"
            assoc.loc[assoc["aux_idx"] == _aid, "reattrib_basis"] = (
                "outband" if _outband_a else "ambig")
            _g_a = [int(_aid)] + [int(x.aux_idx) for x in _other]
            _a_amb = any(int(assoc[assoc["aux_idx"] == x]["n_chains_band"]
                             .iloc[0] or 0) >= 2 for x in _g_a)
            _b_amb = int(assoc[assoc["aux_idx"] == int(_b.aux_idx)]
                         ["n_chains_band"].iloc[0] or 0) >= 2
            trip_rows.append({
                "fault_id": _fid, "src": "reattributed",
                "a1281": "/".join([str(_aid)] + [str(int(x.aux_idx)) for x in _other]),
                "a1894": int(_b.aux_idx),
                "sides_1281": "/".join([str(int(_arm_side))]
                                       + [str(int(x.side)) for x in _other]),
                "side_1894": _s94,
                "span_m": round(abs(_s_a - _b.arc_s)),
                "verdict": _v,
                "form": "a-b-a" if _other else "a-b",
                "gzeeb_check": "重归属组"
                + ("；a 归属歧义降信" if _a_amb else "")
                + ("；b 归属歧义降信" if _b_amb else ""),
            })
            _members.add(_aid)
            _reatt += 1
            break  # 一个 a 一次重归属
    print(f"孤立 a 重归属: {_reatt} 点")
    # b 重归属（2026-09-29 用户裁定）：低置信度（n_chains_band≥2）且孤立
    # （无组）的 b，周边（带内候选链）有孤立 a 时允许调整归属寻 a-b-a/a-b
    _iso_a_ids = {int(x.aux_idx) for x in asub.itertuples(index=False)
                  if int(x.aux_idx) not in _members}
    _reatt_b = 0
    for _, _br in bsub.iterrows():
        _bid = int(_br["aux_idx"])
        _outband_b = str(_br["dist_band_ok"]) == "out"
        if _bid in _members:
            continue  # 已有组（含二次判别组）——不动
        if (int(_br["n_chains_band"] or 0) < 2
                and str(_br["dist_band_ok"]) != "out"):
            continue  # 非低置信度且带内归属不调整
        _bpt = wt.iloc[_bid].geometry
        if "1894" not in band:
            continue
        _blo, _bhi = band["1894"]
        _bpt_m = _pm(_bpt)
        for _fid, _ch in chains.items():
            if _fid == _br["fault_id"]:
                continue
            _dm = chains_m[_fid].distance(_bpt_m)
            if not (_blo <= _dm <= _bhi):
                continue
            _s_b, _side_b, _dp = _arc_side(_ch, _bpt, LON_M, LAT_M)
            if _side_b is None:
                continue
            _cand = [int(x.aux_idx) for x in asub[(asub["fault_id"] == _fid)
                                                  & (asub["aux_idx"].astype(int)
                                                     .isin(_iso_a_ids))]
                     .itertuples(index=False)
                     if str(x.dist_band_ok) != "out"]  # 伙伴 a 带内硬闸（2026-09-30）
            if not _cand:
                continue
            _arms = []
            for _ca in _cand:
                _cg = wt.iloc[_ca].geometry
                _cs, _cside, _cdp = _arc_side(_ch, _cg, LON_M, LAT_M)
                if abs(_cs - _s_b) <= ARM_MAX_M and _cside is not None:
                    _arms.append((_ca, _cs, _cside))
            if not _arms:
                continue
            _sides = [int(x[2]) for x in _arms]
            _s94 = int(_side_b)
            if all(x_ == _s94 for x_ in _sides):
                _v = "正断层产状点"
            elif all(x_ != _s94 for x_ in _sides):
                _v = "逆断层产状点"
            else:
                continue  # 混侧不成组
            # 接受 b 重归属；旧存疑行移除（存疑组不验证归属）
            trip_rows[:] = [x for x in trip_rows
                            if int(x["a1894"]) != _bid or not x["verdict"].startswith("存疑")]
            assoc.loc[assoc["aux_idx"] == _bid, "fault_id"] = _fid
            _new_seg = min((int(_sg) for _sg in
                            ent[ent["fault_id"] == _fid]["seg_idx"]),
                           key=lambda _s: fl.geometry[_s].distance(_bpt))
            assoc.loc[assoc["aux_idx"] == _bid, "seg_idx"] = _new_seg
            assoc.loc[assoc["aux_idx"] == _bid, "arc_s"] = round(_s_b, 0)
            assoc.loc[assoc["aux_idx"] == _bid, "side"] = _s94
            assoc.loc[assoc["aux_idx"] == _bid, "dist_m"] = round(_dm, 1)
            _blo, _bhi = band["1894"]
            assoc.loc[assoc["aux_idx"] == _bid, "dist_band_ok"] = (
                "" if _blo <= _dm <= _bhi else "out")
            assoc.loc[assoc["aux_idx"] == _bid, "method"] = "reattributed"
            assoc.loc[assoc["aux_idx"] == _bid, "reattrib_basis"] = (
                "outband" if _outband_b else "ambig")
            # 伴侣 a 不动（本就归属该链——「只允许低置信度 a 或 b 调整归属」；
            # 非低置信度伴侣 a 的归属零变化）
            _g_a = [int(x[0]) for x in _arms]
            _a_amb = any(int(assoc[assoc["aux_idx"] == x]["n_chains_band"]
                             .iloc[0] or 0) >= 2 for x in _g_a)
            _b_amb = int(assoc[assoc["aux_idx"] == _bid]
                         ["n_chains_band"].iloc[0] or 0) >= 2
            trip_rows.append({
                "fault_id": _fid, "src": "reattributed_b",
                "a1281": "/".join(str(x[0]) for x in _arms),
                "a1894": _bid,
                "sides_1281": "/".join(str(x[2]) for x in _arms),
                "side_1894": _s94,
                "span_m": round(max([x[1] for x in _arms] + [_s_b])
                                - min([x[1] for x in _arms] + [_s_b])),
                "verdict": _v,
                "form": "a-b-a" if len(_arms) == 2 else "a-b",
                "gzeeb_check": "b 重归属组"
                + ("；a 归属歧义降信" if _a_amb else "")
                + ("；b 归属歧义降信" if _b_amb else ""),
            })
            for _ca, _cs, _cside in _arms:
                _members.add(_ca)
                _iso_a_ids.discard(_ca)
            _members.add(_bid)
            _reatt_b += 1
            break  # 一个 b 一次重归属
    print(f"孤立 b 重归属: {_reatt_b} 点")


    # a 唯一依附（2026-10-01 用户裁定 verbatim）：「a 只能依附于 1 个 b，
    # 不能被 b 共享；若共享时，a-b-a 模式优先，孤立 a-b 模式的 b」——
    # 共享消解：a-b-a 模式优先（层级高者留），同级保跨距小者；被挤的
    # a-b 模式 b 孤立（行撤销，落独立箭头+审查登记）；被挤行若余 a 则
    # 降 a-b（侧别判别重算）。a1742 案：归 b1743 的 a-b-a 互证组，b1718
    # 可疑正判组撤销（同弧段判别互斥同步消解）
    from collections import defaultdict as _dd2
    _n_uniq = 0
    _amap = _dd2(list)
    for _ri, _t in enumerate(trip_rows):
        for _x in str(_t["a1281"]).split("/"):
            _amap[int(_x)].append(_ri)
    for _aid, _ris in sorted(_amap.items()):
        if len(_ris) < 2:
            continue

        def _score(_ri):
            _t = trip_rows[_ri]
            return (2 if _t["form"] == "a-b-a" else 1, -float(_t["span_m"]))

        _win = max(_ris, key=_score)
        for _ri in _ris:
            if _ri == _win:
                continue
            _t = trip_rows[_ri]
            _ids = [int(x) for x in str(_t["a1281"]).split("/")]
            _ids.remove(_aid)
            review.append({"aux_idx": _aid, "sub_no": 1281,
                           "note": f"a 唯一依附：归 b{trip_rows[_win]['a1894']}"
                                   f"（层级/紧凑优先），自 b{_t['a1894']} 组解除共享"})
            if not _ids:
                _t["_drop"] = True
                review.append({"aux_idx": _t["a1894"],
                               "sub_no": int(prof.b_symbol_raw),
                               "note": f"{_t['fault_id']} b{_t['a1894']} 失唯一 a，"
                                       f"组撤销（独立箭头，倾向-倾角落类）"})
            else:
                _t["a1281"] = "/".join(str(x) for x in _ids)
                _t["sides_1281"] = "/".join(
                    str(int(assoc[assoc["aux_idx"] == x]["side"].iloc[0]))
                    for x in _ids)
                _t["form"] = "a-b"
                _sb = int(_t["side_1894"])
                _sa = {int(assoc[assoc["aux_idx"] == x]["side"].iloc[0])
                       for x in _ids}
                _t["verdict"] = ("正断层产状点" if _sb in _sa else "逆断层产状点")
                _arcs = [float(assoc[assoc["aux_idx"] == x]["arc_s"].iloc[0])
                         for x in _ids]
                _arcs.append(float(assoc[assoc["aux_idx"] == int(_t["a1894"])]
                                   ["arc_s"].iloc[0]))
                _t["span_m"] = round(max(_arcs) - min(_arcs))
            _n_uniq += 1
    if _n_uniq:
        trip_rows[:] = [t_ for t_ in trip_rows if not t_.pop("_drop", False)]
        print(f"a 唯一依附: 共享消解 {_n_uniq} 处（a 只依附 1 个 b）")

    # a-a 对兜底（2026-10-01 用户裁定，唯一性强制之后执行——重复裁定明确
    # 时序：被唯一性释放的孤立低置信 b 由此获得被 a-a 对认领的通道，
    # b1718→F071 案）：判别结束后，孤立的 a-a 对
    # （同链、同侧合法、无 b 依附）若周边存在可配对的低置信度 b——
    # **优先把 b 归属调整与之配对组建设 a-b-a 模式**。资格与 b 重归属
    # 同口径：低置信度（歧义 n≥2 ∨ 现归属带外）且孤立（未参组）、
    # 落点在本链 1894 带内、弧位在两 a 之间且双臂 ≤4km；b 注释随迁；
    # src=reattributed_b_aa 挂「a-a 配对兜底」注记；一个 b 一次移动
    _members = set()
    for _t in trip_rows:
        _members.add(int(_t["a1894"]))
        for _x in str(_t["a1281"]).split("/"):
            _members.add(int(_x))
    _n_aa = 0
    for _fid, _agrp in asub.groupby("fault_id"):
        _free_a = [x for x in _agrp.itertuples(index=False)
                   if int(x.aux_idx) not in _members
                   and str(x.dist_band_ok) != "out" and x.side is not None]
        if len(_free_a) < 2 or "1894" not in band:
            continue
        _free_a.sort(key=lambda x: x.arc_s)
        # 相邻同侧 a 对（弧距 ≤2×臂长，容 b 居中）
        for _i in range(len(_free_a) - 1):
            _a1, _a2 = _free_a[_i], _free_a[_i + 1]
            if _a1.side != _a2.side:
                continue  # a-b-a 合法硬约束：两 a 必同侧
            if _a2.arc_s - _a1.arc_s > 2 * ARM_MAX_M:
                continue
            # 寻低置信度孤立 b：落点本链带内、弧位居中、双臂合法
            _cand_b = []
            for _, _br in bsub.iterrows():
                _bid = int(_br["aux_idx"])
                if _bid in _members:
                    continue  # 已有组不动
                if (int(_br["n_chains_band"] or 0) < 2
                        and str(_br["dist_band_ok"]) != "out"):
                    continue  # 非低置信度不调整（同 b 重归属资格）
                _bpt = wt.iloc[_bid].geometry
                _dm = chains_m[_fid].distance(_pm(_bpt))
                if not (band["1894"][0] <= _dm <= band["1894"][1]):
                    continue  # 落点须本链带内
                _s_b, _side_b, _dp = _arc_side(chains[_fid], _bpt, LON_M, LAT_M)
                if _side_b is None:
                    continue
                if not (_a1.arc_s < _s_b < _a2.arc_s):
                    continue  # 弧位居两 a 之间（a-b-a 构型）
                if min(_s_b - _a1.arc_s, _a2.arc_s - _s_b) > ARM_MAX_M:
                    continue
                _span = _a2.arc_s - _a1.arc_s
                _cand_b.append((_span, _bid, _bpt, _dm, _s_b, _side_b, _br))
            if not _cand_b:
                continue
            _cand_b.sort(key=lambda x: x[0])  # 空间最紧凑优先
            _span, _bid, _bpt, _dm, _s_b, _side_b, _br = _cand_b[0]
            # a-b 间距闸
            _dab = min(
                math.hypot((wt.iloc[int(_a1.aux_idx)].geometry.x - _bpt.x) * LON_M,
                           (wt.iloc[int(_a1.aux_idx)].geometry.y - _bpt.y) * LAT_M),
                math.hypot((wt.iloc[int(_a2.aux_idx)].geometry.x - _bpt.x) * LON_M,
                           (wt.iloc[int(_a2.aux_idx)].geometry.y - _bpt.y) * LAT_M))
            if _dab < MIN_AB_M:
                v = "存疑（a-b 间距过近，几何退化）"
            else:
                v = ("正断层产状点" if int(_side_b) == int(_a1.side)
                     else "逆断层产状点")
            _outband_b = str(_br["dist_band_ok"]) == "out"
            assoc.loc[assoc["aux_idx"] == _bid, "fault_id"] = _fid
            _new_seg = min((int(_sg) for _sg in
                            ent[ent["fault_id"] == _fid]["seg_idx"]),
                           key=lambda _s: fl.geometry[_s].distance(_bpt))
            assoc.loc[assoc["aux_idx"] == _bid, "seg_idx"] = _new_seg
            assoc.loc[assoc["aux_idx"] == _bid, "arc_s"] = round(_s_b, 0)
            assoc.loc[assoc["aux_idx"] == _bid, "side"] = int(_side_b)
            assoc.loc[assoc["aux_idx"] == _bid, "dist_m"] = round(_dm, 1)
            assoc.loc[assoc["aux_idx"] == _bid, "dist_band_ok"] = (
                "" if band["1894"][0] <= _dm <= band["1894"][1] else "out")
            assoc.loc[assoc["aux_idx"] == _bid, "method"] = "reattributed"
            assoc.loc[assoc["aux_idx"] == _bid, "reattrib_basis"] = (
                "outband" if _outband_b else "ambig")
            _b_amb = int(_br["n_chains_band"] or 0) >= 2
            _a_amb = any(int(x.n_chains_band or 0) >= 2 for x in (_a1, _a2))
            trip_rows.append({
                "fault_id": _fid, "src": "reattributed_b_aa",
                "a1281": f"{int(_a1.aux_idx)}/{int(_a2.aux_idx)}",
                "a1894": _bid,
                "sides_1281": f"{int(_a1.side)}/{int(_a2.side)}",
                "side_1894": int(_side_b),
                "span_m": round(_span),
                "verdict": v,
                "form": "a-b-a",
                "gzeeb_check": "a-a 配对兜底"
                + ("；a 归属歧义降信" if _a_amb else "")
                + ("；b 归属歧义降信" if _b_amb else ""),
            })
            review.append({"aux_idx": _bid, "sub_no": int(prof.b_symbol_raw),
                           "note": f"{_fid} a-a 对 [{int(_a1.aux_idx)},"
                                   f"{int(_a2.aux_idx)}] 兜底：b{_bid} 自 "
                                   f"{_br['fault_id']} 调整归属补位（{_dm:.0f}m 带内）"})
            for _x in (_a1, _a2):
                _members.add(int(_x.aux_idx))
            _members.add(_bid)
            _n_aa += 1
            break  # 每条链的 a 对逐个处理（本次一链一对）
    if _n_aa:
        print(f"a-a 对兜底: {_n_aa} 组（b 调整归属补位 a-b-a）")

    # a-b 臂隙兜底（2026-10-01 用户裁定 verbatim）：「当断层辅助点解析
    # 完成后，我们允许 a-b 模式增加臂隙至 5km，沿断层寻找孤立的 a，以
    # 达到可能 a-b-a 模式，只限于寻找孤立状态的 a」——候选硬约束：未参组
    # （孤立）、带内、侧别有效、与既有 a 同侧（a-b-a 合法硬约束）、位于
    # b 的另一弧侧、a-b≥200m；跨距/形式/注记更新，审查留痕
    ARM_EXT_M = 5000.0  # a-b 臂隙兜底上限（用户裁定 5km）
    _members = set()
    for _t in trip_rows:
        _members.add(int(_t["a1894"]))
        for _x in str(_t["a1281"]).split("/"):
            _members.add(int(_x))
    _n_ext = 0
    for _t in trip_rows:
        if _t["form"] != "a-b" or str(_t["verdict"]).startswith("存疑"):
            continue
        _fid = _t["fault_id"]
        _b_id = int(_t["a1894"])
        _a_id = int(_t["a1281"])
        _brow = assoc[assoc["aux_idx"] == _b_id].iloc[0]
        _arow = assoc[assoc["aux_idx"] == _a_id].iloc[0]
        if _arow["side"] is None:
            continue
        _a_side = int(_arow["side"])
        _b_arc, _a_arc = float(_brow["arc_s"]), float(_arow["arc_s"])
        _cands = []
        for _x in asub[asub["fault_id"] == _fid].itertuples(index=False):
            _xa = int(_x.aux_idx)
            if _xa in _members or _xa == _a_id:
                continue  # 只限孤立状态的 a
            if str(_x.dist_band_ok) == "out" or _x.side is None:
                continue
            if int(_x.side) != _a_side:
                continue  # 两 a 必同侧（合法硬约束）
            if (float(_x.arc_s) < _b_arc) == (_a_arc < _b_arc):
                continue  # 须位于 b 的另一弧侧
            _gap = abs(float(_x.arc_s) - _b_arc)
            if _gap > ARM_EXT_M:
                continue
            _cands.append((_gap, _x))
        if not _cands:
            continue
        _cands.sort(key=lambda c: c[0])
        _gap, _x = _cands[0]
        _bpt = wt.iloc[_b_id].geometry
        _xpt = wt.iloc[int(_x.aux_idx)].geometry
        if math.hypot((_xpt.x - _bpt.x) * LON_M, (_xpt.y - _bpt.y) * LAT_M) < MIN_AB_M:
            continue  # 几何退化不升级（保守）
        _t["a1281"] = f"{_a_id}/{int(_x.aux_idx)}"
        _t["sides_1281"] = f"{_a_side}/{int(_x.side)}"
        _t["form"] = "a-b-a"
        _arcs = [_a_arc, _b_arc, float(_x.arc_s)]
        _t["span_m"] = round(max(_arcs) - min(_arcs))
        _t["gzeeb_check"] = (str(_t["gzeeb_check"] or "") + "；臂隙5km兜底").lstrip("；")
        review.append({"aux_idx": int(_x.aux_idx), "sub_no": 1281,
                       "note": f"{_fid} 臂隙5km兜底：a{int(_x.aux_idx)} 补入 "
                               f"b{_b_id} 组升级 a-b-a（弧隙 {_gap:.0f}m）"})
        _members.add(int(_x.aux_idx))
        _n_ext += 1
    if _n_ext:
        print(f"a-b 臂隙兜底: {_n_ext} 组升级 a-b-a（≤5km 孤立 a 补位）")

    # a 复用登记（2026-09-29 分析发现）：同一 a 被 ≥2 个 b 共享=a-b-b-a
    # 形态（一对双短线被两个箭头复用）——地质语义可疑（测量站位重复或
    # 制图重复），登记审查交人工；规则层每 b 独立取臂允许复用（不改判）。
    from collections import defaultdict as _dd
    _ag = _dd(set)
    for _t in trip_rows:
        for _x in str(_t["a1281"]).split("/"):
            _ag[_x].add(_t["a1894"])
    _reuse = {_x: _bs for _x, _bs in _ag.items() if len(_bs) >= 2}
    for _x, _bs in sorted(_reuse.items()):
        review.append({"aux_idx": int(_x), "sub_no": 1281,
                       "note": f"a 复用（a-b-b-a 形态）：被 b {sorted(_bs)} 共享"})
    if _reuse:
        print(f"a 复用登记: {len(_reuse)} 个 a（a-b-b-a 形态，交人工）")

    # 走滑钩对空间识别（2026-10-01 用户裁定「标定算法根据空间知识识别
    # 走滑断层辅助点」）：候选池=辅助点类别中未被 a/b/注释角色消费的点
    # （符号无关）；按空间签名配对（异侧+距带 [50,500]m+垂足纵向 ≤2km），
    # strike_slip_sense 直算旋向；产出 _fault_hooks_<key>.csv（含符号佐证
    # 列 sym1/sym2——符号码降级为确认通道），gzeeb 走滑互验消费之
    # consumed=已被 a(1281)/b(1894)/倾角注释角色消费者（其余符号入候选池；
    # 符号 0=注释角色恒排除——英吉沙 F105/F162 注释对假阳性案）
    _consumed = set(assoc[assoc["sub_no"].isin([1894, 1281])]
                    ["aux_idx"].astype(int))
    _consumed |= set(assoc[assoc["kind"] == "number"]["aux_idx"].astype(int))
    _pool = [(int(r_["_src_id"]), r_.geometry.x, r_.geometry.y)
             for _, r_ in aux_cat.iterrows()
             if int(r_["_src_id"]) not in _consumed
             and int(r_["symbol_no"]) != 0]
    _sym_of = dict(zip(aux_cat["_src_id"].astype(int),
                       aux_cat["symbol_no"].astype(int)))
    # 点级最近链归属（防跨断层假对——奥 515/516 双断层带内重复配案）：
    # 每点先归最近链（归属窗 600m=带顶 500m+裕量），同链子集内配对
    _assign = {}
    for _pid, _px, _py in _pool:
        _d, _fid = min((ch.distance(Point(_px, _py)) * LON_M, fid)
                       for fid, ch in chains.items())
        if _d <= 600.0:
            _assign.setdefault(_fid, []).append((_pid, _px, _py))
    # 段弧位范围（端点投影）——钩对语义=垂足区间内区段的运动学性质
    # （2026-10-01 用户想法：钩对表征所属断层的**某段**而非整个实体）
    _seg_arc = {}
    for _fid, _grp in ent.groupby("fault_id"):
        _ch = chains.get(_fid)
        if _ch is None:
            continue
        for _sg in _grp["seg_idx"].astype(int):
            _g = fl.geometry[_sg]
            _c0, _c1 = _g.coords[0], _g.coords[-1]
            _a0, _ = chain_arc_position(_ch, _c0[0], _c0[1], LON_M, LAT_M)
            _a1, _ = chain_arc_position(_ch, _c1[0], _c1[1], LON_M, LAT_M)
            _seg_arc[(_fid, _sg)] = (min(_a0, _a1), max(_a0, _a1))
    _hook_rows = []
    for _fid, _sub in _assign.items():
        _prs = identify_strike_slip_hooks(chains[_fid], _sub, LON_M, LAT_M)
        for _pr in _prs:
            _i1, _i2 = _pr["ids"]
            _lo, _hi = _pr["foot_arc_m"]
            _segs = [int(_sg) for (_f, _sg), (_s0, _s1) in _seg_arc.items()
                     if _f == _fid and _s1 > _lo and _s0 < _hi]
            _hook_rows.append({
                "fault_id": _fid, "id1": _i1, "id2": _i2,
                "sym1": _sym_of.get(_i1, ""), "sym2": _sym_of.get(_i2, ""),
                "z": round(_pr["z"], 0), "sense": _pr["sense"],
                "dist1_m": _pr["dist_m"][0], "dist2_m": _pr["dist_m"][1],
                "foot_sep_m": _pr["foot_sep_m"],
                "foot_arc1_m": _lo, "foot_arc2_m": _hi,
                "segs": ",".join(map(str, _segs)),
            })
    _hdf = pd.DataFrame(_hook_rows)
    _hp = outdir / f"_fault_hooks_{sh.key}.csv"
    if not len(_hdf):
        # 空表写表头（防下游 read_csv 空文件错误）
        _hdf = pd.DataFrame(columns=["fault_id", "id1", "id2", "sym1", "sym2",
                                     "z", "sense", "dist1_m", "dist2_m",
                                     "foot_sep_m", "foot_arc1_m", "foot_arc2_m",
                                     "segs"])
    _hdf.to_csv(_hp, index=False, encoding="utf-8-sig")
    print(f"走滑钩空间识别: {len(_hdf)} 对 → {_hp.name}"
          f"（候选池 {len(_pool)} 点，符号佐证 {sorted(set(_hdf['sym1']) | set(_hdf['sym2'])) if len(_hdf) else '无'}）")

    tdf = pd.DataFrame(trip_rows)
    tdf.to_csv(outdir / f"_fault_triplets_{sh.key}.csv", index=False, encoding="utf-8-sig")
    assoc.to_csv(outdir / f"fault_aux_{sh.key}.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(review).to_csv(outdir / f"_fault_aux_review_{sh.key}.csv",
                                index=False, encoding="utf-8-sig")
    pd.DataFrame(anomalies).to_csv(outdir / f"_fault_aux_anomalies_{sh.key}.csv",
                                   index=False, encoding="utf-8-sig")
    vc = tdf["verdict"].value_counts().to_dict() if len(tdf) else {}
    print(f"三联体: {len(tdf)} 组 {vc}")
    print(f"审查册: {len(review)} 条 / 异常册: {len(anomalies)} 条")
    return {"entities": len(chains), "assoc": len(assoc), "pairs": len(pairs_rows),
            "triplets": len(tdf), "verdicts": vc, "review": len(review)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c auxchain")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    print(calibrate_auxchain(args.sheet, out_dir=args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
