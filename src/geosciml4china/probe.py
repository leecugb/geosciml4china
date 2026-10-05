# -*- coding: utf-8 -*-
"""新图幅零注入普查（2026-10-05 用户指令「根据测试，优化泛化能力和速度」）：
一条命令完成新项目接入所需的全部普查与注册。

g4c probe --root D:/新图幅 --key x9 [--register]

普查项（全部来自图幅自身数据，零外部信息）：
  ① 中心纬度（BB001 面元范围中值）
  ② aux 类词与 b 子图号（BB099 CHFCEC 类词 × 子图号普查——含 1281/1894/
    1851 的类词即断层辅助点类；b=1281 的配对倾向码）
  ③ 要素计数（断层/界线/产状/褶皱/面元分布/单元数）
  ④ 数据形态预警（空码面元/零长度界线——td 案形态）
输出：TOML 段 + SheetProfile 段 + verify EXPECT 占位段（直接粘贴即可）。
--register：运行时注册（register_sheet + PROFILES 注入 + EXPECT 占位注入），
注册后即可 g4c pipeline --sheet <key>。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path


def _load_l0(root: Path, fname: str):
    os.environ.setdefault("JWD_SOURCE", "raw")
    from pymapgis.semantics import load_source_layer
    return load_source_layer(str(root), fname, graphic=(fname.endswith(".WT")))


def probe(root: Path, key: str, register: bool = False) -> dict:
    from shapely.geometry import mapping

    # ① 纬度（BB001 面元范围中值）
    g = _load_l0(root, "LDZOFBB001.WP")
    ys = []
    for geom in g.geometry:
        coords = mapping(geom)["coordinates"]
        polys = coords if geom.geom_type == "Polygon" else \
            [c for p in coords for c in p]
        ys += [pt[1] for ring in polys for pt in ring]
    lat_mid = round(sum(ys) / len(ys), 1)

    # ② aux 类词与 b 子图号（BB099 普查）
    wt = _load_l0(root, "LDZOFBB099.WT")
    cats = collections.Counter(str(c) for c in wt["CHFCEC"])
    aux_cat, b_raw = "", 1894
    for cat in cats:
        sub = wt[wt["CHFCEC"] == cat]
        sn = collections.Counter(str(int(float(s))) for s in sub["symbol_no"])
        has_1281 = sn.get("1281", 0)
        partners = [k for k in sn if k not in ("1281", "0")
                    and sn[k] >= max(2, has_1281 // 2)]
        if has_1281 and partners:
            aux_cat = cat
            b_raw = int(partners[0])
            break
    if not aux_cat:  # 无 1281 配对——退而取含 1894/1851 的类词
        for cat in cats:
            sub = wt[wt["CHFCEC"] == cat]
            sn = collections.Counter(str(int(float(s))) for s in sub["symbol_no"])
            if sn.get("1894", 0) >= 2 or sn.get("1851", 0) >= 2:
                aux_cat = cat
                b_raw = 1894 if sn.get("1894", 0) >= sn.get("1851", 0) else 1851
                break

    # ③ 计数
    counts = {}
    for fn, name in (("LDZOFBA003.WL", "faults"), ("LDZOFBA002.WL", "boundaries"),
                     ("LDZOFBA016.WT", "attitudes"), ("LDZOFBA005.WL", "folds")):
        try:
            counts[name] = len(_load_l0(root, fn))
        except Exception:
            counts[name] = 0
    poly_dist, units = {}, set()
    for fn in ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP", "LDZOFBB004.WP"):
        try:
            gg = _load_l0(root, fn)
            poly_dist[fn] = len(gg)
            units |= set(str(c) for c in gg["QDUECC"])
        except Exception:
            pass

    # ④ 形态预警（td 案：空码面元/零长度界线）
    warnings = []
    for fn in ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP", "LDZOFBB004.WP"):
        try:
            gg = _load_l0(root, fn)
            nb = int((gg["QDUECC"].astype(str).str.strip() == "").sum())
            if nb:
                warnings.append(f"{fn} 空码面元×{nb}")
        except Exception:
            pass
    try:
        bb = _load_l0(root, "LDZOFBA002.WL")
        _b = bb.geometry.bounds
        nz = int(((_b["maxx"] - _b["minx"] < 1e-12)
                  & (_b["maxy"] - _b["miny"] < 1e-12)).sum())
        if nz:
            warnings.append(f"零长度界线×{nz}")
    except Exception:
        pass

    out = {
        "key": key, "root": str(root), "lat_mid": lat_mid,
        "aux_filter": aux_cat, "b_symbol_raw": b_raw,
        "counts": counts, "poly_dist": poly_dist,
        "n_units_raw": len(units), "warnings": warnings,
    }

    # 输出模板
    print(f"== 普查结果（{key}，全部来自图幅自身数据） ==")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("\n---- TOML 段（geosciml4china.toml） ----")
    print(f'[sheets.{key}]\nroot = "{root}"\ncode = "J43T00000{key[-1]}"'
          f'\ntitle = "零注入接入 {key}"\n'
          f'aux_pairs_csv = "fault_aux_number_{b_raw}_pairs.csv"\n'
          f'aux_assoc_csv = "fault_aux_{key}.csv"\n'
          f'aux_triplets_csv = "_fault_triplets_{key}.csv"\n'
          f'calibration_csv = "_gzbd_calibration_report.csv"')
    print("\n---- SheetProfile 段（pymapgis PROFILES） ----")
    print(f'"{key}": SheetProfile(sheet="{key}", sheet_title="零注入接入 {key}", '
          f'center_lat_hint={lat_mid}, bbox_margin_frac=0.05, '
          f'aux_filter="{aux_cat}", b_symbol_raw={b_raw}, b_dip_offset_deg=0.0, '
          f'char_dists={{}}, b_angle_remap_deg=0.0, '
          f'color_mapping="output/geosciml/{key}_style_generated.json", '
          f'fault_styles="output/geosciml/{key}_fault_styles_generated.json", '
          f'svg_pattern_registry="", assoc_csv="fault_aux_{key}.csv", '
          f'entities_csv="fault_entities_{key}.csv", '
          f'anomaly_csv="_fault_aux_anomalies.csv", render_themes=[], '
          f'l1_stages=[], verify_stages=[])')

    if register:
        from geosciml4china.sheets import register_sheet, Sheet
        from pymapgis.semantics.profile import PROFILES, SheetProfile
        PROFILES[key] = SheetProfile(
            sheet=key, sheet_title=f"零注入接入 {key}",
            center_lat_hint=lat_mid, bbox_margin_frac=0.05,
            aux_filter=aux_cat, b_symbol_raw=b_raw, b_dip_offset_deg=0.0,
            char_dists={}, b_angle_remap_deg=0.0,
            color_mapping=f"output/geosciml/{key}_style_generated.json",
            fault_styles=f"output/geosciml/{key}_fault_styles_generated.json",
            svg_pattern_registry="",
            assoc_csv=f"fault_aux_{key}.csv",
            entities_csv=f"fault_entities_{key}.csv",
            anomaly_csv="_fault_aux_anomalies.csv",
            render_themes=[], l1_stages=[], verify_stages=[])
        register_sheet(Sheet(
            key=key, code=f"J43T00000{key[-1]}", title=f"零注入接入 {key}",
            root=Path(root),
            aux_pairs_csv=f"fault_aux_number_{b_raw}_pairs.csv",
            aux_assoc_csv=f"fault_aux_{key}.csv",
            aux_triplets_csv=f"_fault_triplets_{key}.csv",
            calibration_csv="_gzbd_calibration_report.csv"))
        from geosciml4china.convert import verify
        verify.EXPECT[key] = dict(
            units=len(units), poly_mfs=sum(poly_dist.values()), contacts=0,
            contact_nil=0, sds=counts["faults"], sds_nil_faulttype=0,
            planes=counts["attitudes"], polarity=0, folds=counts["folds"],
            fold_nil=0, members=0, compositions=0,
            six_mode=(0, 0, 0, 0, 0, 0), orphan_tolerance=True,
            banners=0, dv_blocks=0, ms_dist={}, hwd=0, relations=0,
            measure_points=0, char_dist_b=0.0,
            lite_counts={"geologic_unit_view": poly_dist.get("LDZOFBB001.WP", 0),
                         "contact_view": 0,
                         "shear_displacement_structure_view": counts["faults"],
                         "site_observation_view": counts["attitudes"],
                         "fault_attitude_point_view": 0,
                         "fossil_specimen_view": 0})
        print(f"\n已注册 {key}（profile+sheet+EXPECT 占位）——"
              f"可运行 g4c pipeline --sheet {key}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c probe")
    ap.add_argument("--root", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--register", action="store_true")
    args = ap.parse_args()
    probe(Path(args.root), args.key, args.register)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
