# -*- coding: utf-8 -*-
"""实体旋向表 _entity_hook_dir 单元测试（2026-10-16 泛化通道）。"""
from collections import defaultdict

import pytest

from geosciml4china.calibrate.gzeeb import _entity_hook_dir


def _mk(hook_by_seg):
    return {int(s): [dict(h) for h in hrs] for s, hrs in hook_by_seg.items()}


SEG2FID = {1: "F01", 2: "F01", 3: "F02", 4: "F03", 5: "F04"}


def test_unanimous_right():
    d = _entity_hook_dir(SEG2FID, _mk({
        1: [{"sense": "右行"}, {"sense": "右行"}],
        2: [{"sense": "右行"}]}))
    assert d == {"F01": "右行"}


def test_unanimous_left():
    d = _entity_hook_dir(SEG2FID, _mk({
        3: [{"sense": "左行"}, {"sense": "左行"}]}))
    assert d == {"F02": "左行"}


def test_mixed_sense_excluded():
    d = _entity_hook_dir(SEG2FID, _mk({
        1: [{"sense": "右行"}],
        2: [{"sense": "左行"}]}))
    assert "F01" not in d


def test_hookless_entity_absent():
    d = _entity_hook_dir(SEG2FID, _mk({1: [{"sense": "右行"}]}))
    assert "F03" not in d and "F04" not in d


def test_unknown_sense_ignored():
    d = _entity_hook_dir(SEG2FID, _mk({
        4: [{"sense": "右行"}, {"sense": "不明"}]}))
    assert d == {"F03": "右行"}  # 非标准取值不参与 unanimity 判定


def test_seg_without_fid_skipped():
    d = _entity_hook_dir(SEG2FID, _mk({999: [{"sense": "右行"}]}))
    assert d == {}


def test_line_aux_minimal_dict():
    # 线层接线注入的最小字典形态（{"sense","src"}）同样参与
    d = _entity_hook_dir(SEG2FID, _mk({
        5: [{"sense": "左行", "src": "line_aux"}]}))
    assert d == {"F04": "左行"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
