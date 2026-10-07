# -*- coding: utf-8 -*-
"""产状类型自支持标定（geosciml4china.calibrate 第三域移植，2026-10-02）。

移植自 _audit_attitudes.py（275 行，2026-09-24 用户定约束，双幅通用）：
产状点 → 宿主面单元（含面元归属覆盖）→ 时代/岩性 → 类型约束校验：
- R1' 新生代/中生代地层宿主 → 必须 202001/202004；
- R2' 片理(202005) → 允许古生代/前寒武纪地层（Mz/Cz 宿主违反）；
- R3' 片麻理 → 仅前寒武纪地层（裁定宿主规则：HtA/Pt1K. → 片麻理产状，
  2026-09-24 用户裁定；原始 GZBBGA 不改写，有效类型入 sem_type）；
- R4' 面理(202011/202007) → 仅岩浆岩（侵入岩宿主一律派生面理产状）；
- 裁定宿主规则：HtA/Pt1K. → 片麻理产状（豁免通用约束）。

2026-09-24 优化（用户定）：
① 宿主判定双轨化——精确命中（contains）优先，无命中时贴线最近面兜底
  （≤NEAR_MAX°≈200m），宿主方法与距离入证据列（host_dist_m/probe_method）；
② 数据质量门——走向⊥倾向（|∠−90|>0.5°）与倾角域值（∉[0,90]）登记入册；
③ 单元内类型一致性审计——同宿主单元混标类型超出宿主族允许集时登记
  「单元混标审查」（Pz 沉积层理/片理二元合法不登记）；
④ 标定表证据列 host_code/host_layer/host_era/host_dist_m/probe_method/era_rank。
违反登记 _attitude_anomalies.csv（不改码）；全量 _attitude_calibration.csv。
库尔干影子逐字节复现为准入闸。

CLI: python -m geosciml4china.calibrate.attitudes --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.strtree import STRtree

# pymapgis 完整地质栈导入守卫（2026-10-04 CI 泛化：PyPI mapgis2shp 仅含
# 极简读取器——rendering 子包未发布；缺席时绑定 None 使模块 import 安全，
# 执行路径首用自然报错；完整栈在场行为不变）
try:
    from pymapgis.rendering.pdf_writer import (_unit_age_rank,
                                               corrected_polygon_code,
                                               load_polygon_overrides)
except ModuleNotFoundError:  # PyPI-minimal 环境
    _unit_age_rank = corrected_polygon_code = load_polygon_overrides = None

from ..sheets import get_sheet

STRATA = {"sediment", "volcanic", "metamorphic"}
MAGMA = {"intrusive", "volcanic"}
_STRATA_CLASS = {"LDZOFBB001.WP": "sediment", "LDZOFBB002.WP": "volcanic",
                 "LDZOFBB003.WP": "intrusive", "LDZOFBB004.WP": "metamorphic"}
ADJ_HOST = {"HtA": "片麻理产状", "Pt1K": "片麻理产状"}
NEAR_MAX = 0.0024          # 贴线最近面兜底阈值（≈200m）
_FAMILY_ALLOW = {"metamorphic": {"片理", "片麻理"},
                 "intrusive": {"面理"},
                 # 火山岩：地层产状合法（2026-09-24 用户裁定）+ 面理（R4' 岩浆岩合法宿主）
                 "volcanic": {"面理", "层理", "倒转层理"},
                 "Mz-Cz": {"层理", "倒转层理"}}
_CAT = {"202001": "层理", "202004": "倒转层理", "202005": "片理",
        "202011": "面理", "202007": "面理", "面理产状": "面理",
        "片麻理产状": "片麻理", "地层产状": "层理", "片理产状": "片理",
        "倒转层理": "倒转层理"}
# 码义 → 语义标签（同码继承原则 2026-10-03：码义已定，sem_type 继承语义）
_CODE_SEM = {"202001": "地层产状", "202004": "倒转层理",
             "202005": "片理产状", "202007": "面理产状",
             "202011": "面理产状"}

# 族映射（先验拟合张力检测用：层理族含 地层/倒转 两个标签——
# 族级比较避免 202004 倒转层理 被误报张力）
_FAMILY_OF = {"地层产状": "层理", "倒转层理": "层理", "片理产状": "片理",
              "面理产状": "面理", "片麻理产状": "片麻理"}

# 宿主签名 → 拟合候选语义（2026-10-07 用户裁定：GZBBGA 纳入先验拟合标定；
# 先验=宿主岩性族×时代组的地质学约束，与 R1'-R4'/Pt1 裁定同源）
_HOST_FIT = {
    ("intrusive", "*"): "面理产状",
    ("metamorphic", "Pc"): "片麻理产状",
    ("metamorphic", "Pz"): "片理产状",
    ("sediment", "*"): "地层产状",
    ("volcanic", "*"): "地层产状",
}

FIT_MIN_SEGS = 5        # 码级拟合最少段数
FIT_DOMINANCE = 0.6     # 码级拟合主导阈值


def _fit_candidate(grp: pd.DataFrame) -> str | None:
    """宿主签名投票 → 主导拟合候选（≥FIT_MIN_SEGS 且 ≥FIT_DOMINANCE）；
    无主导 → None。纯统计，不含注册表优先级。

    变质宿主按 Pt1 时代规则分流（2026-10-07 修复：原「Pc→片麻理」把
    全部前寒武误当 Pt1——ChSt./ChA.（长城系 Pt2）合法宿主是片理）：
    Pt1 → 片麻理；其余变质（Pt2/Pt3/Pz）→ 片理。
    """
    from collections import Counter
    votes = Counter()
    for _, r in grp.iterrows():
        hl = r.get("host_layer")
        he = r.get("host_era")
        hc = r.get("host_code")
        if hl is None:
            continue  # 无宿主点不投票
        if hl == "metamorphic":
            sem = "片麻理产状" if hc is not None and is_pt1_host(hc) \
                else "片理产状"
        else:
            sem = _HOST_FIT.get((hl, he)) or _HOST_FIT.get((hl, "*"))
        if sem:
            votes[sem] += 1
    if len(grp) < FIT_MIN_SEGS:
        return None
    top, n = votes.most_common(1)[0] if votes else ("", 0)
    return top if top and n / len(grp) >= FIT_DOMINANCE else None


def _fit_code_semantics(df: pd.DataFrame) -> dict:
    """码级先验拟合（纯函数，CI 可测）：{GZBBGA: (语义, 来源)}。

    注册表码 → (注册码义, registry)；未注册码 → 宿主签名统计拟合：
    主导候选存在 → (拟合语义, fitted)；否则 → (原码, pending)。
    """
    out = {}
    for code, grp in df.groupby("GZBBGA"):
        code = str(code)
        if code in _CODE_SEM:
            out[code] = (_CODE_SEM[code], "registry")
            continue
        cand = _fit_candidate(grp)
        out[code] = (cand, "fitted") if cand else (code, "pending")
    return out


def norm(c):
    return re.sub(r"[→↓↑.]", "", str(c)).strip()


def era_of(r):
    if r is None:
        return None
    if r >= 800:
        return "Mz-Cz"
    if r >= 300:
        return "Pz"
    return "Pc"


def is_pt1_host(hc) -> bool:
    """Pt1 时代级裁定规则（2026-09-27 用户给定先验，裁定级）：
    Pt1（下元古界）单元宿主的地层产状=片麻理产状。
    判定：ADJ_HOST 注册集（HtA/Pt1K）∪ 码面 Pt1 前缀（norm 后 Pt1 开头）
    ——单元级裁定（09-24）的时代化升格，未来新 Pt1 单元自动生效。"""
    if hc is None:
        return False
    c = norm(hc)
    return c in ADJ_HOST or c.startswith("Pt1")


def calibrate_attitudes(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    outdir = Path(out_dir) if out_dir else sh.root
    outdir.mkdir(parents=True, exist_ok=True)

    def _l0(name):
        # 泛化（2026-10-02）：geojson/L0 优先；缺失时 MapGIS 源兜底；
        # 仍无则返回空表（新幅缺层面层优雅跳过——奥/巴无 002 火山岩面层）
        p = sh.root / "geojson" / "L0" / f"{name}.geojson"
        if p.exists():
            return gpd.read_file(p)
        src = sh.root / name
        if src.exists():
            from pymapgis.semantics import load_source_layer
            return load_source_layer(str(sh.root), name, graphic=False)
        return gpd.GeoDataFrame({"geometry": [], "QDUECC": []},
                                crs="EPSG:4326")

    att = _l0("LDZOFBA016.WT")
    ov_path = None
    for _cand in (sh.root / "polygon_attribution_overrides.json",
                  sh.root / "data" / "polygon_attribution_overrides.json"):
        if _cand.exists():
            ov_path = _cand
            break
    ov = load_polygon_overrides(str(ov_path)) if ov_path is not None else \
        {"overrides": {}}
    geoms, codes, layers = [], [], []
    for fn, cls in _STRATA_CLASS.items():
        g = _l0(fn)
        if not len(g):
            print(f"  面层 {fn} 缺失——跳过（宿主判定不含该族）")
            continue
        for i in range(len(g)):
            raw = str(g["QDUECC"].iloc[i])
            code = corrected_polygon_code(fn, i, raw, ov)
            geoms.append(g.geometry.iloc[i])
            codes.append(code)
            layers.append(cls)
    tree = STRtree(geoms)

    rows, anom = [], []
    for i, g in enumerate(att.geometry):
        # ① 宿主判定双轨化：精确命中优先，贴线最近面兜底（≤200m）
        hit, method, hdist = None, "无宿主", None
        for gi in tree.query(g):
            if geoms[gi].contains(g):
                hit = gi
                method, hdist = "contains", 0.0
                break
        if hit is None:
            cand = [(geoms[gi].distance(g), gi) for gi in tree.query(g.buffer(NEAR_MAX))]
            if cand:
                hdist, hit = min(cand)
                if hdist <= NEAR_MAX:
                    method = "nearest"
                else:
                    hit = None
        hc = codes[hit] if hit is not None else None
        hl = layers[hit] if hit is not None else None
        rk = _unit_age_rank(hc) if hit is not None else None
        he = era_of(rk) if hit is not None else None
        t = str(att["GZBBGA"].iloc[i])
        # ② 数据质量门：走向⊥倾向 + 倾角域值
        dq_issue = False
        try:
            a = float(att["GZBBAB"].iloc[i])
            b = float(att["GZBBAC"].iloc[i])
            d = abs(abs(a - b) - 90) % 180
            d = min(d, 180 - d)
            if d > 0.5:
                dq_issue = True
                anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                                 host_era=he, rule="数据质量门",
                                 reason=f"走向⊥倾向偏差 {d:.2f}°（走向{a} 倾向{b}）"))
        except (TypeError, ValueError):
            dq_issue = True
            anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                             host_era=he, rule="数据质量门",
                             reason="走向/倾向字段缺失"))
        try:
            dv = float(att["GZBBAD"].iloc[i])
            if not (0.0 <= dv <= 90.0):
                dq_issue = True
                anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                                 host_era=he, rule="数据质量门",
                                 reason=f"倾角 {dv}° 超域值 [0,90]"))
        except (TypeError, ValueError):
            dq_issue = True
            anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                             host_era=he, rule="数据质量门",
                             reason="倾角字段缺失"))
        # 同码继承原则（2026-10-03 用户裁定）：码义已标定的编码值——要素
        # sem_type 直接继承码义语义标签（_CAT 表承载码义），不再携带原码；
        # 未注册码走先验拟合码义（2026-10-07 裁定，下方码级拟合后回填）；
        # 宿主派生规则（侵入岩→面理、Pt1→片麻理）在下方覆盖
        sem = _CODE_SEM.get(t, t)
        verdict = "通过"
        adjudicated = False
        # 岩浆岩宿主派生（2026-09-24 用户裁定：岩浆岩中产状归面理产状）——
        # 侵入岩宿主一律派生面理产状；火山岩宿主与同日早前
        # 「火山岩宿主地层产状合法」裁定存在张力，暂维持原码待确认
        if hl == "intrusive":
            sem = "面理产状"
        # Pt1 时代级裁定规则（2026-09-27 用户给定先验，豁免通用约束）
        if hc is not None and is_pt1_host(hc):
            sem = "片麻理产状"
            verdict = "裁定（Pt1 时代规则）"
            adjudicated = True
        # R1' / R2' / R4'（裁定宿主规则点由 R3' 语义管辖，不参与以下校验）
        if not adjudicated:
            if he == "Mz-Cz" and hl in STRATA and t not in ("202001", "202004"):
                anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                                 host_era=he, rule="R1'",
                                 reason="Mz/Cz 地层产状必须为地层/倒转地层产状"))
                verdict = "违反 R1'（待裁定）"
            if t == "202005" and not (he in ("Pz", "Pc") and hl in STRATA):
                anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                                 host_era=he, rule="R2'",
                                 reason="片理产状允许于古生代/前寒武纪地层"))
                verdict = "违反 R2'（待裁定）"
            if t in ("202011", "202007") and hl not in MAGMA:
                # 202007=面理产状（2026-09-24 用户裁定），与 202011 同受 R4' 约束
                anom.append(dict(idx=i, gzbbga=t, host=hc, host_layer=hl,
                                 host_era=he, rule="R4'",
                                 reason="面理产状只能出现在岩浆岩中"))
                verdict = "违反 R4'（待裁定）"
        rows.append(dict(idx=i, GZBBGA=t, host_code=hc, host_layer=hl,
                         host_era=he, host_dist_m=hdist, probe_method=method,
                         era_rank=rk, sem_type=sem, verdict=verdict,
                         dq_issue=dq_issue))

    # 置信度评分（2026-09-24 用户定，透明三级 + 降级）：
    # 基分 1.0；正式违反 → 0.3；类型超宿主族允许集（嫌疑未裁决）→ ≤0.5；
    # 宿主兜底 nearest 按距离降级（下限 0.4）；无宿主 → ≤0.4；
    # 数据质量门问题 → 0.3；裁定（宿主规则）维持 1.0
    def _conf(r):
        v = str(r["verdict"])
        if "违反" in v:
            c = 0.3
        else:
            c = 1.0
        if r["dq_issue"]:
            c = min(c, 0.3)
        cat = _CAT.get(str(r["sem_type"]), str(r["sem_type"]))
        fam_allow = _FAMILY_ALLOW.get(r["host_layer"]) or _FAMILY_ALLOW.get(
            r["host_era"])
        if fam_allow is not None and cat not in fam_allow:
            c = min(c, 0.5)
        if r["probe_method"] == "nearest" and r["host_dist_m"] is not None:
            deg = float(r["host_dist_m"]) / NEAR_MAX * 0.4
            c = min(c, max(0.4, 1.0 - deg))
        elif r["probe_method"] == "无宿主":
            c = min(c, 0.4)
        return round(c, 2)

    # ③ 单元内类型一致性审计（混标审查）：同宿主单元的类型超出宿主族允许集
    # 时登记（Pz 沉积层理/片理二元合法不登记）；登记不改码
    df0 = pd.DataFrame(rows)
    df0["cat"] = df0["sem_type"].map(lambda v: _CAT.get(str(v), str(v)))
    for code, grp in df0.dropna(subset=["host_code"]).groupby("host_code"):
        fam = grp.iloc[0]
        allow = _FAMILY_ALLOW.get(fam["host_layer"]) or _FAMILY_ALLOW.get(
            fam["host_era"])
        if allow is None:
            continue  # Pz 沉积等：二元合法不审查
        cats = set(grp["cat"])
        if not cats <= allow:
            anom.append(dict(idx="/".join(str(i) for i in grp["idx"]),
                             gzbbga="/".join(sorted(set(grp["GZBBGA"]))),
                             host=code, host_layer=fam["host_layer"],
                             host_era=fam["host_era"], rule="单元混标审查",
                             reason=f"宿主族允许 {sorted(allow)}，实有 "
                                    f"{sorted(cats)}"))

    # 码级先验拟合（2026-10-07 用户裁定：GZBBGA 纳入先验拟合标定范畴）——
    # 未注册码据宿主签名统计获语义（source=fitted）；已注册码族级张力检测
    # （拟合族≠注册族 → 登记 _attitude_anomalies，不改码义）。
    # codebook GZBBGA 用户编辑居最高通道（v1.1 收录闭环：编辑 codebook →
    # prepare 生效，与 GZEEB 修改-再转化同构）
    _dfc = pd.DataFrame(rows)
    _code_sem = _fit_code_semantics(_dfc)
    from .codebook import load_codebook
    _cb = load_codebook(sh.root, sh.key)
    if _cb:
        for code, ent in (_cb.get("codes", {}).get("GZBBGA") or {}).items():
            u = str(ent.get("user_semantic") or "").strip()
            if u and u not in ("nan", "None") and code in _code_sem:
                _code_sem[code] = (u, "user")
    for i, r in enumerate(rows):
        t = str(r["GZBBGA"])
        _sem_c, _src_c = _code_sem[t]
        r["code_sem"] = _sem_c
        r["code_source"] = _src_c
        if _src_c == "registry" and len(_dfc[_dfc["GZBBGA"] == t]) >= FIT_MIN_SEGS:
            _fitted = _fit_candidate(_dfc[_dfc["GZBBGA"] == t])
            if _fitted and _FAMILY_OF.get(_fitted) != _FAMILY_OF.get(_sem_c):
                anom.append(dict(idx="码级", gzbbga=t, host="—", host_layer="—",
                                 host_era="—", rule="码义拟合张力",
                                 reason=f"注册码义 {_sem_c} × 宿主拟合 {_fitted}"
                                        f"（登记不改码义）"))
        # 未注册码：拟合语义回填（无拟合则保持原码 + pending）；
        # source=user（codebook 编辑）的码全段回填（编辑→prepare 生效，
        # 违反/裁定行豁免——宿主裁定规则不因码级编辑失效）
        if _src_c == "fitted" and r["sem_type"] == t and \
                "违反" not in str(r["verdict"]) and \
                "裁定" not in str(r["verdict"]):
            r["sem_type"] = _sem_c
            r["verdict"] = "标定（拟合提案待裁定）"
        elif _src_c == "user" and \
                "违反" not in str(r["verdict"]) and \
                "裁定" not in str(r["verdict"]):
            r["sem_type"] = _sem_c
            r["verdict"] = "标定（codebook 用户裁定）"
        elif _src_c == "pending" and r["sem_type"] == t and \
                "违反" not in str(r["verdict"]):
            r["verdict"] = "标定（未拟合·待裁定）"

    # 影子置信度（统一框架 S×I×F，2026-09-27 裁定参数；旧列 confidence 不动）
    from pymapgis.semantics.confidence import (emit_columns, evaluate,
                                               fit_from_residual)

    def _conf_shadow(r):
        v = str(r["verdict"])
        # 顺序敏感：违反类先判（「违反 R1'（待裁定）」含"裁定"子串）
        if "违反" in v or r["dq_issue"]:
            return evaluate("verified", fit=0.0,  # 硬违反直落冲突册
                            reasons=("违反" if "违反" in v else "数据质量门",))
        if "裁定" in v:                        # Pt1 时代规则等裁定宿主规则
            return evaluate("adjudicated", adjudicated=True,
                            reasons=("裁定宿主规则",))
        if r["probe_method"] == "无宿主":
            return evaluate("code_read", "single", evaluated=False,
                            reasons=("无宿主（无假设可评）",))
        cat = _CAT.get(str(r["sem_type"]), str(r["sem_type"]))
        fam_allow = _FAMILY_ALLOW.get(r["host_layer"]) or _FAMILY_ALLOW.get(
            r["host_era"])
        fam_suspect = fam_allow is not None and cat not in fam_allow
        # 根假设类（F2 审计修正 2026-09-28）：仅计真证据源——
        # REGISTRY=码义注册表（用户裁定语义=核验先验，独立于图面）
        # HOST=宿主包含/nearest（图面面元数据）；防守性检查（数据质量门/
        # 族允许集）是约束门——通过≠互证，不计 I 类。
        if r["probe_method"] == "nearest" and r["host_dist_m"] is not None:
            f = fit_from_residual(float(r["host_dist_m"]), NEAR_MAX)
            fnote = f"res={r['host_dist_m']} tol={NEAR_MAX}（名米实度，同单位）"
        else:
            f, fnote = 1.0, ""
        return evaluate("verified", "multi_root", f,
                        counterexample_open=fam_suspect,
                        reasons=(f"probe={r['probe_method']}",
                                 "REGISTRY(码义注册)×HOST(宿主数据)"),
                        fit_note=fnote)

    for r in rows:
        r["confidence"] = _conf(r)
        emit_columns(r, _conf_shadow(r), shadow=True)
    out_p = outdir / "_attitude_calibration.csv"
    pd.DataFrame(rows).to_csv(out_p, index=False, encoding="utf-8-sig")
    anom_p = None
    if anom:
        anom_p = outdir / "_attitude_anomalies.csv"
        pd.DataFrame(anom).to_csv(anom_p, index=False, encoding="utf-8-sig")
    print(f"产状标定: {len(rows)} 点 → {out_p.name}；"
          f"违反登记 {len(anom)} 条 → {anom_p.name if anom_p else '无'}")
    if anom:
        for a in anom:
            print(f"  ✗ 点{a['idx']} {a['gzbbga']} 宿主={a['host']}"
                  f"({a['host_layer']}/{a['host_era']}) {a['rule']}")
    return {"rows": len(rows), "anomalies": len(anom), "out_dir": str(outdir)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-attitudes")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    calibrate_attitudes(args.sheet, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
