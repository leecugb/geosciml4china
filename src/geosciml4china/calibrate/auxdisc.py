# -*- coding: utf-8 -*-
"""断层辅助点实体链判别（geosciml4china.calibrate 第 1.5 域，2026-09-29 泛化优化）。

**实体基础原则（用户裁定）**：辅助点归属判别建立在断层实体基础上——b/a 归属、
弧长、三联体均以实体链（而非单段）为上下文：跨段三元组恢复成组、fault_id 取
实体号（F%03d）、实体级 aux 汇总随之可写回。

判别链（全部裁定在案）：
  · b/a 归属：实体链折线上最近点（米制）→ 弧长 s、垂直距、侧别（<20m 噪声→None）
  · 距离带：逐类（1894/1281）中位±20%（b/a 与所属断层距离约束，用户裁定）
  · 注释配对：注释依附 b、1:1、≤2km（共享库 pair_dip_annotations；本幅无倾角
    注释类别→跳过，倾角留空——不继承 GZECE，用户裁定）
  · 三联体：链弧长上 b 上下游最近 a（臂长≤4km）→ 判别序：带外→存疑 /
    a-b<200m→存疑 / 侧别 None→存疑 / 1281 异侧→存疑 / 同侧=正、异侧=逆
  · GZEEB 互验（05→逆期望）：互证/冲突如实登记；存疑入审查册——零自动改码
  · 孤立的 a 无意义（不成组不入运动语义）

CLI: python -m geosciml4china.calibrate.auxdisc --sheet <key> [--out DIR]
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
BAND_FRAC = 0.2          # 中位±20%带
ARM_MAX_M = 4000.0       # 三联体臂长上限
PAIR_MAX_M = 2000.0      # 注释配对硬约束
EXPECT_REVERSE = {"05", "07"}  # GZEEB 逆断层期望码（互验基准）


def _chain_of(seg_geoms: list, seg_idx: list[int]) -> LineString | None:
    """实体段集 → 链折线（端点相接拼接、必要时反向；单段=自身）。"""
    segs = {i: list(g.coords) for i, g in zip(seg_idx, seg_geoms)}
    if len(segs) == 1:
        return LineString(next(iter(segs.values())))
    # 端点邻接拼接（贪心：未用端点互达 10m 内）
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
        other_w = 0 if w == 1 else 1
        cur_i, cur_w = i, other_w
        while True:
            nxt = None
            for (j, wj), pj in eps.items():
                if j == cur_i or (j, wj) in used:
                    continue
                d = math.hypot((pj[0] - coords[-1][0]) * 1.0, (pj[1] - coords[-1][1]) * 1.0)
                if d < 1e-4:  # ~10m 量级（度）
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


def calibrate_aux(sheet_key: str, out_dir=None) -> dict:
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

    # 实体链
    chains = {}
    for fid, sub in ent.groupby("fault_id"):
        idxs = [int(x) for x in sub["seg_idx"]]
        ch = _chain_of([fl.geometry[i] for i in idxs], idxs)
        if ch is not None:
            chains[fid] = ch
    print(f"实体链: {len(chains)}（实体 {ent['fault_id'].nunique()}）")

    aux_cat = wt[wt["CHFCEC"].astype(str) == prof.aux_filter]

    # b/a 归属：实体链最近
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
        rows.append({
            "aux_idx": idx, "kind": "symbol", "sub_no": sn,
            "angle": float(r["angle"]) if str(r["angle"]).strip() else None,
            "dip": None, "fault_id": fid, "seg_idx": None,
            "dist_m": round(dm, 1), "arc_s": round(s_, 0),
            "side": side, "dperp_m": round(dperp, 1),
            "method": "chain_nearest", "in_band": None,
        })
    assoc = pd.DataFrame(rows).sort_values("aux_idx")

    # 距离带（逐类中位±20%）
    band = {}
    for sn in ("1894", "1281"):
        ds = [float(x) for x in assoc[assoc["sub_no"] == int(sn)]["dist_m"]]
        if not ds:
            continue
        med = sorted(ds)[len(ds) // 2]
        band[sn] = (med * (1 - BAND_FRAC), med * (1 + BAND_FRAC))
        print(f"距离带 {sn}: 中位 {med:.1f}m 带 [{med*0.8:.0f},{med*1.2:.0f}]")
    assoc["dist_band_ok"] = [
        "" if (str(sn) not in band or (r_.dist_m is not None and
                                       band[str(sn)][0] <= float(r_.dist_m) <= band[str(sn)][1]))
        else "out"
        for sn, r_ in zip(assoc["sub_no"], assoc.itertuples(index=False))]
    n_out = int((assoc["dist_band_ok"] == "out").sum())
    print(f"带外点: {n_out}（审查登记）")

    # 注释配对（无倾角注释类别→跳过，倾角留空）
    num_cat = wt[wt["CHFCEC"].astype(str) == "断层注释"]
    pairs_rows, anomalies = [], []
    if len(num_cat):
        b_pts = {}
        for _, r in assoc[assoc["sub_no"] == int(prof.b_symbol_raw)].iterrows():
            pt = wt.iloc[int(r["aux_idx"])].geometry
            b_pts[int(r["aux_idx"])] = (pt.x, pt.y)
        nums = []
        for _, r in num_cat.iterrows():
            m = re.fullmatch(r"(\d+(?:\.\d+)?)°?", str(r["CHFCED"]).strip())
            if not m:
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
            brow = assoc[assoc["aux_idx"] == bidx].iloc[0]
            pairs_rows.append({
                "num_idx": p["aux_idx"], "dip": p.get("dip"),
                "seg_num": "", "idx1894": bidx, "seg_1894": "",
                "dist_m": p["dist_m"], "same_seg": "",
            })
            assoc.loc[assoc["aux_idx"] == bidx, "dip"] = p.get("dip")
    if pairs_rows:
        pd.DataFrame(pairs_rows).sort_values("num_idx").to_csv(
            outdir / f"fault_aux_number_{prof.b_symbol_raw}_pairs.csv",
            index=False, encoding="utf-8-sig")
    print(f"配对: {len(pairs_rows)} 注释 / b 覆盖 "
          f"{assoc['dip'].notna().sum()}/{int((assoc['sub_no'] == int(prof.b_symbol_raw)).sum())}")

    # 三联体（实体链弧长判别）
    bsub = assoc[assoc["sub_no"] == int(prof.b_symbol_raw)]
    asub = assoc[assoc["sub_no"] == 1281]
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
                sn = str(int(row["sub_no"]))
                return sn not in band or (band[sn][0] <= float(row["dist_m"]) <= band[sn][1])
            if not (_band_ok(b) and all(_band_ok(a) for a in arms)):
                v = "存疑（距离偏离中位数±20%带）"
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
                    if len(sa) > 1:
                        v = "存疑（1281自身异侧）"
                    elif b["side"] in sa:
                        v = "正断层产状点"
                    else:
                        v = "逆断层产状点"
            # 互验（b 宿主段码；实体跨段取 b 最近段）
            seg_of_b = int(fl.geometry.distance(wt.iloc[b_id].geometry).idxmin())
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
                "gzeeb_check": chk,
            })
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
    ap = argparse.ArgumentParser(prog="g4c aux")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    print(calibrate_aux(args.sheet, out_dir=args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
