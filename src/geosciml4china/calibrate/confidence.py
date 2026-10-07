# -*- coding: utf-8 -*-
"""codebook 置信度文件（2026-10-07 用户裁定配套）：codebook_confidence_<key>.json。

定位三边界（评估裁定）：
  ① 只读孪生——codebook=可编辑的词典，本文件=只读的标定统计档案；
  ② 机械汇总——只从既有标定 CSV 一次聚合计数，不引入任何新计算口径
    （不重判别、不重置信度重估），绝不做第四真值源；
  ③ 同纪元——与 codebook 同次 prepare 生成、同批时间戳。

内容：各要素域（界线/断层/产状/褶皱/化石/辅助点/面元）的裁决分布、
置信带（S×I×F band）分布、覆盖率、pending/冲突引用；codebook_quality
（各族码源分布、用户编辑数）；provenance（注册表/生成器/同批纪元）。

CLI: g4c confidence --sheet K（重新生成 + 摘要）。
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import pandas as pd

from ..sheets import get_sheet

CONFIDENCE_SCHEMA = "geosciml4china/codebook-confidence/v1"

# 裁决口径中「已建立语义」的排除类（状态/裁决含这些词的段未建立具体语义）
_UNSETTLED_HINTS = ("未覆盖", "兜底", "分歧", "存疑")


def confidence_path(root: Path, key: str) -> Path:
    return Path(root) / f"codebook_confidence_{key}.json"


def _vc(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    return df[col].astype(str).value_counts().to_dict()


def _established_pct(df: pd.DataFrame, col: str) -> float | None:
    """覆盖率 = 1 − 未建立语义段占比（未覆盖/兜底/分歧/存疑）。"""
    if col not in df.columns or not len(df):
        return None
    s = df[col].astype(str)
    unsettled = s.apply(lambda v: any(h in v for h in _UNSETTLED_HINTS))
    return round(100.0 * (1.0 - float(unsettled.mean())), 1)


def _band_counts(df: pd.DataFrame) -> dict:
    for col in ("conf_band_u", "conf_band"):
        if col in df.columns:
            return df[col].astype(str).value_counts().to_dict()
    return {}


def _domain_csv(root: Path, verdict_col: str, extra: dict | None = None) -> dict | None:
    df = pd.read_csv(root, dtype=str)
    out = {
        "total": int(len(df)),
        "verdicts": _vc(df, verdict_col),
        "conf_bands": _band_counts(df),
        "coverage_pct": _established_pct(df, verdict_col),
    }
    if extra:
        out.update(extra)
    return out


def _codebook_quality(cb: dict | None) -> dict:
    if not cb:
        return {}
    out = {}
    for fam, fam_d in (cb.get("codes") or {}).items():
        src = {}
        n_user = 0
        for e in fam_d.values():
            s = str(e.get("source") or "calibration")
            src[s] = src.get(s, 0) + 1
            u = str(e.get("user_semantic") or "").strip()
            if u and u not in ("nan", "None"):
                n_user += 1
        out[fam] = {"codes": len(fam_d), "by_source": src,
                    "user_edits": n_user}
    return out


def build_confidence(sheet_key: str, out_dir=None) -> dict:
    """机械聚合既有标定件 → codebook_confidence_<key>.json（不重算）。"""
    sh = get_sheet(sheet_key)
    root = Path(out_dir) if out_dir else Path(sh.root)
    root.mkdir(parents=True, exist_ok=True)

    domains: dict = {}

    p = root / "_gzbd_semantic_interpretation.csv"
    if p.exists():
        df = pd.read_csv(p, dtype=str)
        st = df["状态"].astype(str)
        domains["boundaries"] = {
            "total": int(len(df)),
            "verdicts": _vc(df, "状态"),
            "conf_bands": _band_counts(df),
            "coverage_pct": _established_pct(df, "状态"),
            "pending": int((st == "分歧未裁定").sum()),
        }
        cr = root / f"_gzbd_conflicts_{sheet_key}.csv"
        if cr.exists():
            domains["boundaries"]["conflict_register"] = cr.name

    p = root / f"_gzeeb_calibration_{sheet_key}.csv"
    if p.exists():
        df = pd.read_csv(p, dtype=str)
        domains["faults"] = {
            "total": int(len(df)),
            "verdicts": _vc(df, "verdict"),
            "conf_bands": _band_counts(df),
            "structural_types": _vc(df, "structural_type"),
            "coverage_pct": _established_pct(df, "verdict"),
        }
        cr = root / f"_gzeeb_conflicts_{sheet_key}.csv"
        if cr.exists():
            domains["faults"]["conflict_register"] = cr.name

    p = root / "_attitude_calibration.csv"
    if p.exists():
        domains["attitudes"] = _domain_csv(p, "verdict")

    for dom, tmpl in (("folds", f"_fold_calibration_{sheet_key}.csv"),
                      ("fossils", f"_fossil_calibration_{sheet_key}.csv")):
        p = root / tmpl
        if p.exists():
            domains[dom] = _domain_csv(p, "verdict")

    p = root / f"fault_aux_{sheet_key}.csv"
    if p.exists():
        df = pd.read_csv(p, dtype=str)
        domains["aux_points"] = {
            "total": int(len(df)),
            "kinds": _vc(df, "kind"),
        }
        an = root / f"_fault_aux_anomalies_{sheet_key}.csv"
        if an.exists():
            domains["aux_points"]["anomaly_register"] = an.name

    p = root / "geojson" / "L1" / "polygons.geojson"
    if p.exists():
        import geopandas as gpd
        g = gpd.read_file(p)
        codes = g["QDUECC_eff"].astype(str).str.strip() \
            if "QDUECC_eff" in g.columns else g["QDUECC"].astype(str).str.strip()
        domains["polygons"] = {
            "total": int(len(g)),
            "blank_code": int((codes == "").sum()),
            "units": int(codes[codes != ""].nunique()),
        }

    from .codebook import codebook_path, load_codebook
    cb = load_codebook(root, sheet_key)
    conf = {
        "codebook_confidence": CONFIDENCE_SCHEMA,
        "sheet": sheet_key,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "readonly": True,
        "note": "只读标定统计档案——机械汇总既有标定 CSV（不重算）；"
                "人工裁定请编辑 codebook_<key>.json",
        "domains": domains,
        "codebook_quality": _codebook_quality(cb),
        "provenance": {
            "generator": "geosciml4china prepare",
            "codebook_generated": (cb or {}).get("generated"),
            "registries": [f"fault_semantics_{sheet_key}.json"]
                          if (root / f"fault_semantics_{sheet_key}.json").exists()
                          else [],
        },
    }
    p = confidence_path(root, sheet_key)
    p.write_text(json.dumps(conf, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return conf


def summary(conf: dict) -> str:
    lines = [f"codebook_confidence {conf['sheet']}（{conf['codebook_confidence']}）"]
    for dom, d in conf["domains"].items():
        cov = d.get("coverage_pct")
        lines.append(f"  {dom}: total={d.get('total')}"
                     + (f" 覆盖率={cov}%" if cov is not None else "")
                     + (f" pending={d['pending']}" if d.get("pending") else ""))
    for fam, q in conf.get("codebook_quality", {}).items():
        lines.append(f"  [{fam}] {q['codes']} 码（源分布 {q['by_source']}，"
                     f"用户编辑 {q['user_edits']}）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c confidence",
                                 description="生成 codebook 置信度文件（只读"
                                             "标定统计档案 JSON）")
    ap.add_argument("--sheet", required=True)
    args = ap.parse_args()
    conf = build_confidence(args.sheet)
    print(summary(conf))
    print(f"已写出: {confidence_path(Path(get_sheet(args.sheet).root), args.sheet)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
