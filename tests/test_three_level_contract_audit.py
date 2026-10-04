# -*- coding: utf-8 -*-
"""三层逻辑 L3 契约审计（2026-10-04 用户裁定「类别编码值拥有最高优先级」
+「GZBD 同样需要标定」）：同编码值要素经全继承后终态语义必须统一——
例外仅限覆盖库/裁定行与「先验建议→」建议型机制行；映射表必须覆盖全部
在数编码且 semantic 列与终态一致。

方法=读校准工件直接断言（不重算标定）：GZEEB 校准 CSV 按码分组查
structural_type 唯一性；GZBD 解释表按码分组查 canon 归一标定语义唯一性；
三张映射表逐一核对覆盖率与 semantic 一致性。
"""
import re

import pandas as pd
import pytest

SHEETS = [("jwsss", r"D:\jwsss"), ("jwss", r"D:\jwss")]

_GZBD_SEM_NORM = {"角度不整合界线": "角度不整合", "平行不整合界线": "平行不整合",
                  "推测地质界线（覆盖区延伸段）": "推测界线"}
_SYN_FOLD = {"推测地质界线": "推测界线"}


def _canon(raw):
    t = re.sub(r"（先验建议.*?）", "", str(raw or "")).strip()
    t = _GZBD_SEM_NORM.get(t, t)
    t = _SYN_FOLD.get(t, t)
    return t[:-2] if t.endswith("界线") and len(t) > 2 else t


def _load(path):
    try:
        return pd.read_csv(path, dtype=str)
    except FileNotFoundError:
        return None


@pytest.mark.parametrize("key,root", SHEETS)
def test_gzeeb_l3_uniformity(key, root):
    """GZEEB：同码段 structural_type 唯一（覆盖库/制图误差裁定行豁免）。"""
    df = _load(rf"{root}\_gzeeb_calibration_{key}.csv")
    if df is None:
        pytest.skip("校准件不在场")
    exempt = df["verdict"].isin(["裁定（覆盖库）", "制图误差（剔除）"])
    for code, sub in df[~exempt].groupby("GZEEB"):
        sems = set(sub["structural_type"].dropna())
        assert len(sems) == 1, f"{key} GZEEB={code} 终态语义不唯一: {sems}"


@pytest.mark.parametrize("key,root", SHEETS)
def test_gzbd_l3_uniformity(key, root):
    """GZBD：同码段 canon 标定语义唯一（建议型/裁定行豁免）。"""
    df = _load(rf"{root}\_gzbd_semantic_interpretation.csv")
    if df is None:
        pytest.skip("解释表不在场")
    exempt = df["状态"].isin(["用户裁定改码", "分歧未裁定", "制图误差（剔除）"])
    sugg = df["标定语义"].astype(str).str.contains("（先验建议", na=False)
    for code, sub in df[~exempt & ~sugg].groupby(
            df["GZBD_eff"].fillna(df["GZBD原码"])):
        sems = {_canon(x) for x in sub["标定语义"]}
        assert len(sems) == 1, f"{key} GZBD={code} 终态语义不唯一: {sems}"


@pytest.mark.parametrize("key,root", SHEETS)
def test_map_tables_complete_and_consistent(key, root):
    """映射表覆盖全部在数编码，semantic 与终态分布一致。"""
    cal = _load(rf"{root}\_gzeeb_calibration_{key}.csv")
    gmap = _load(rf"{root}\code_semantics_map_{key}.csv")
    interp = _load(rf"{root}\_gzbd_semantic_interpretation.csv")
    bmap = _load(rf"{root}\boundary_semantics_map_{key}.csv")
    if cal is None or gmap is None:
        pytest.skip("GZEEB 工件不在场")
    # 覆盖：映射表码集 == 数据码集
    assert set(cal["GZEEB"].dropna()) == set(gmap["GZEEB"].dropna()), \
        f"{key} GZEEB 映射表覆盖缺口"
    # 一致：semantic == 终态唯一值（用户修改列空时）
    for _, r in gmap.iterrows():
        if str(r.get("user_semantic") or "") not in ("", "nan", "None"):
            continue  # 用户修改行 semantic=用户值（生效路径另行验证）
        sems = set(cal[cal["GZEEB"] == r["GZEEB"]]["structural_type"].dropna())
        assert sems == {r["semantic"]}, \
            f"{key} GZEEB={r['GZEEB']} 映射表 semantic={r['semantic']} ≠ 终态 {sems}"
    if interp is None or bmap is None:
        pytest.skip("GZBD 工件不在场")
    assert (set(interp["GZBD_eff"].fillna(interp["GZBD原码"]).dropna())
            == set(bmap["GZBD"].dropna())), f"{key} GZBD 映射表覆盖缺口"
    exempt = interp["状态"].isin(["用户裁定改码", "分歧未裁定", "制图误差（剔除）"])
    sugg = interp["标定语义"].astype(str).str.contains("（先验建议", na=False)
    for _, r in bmap.iterrows():
        if str(r.get("user_semantic") or "") not in ("", "nan", "None"):
            continue
        sub = interp[(interp["GZBD_eff"].fillna(interp["GZBD原码"]) == r["GZBD"])
                     & ~exempt & ~sugg]
        if not len(sub):
            continue  # 全建议型/裁定行的码（如 16）——映射语义走注册/裁定级
        sems = {_canon(x) for x in sub["标定语义"]}
        assert sems == {_canon(r["semantic"])}, \
            f"{key} GZBD={r['GZBD']} 映射表 semantic={r['semantic']} ≠ 终态 {sems}"


@pytest.mark.parametrize("key,root", SHEETS)
def test_own_label_preserved(key, root):
    """own 留档分层可读：own_structural_type / 原标定语义 列在场且非空率达标。"""
    cal = _load(rf"{root}\_gzeeb_calibration_{key}.csv")
    if cal is None:
        pytest.skip("校准件不在场")
    assert "own_structural_type" in cal.columns
    assert cal["own_structural_type"].notna().mean() > 0.99
    interp = _load(rf"{root}\_gzbd_semantic_interpretation.csv")
    if interp is None:
        pytest.skip("解释表不在场")
    assert "原标定语义" in interp.columns
    assert interp["原标定语义"].notna().mean() > 0.99
