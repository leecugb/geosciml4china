# -*- coding: utf-8 -*-
"""glyphcls 单元测试：规则分类器 + 注册对账（合成几何 + K46 实证三码）。"""
from geosciml4china.calibrate.glyphcls import (audit_registry,
                                               classify_glyph, glyph_features)


def _geom(strokes, closed=None, bbox=(-0.5, -0.5, 0.5, 0.5)):
    subs = []
    for pts, cl in (strokes if isinstance(strokes, list) else []):
        subs.append({"points": pts, "closed": cl, "circle": None})
    for pts in (closed or []):
        subs.append({"points": pts, "closed": True, "circle": None})
    return {"subpaths": subs, "circles": [], "bbox": list(bbox)}


def test_double_tick_parallel():
    g = _geom([([[-0.25, -0.5], [-0.25, 0.5]], False),
               ([[0.25, -0.5], [0.25, 0.5]], False)])
    assert classify_glyph(glyph_features(g)) == "double_tick"


def test_strike_dip_perpendicular():
    g = _geom([([[0.0, -0.5], [0.0, 0.5]], False),
               ([[-0.25, 0.12], [0.25, 0.12]], False)])
    assert classify_glyph(glyph_features(g)) == "strike_dip"


def test_closed_marker():
    sq = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]
    g = _geom([], closed=[sq])
    assert classify_glyph(glyph_features(g)) == "closed_marker"


def test_first_last_same_point_counts_closed():
    sq = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]
    g = _geom([(sq, False)])  # closed 标志缺席但首尾同点
    assert classify_glyph(glyph_features(g)) == "closed_marker"


def test_single_stroke():
    g = _geom([([[0.0, -0.5], [0.0, 0.5]], False)])
    assert classify_glyph(glyph_features(g)) == "single_stroke"


def test_complex_three_strokes():
    g = _geom([([[0.0, -0.5], [0.0, 0.5]], False),
               ([[-0.25, 0.0], [0.25, 0.0]], False),
               ([[-0.3, -0.3], [0.3, 0.3]], False)])
    assert classify_glyph(glyph_features(g)) == "complex"


def test_empty():
    assert classify_glyph(glyph_features(_geom([]))) == "empty"


def test_registry_audit_consistent():
    class _FakeLib:
        pass

    import geosciml4china.calibrate.glyphcls as gc

    real = gc.load_glyph_classes

    def fake(lib, codes):
        return {c: ("double_tick" if c in ("1281", "1519") else "strike_dip")
                for c in codes}

    gc.load_glyph_classes = fake
    try:
        rows = audit_registry(_FakeLib(), {
            "1281": {"role": "base"},
            "1519": {"role": "tick_variant", "family": "1281"},
            "1894": {"role": "base"},
            "99": {"role": "exclude"},
        })
    finally:
        gc.load_glyph_classes = real
    ok = {r["symbol_no"]: r["verdict"] for r in rows}
    assert ok["1281"].startswith("一致")
    assert ok["1519"].startswith("一致")
    assert ok["1894"].startswith("一致")
    assert "99" not in ok          # exclude 不参与 a/b 对账


def test_registry_audit_conflict():
    class _FakeLib:
        pass

    import geosciml4china.calibrate.glyphcls as gc
    real = gc.load_glyph_classes
    gc.load_glyph_classes = lambda lib, codes: {c: "closed_marker"
                                                for c in codes}
    try:
        rows = audit_registry(_FakeLib(),
                              {"1281": {"role": "base"}})
    finally:
        gc.load_glyph_classes = real
    assert rows[0]["verdict"].startswith("冲突")


def test_hook_glyph_sharp_bend():
    """168 型：4 顶点锐角折线（两次 ~120° 弯）。"""
    g = _geom([([[0.0, 0.0], [0.0, 0.86], [-0.4, 0.5], [0.1, 0.3]], False)])
    assert classify_glyph(glyph_features(g)) == "hook_glyph"


def test_complex_outline_not_hook():
    """1630 裁定回归（2026-10-16 用户：1630 非走滑钩）——
    多顶点掉头轮廓如实归 complex。"""
    run = [(i * 0.02, 0.0) for i in range(30)]
    back = [(0.56 - i * 0.02, 0.005) for i in range(30)]  # 近平行回折→~166° 掉头
    pts1 = run + back          # 末端发夹掉头（≈180° 弯）
    g = _geom([(pts1, False), (list(pts1), False)])
    f = glyph_features(g)
    assert f["n_points"] >= 60 and f["dup_pairs"] == 1
    assert f["max_turn"] >= 150
    assert classify_glyph(f) == "complex"


def test_existing_classes_unaffected_by_hook_rules():
    """回归：1281/1894/1827 三分型不受钩规则影响。"""
    g1281 = _geom([([[-0.25, -0.5], [-0.25, 0.5]], False),
                   ([[0.25, -0.5], [0.25, 0.5]], False)])
    assert classify_glyph(glyph_features(g1281)) == "double_tick"
    g1894 = _geom([([[0.0, -0.5], [0.0, 0.5]], False),
                   ([[-0.25, 0.12], [0.25, 0.12]], False)])
    assert classify_glyph(glyph_features(g1894)) == "strike_dip"
    sq = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]
    g1827 = _geom([], closed=[sq])
    assert classify_glyph(glyph_features(g1827)) == "closed_marker"


def test_closed_bent_marker_honest_boundary():
    """168/1827 边界如实登记：闭合锐角小标记单体字形不可分——
    一律 closed_marker（钩语义属空间成对层，符号列仅佐证）。"""
    c_hook = _geom([], closed=[[[0.0, 0.0], [0.0, 0.86], [-0.45, 0.62],
                               [0.05, 0.2], [0.0, 0.0]]])
    square = _geom([], closed=[[[0.0, 0.0], [0.7, 0.25], [0.5, 0.9],
                               [-0.2, 0.65], [0.0, 0.0]]])
    assert classify_glyph(glyph_features(c_hook)) == "closed_marker"
    assert classify_glyph(glyph_features(square)) == "closed_marker"


def test_strike_dip_bent_bar_regression():
    """1894 回归：T 形横杆带中点折弯仍判 strike_dip（两笔划优先）。"""
    g = _geom([([[0.0, -0.5], [0.0, 0.5]], False),
               ([[-0.25, 0.12], [0.05, 0.2], [0.25, 0.12]], False)])
    assert classify_glyph(glyph_features(g)) == "strike_dip"


def test_hook_component_238():
    """238 型：斜杆+竖笔两笔小角形（126°/90°）。"""
    g = _geom([([[-0.45, -0.02], [0.3, 0.2]], False),
               ([[0.05, -0.002], [0.05, 0.23]], False)])
    assert classify_glyph(glyph_features(g)) == "hook_component"


def test_hook_component_239():
    """239 型：竖笔+折笔（90° 与 ~52° 端向，75° 弯）。"""
    g = _geom([([[0.05, -0.24], [0.05, -0.05]], False),
               ([[0.05, -0.05], [0.4, -0.1], [0.7, 0.26]], False)])
    assert classify_glyph(glyph_features(g)) == "hook_component"


def test_hook_component_not_capturing_1894():
    """1894 回归：⊥ 对（0°/90°）仍是 strike_dip 而非钩构件。"""
    g = _geom([([[0.0, -0.5], [0.0, 0.5]], False),
               ([[-0.25, 0.12], [0.05, 0.2], [0.25, 0.12]], False)])
    assert classify_glyph(glyph_features(g)) == "strike_dip"
