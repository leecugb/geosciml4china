# -*- coding: utf-8 -*-
"""化石/特异点自支持标定（geosciml4china.calibrate 第四域移植，2026-10-02）。

移植自 _audit_fossils.py（244 行，2026-09-26 三类体系用户裁定后建，双幅通用）。
对象：LDZOFBB099.WT 中 CHFCEC=化石（1415 植物/1445 动物/3021 孢粉）与
CHFCEC=泥火山（1304）点。证据只登记不改码，冲突交人工裁定。

多通道互证（每通道独立证据）：
- A 宿主相容：化石产于沉积地层——sediment 通过 / volcanic 审查（火山碎屑
  夹层可产化石）/ metamorphic/intrusive/无宿主 → 冲突候选；泥火山应落
  第四系（Q 开头单元）；宿主判定双轨（contains 优先，贴线最近面 ≤200m 兜底）；
- B 类别-码交叉：化石码点必须在 CHFCEC=化石类，否则「类别误挂候选」；
  化石类中未知码 → 审查；
- C 角度约定带：按类约定角（1415/1445/1304≈0°、3021≈180°）环形偏差
  >15° → 摆放异常审查；
- D 覆盖相容：落冰川/水体面元 → 冲突候选；
- E 聚集性注记：距最近同类 >10km → isolation 注记（非违规）。

输出：_fossil_calibration_<sheet>.csv（逐点六列证据+verdict+confidence）
/ _fossil_conflicts_<sheet>.csv（冲突登记册，合并保留 adjudicated 条目）。
库尔干影子逐字节复现为准入闸。

CLI: python -m geosciml4china.calibrate.fossils --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree

from pymapgis.rendering.pdf_writer import (corrected_polygon_code,
                                           load_polygon_overrides)
from pymapgis.semantics.profile import get_profile

from ..data import data_path
from ..sheets import get_sheet
from ..convert import model

_STRATA_CLASS = {"LDZOFBB001.WP": "sediment", "LDZOFBB002.WP": "volcanic",
                 "LDZOFBB003.WP": "intrusive", "LDZOFBB004.WP": "metamorphic"}
NEAR_MAX = 0.0024          # 贴线最近面兜底阈值（≈200m，与产状标定同）


def ang_dev(a, conv):
    d = abs((float(a) - conv) % 360.0)
    return min(d, 360.0 - d)


def calibrate_fossils(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
    outdir = Path(out_dir) if out_dir else sh.root
    outdir.mkdir(parents=True, exist_ok=True)

    # 注册表链（泛化 2026-10-02）：图幅文件优先 → 包数据兜底
    _reg_cands = [sh.root / "fossil_code_semantics.json",
                  sh.root / "data" / "fossil_code_semantics.json",
                  data_path("fossil_code_semantics.json")]
    reg = None
    for _c in _reg_cands:
        _cp = Path(_c)
        if _cp.exists():
            reg = json.load(open(_cp, encoding="utf-8"))
            break
    ftypes = reg["fossil_types"]
    mv = reg["mud_volcano"]
    band = float(reg["angle_band_deg"])
    iso_m = float(reg["isolation_note_m"])
    sem_of = {**{k: v["semantic"] for k, v in ftypes.items()},
              **{k: v["semantic"] for k, v in mv.items()}}
    conv_of = {**{k: v["angle_conv"] for k, v in ftypes.items()},
               **{k: v["angle_conv"] for k, v in mv.items()}}
    fossil_codes = tuple(ftypes.keys())  # 注册表驱动（FOSSIL_CODES 泛化）

    def _l0(name):
        # geojson/L0 优先；缺失时 MapGIS 源兜底；仍无则空表
        p = sh.root / "geojson" / "L0" / f"{name}.geojson"
        if p.exists():
            return gpd.read_file(p)
        src = sh.root / name
        if src.exists():
            from pymapgis.semantics import load_source_layer
            return load_source_layer(str(sh.root), name, graphic=False)
        return gpd.GeoDataFrame({"geometry": [], "QDUECC": []},
                                crs="EPSG:4326")

    wt = _l0("LDZOFBB099.WT")
    if not len(wt) or "CHFCEC" not in wt.columns:
        print(f"化石标定[{sh.key}]: 0 点（无注记图层）")
        return {"rows": 0, "conflicts": 0, "out_dir": str(outdir)}

    # 宿主面元（四 WP + 覆盖库改正，与产状标定同构）
    ov_path = None
    for _c in (sh.root / "polygon_attribution_overrides.json",
               sh.root / "data" / "polygon_attribution_overrides.json"):
        if _c.exists():
            ov_path = _c
            break
    ov = load_polygon_overrides(str(ov_path)) if ov_path is not None else \
        {"overrides": {}}
    geoms, codes, layers = [], [], []
    for fn, cls in _STRATA_CLASS.items():
        g = _l0(fn)
        if not len(g):
            continue
        for i in range(len(g)):
            raw = str(g["QDUECC"].iloc[i])
            geoms.append(g.geometry.iloc[i])
            codes.append(corrected_polygon_code(fn, i, raw, ov))
            layers.append(cls)
    tree = STRtree(geoms)

    def host(x, y):
        p = Point(x, y)
        idxs = tree.query(p, predicate="intersects")
        if len(idxs):
            return codes[idxs[0]], layers[idxs[0]], 0.0, "contains"
        dists = sorted((g.distance(p), i) for i, g in enumerate(geoms))
        if dists and dists[0][0] <= NEAR_MAX:
            di = dists[0][1]
            return codes[di], layers[di], dists[0][0] * 111320.0, "nearest"
        return None, None, None, "无宿主"

    # 覆盖面元（冰川/水体）
    cover = []
    wpath = sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson"
    if wpath.exists():
        cover = [g for g in gpd.read_file(wpath).geometry.values
                 if g is not None and not g.is_empty]

    rows, conflicts = [], []
    # 类别参数化（2026-10-02 泛化审计）：图幅类别名随幅（aux_filter 先例）
    _fossil_cats = list(getattr(prof, "fossil_categories", None)
                        or [model.SPECIMEN_KINDS["fossil"], model.SPECIMEN_KINDS["mudvolcano"]])
    targets = wt[wt["CHFCEC"].isin(_fossil_cats)]
    pts_cache = {}
    for idx, r in targets.iterrows():
        g = r.geometry
        if g is None or g.is_empty:
            continue
        cat = str(r["CHFCEC"])
        sn = str(int(r["symbol_no"]))
        sem = sem_of.get(sn)
        hc, hl, hdist, method = host(g.x, g.y)
        checks, viol = [], []
        # A 宿主相容
        if cat == model.SPECIMEN_KINDS["fossil"]:
            if hl == "sediment":
                checks.append(f"宿主{hc}(沉积)")
            elif hl == "volcanic":
                checks.append(f"宿主{hc}(火山岩)")
                viol.append(f"宿主火山岩 {hc}（审查：碎屑夹层可产化石）")
            elif hl is None:
                viol.append("无宿主（水面/图外）")
            else:
                viol.append(f"宿主{hl} {hc}（化石应产沉积地层）")
        else:  # 泥火山（宿主码剥饰后首字符须为 Q——装饰码形如 →Qh↑vl→-Qh↑ch）
            hc_norm = re.sub(r"[→↓↑\-]", "", str(hc or "")).strip()
            if hc_norm.startswith("Q"):
                checks.append(f"宿主{hc}(第四系)")
            elif hl is None:
                viol.append("无宿主（水面/图外）")
            else:
                viol.append(f"泥火山宿主 {hc} 非第四系")
        # B 码在化石类中已知性（类别本身已由 CHFCEC 保证；未知码审查）
        if sem is None:
            viol.append(f"子图码 {sn} 未注册（"
                        f"{'化石' if cat == '化石' else '泥火山'}类未知码）")
        else:
            checks.append(f"码义{sem}")
        # C 角度约定带
        if sn in conv_of:
            dv = ang_dev(r["angle"], conv_of[sn])
            if dv <= band:
                checks.append(f"角度{float(r['angle']):.1f}°(Δ{dv:.1f})")
            else:
                viol.append(f"角度 {float(r['angle']):.1f}° 偏离约定 "
                            f"{conv_of[sn]:.0f}°±{band:.0f}°（Δ{dv:.1f}°）")
        # D 覆盖相容
        p = g
        if any(cv.contains(p) or cv.touches(p) for cv in cover):
            viol.append("落冰川/水体面元")
        pts_cache[int(idx)] = (g.x, g.y)
        # 判定
        if viol:
            verdict, conf = "违反（待裁定）", 0.3
            conflicts.append({
                "idx": int(idx), "category": cat, "sub_no": sn,
                "issue": f"{sem or sn} 证据冲突",
                "evidence": "；".join(viol), "status": "pending_review"})
        else:
            verdict = "verified" if len(checks) >= 3 else "consistent"
            conf = 0.9 if len(checks) >= 3 else 0.75
        rows.append(dict(idx=int(idx), category=cat, sub_no=sn,
                         sem_type=sem or "未知", host_code=hc,
                         host_class=hl, host_dist_m=hdist,
                         probe_method=method, angle=float(r["angle"]),
                         verdict=verdict, confidence=conf,
                         checks="；".join(checks)))

    # E 聚集性注记（非违规）：化石类内最近距 >iso_m
    fpts = [(r["idx"], pts_cache[r["idx"]]) for r in rows
            if r["category"] == model.SPECIMEN_KINDS["fossil"] and r["idx"] in pts_cache]
    LON_M = 111320.0 * math.cos(math.radians(prof.center_lat_hint))
    for r in rows:
        if r["category"] != model.SPECIMEN_KINDS["fossil"] or r["idx"] not in pts_cache:
            continue
        x, y = pts_cache[r["idx"]]
        dmin = min((math.hypot((x - ox) * LON_M, (y - oy) * 111320.0)
                    for oi, (ox, oy) in fpts if oi != r["idx"]),
                   default=float("nan"))
        r["nearest_fossil_m"] = round(dmin, 0) if dmin == dmin else None
        if dmin == dmin and dmin > iso_m:
            r["checks"] += f"；孤立化石点（最近同类 {dmin / 1000:.1f}km）"
            r["confidence"] = min(r["confidence"], 0.6)

    # 影子置信度（统一框架 S×I×F，2026-09-27 裁定参数；旧列 confidence 不动）
    from pymapgis.semantics.confidence import (check_classes, emit_columns,
                                               evaluate, fit_from_residual)
    _FCLASS = {"HOST": ("宿主",), "REG": ("码义",), "ANG": ("角度",)}
    for r in rows:
        v = str(r["verdict"])
        if "违反" in v:
            bd = evaluate("verified", fit=0.0,
                          reasons=("违反", str(r.get("sem_type", ""))))
        else:
            sn = str(r["sub_no"])
            n_cls = len(check_classes(r.get("checks", ""), _FCLASS))
            indep = ("multi_root" if n_cls >= 3
                     else "intra_class" if n_cls == 2 else "single")
            if sn in conv_of:
                dv = ang_dev(r["angle"], conv_of[sn])
                f = fit_from_residual(dv, band)
                fnote = f"res={dv:.2f}° tol={band}°"
            else:
                f, fnote = 1.0, "无角度约定码"
            isolated = (r.get("nearest_fossil_m") is not None
                        and r["nearest_fossil_m"] == r["nearest_fossil_m"]
                        and r["nearest_fossil_m"] > iso_m)
            bd = evaluate("verified", indep, f,
                          counterexample_open=isolated,
                          reasons=(f"checks={n_cls}类",), fit_note=fnote)
        emit_columns(r, bd, shadow=True)

    # B 反向通道：化石码点不在化石类（类别误挂候选，全 WT 扫描）
    in_fossil = set(int(i) for i in targets.index)
    for idx, r in wt.iterrows():
        sn = str(int(r["symbol_no"]))
        if sn in fossil_codes and int(idx) not in in_fossil:
            conflicts.append({
                "idx": int(idx), "category": str(r["CHFCEC"]),
                "sub_no": sn,
                "issue": "化石码点挂非化石类（类别误挂候选）",
                "evidence": f"子图{sn}({sem_of.get(sn, '?')}) 位于 "
                            f"CHFCEC={r['CHFCEC']}",
                "status": "pending_review"})

    out = pd.DataFrame(rows)
    out_p = outdir / f"_fossil_calibration_{sh.key}.csv"
    if not len(out):
        out.to_csv(out_p, index=False, encoding="utf-8-sig")
        print(f"化石标定[{sh.key}]: 0 点（无化石/泥火山要素）→ {out_p.name}")
        return {"rows": 0, "conflicts": 0, "out_dir": str(outdir)}
    out.to_csv(out_p, index=False, encoding="utf-8-sig")
    reg_p = outdir / f"_fossil_conflicts_{sh.key}.csv"
    if conflicts:
        new_conf = pd.DataFrame(conflicts)
        if reg_p.exists():
            old = pd.read_csv(reg_p, dtype=str)
            keep = old[old["status"] == "adjudicated"]
            new_conf = pd.concat([keep, new_conf], ignore_index=True)
        new_conf.to_csv(reg_p, index=False, encoding="utf-8-sig")
    print(f"化石标定[{sh.key}]: {len(out)} 点（化石 "
          f"{(out['category'] == '化石').sum()} + 泥火山 "
          f"{(out['category'] == '泥火山').sum()}）"
          f"→ {out_p.name}；冲突 {len(conflicts)} 条")
    print("  verdict:", out["verdict"].value_counts().to_dict())
    print("  类型分布:", out["sem_type"].value_counts().to_dict())
    return {"rows": len(out), "conflicts": len(conflicts),
            "verdicts": out["verdict"].value_counts().to_dict(),
            "out_dir": str(outdir)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-fossils")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    calibrate_fossils(args.sheet, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
