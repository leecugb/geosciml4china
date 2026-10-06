# -*- coding: utf-8 -*-
"""codebook 单元测试（2026-10-06 用户裁定：编码-地质语义映射表以 JSON
输出 = codebook；用户可改；转换建立在其上）。

CI 契约：合成件（临时 root + 手写 CSV 映射表/注册表 JSON），不依赖
pymapgis.semantics——只测合并、权威序、用户编辑跨轮保留与 semantic_of
解析。codebook 模块无模块级 pymapgis 依赖，极简环境可跑。
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from geosciml4china.calibrate.codebook import (CODEBOOK_SCHEMA,
                                               build_codebook,
                                               codebook_path,
                                               load_codebook,
                                               semantic_of)
from geosciml4china.sheets import Sheet, register_sheet


@pytest.fixture()
def cb_root(tmp_path):
    """临时图幅：GZEEB/GZBD/GZELD 三 CSV + GZEEB 注册表。"""
    register_sheet(Sheet(
        key="cbu", code="J43T009999", title="codebook unit",
        root=tmp_path, aux_pairs_csv="", aux_assoc_csv="",
        aux_triplets_csv="", calibration_csv=""))
    pd.DataFrame([
        dict(GZEEB="01", segs=10, semantic="断层泛称", source="MLE无族义(泛称)",
             confidence="", mle_distribution="", final_distribution="",
             evidence_votes="", user_semantic="", user_note=""),
        dict(GZEEB="16", segs=5, semantic="走滑断层", source="签名",
             confidence="", mle_distribution="", final_distribution="",
             evidence_votes="", user_semantic="", user_note=""),
    ]).to_csv(tmp_path / "code_semantics_map_cbu.csv", index=False)
    pd.DataFrame([
        dict(GZBD="01", segs=20, semantic="整合接触", source="MLE精化",
             confidence="", national_label="", contactType_term="",
             label_distribution="", divergent_segs=0,
             user_semantic="", user_note=""),
    ]).to_csv(tmp_path / "boundary_semantics_map_cbu.csv", index=False)
    pd.DataFrame([
        dict(GZELD="103", segs=1, semantic="右行走滑", source="全局先验",
             confidence="", structural_distribution="",
             user_semantic="", user_note=""),
    ]).to_csv(tmp_path / "gzeld_semantics_map_cbu.csv", index=False)
    (tmp_path / "fault_semantics_cbu.json").write_text(json.dumps(
        {"gzeeb_semantics": {"16": {"semantic": "左型走滑断层",
                                     "verdict": "adjudicated"}},
         "gzeld_semantics": {}}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_build_schema_and_merge(cb_root):
    cb = build_codebook("cbu")
    assert cb["codebook"] == CODEBOOK_SCHEMA
    assert cb["sheet"] == "cbu"
    assert codebook_path(cb_root, "cbu").exists()
    # 注册表覆盖 CSV：16 = 左型走滑断层（registry 居最高权威）
    e16 = cb["codes"]["GZEEB"]["16"]
    assert e16["source"] == "registry"
    assert e16["semantic"] == "左型走滑断层"
    # CSV 推导层：01 = 断层泛称
    assert cb["codes"]["GZEEB"]["01"]["semantic"] == "断层泛称"
    # GZELD 全局先验补缺（101 不在 CSV 但在包数据全局先验中）
    assert cb["codes"]["GZELD"]["101"]["semantic"] == "压性"
    assert cb["codes"]["GZELD"]["101"]["source"] == "global_prior"


def test_semantic_of_authority(cb_root):
    cb = build_codebook("cbu")
    assert semantic_of(cb, "GZEEB", "16") == "左型走滑断层"   # registry
    assert semantic_of(cb, "GZEEB", "01") == "断层泛称"      # 校准推导
    assert semantic_of(cb, "GZBD", "01") == "整合接触"
    assert semantic_of(cb, "GZEEB", "99") == ""              # 未注册码
    assert semantic_of(None, "GZEEB", "01") == ""            # codebook 缺席


def test_user_edit_preserved_across_regeneration(cb_root):
    cb = build_codebook("cbu")
    # 用户直接编辑 JSON（codebook 就是 codebook——允许用户修改）
    cb["codes"]["GZEEB"]["01"]["user_semantic"] = "边界断裂"
    cb["codes"]["GZEEB"]["01"]["user_note"] = "人工裁定"
    codebook_path(cb_root, "cbu").write_text(
        json.dumps(cb, ensure_ascii=False, indent=1), encoding="utf-8")
    # 再生成（管线二跑）：用户编辑跨轮保留
    cb2 = build_codebook("cbu")
    assert semantic_of(cb2, "GZEEB", "01") == "边界断裂"
    assert cb2["codes"]["GZEEB"]["01"]["user_note"] == "人工裁定"
    # 注册表条目豁免用户编辑（注册表权威更高）
    assert semantic_of(cb2, "GZEEB", "16") == "左型走滑断层"
    # load_codebook 读取
    assert load_codebook(cb_root, "cbu")["codes"]["GZBD"]["01"]["semantic"] \
        == "整合接触"
