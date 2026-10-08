# -*- coding: utf-8 -*-
"""codebook 置信度文件单元测试（2026-10-07 配套裁定）。

CI 契约：合成件（临时 root + 手写标定 CSV/codebook JSON），不依赖
pymapgis.semantics——只测机械汇总（裁决/置信带计数、覆盖率口径、
codebook_quality、只读 schema 与 provenance）。
"""
import json

import pandas as pd
import pytest

from geosciml4china.calibrate.confidence import (CONFIDENCE_SCHEMA,
                                                 build_confidence,
                                                 confidence_path,
                                                 summary)
from geosciml4china.sheets import Sheet, register_sheet


@pytest.fixture()
def cf_root(tmp_path):
    register_sheet(Sheet(
        key="cfu", code="J43T009998", title="confidence unit",
        root=tmp_path, aux_pairs_csv="", aux_assoc_csv="",
        aux_triplets_csv="", calibration_csv=""))
    pd.DataFrame([
        dict(idx=0, GZBD原码="01", 原码语义="实测地质界线", 标定语义="整合接触",
             状态="标定通过", 证据="志书单元对规则", 先验年轻侧="",
             conf_band_u="consistent", confidence_u="0.51"),
        dict(idx=1, GZBD原码="01", 原码语义="实测地质界线", 标定语义="整合接触",
             状态="标定通过", 证据="志书单元对规则", 先验年轻侧="",
             conf_band_u="consistent", confidence_u="0.51"),
        dict(idx=2, GZBD原码="02", 原码语义="实测地质界线",
             标定语义="不整合接触（先验建议→04/24）",
             状态="分歧未裁定", 证据="单元对 期望 04/24", 先验年轻侧="right",
             conf_band_u="conflict", confidence_u="0.0"),
        dict(idx=3, GZBD原码="10", 原码语义="断层", 标定语义="断层接触",
             状态="断层标定", 证据="与 FBA003 重合 100%", 先验年轻侧="",
             conf_band_u="consistent", confidence_u="0.85"),
        dict(idx=4, GZBD原码="16", 原码语义="推测界线", 标定语义="",
             状态="未覆盖（先验缺口）", 证据="", 先验年轻侧="",
             conf_band_u="unassessed", confidence_u="0.18"),
    ]).to_csv(tmp_path / "_gzbd_semantic_interpretation.csv", index=False)
    pd.DataFrame([
        dict(idx=0, structural_type="逆断层", verdict="verified",
             conf_band_u="consistent"),
        dict(idx=1, structural_type="断层泛称", verdict="兜底（一般断层）",
             conf_band_u="unassessed"),
        dict(idx=2, structural_type="逆断层", verdict="consistent",
             conf_band_u="consistent"),
    ]).to_csv(tmp_path / "_gzeeb_calibration_cfu.csv", index=False)
    pd.DataFrame([
        dict(idx=0, GZBBGA="202001", host_code="D2t", probe_method="contains",
             sem_type="bedding", verdict="pass"),
        dict(idx=1, GZBBGA="202004", host_code="ηγT2", probe_method="contains",
             sem_type="bedding", verdict="违反 R2'（待裁定）"),
    ]).to_csv(tmp_path / "_attitude_calibration.csv", index=False)
    # 既有 codebook（含一笔用户编辑）
    (tmp_path / "codebook_cfu.json").write_text(json.dumps({
        "codebook": "geosciml4china/codebook/v1", "sheet": "cfu",
        "generated": "2026-10-07T00:00:00",
        "codes": {"GZEEB": {
            "01": {"semantic": "断层泛称", "source": "MLE无族义(泛称)",
                   "segs": 1, "user_semantic": "边界断裂", "user_note": ""},
            "05": {"semantic": "逆断层", "source": "MLE逻辑判断",
                   "segs": 2, "user_semantic": "", "user_note": ""}},
            "GZELD": {
            "101": {"semantic": "压性", "source": "global_prior",
                    "segs": 0, "user_semantic": "", "user_note": ""}},
            "GZBD": {
            "01": {"semantic": "整合接触", "source": "MLE精化",
                   "segs": 0, "user_semantic": "", "user_note": ""},
            "10": {"semantic": "断层接触（断裂界线）", "source": "路由码",
                   "segs": 0, "user_semantic": "", "user_note": ""},
            "16": {"semantic": "推测地质界线", "source": "registry",
                   "segs": 0, "user_semantic": "", "user_note": ""}}},
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_schema_domains_and_reconciliation(cf_root):
    conf = build_confidence("cfu")
    assert conf["codebook_confidence"] == CONFIDENCE_SCHEMA
    assert conf["readonly"] is True
    assert confidence_path(cf_root, "cfu").exists()
    b = conf["domains"]["boundaries"]
    assert b["total"] == 5
    assert b["verdicts"]["分歧未裁定"] == 1
    assert b["pending"] == 1
    assert b["conf_bands"]["conflict"] == 1
    # 覆盖率口径：5 段中 1 分歧 + 1 未覆盖 = 60% 建立
    assert b["coverage_pct"] == 60.0
    f = conf["domains"]["faults"]
    assert f["total"] == 3
    assert f["structural_types"]["逆断层"] == 2
    # 断层覆盖口径：1 兜底 → 66.7%
    assert f["coverage_pct"] == 66.7
    assert conf["domains"]["attitudes"]["total"] == 2


def test_conflicts_detail_records(cf_root):
    """矛盾冲突逐段明细（2026-10-07 用户建议）：图面码×先验/证据冲突
    逐段入档——记录但不修改编码。"""
    conf = build_confidence("cfu")
    b = conf["conflicts"]["boundaries"]
    assert len(b) == 1
    e = b[0]
    assert e["idx"] == 2 and e["code"] == "02"
    assert e["code_semantic"] == "实测地质界线"
    assert "先验建议" in e["segment_semantic"], "段级语义须以 segment_semantic 保持在档"
    assert e["conf_band"] == "conflict" and e["confidence"] == 0.0
    a = conf["conflicts"]["attitudes"]
    assert len(a) == 1 and a[0]["verdict"].startswith("违反")
    assert a[0]["host_code"] == "ηγT2"


def test_semantic_tension_gneissic_vs_foliation(cf_root):
    """码级×段级语义张力（2026-10-07 用户裁定）：段级宿主裁定（片麻理）
    × codebook 码级语义（面理）的矛盾逐条记录在置信度文件。"""
    # codebook 补 GZBBGA 202007 → 面理产状；标定 CSV 补 135 式 Pt1 片麻理段
    cbp = cf_root / "codebook_cfu.json"
    import json as _json
    cb = _json.loads(cbp.read_text(encoding="utf-8"))
    cb["codes"]["GZBBGA"] = {"202007": {"semantic": "面理产状",
                                        "source": "registry", "segs": 0,
                                        "user_semantic": "", "user_note": ""}}
    cbp.write_text(_json.dumps(cb, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    pd.DataFrame([
        dict(idx=135, GZBBGA="202007", host_code="Pt1K.", host_layer="metamorphic",
             host_era="Pc", sem_type="片麻理产状", verdict="裁定（Pt1 时代规则）",
             code_sem="片麻理产状", code_source="registry"),
        dict(idx=134, GZBBGA="202007", host_code="ηγT2", host_layer="intrusive",
             host_era="Mz-Cz", sem_type="面理产状", verdict="通过",
             code_sem="面理产状", code_source="registry"),
    ]).to_csv(cf_root / "_attitude_calibration.csv", index=False)
    conf = build_confidence("cfu")
    t = conf["conflicts"].get("attitudes_semantic_tension", [])
    assert len(t) == 1, f"张力应恰 1 条（135），实 {len(t)}"
    e = t[0]
    assert e["idx"] == 135
    assert e["segment_semantic"] == "片麻理产状"
    assert e["codebook_semantic"] == "面理产状"
    assert conf["domains"]["attitudes"]["semantic_tensions"] == 1


def test_codebook_quality_and_provenance(cf_root):
    conf = build_confidence("cfu")
    q = conf["codebook_quality"]
    assert q["GZEEB"]["codes"] == 2
    assert q["GZEEB"]["user_edits"] == 1
    assert q["GZEEB"]["by_source"]["MLE逻辑判断"] == 1
    assert q["GZELD"]["by_source"]["global_prior"] == 1
    assert conf["provenance"]["codebook_generated"] == "2026-10-07T00:00:00"
    # 摘要可读且不炸
    s = summary(conf)
    assert "boundaries" in s and "GZEEB" in s


def test_measurement_error_terms(cf_root):
    """测量误差项（2026-10-08 用户建模裁定）：ε₁ 界线（codebook 理论 vs
    段级实测语义偏差）+ ε₂ 断层（kin 一致性 + aux 证据冲突）。"""
    conf = build_confidence("cfu")
    me = conf["measurement_error"]
    b = me["boundary_deviation"]
    assert b["contradiction"] == 1          # 分歧未裁定（idx 2）= 超阈保留
    assert b["match"] >= 1 and b["deviation"] >= 1
    segs = {s["idx"]: s for s in b["segments"]}
    assert segs[2]["class"] == "contradiction"
    f = me["fault_kinematic_deviation"]
    assert f["total"] == 3
    # 合成件无 gzeld_sem → 全中性（无测量）；无冲突册 → 证据冲突 0
    assert f["neutral"] == 3 and f["violation"] == 0
    assert f["evidence_conflict_count"] == 0
