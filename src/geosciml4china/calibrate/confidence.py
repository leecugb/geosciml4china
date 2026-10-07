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

# 分域规范裁决分类（2026-10-07 一阶标定审计优化）：各域裁决词汇不同
# （状态/verdict/通过/违反/decided…），全局关键字匹配会漏判——
# attitudes/fossils 的「违反（待裁定）」不含 未覆盖/兜底/分歧 字样。
# 每域显式给出 pending（待裁定）与 fallback（兜底回落）判定；其余=已建立。
def _settle(df: pd.DataFrame, col: str, pending_kw=(), fallback_kw=()):
    """返回 (established, pending, fallback) 计数。pending/fallback 互斥优先。"""
    s = df[col].astype(str)
    pend = s.apply(lambda v: any(k in v for k in pending_kw)) if pending_kw \
        else pd.Series(False, index=df.index)
    fall = s.apply(lambda v: any(k in v for k in fallback_kw)) if fallback_kw \
        else pd.Series(False, index=df.index)
    est = ~(pend | fall)
    return int(est.sum()), int(pend.sum()), int(fall.sum())


def _band_consistent_pct(df: pd.DataFrame) -> float | None:
    """置信带已评价率（consistent+verified 占比）——与「语义建立率」互补：
    verdict=consistent 但 band=unassessed 的继承段（无独立核验）在此显形。"""
    for col in ("conf_band_u", "conf_band"):
        if col in df.columns and len(df):
            b = df[col].astype(str)
            return round(100.0 * float(b.isin(("consistent", "verified")).mean()), 1)
    return None


def confidence_path(root: Path, key: str) -> Path:
    return Path(root) / f"codebook_confidence_{key}.json"


def _vc(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    return df[col].astype(str).value_counts().to_dict()


def _coverage(est: int, total: int) -> float | None:
    return round(100.0 * est / total, 1) if total else None


def _band_counts(df: pd.DataFrame) -> dict:
    for col in ("conf_band_u", "conf_band"):
        if col in df.columns:
            return df[col].astype(str).value_counts().to_dict()
    return {}


def _domain_csv(root: Path, verdict_col: str, pending_kw=(), fallback_kw=(),
                extra: dict | None = None) -> dict | None:
    df = pd.read_csv(root, dtype=str)
    est, pend, fall = _settle(df, verdict_col, pending_kw, fallback_kw)
    out = {
        "total": int(len(df)),
        "verdicts": _vc(df, verdict_col),
        "conf_bands": _band_counts(df),
        "established": est, "pending": pend, "fallback": fall,
        "coverage_pct": _coverage(est, len(df)),
        "band_consistent_pct": _band_consistent_pct(df),
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
        est, unsettled, fall = _settle(df, "状态", pending_kw=("未覆盖", "分歧"))
        domains["boundaries"] = {
            "total": int(len(df)),
            "verdicts": _vc(df, "状态"),
            "conf_bands": _band_counts(df),
            "established": est, "unsettled": unsettled, "fallback": fall,
            "pending": int((st == "分歧未裁定").sum()),  # 严格裁定队列
            "coverage_pct": _coverage(est, len(df)),
            "band_consistent_pct": _band_consistent_pct(df),
        }
        cr = root / f"_gzbd_conflicts_{sheet_key}.csv"
        if cr.exists():
            domains["boundaries"]["conflict_register"] = cr.name

    p = root / f"_gzeeb_calibration_{sheet_key}.csv"
    if p.exists():
        df = pd.read_csv(p, dtype=str)
        est, pend, fall = _settle(df, "verdict",
                                  pending_kw=("矛盾", "存疑", "分歧"),
                                  fallback_kw=("兜底",))
        domains["faults"] = {
            "total": int(len(df)),
            "verdicts": _vc(df, "verdict"),
            "conf_bands": _band_counts(df),
            "structural_types": _vc(df, "structural_type"),
            "established": est, "pending": pend, "fallback": fall,
            "coverage_pct": _coverage(est, len(df)),
            "band_consistent_pct": _band_consistent_pct(df),
        }
        cr = root / f"_gzeeb_conflicts_{sheet_key}.csv"
        if cr.exists():
            domains["faults"]["conflict_register"] = cr.name

    p = root / "_attitude_calibration.csv"
    if p.exists():
        domains["attitudes"] = _domain_csv(p, "verdict", pending_kw=("违反",))

    p = root / f"_fossil_calibration_{sheet_key}.csv"
    if p.exists():
        domains["fossils"] = _domain_csv(p, "verdict", pending_kw=("违反",))

    p = root / f"_fold_calibration_{sheet_key}.csv"
    if p.exists():
        # 褶皱=词表码义标定域（无段级证据通道，2026-10-03 裁定）——
        # 置信带按设计缺席，显式标注而非留空
        df = pd.read_csv(p, dtype=str)
        domains["folds"] = {
            "total": int(len(df)),
            "verdicts": _vc(df, "verdict"),
            "mode": "vocabulary_only",
            "note": "词表码义标定域（无段级证据通道，置信带按设计缺席）",
        }

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
    # 辅助点判别裁决在三联体件（_fault_triplets_<key>.csv）——
    # 聚合其模式/裁决分布（逆断层产状点/正断层产状点/存疑）
    tp = root / f"_fault_triplets_{sheet_key}.csv"
    if tp.exists():
        t = pd.read_csv(tp, dtype=str)
        est, pend, _ = _settle(t, "verdict", pending_kw=("存疑",))
        domains.setdefault("aux_points", {})["triplets"] = {
            "total": int(len(t)),
            "verdicts": _vc(t, "verdict"),
            "forms": _vc(t, "form"),
            "established": est, "pending": pend,
        }

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
