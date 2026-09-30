# -*- coding: utf-8 -*-
"""断层样式生成器（2026-09-28，F2 域扩展：与 stylegen 同构的断层域）。

**GeoSciML 断层语义 + DZ/T 0179-2025 断层符号约定 → 断层渲染样式文件**
（fault_rendering_styles schema），与 MapGIS→GeoSciML 转换解耦：

- 语义源：GeoSciML Lite `shear_displacement_structure_view.geojson`
  （genericSymbolizer = gzeeb_eff 校准码）+ `geosciml.mapping` 的
  gzeeb→faultType 词表映射（各幅经 config.init_sheet 参数化）；
- 默认规则（词表→样式，DZ/T 0179 本地表达）：
  fault 泛称→红实线；reverse_fault→红实线；thrust_fault→深红+尖三角齿；
  normal_fault→红实线+短刺；dextral/sinistral→红实线（钩线由辅助点驱动）；
  推测证据（04/indirect）→虚线 [4,2]；
- **overrides 裁定层**（data/fault_style_overrides_<sheet>.json）：
  一次播种自现行手工样式（transcription basis=adjudicated，与面元
  stylegen --seed-overrides 同构），此后 生成默认 < 裁定层；
- 回归门：`--diff` 与现行手工样式逐码（name/line/decoration）对账，
  播种后差异必须为 0（与原 fault_type_overrides 语义裁定正交不冲突——
  那是段级类型覆盖，本文件是码级画法）。

CLI:
    python -m geosciml_render.stylegen_fault --sheet kurgan [--diff]
        [--seed-overrides]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..sheets import get_sheet, list_sheets


def _sheet_cfg(key: str) -> dict:
    """注册表图幅 → stylegen_fault 配置（历史键名保持，函数体零改动）。"""
    sh = get_sheet(key)
    return {
        "sds_view": sh.lite_out / "shear_displacement_structure_view.geojson",
        "handauth": sh.handauth_fault_styles,
        "overrides": sh.fault_style_overrides,
        "out": sh.fault_styles_generated,
        "sheet_title": sh.title.split("1:250000")[0] if "1:250000" in sh.title else sh.title,
    }


class _SheetCfgDict(dict):
    """惰性 SHEETS 映射（与 stylegen 同构）。"""

    def __getitem__(self, key):
        return _sheet_cfg(key)

    def __contains__(self, key):
        try:
            get_sheet(key)
            return True
        except KeyError:
            return False


SHEETS = _SheetCfgDict()

# 词表 → 默认画法（DZ/T 0179-2025 本地表达；装饰仅给类型与默认参数，
# 尺寸/侧别等细节归 overrides 裁定层）
VOCAB_DEFAULT = {
    "fault": {"name": "断层（泛称）",
              "line": {"rgb": [220, 20, 20], "width": 0.6, "style": "solid"}},
    "reverse_fault": {"name": "逆断层",
                      "line": {"rgb": [220, 20, 20], "width": 0.6, "style": "solid"}},
    "thrust_fault": {"name": "推覆体边界",
                     "line": {"rgb": [180, 0, 0], "width": 0.7, "style": "solid"},
                     "decoration": {"type": "reverse_fault_teeth",
                                    "rgb": [180, 0, 0], "filled": True,
                                    "tooth_length_frac": 0.004,
                                    "spacing_frac": 0.008}},
    "normal_fault": {"name": "正断层",
                     "line": {"rgb": [220, 20, 20], "width": 0.6, "style": "solid"},
                     "decoration": {"type": "normal_fault_ticks"}},
    "dextral_strike_slip_fault": {"name": "右行走滑断层",
                                  "line": {"rgb": [220, 20, 20], "width": 0.6,
                                           "style": "solid"}},
    "sinistral_strike_slip_fault": {"name": "左行走滑断层",
                                    "line": {"rgb": [220, 20, 20], "width": 0.6,
                                             "style": "solid"}},
}
# 证据级别虚线化不在码级静态样式中硬编码——渲染时由证据层（evidence_class
# 覆盖裁定）叠加 [4,2]（三维分层：证据层 ⊥ 结构层，码义随幅原则）


def read_sds_codes(sheet: str) -> dict:
    """sds_view → {gzeeb_eff 码: 段数}（GeoSciML 侧语义源）。"""
    p = SHEETS[sheet]["sds_view"]
    doc = json.loads(p.read_text(encoding="utf-8"))
    feats = doc.get("features") or []
    assert feats, f"sds_view empty: {p}（须先 build lite）"
    out: dict[str, int] = {}
    for f in feats:
        c = str((f.get("properties") or {}).get("genericSymbolizer") or "")
        out[c] = out.get(c, 0) + 1
    return out


def _vocab_of(code: str, sheet: str) -> str:
    from ..convert import config as _cfg
    from ..convert import mapping as _mp
    _cfg.init_sheet(sheet)  # 词表映射按幅切换（原隐式默认 kurgan 的潜伏跨幅隐患修除）
    return _mp.gzeeb_row(code).get("term") or "fault"


def load_overrides(sheet: str) -> dict:
    p = SHEETS[sheet]["overrides"]
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("overrides", {})


def generate(sheet: str, overrides: dict | None = None) -> dict:
    """词表默认 + overrides 裁定层 → fault_rendering_styles schema。"""
    cfg = SHEETS[sheet]
    overrides = overrides or {}
    hp = cfg["handauth"]
    hand = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    # 新幅首接无手工样式本：各节走默认（[220,20,20]/0.5/{} 见组装段）
    codes = read_sds_codes(sheet)
    ft: dict[str, dict] = {}
    # 并集：图上出现码 ∪ 裁定层注册码（0 段保留注册语义，如库尔干 02）
    all_codes = sorted(set(codes) | set((overrides.get("fault_types") or {}).keys()))
    for code in all_codes:
        ov = (overrides.get("fault_types") or {}).get(code) or {}
        term = ov.get("_term") or _vocab_of(code, sheet)
        base = json.loads(json.dumps(VOCAB_DEFAULT.get(term, VOCAB_DEFAULT["fault"])))
        entry = {
            "name": ov.get("name", base["name"]),
            "source_field": "GZEEB",
            "count": codes.get(code, 0),
            "line": ov.get("line", base["line"]),
        }
        deco = ov.get("decoration", base.get("decoration", "none"))
        entry["decoration"] = deco
        if ov.get("confidence"):
            entry["confidence"] = ov["confidence"]
        ft[code] = entry
    out = {
        "_meta": {
            "title": f"{cfg['sheet_title']}断裂构造渲染样式（语义生成 · DZ/T 0179-2025）",
            "standard": "DZ/T 0179-2025", "scale": "1:250000",
            "created": "2026-09-28",
            "color_source": "GeoSciML sds_view + geosciml.mapping 词表 + overrides 裁定层",
            "generator": "geosciml_render.stylegen_fault（语义→样式；"
                         f"overrides 见 {cfg['overrides'].name}）",
            "supersedes": cfg["handauth"].name + "（手工规则版，保留供对账）",
        },
        "default_color": (overrides.get("default_color")
                          or hand.get("default_color", [220, 20, 20])),
        "default_width": (overrides.get("default_width")
                          or hand.get("default_width", 0.5)),
        "width_by_gzeee": (overrides.get("width_by_gzeee")
                           or hand.get("width_by_gzeee", {})),
        "fault_types": ft,
        "named_faults": (overrides.get("named_faults")
                         or hand.get("named_faults", {})),
        "deep_faults": (overrides.get("deep_faults")
                        or hand.get("deep_faults", {})),
        "remote_sensing_faults": (overrides.get("remote_sensing_faults")
                                  or hand.get("remote_sensing_faults", {})),
        "dip_label": (overrides.get("dip_label")
                      or hand.get("dip_label", {})),
    }
    return out


def seed_overrides(sheet: str) -> Path:
    """现行手工样式 → overrides 裁定层（一次转录，basis=adjudicated）。"""
    cfg = SHEETS[sheet]
    hand = json.loads(cfg["handauth"].read_text(encoding="utf-8"))
    ov_types = {}
    for code, e in (hand.get("fault_types") or {}).items():
        ent = {k: e[k] for k in ("name", "line", "decoration") if k in e}
        if e.get("confidence"):
            ent["confidence"] = e["confidence"]
        ov_types[code] = ent
    doc = {
        "_meta": {
            "title": f"{cfg['sheet_title']}断层样式裁定层",
            "basis": "adjudicated（播种自 " + cfg["handauth"].name + "，2026-09-28 转录）",
            "note": "生成默认 < 本层；修改须经裁定流程",
        },
        "overrides": {
            "fault_types": ov_types,
            "default_color": hand.get("default_color"),
            "default_width": hand.get("default_width"),
            "width_by_gzeee": hand.get("width_by_gzeee", {}),
            "named_faults": hand.get("named_faults", {}),
            "deep_faults": hand.get("deep_faults", {}),
            "remote_sensing_faults": hand.get("remote_sensing_faults", {}),
            "dip_label": hand.get("dip_label", {}),
        },
    }
    cfg["overrides"].write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    return cfg["overrides"]


def diff_styles(sheet: str, generated: dict) -> list[str]:
    """逐码对账（name/line/decoration）vs 现行手工样式。"""
    hand = json.loads(SHEETS[sheet]["handauth"].read_text(encoding="utf-8"))
    hf = hand.get("fault_types") or {}
    gf = generated.get("fault_types") or {}
    diffs = []
    for code in sorted(set(hf) | set(gf)):
        h, g = hf.get(code), gf.get(code)
        if h is None:
            diffs.append(f"[仅生成] {code}")
            continue
        if g is None:
            diffs.append(f"[仅手工] {code}")
            continue
        for k in ("name", "line", "decoration"):
            if json.dumps(h.get(k), sort_keys=True, ensure_ascii=False) != \
               json.dumps(g.get(k), sort_keys=True, ensure_ascii=False):
                diffs.append(f"[{k}] {code}: 手工={json.dumps(h.get(k), ensure_ascii=False)[:80]}"
                             f" vs 生成={json.dumps(g.get(k), ensure_ascii=False)[:80]}")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(prog="geosciml_render.stylegen_fault")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()], required=True)
    ap.add_argument("--seed-overrides", action="store_true",
                    help="现行手工样式播种为 overrides 裁定层（一次转录）")
    ap.add_argument("--diff", action="store_true", help="与手工样式逐码对账")
    args = ap.parse_args()
    cfg = SHEETS[args.sheet]
    if args.seed_overrides:
        p = seed_overrides(args.sheet)
        print("播种 overrides:", p)
    out = generate(args.sheet, load_overrides(args.sheet))
    cfg["out"].write_text(json.dumps(out, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"生成: {cfg['out']}（码 {len(out['fault_types'])}）")
    if args.diff:
        diffs = diff_styles(args.sheet, out)
        print(f"对账 vs {cfg['handauth'].name}: 差异 {len(diffs)}")
        for d in diffs:
            print(" ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
