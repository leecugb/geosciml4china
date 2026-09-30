"""geosciml4china 冒烟测试（CI 基线；图幅数据不在仓内，图幅级用例自动跳过）。"""
from __future__ import annotations

import importlib

import pytest


def test_version():
    import geosciml4china
    assert geosciml4china.__version__


@pytest.mark.parametrize("mod", [
    "geosciml4china.data",
    "geosciml4china.sheets",
    "geosciml4china.cli",
    "geosciml4china.convert.config",
    "geosciml4china.convert.mapping",
    "geosciml4china.convert.model",
    "geosciml4china.convert.vocab",
    "geosciml4china.convert.validate",
    "geosciml4china.convert.emit.xmlcore",
    "geosciml4china.convert.emit.features",
    "geosciml4china.convert.lite.views",
    "geosciml4china.convert.lite.geojson",
    "geosciml4china.convert.build",
    "geosciml4china.convert.verify",
    "geosciml4china.render.codemap",
    "geosciml4china.render.stylegen",
    "geosciml4china.render.stylegen_fault",
    "geosciml4china.render.map_builder",
    "geosciml4china.render.mirror",
    "geosciml4china.render.render",
    "geosciml4china.render.fault_measure",
    "geosciml4china.render.gml_overlay",
])
def test_import(mod):
    importlib.import_module(mod)


def test_package_data_present():
    from geosciml4china import data as d
    for p in (d.DZT0179_COLOR_LIBRARY, d.DZT0179_PATTERN_REGISTRY,
              d.CGI_TERMS, d.CGI_VOCABS_DIR, d.ICS_ERAS):
        assert p.exists(), p
    assert sum(1 for _ in d.xsd_root().rglob("*.xsd")) >= 70


def test_sheets_registry_defaults():
    from geosciml4china.sheets import get_sheet, list_sheets
    keys = [s.key for s in list_sheets()]
    assert "kurgan" in keys and "yingjisha" in keys
    k = get_sheet("kurgan")
    assert k.code == "J43C001002"
    assert k.gml_out.name == "kurgan_geosciml_full.gml"
    assert k.lite_expect_counts == (713, 1316, 310, 305)


def test_config_contract_kurgan():
    """convert.config 消费契约：模块常量 + init_sheet 重绑定。"""
    from geosciml4china.convert import config
    config.init_sheet("kurgan")
    assert config.SHEET == "J43C001002"
    assert "J43C001002" in config.BASE_URI
    assert config.EXPECTED_UNITS == 57
    config.init_sheet("yingjisha")
    assert config.SHEET == "J43C002003"
    assert config.EXPECTED_UNITS == 95
    config.init_sheet("kurgan")  # 复原


def test_namespace_placeholder_gate():
    from geosciml4china.convert import config
    assert config.NAMESPACE_FINAL is False
    assert config.NAMESPACE_PLACEHOLDER in config.BASE_URI


@pytest.mark.skipif(not __import__("pathlib").Path(r"D:\JWD").exists(),
                    reason="图幅数据不在本机")
def test_kurgan_sheet_files_resolve():
    from geosciml4china.sheets import get_sheet
    k = get_sheet("kurgan")
    assert k.geojson_l1.is_dir()
    assert k.vocab_mapping.exists()
    assert k.style_skeleton.exists()
    assert k.aux_pairs.exists()


def test_priors_packaged_and_overlay_merge():
    """先验库随包（全链范围裁定 2026-09-29）：区域主本可载+图幅扩展册合并。"""
    from geosciml4china.calibrate import load_priors
    p = load_priors()
    assert len(p["unit_pair_rules"]) >= 300 and len(p["generic_rules"]) >= 5
    assert p["_meta"]["authority"].startswith("本库为判断地层接触关系")
    p2 = load_priors("aoyiyayilake")  # 无扩展册 → 主本原样
    assert len(p2["unit_pair_rules"]) == len(p["unit_pair_rules"])


def test_pipeline_module_importable():
    import geosciml4china.pipeline as pl
    assert callable(pl.run_pipeline)


def test_scope_contract_11_files():
    """十一文件处理域契约（2026-09-29 用户裁定）：SCOPE_FILES 恰 11 件、
    主题源映射全在契约内。"""
    from geosciml4china.scope import SCOPE_FILES, THEME_SOURCES
    assert len(SCOPE_FILES) == 11
    for theme, srcs in THEME_SOURCES.items():
        for s in srcs:
            assert s in SCOPE_FILES, f"{theme} 源文件越界: {s}"


def test_scope_official_names_complete():
    """11 文件皆有规范正式图层名；分级互斥完备。"""
    from geosciml4china.scope import (CONDITIONAL_FILES, CORE_FILES,
                                      OFFICIAL_LAYER_NAMES, SCOPE_FILES)
    assert set(OFFICIAL_LAYER_NAMES) == set(SCOPE_FILES)
    assert CORE_FILES | CONDITIONAL_FILES == SCOPE_FILES
    assert not (CORE_FILES & CONDITIONAL_FILES)


def test_preflight_synthetic(tmp_path):
    """合成图幅目录：CORE 缺失→False；齐全→True。"""
    from geosciml4china.sheets import Sheet, register_sheet
    from geosciml4china.preflight import check_scope_files
    register_sheet(Sheet(key="_t0", code="T0", title="t", root=tmp_path))
    ok, rows = check_scope_files("_t0", read=False)
    assert not ok  # 全缺
    from geosciml4china.scope import CORE_FILES
    for f in CORE_FILES:
        (tmp_path / f).write_text("x", encoding="ascii")
    ok, _ = check_scope_files("_t0", read=False)
    assert ok


def test_calibrate_gzbd_importable():
    """gzbd 标定模块导入（函数化移植完整性）。"""
    from geosciml4china.calibrate import gzbd
    assert callable(gzbd.calibrate_boundaries)


def test_gzbd_calib_domain_and_fallback_rule():
    """2026-09-29 用户对齐裁定：标定域十码 + 域外码统一一般地质界线兜底。
    兜底分支必须存在于 B 树（防域外码漏进先验/通则级联误标）。"""
    import io
    import geosciml4china.calibrate.gzbd as gz
    import inspect
    src = io.open(gz.__file__, encoding="utf-8").read()
    assert '_CALIB_DOMAIN = {"01", "02", "04", "10", "11", "16", "24", "43", "60", "81"}' in src
    assert 'gz not in _CALIB_DOMAIN' in src and '"verdict": "特殊码兜底"' in src
    assert '_gzbd_special_fallback.csv' in src  # 审计报告存档
    assert '状态="特殊码兜底（一般地质界线）"' in src


def test_pending_fallback_section(tmp_path):
    """兜底码提示节：空/缺档案→零行；非空→表格列出码与段数（幂等渲染）。"""
    from geosciml4china.convert import pending as _p
    import csv as _csv
    lines: list = []
    _p._fallback_section(lines, tmp_path / "nope.csv")
    assert lines == []
    fb = tmp_path / "_gzbd_special_fallback.csv"
    with open(fb, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=["GZBD原码", "状态"])
        w.writeheader()
        w.writerow({"GZBD原码": "03", "状态": "特殊码兜底（一般地质界线）"})
        w.writerow({"GZBD原码": "03", "状态": "特殊码兜底（一般地质界线）"})
        w.writerow({"GZBD原码": "99", "状态": "特殊码兜底（一般地质界线）"})
    _p._fallback_section(lines, fb)
    body = "\n".join(lines)
    assert "特殊码兜底登记" in body
    assert "| 03 | 2 |" in body and "| 99 | 1 |" in body
    assert "回填 decided" in body


def test_name_segment_parser():
    """名称段式解析（2026-09-29 用户要求：「路乐河组二段」类地层名称）。"""
    from geosciml4china.calibrate.gzbd import name_segment
    assert name_segment("路乐河组二段") == ("路乐河组", 2)
    assert name_segment("白沙河组四段") == ("白沙河组", 4)
    assert name_segment("阿尔金山群下岩段") == ("阿尔金山群", -3)  # 下=-3 最老
    assert name_segment("阿尔金山群上岩段") == ("阿尔金山群", -1)  # 上=-1 最新（数值大=新，与绝对段号同向）
    assert name_segment("乌鲁阿特组下段") == ("乌鲁阿特组", -3)
    assert name_segment("群鸭湖组第二段") == ("群鸭湖组", 2)   # 第X段（审计补）
    assert name_segment("乌鲁阿特组中段") == ("乌鲁阿特组", -2)  # 中段（审计补）
    assert name_segment("克孜勒陶组") is None       # 非段式
    assert name_segment("黄河一段") is None         # 无组/群防误解析
    assert name_segment("") is None


def test_ht_paleoproterozoic_simultaneous():
    """滹沱纪 Ht 与古元古代 Pt1 同时代（2026-09-29 用户裁定）。"""
    from pymapgis.rendering.pdf_writer import _unit_age_rank
    assert _unit_age_rank("HtA") == 101 == _unit_age_rank("Pt1K")
    assert _unit_age_rank("HtA") < _unit_age_rank("Pt2")  # 仍老于 Pt2


def test_entities_module_importable():
    """归组器移植完整性（2026-09-29：四步链第①步入包）。"""
    from geosciml4china.calibrate import entities
    assert callable(entities.calibrate_entities)
