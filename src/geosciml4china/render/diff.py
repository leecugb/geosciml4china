"""像素差分 + 掩膜归类 + 报告（镜像对账硬门：unclassified==0）。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


def _read_rgb(path: str | Path) -> np.ndarray:
    im = Image.open(path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return np.asarray(im, dtype=np.int16)


def pixel_diff(png_a: str | Path, png_b: str | Path, *,
               channel_tol: int = 8) -> tuple[np.ndarray, tuple[int, int]]:
    """同尺寸断言；任通道 |Δ|>channel_tol → mismatch。"""
    a, b = _read_rgb(png_a), _read_rgb(png_b)
    assert a.shape == b.shape, f"尺寸不一致: {a.shape} vs {b.shape}"
    mism = (np.abs(a - b) > channel_tol).any(axis=2)
    return mism, (mism.shape[0], mism.shape[1])


def classify(mism: np.ndarray, masks: list[tuple[str, np.ndarray]]) -> dict:
    """每个 mismatch 像素归属首个命中掩膜；未归类计数=硬门。"""
    rest = mism.copy()
    out = {"total_mismatch": int(mism.sum()), "classes": {}, "unclassified": 0}
    for name, m in masks:
        hit = int((rest & m).sum())
        out["classes"][name] = hit
        rest &= ~m
    out["unclassified"] = int(rest.sum())
    out["_rest_mask"] = rest
    return out


def write_diff_heat(png_a: str | Path, mism: np.ndarray,
                    classified_rest: np.ndarray, out_path: str | Path) -> None:
    """差异热力图：基图淡显 + 掩膜归类差异蓝 + 未归类差异红。"""
    base = (_read_rgb(png_a) * 0.35 + 255 * 0.65).astype(np.uint8)
    heat = base.copy()
    blue = mism & ~classified_rest
    heat[blue] = [60, 120, 255]
    heat[classified_rest] = [255, 30, 30]
    Image.fromarray(heat).save(out_path)


def write_report(res: dict, out_json: str | Path, out_md: str | Path,
                 meta: dict) -> None:
    res = dict(res)
    res.pop("_rest_mask", None)
    Path(out_json).write_text(json.dumps({"meta": meta, **res},
                                         ensure_ascii=False, indent=1),
                            encoding="utf-8")
    lines = ["# GeoSciML 镜像渲染对账报告", "",
             f"- 画布: {meta.get('shape')}（dpi={meta.get('dpi')}, bare, bbox 单源共享）",
             f"- 差分阈值: channel_tol={meta.get('channel_tol')}",
             f"- mismatch 总像素: {res['total_mismatch']}",
             f"- **未归类（硬门）: {res['unclassified']}**", "",
             "| 掩膜类 | 像素数 |", "|---|---|"]
    for k, v in res["classes"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "硬门规则：unclassified==0 为通过；掩膜类计数为已知差异",
              "（81 冰雪层 / excluded 段 / 片麻理符号形态）的量化登记。"]
    Path(out_md).write_text("\n".join(lines), encoding="utf-8")
