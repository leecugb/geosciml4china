# -*- coding: utf-8 -*-
"""推测断层（GZEEB=04）地质语义标定（geosciml4china.calibrate 第六域移植，
2026-10-02 用户裁定「保留第一项规则即可」——仅覆盖度检查）。

覆盖度核定：≥80% 采样点落松散第四系（剔 Qp1X）/冰雪 → 「推测」前提成立
→ 标定通过；<40%（基岩出露为主）→ 矛盾（交人工）；其余 → 存疑。
连接性（②）与侧别/走向一致（③）按用户裁定不再保留。

输出: _inferred_fault_calibration.csv（04 段逐段：seg_idx/GZEEB/fid/
coverage/verdict）。

CLI: python -m geosciml4china.calibrate.inferred_faults --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import unary_union

from pymapgis.rendering.pdf_writer import _unit_age_rank
from pymapgis.semantics.profile import get_profile

from ..sheets import get_sheet

COV_PASS = 0.8      # ≥80% 覆盖 → 标定通过（推测前提）
COV_CONFLICT = 0.4  # <40% 覆盖 → 矛盾（基岩出露为主）
N_SAMPLE = 8        # 采样点数（t=0.08..0.92 等距）


def calibrate_inferred_faults(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
    lat = float(prof.center_lat_hint)
    outdir = Path(out_dir) if out_dir else sh.root
    outdir.mkdir(parents=True, exist_ok=True)

    faults = gpd.read_file(sh.root / "geojson" / "L1" / "faults.geojson") \
        .sort_values("_src_id").reset_index(drop=True)
    sed = gpd.read_file(sh.root / "geojson" / "L0" / "LDZOFBB001.WP.geojson")
    ice_p = sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson"
    ice = gpd.read_file(ice_p) if ice_p.exists() else \
        gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")

    ent_csv = sh.root / (prof.entities_csv or "fault_entities.csv")
    ent = pd.read_csv(ent_csv, dtype=str)
    seg2fid = dict(zip(ent["seg_idx"].astype(int), ent["fault_id"].astype(str)))

    # 松散第四系（逐行 Qp1X 剔除——2026-10-02 修正冻结链 iloc[0] 缺陷）
    sed = sed.assign(_age=sed["QDUECC"].map(_unit_age_rank))
    q_geoms = [g for g, a, c in zip(sed.geometry.values, sed["_age"].values,
                                    sed["QDUECC"].astype(str).values)
               if g is not None and not g.is_empty and a is not None
               and a >= 1300 and "Qp1X" not in c]
    q_u = unary_union(q_geoms) if q_geoms else None
    ice_u = ice.geometry.union_all() if len(ice) else None

    def seg_coverage(coords):
        line = LineString(coords)
        hit = 0
        for t in np.linspace(0.08, 0.92, N_SAMPLE):
            q = line.interpolate(float(t), normalized=True)
            if (q_u is not None and q_u.intersects(q)) or \
               (ice_u is not None and ice_u.intersects(q)):
                hit += 1
        return hit / N_SAMPLE

    # 候选段集（2026-10-02 泛化）：原始码 04 ∪ 覆盖库生效码 04（英吉沙型——
    # 原码 01/02 经 adjudicated 生效 04 的推测段）
    cand = {i for i in range(len(faults))
            if f"{int(faults.iloc[i]['GZEEB']):02d}" == "04"}
    _gz_p = sh.root / f"_gzeeb_calibration_{sh.key}.csv"
    if _gz_p.exists():
        _gz = pd.read_csv(_gz_p, dtype=str)
        cand |= {int(i) for i in _gz[_gz["gzeeb_eff"].astype(str) == "04"]["idx"]}
    rows = []
    for i in sorted(cand):
        gzeeb = f"{int(faults.iloc[i]['GZEEB']):02d}"
        coords = list(faults.geometry.iloc[i].coords)
        cov = seg_coverage(coords)
        if cov >= COV_PASS:
            verdict = "标定通过（推测断层）"
        elif cov < COV_CONFLICT:
            verdict = "矛盾（基岩出露为主）"
        else:
            verdict = "存疑（覆盖不足）"
        rows.append({"seg_idx": i, "GZEEB": gzeeb,
                     "fid": seg2fid.get(i, ""),
                     "coverage": round(cov, 2), "verdict": verdict})

    out = pd.DataFrame(rows)
    out_p = outdir / f"_inferred_fault_calibration.csv"
    out.to_csv(out_p, index=False, encoding="utf-8-sig")
    print(f"推测断层（04）覆盖度核定: {len(out)} 段 → {out_p.name}")
    print(out["verdict"].value_counts().to_string())
    if len(out):
        print(out[["seg_idx", "fid", "coverage", "verdict"]]
              .to_string(index=False))
    return {"rows": len(out), "verdicts": out["verdict"].value_counts().to_dict(),
            "out_dir": str(outdir)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-inferred-faults")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    calibrate_inferred_faults(args.sheet, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
