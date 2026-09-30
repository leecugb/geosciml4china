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
from shapely.geometry import LineString
from shapely.ops import unary_union

from pymapgis.rendering.aux_logic import pair_dip_annotations
from pymapgis.semantics.profile import get_profile

from ..sheets import get_sheet

SIDE_NOISE_M = 20.0      # 侧别噪声阈值（点垂直距<20m 侧别不可判）
MIN_AB_M = 200.0         # a-b 最小间距（符号重叠级）
BAND_FRAC = 0.2          # 距离带下限（a/b 统一 -20%）
B_BAND_HI_FRAC = 0.4     # b(1894) 带上限 +40%（2026-09-30 用户裁定，b1745 案：
                         # 夹缝点——F052 80.3m 太近带外、F129 291.3m 擦边带外；
                         # 取 +40%（315.7m）兼容发现 A 修复后真值 305.3m 双口径同带籍）
A_BAND_HI_FRAC = 0.75    # a(1281) 带上限（下限维持 -20%）：
                         # 2026-09-30 +50%（a1739 案：唯一非孤儿链带外 a 合法化）→
                         # 2026-09-30 +75%（a1742 案：跨段三元组成员 153.2m 合法化；
                         # 选 +75% 非最小拟合 +60%——兼容发现 A 度量修复后真值
                         # 167.9m，两种口径同带籍）
ARM_MAX_M = 4000.0       # 三联体臂长上限
PAIR_MAX_M = 2000.0      # 注释配对硬约束
EXPECT_REVERSE = {"05", "07"}  # GZEEB 逆断层期望码（互验基准）


def _band_limits(sub_no: str, med: float) -> tuple[float, float]:
    """逐类距离带：下限统一 med×(1−BAND_FRAC)；上限 a(1281)=A_BAND_HI_FRAC、
    b(1894)=B_BAND_HI_FRAC（2026-09-30 非对称带系列裁定）。"""
    hi_frac = A_BAND_HI_FRAC if str(sub_no) == "1281" else B_BAND_HI_FRAC
    return (med * (1 - BAND_FRAC), med * (1 + hi_frac))


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
        used.add((i, w))
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
            used.add((j, wj))
            cj = list(segs[j]) if wj == 0 else list(reversed(segs[j]))
            if math.hypot((cj[0][0] - coords[-1][0]), (cj[0][1] - coords[-1][1])) > \
               math.hypot((cj[-1][0] - coords[-1][0]), (cj[-1][1] - coords[-1][1])):
                cj = list(reversed(cj))
            coords += cj[1:]
            cur_i, cur_w = j, (0 if wj == 1 else 1)
        chains.append(LineString(coords))
    return unary_union(chains) if len(chains) > 1 else chains[0]


def _arc_side(chain: LineString, pt, LON_M: float, LAT_M: float):
    """点 → 链折线（米制）弧长/侧别/垂直距（细采样独立实现）。"""
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
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
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

    aux_cat = wt[wt["CHFCEC"].astype(str) == prof.aux_filter]

    rows = []
    for _, r in aux_cat.iterrows():
        idx = int(r["_src_id"])
        sn = int(r["symbol_no"])
        pt = r.geometry
        best = None
        for fid, ch in chains.items():
            dm = ch.distance(pt) * LON_M
            if best is None or dm < best[0]:
                best = (dm, fid, ch)
        dm, fid, ch = best
        s_, side, dperp = _arc_side(ch, pt, LON_M, LAT_M)
        _seg = int(fl.geometry.distance(pt).idxmin())  # b 最近段（build 键接/互验用）
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

    band = {}
    for sn in ("1894", "1281"):
        ds = [float(x) for x in assoc[assoc["sub_no"] == int(sn)]["dist_m"]]
        if not ds:
            continue
        med = sorted(ds)[len(ds) // 2]
        band[sn] = _band_limits(sn, med)
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
        if float(_d) > 2 * (band[_sn][0] / 0.8):
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
        _n = sum(1 for _ch in chains.values()
                 if _lo <= _ch.distance(_pt) * LON_M <= _hi)
        assoc.at[_idx, "n_chains_band"] = _n
        if _n >= 2:
            if _sn == "1281":
                _n_ambig += 1
            else:
                _n_ambig_b += 1
    print(f"a 归属歧义（≥2 链带内）: {_n_ambig} 点 / b: {_n_ambig_b} 点（置信度降低）")

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
            _best_p, _best_c = None, float("inf")
            _m = min(len(_bs), len(_ns))
            for _p in _perm(_ns, _m):
                if any((_bs[i], _p[i]) not in _nmap for i in range(_m)):
                    continue  # 超闸边不可用
                _c = sum(_nmap[(_bs[i], _p[i])] for i in range(_m))
                if _c < _best_c:
                    _best_p, _best_c = _p, _c
            for _i, _b_ in enumerate(_bs):
                if _i < _m:
                    _newpairs[_b_] = (_best_p[_i], round(_nmap[(_b_, _best_p[_i])], 1))
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
        _dipmap = {int(r_.num_idx): r_.dip for r_ in
                   pd.DataFrame(pairs_rows).itertuples(index=False)}
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
        _pdf.to_csv(outdir / f"fault_aux_number_{prof.b_symbol_raw}_pairs.csv",
                    index=False, encoding="utf-8-sig")
    print(f"配对: {len(pairs_rows)} 注释 / b 覆盖 "
          f"{assoc['dip'].notna().sum()}/{int((assoc['sub_no'] == 1894).sum())}")

    bsub = assoc[(assoc["sub_no"] == 1894)
                 & (assoc["status_note"].astype(str) != "orphan")]
    asub = assoc[(assoc["sub_no"] == 1281)
                 & (assoc["status_note"].astype(str) != "orphan")]
    seg_gzeeb = {i: str(fl.iloc[i].get("GZEEB") or "").zfill(2) for i in range(len(fl))}
    review, trip_rows = [], []
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
            if not (_band_ok(b) and all(_band_ok(a) for a in arms)):
                # 距离带硬闸（2026-09-29 严格化）：带外成员禁止成组——
                # 参照非法 a-b-a 先例，不发射、只登记审查（带外归属者可经
                # 重归属移至带内合法链；无合法去处者留审查）
                _bad = [b_id] + [int(a_.aux_idx) for a_ in arms
                                 if not _band_ok(a_)]
                review.append({"aux_idx": b_id, "sub_no": int(prof.b_symbol_raw),
                               "note": f"{fid} 带外成员 {_bad}（距离偏离"
                                       f"中位数距离带）禁止成组"})
                continue
            else:
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
                exp = "逆断层产状点" if gtype in EXPECT_REVERSE else ""
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
                + ("；b 归属歧义降信" if _bambig else ""),
            })
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
        for _fid, _ch in chains.items():
            if _fid == _old_fid:
                continue
            _dm = _ch.distance(_apt) * LON_M
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
        if _bid in _members and not _outband_b:
            continue  # 已有组（且归属带内合法）——不动
        if (int(_br["n_chains_band"] or 0) < 2
                and str(_br["dist_band_ok"]) != "out"):
            continue  # 非低置信度且带内归属不调整
        _bpt = wt.iloc[_bid].geometry
        if "1894" not in band:
            continue
        _blo, _bhi = band["1894"]
        for _fid, _ch in chains.items():
            if _fid == _br["fault_id"]:
                continue
            _dm = _ch.distance(_bpt) * LON_M
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
