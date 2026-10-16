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
    pend = (s.apply(lambda v: any(k in v for k in pending_kw)).astype(bool)
            if pending_kw else pd.Series(False, index=df.index, dtype=bool))
    fall = (s.apply(lambda v: any(k in v for k in fallback_kw)).astype(bool)
            if fallback_kw else pd.Series(False, index=df.index, dtype=bool))
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
    try:
        df = pd.read_csv(root, dtype=str)
    except pd.errors.EmptyDataError:
        # 空域件容忍（2026-10-08 新疆115 泛化：无该域产出的幅返回 None）
        return None
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

    from .codebook import codebook_path, load_codebook
    cb = load_codebook(root, sheet_key)   # 前置装载：码级×段级张力检测与
                                          # codebook_quality 共用（2026-10-07）

    domains: dict = {}
    conflicts: dict = {}   # 逐段矛盾冲突明细（2026-10-07 用户建议入档）

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
        # 矛盾明细：图面码×先验期望冲突（永不改码，只登记）。
        # segment_semantic = 冲突段的段级标定语义（2026-10-07 用户裁定：
        # 段级语义保持在置信度文件；接口二产品语义以 codebook 为准）
        sub = df[st == "分歧未裁定"]
        if len(sub):
            conflicts["boundaries"] = [
                {"idx": int(r["idx"]), "code": str(r.get("GZBD原码") or ""),
                 "code_semantic": str(r.get("原码语义") or ""),
                 "segment_semantic": str(r.get("标定语义") or ""),
                 "evidence": str(r.get("证据") or ""),
                 "younger_side": str(r.get("先验年轻侧") or ""),
                 "conf_band": str(r.get("conf_band_u") or ""),
                 "confidence": float(r.get("confidence_u") or 0)}
                for _, r in sub.iterrows()
            ]

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
        sub = df[df["verdict"].astype(str).str.contains("矛盾|存疑|分歧", regex=True)]
        if len(sub):
            conflicts["faults"] = [
                {"idx": int(r["idx"]),
                 "structural_type": str(r.get("structural_type") or ""),
                 "segment_semantic": str(r.get("structural_type") or ""),
                 "verdict": str(r.get("verdict") or ""),
                 "conf_band": str(r.get("conf_band_u") or "")}
                for _, r in sub.iterrows()
            ]

    p = root / "_attitude_calibration.csv"
    if p.exists():
        domains["attitudes"] = _domain_csv(p, "verdict", pending_kw=("违反",))
        _dfa = pd.read_csv(p, dtype=str)
        sub = _dfa[_dfa["verdict"].astype(str).str.contains("违反", regex=True)]
        if len(sub):
            conflicts["attitudes"] = [
                {"idx": int(r["idx"]), "GZBBGA": str(r.get("GZBBGA") or ""),
                 "sem_type": str(r.get("sem_type") or ""),
                 "segment_semantic": str(r.get("sem_type") or ""),
                 "host_code": str(r.get("host_code") or ""),
                 "verdict": str(r["verdict"])}
                for _, r in sub.iterrows()
            ]
        # GZBBGA 码级质量（2026-10-07 裁定：GZBBGA 纳入先验拟合标定——
        # 码义来源 registry/fitted/pending 分布）
        if "code_source" in _dfa.columns:
            _cq = {}
            for _g, _grp in _dfa.groupby("GZBBGA"):
                _cq[str(_g)] = {
                    "segments": int(len(_grp)),
                    "code_sem": str(_grp["code_sem"].iloc[0])
                    if "code_sem" in _dfa.columns else "",
                    "by_source": _grp["code_source"].astype(str)
                    .value_counts().to_dict(),
                }
            domains["attitudes"]["GZBBGA_codes"] = _cq
        # 码级×段级语义张力（2026-10-07 用户裁定：片麻理×面理类矛盾
        # 记录在置信度文件——段级宿主裁定语义 ≠ codebook 码级语义的段
        # 逐条登记：sem_type（段级）× codebook_semantic（码级产品语义））
        from .codebook import semantic_of as _cb_sem_of
        _cbg = (cb or {}).get("codes", {}).get("GZBBGA") or {}
        _tensions = []
        for _, r in _dfa.iterrows():
            _code = str(r.get("GZBBGA") or "")
            _seg = str(r.get("sem_type") or "")
            _cbs = _cb_sem_of({"codes": {"GZBBGA": _cbg}}, "GZBBGA", _code) \
                or str(r.get("code_sem") or "")
            if _seg and _cbs and _seg != _cbs:
                _tensions.append({
                    "idx": int(r["idx"]), "GZBBGA": _code,
                    "segment_semantic": _seg,
                    "codebook_semantic": _cbs,
                    "host_code": str(r.get("host_code") or ""),
                    "verdict": str(r.get("verdict") or ""),
                })
        if _tensions:
            conflicts["attitudes_semantic_tension"] = _tensions
            domains["attitudes"]["semantic_tensions"] = len(_tensions)

    p = root / f"_fossil_calibration_{sheet_key}.csv"
    if p.exists():
        domains["fossils"] = _domain_csv(p, "verdict", pending_kw=("违反",))
        try:
            _dff = pd.read_csv(p, dtype=str)
        except pd.errors.EmptyDataError:
            _dff = pd.DataFrame()
        sub = (_dff[_dff["verdict"].astype(str).str.contains("违反", regex=True)]
               if len(_dff) and "verdict" in _dff.columns
               else _dff.iloc[0:0])
        if len(sub):
            conflicts["fossils"] = [
                {"idx": int(r["idx"]), "category": str(r.get("category") or ""),
                 "sem_type": str(r.get("sem_type") or ""),
                 "segment_semantic": str(r.get("sem_type") or ""),
                 "host_code": str(r.get("host_code") or ""),
                 "verdict": str(r["verdict"])}
                for _, r in sub.iterrows()
            ]

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
            # 编图噪声/系统性编图偏差登记（2026-10-11 用户裁定：距离约束判
            # 定的脱线点记入置信度文件——两级分类逐条转录）
            try:
                _adf2 = pd.read_csv(an, dtype=str)
                if "status" in _adf2.columns:
                    for _cls, _key, _note in (
                            ("editing_noise", "editing_noise",
                             "编图噪声（孤立脱线点，超 500m 测量带上限）——"
                             "允许极少数存在"),
                            ("systematic_deviation", "systematic_deviation",
                             "系统性编图偏差（码群主体离散脱线，不属断层辅助"
                             "点/性质点）")):
                        _nz = _adf2[_adf2["status"] == _cls]
                        if len(_nz):
                            domains["aux_points"][_key] = {
                                "total": int(len(_nz)),
                                "note": _note + "——已出辅助点池",
                                "items": _nz.to_dict("records"),
                            }
            except Exception:
                pass
        # 五类合法集核验登记（2026-10-11 用户裁定：超出五类的辅助点=未遵循
        # 国标、超出解析能力——记入置信度文件交裁定）
        ns = root / f"_fault_aux_nonstandard_{sheet_key}.csv"
        if ns.exists():
            try:
                _ndf = pd.read_csv(ns, dtype=str)
                if len(_ndf):
                    domains.setdefault("aux_points", {})["nonstandard_five_class"] = {
                        "total": int(len(_ndf)),
                        "note": "超出五类合法集（上盘运动方向/倾向指示/走滑钩·左行"
                                "/走滑钩·右行/倾角注记）——未遵循国标、超出解析能力",
                        "items": _ndf.to_dict("records"),
                    }
            except Exception:
                pass
        # 不解析登记（2026-10-13 用户裁定 K46C002002 1539/238 孤点案）：
        # 孤立点不做解析、codebook 语义留空值、存置信度文件——逐条转录
        # 符号码排除册中 role=no_parse 的裁定条目
        _rp = root / "data" / f"fault_aux_code_semantics_{sheet_key}.json"
        if _rp.exists():
            try:
                _reg = json.loads(_rp.read_text(encoding="utf-8"))
                _reg = _reg.get("codes", _reg)
                _np = [{"code": str(c), "points": e.get("points", []),
                        "reason": e.get("reason", ""),
                        "adjudicator": e.get("adjudicator", ""),
                        "date": e.get("date", "")}
                       for c, e in _reg.items()
                       if isinstance(e, dict) and e.get("role") == "no_parse"]
                if _np:
                    domains.setdefault("aux_points", {})["no_parse"] = {
                        "total": len(_np),
                        "note": "不解析（裁定）：孤立点不做解析、codebook 语义留"
                                "空值——点留池计量，不赋任何角色语义",
                        "items": _np,
                    }
            except Exception:
                pass
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

    # 测量误差项（2026-10-08 用户建模裁定：codebook 明确后，理论与实测
    # 的偏差构成测量误差——ε₁ 界线：codebook 接触语义 vs 段级实测语义
    # （地质志+人工标定）；ε₂ 断层：codebook 结构语义 vs 附属产状测量点
    # 运动学语义（_kin_consistent 抽象约束 + aux 反演互验））
    measurement_error: dict = {}

    # ε₁ 界线：解释表逐段 vs codebook GZBD 语义
    _bp = root / "_gzbd_semantic_interpretation.csv"
    if _bp.exists():
        from .codebook import semantic_of as _semof
        _dfb = pd.read_csv(_bp, dtype=str)
        _cbs = (cb or {}).get("codes", {}).get("GZBD") or {}

        def _norm_sem(v):
            # NaN 防空（dtype=str 读空单元格仍可能产出 nan）：空语义归 ""
            s = "" if pd.isna(v) else str(v)
            s = s.split("（")[0].strip()
            return {"角度不整合界线": "角度不整合",
                    "平行不整合界线": "平行不整合"}.get(s, s)
        _match = _dev = _contra = _unc = 0
        _dev_segs = []
        for _, r in _dfb.iterrows():
            _seg = _norm_sem(r.get("标定语义"))
            # 对称归一（2026-10-16 A3）：codebook 侧同过 _norm_sem——此前
            # 仅段侧归一，注释变体对（断层接触 vs 断层接触（断裂界线））
            # 被误计为偏差（y1 626 偏差中 593 条为此类），虚高偏差数
            _cod = _norm_sem(_semof({"codes": {"GZBD": _cbs}}, "GZBD",
                                    r.get("GZBD_eff") or r.get("GZBD原码")))
            _st = str(r.get("状态") or "")
            if _st == "分歧未裁定":
                _contra += 1
                _dev_segs.append({"idx": int(r["idx"]),
                                  "segment_semantic": _seg,
                                  "codebook_semantic": _cod,
                                  "class": "contradiction"})
            elif not _seg or not _cod:
                _unc += 1    # 语义未建立（未覆盖/码未解析）——不称匹配
            elif _seg != _cod:
                _dev += 1
                _dev_segs.append({"idx": int(r["idx"]),
                                  "segment_semantic": _seg,
                                  "codebook_semantic": _cod,
                                  "class": "deviation"})
            else:
                _match += 1
        measurement_error["boundary_deviation"] = {
            "total": int(len(_dfb)),
            "match": _match, "deviation": _dev,
            "contradiction": _contra,   # 分歧未裁定=超阈保留观测
            "uncovered": _unc,          # 语义未建立（未覆盖/码未解析）
            "segments": _dev_segs,
        }

    # ε₂ 断层：结构×运动学一致性扫描（violation=超阈测量误差）+ aux 反演
    _fp = root / f"_gzeeb_calibration_{sheet_key}.csv"
    if _fp.exists():
        from .gzeeb import _kin_consistent as _kc
        _dff = pd.read_csv(_fp, dtype=str)
        _ok = _viol = _neutral = 0
        _viol_segs = []
        for _, r in _dff.iterrows():
            _res = _kc(str(r.get("structural_type") or ""),
                        str(r.get("gzeld_sem") or ""))
            if _res is False:
                _viol += 1
                _viol_segs.append({"idx": int(r["idx"]),
                                   "structural_type":
                                       str(r.get("structural_type") or ""),
                                   "kinematic_semantic":
                                       str(r.get("gzeld_sem") or ""),
                                   "class": "violation"})
            elif _res is True:
                _ok += 1
            else:
                _neutral += 1
        # 证据冲突（aux 产状测量点反演互验等——冲突登记册 issue 含
        # 「证据冲突」类）：真测量误差项；「码义未注册/全继承」为
        # 注册状态记录，不计入测量误差
        _crp = root / f"_gzeeb_conflicts_{sheet_key}.csv"
        _ev_conf = []
        if _crp.exists():
            import ast as _ast
            _dfc = pd.read_csv(_crp, dtype=str)
            for _, r in _dfc.iterrows():
                if "证据冲突" not in str(r.get("issue") or ""):
                    continue
                try:
                    _sg = _ast.literal_eval(str(r.get("segs")))
                    if not isinstance(_sg, list):
                        _sg = [int(_sg)]
                except Exception:
                    _sg = []
                for _s in _sg:
                    _ev_conf.append({"idx": int(_s),
                                     "issue": str(r.get("issue") or ""),
                                     "evidence": str(r.get("evidence") or "")[:120],
                                     "class": "evidence_conflict"})
        measurement_error["fault_kinematic_deviation"] = {
            "total": int(len(_dff)),
            "consistent": _ok, "violation": _viol, "neutral": _neutral,
            "segments": _viol_segs,
            "evidence_conflicts": _ev_conf,
            "evidence_conflict_count": len(_ev_conf),
        }

    conf = {
        "codebook_confidence": CONFIDENCE_SCHEMA,
        "sheet": sheet_key,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "readonly": True,
        "note": "只读标定统计档案——机械汇总既有标定 CSV（不重算）；"
                "人工裁定请编辑 codebook_<key>.json",
        "domains": domains,
        "conflicts": conflicts,   # 逐段矛盾冲突明细（2026-10-07 用户建议：
        # 图面码×先验/证据冲突逐段登记——记录但不修改编码；
        # segment_semantic 字段=冲突段的段级标定语义（同日裁定：段级语义
        # 保持在置信度文件；接口二产品语义以 codebook 为准））
        "measurement_error": measurement_error,   # 测量误差项（2026-10-08
        # 用户建模裁定：理论(codebook) vs 实测(段级/产状点) 的偏差=测量误差）
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
        if d is None:
            lines.append(f"  {dom}: 空域（无产出件）")
            continue
        cov = d.get("coverage_pct")
        lines.append(f"  {dom}: total={d.get('total')}"
                     + (f" 覆盖率={cov}%" if cov is not None else "")
                     + (f" pending={d['pending']}" if d.get("pending") else ""))
    n_conf = sum(len(v) for v in conf.get("conflicts", {}).values())
    if n_conf:
        lines.append(f"  conflicts: {n_conf} 段矛盾冲突明细在档"
                     f"（{ {k: len(v) for k, v in conf['conflicts'].items()} }）")
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
