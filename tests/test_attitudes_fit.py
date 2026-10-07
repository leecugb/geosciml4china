# -*- coding: utf-8 -*-
"""GZBBGA 先验拟合单元测试（2026-10-07 用户裁定：GZBBGA 纳入先验拟合标定）。

CI 契约：合成 DataFrame 测纯函数 _fit_candidate/_fit_code_semantics——
注册表优先、宿主签名投票、主导阈值、样本下限、族级张力比较。
"""
import pandas as pd
import pytest

from geosciml4china.calibrate.attitudes import (_fit_candidate,
                                                _fit_code_semantics,
                                                _FAMILY_OF)


def _df(codes_hosts):
    rows = [dict(GZBBGA=c, host_layer=hl, host_era=he, host_code=hc)
            for c, hl, he, hc in codes_hosts]
    return pd.DataFrame(rows)


def test_registry_priority():
    df = _df([("202001", "sediment", "Mz-Cz", "N1k")] * 20
             + [("202007", "intrusive", "Mz-Cz", "ηγT2")] * 10)
    sem = _fit_code_semantics(df)
    assert sem["202001"] == ("地层产状", "registry")
    assert sem["202007"] == ("面理产状", "registry")


def test_fitted_undocumented_intrusive_majority():
    # 未注册码 999999：侵入岩宿主主导 → 拟合面理产状
    df = _df([("999999", "intrusive", "Mz-Cz", "ηγT2")] * 12
             + [("999999", "sediment", "Mz-Cz", "N1k")] * 3)
    sem = _fit_code_semantics(df)
    assert sem["999999"] == ("面理产状", "fitted")


def test_fitted_pt1_metamorphic_gneissic():
    df = _df([("888888", "metamorphic", "Pc", "Pt1K.")] * 9
             + [("888888", "sediment", "Pz", "D2t")] * 1)
    assert _fit_code_semantics(df)["888888"] == ("片麻理产状", "fitted")


def test_pt2_metamorphic_stays_schistosity():
    # 长城系（Pt2）变质宿主 → 片理产状（非 Pt1，不得误拟合为片麻理；
    # 2026-10-07 修复：ChSt./ChA. 案）
    df = _df([("888888", "metamorphic", "Pc", "ChSt.")] * 9
             + [("888888", "metamorphic", "Pc", "ChA.")] * 3)
    assert _fit_code_semantics(df)["888888"] == ("片理产状", "fitted")


def test_below_min_segments_pending():
    df = _df([("777777", "intrusive", "Mz-Cz", "ηγT2")] * 3)  # < FIT_MIN_SEGS
    assert _fit_code_semantics(df)["777777"] == ("777777", "pending")


def test_no_dominance_pending():
    # 无主导：侵入 6 / 沉积 6 → 50% < 60%
    df = _df([("666666", "intrusive", "Mz-Cz", "ηγT2")] * 6
             + [("666666", "sediment", "Mz-Cz", "N1k")] * 6)
    assert _fit_code_semantics(df)["666666"] == ("666666", "pending")


def test_family_comparison_bedding_subtypes_consistent():
    # 202004 倒转层理（层理族）在沉积宿主拟合出地层产状（层理族）——族级
    # 比较应视为一致（不报张力）
    df = _df([("202004", "sediment", "Mz-Cz", "N1k")] * 10)
    fitted = _fit_candidate(df)
    assert fitted == "地层产状"
    assert _FAMILY_OF[fitted] == _FAMILY_OF["倒转层理"] == "层理"


def test_tension_detected_cross_family():
    # 注册码义（片理）× 侵入宿主拟合（面理）——族级张力应可检出
    df = _df([("202005", "intrusive", "Mz-Cz", "ηγT2")] * 10)
    fitted = _fit_candidate(df)
    assert fitted == "面理产状"
    assert _FAMILY_OF[fitted] != _FAMILY_OF["片理产状"]
