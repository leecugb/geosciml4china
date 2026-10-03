# -*- coding: utf-8 -*-
"""褶皱（GZCE）码义标定域（2026-10-03 用户六步架构第三步「依次完成
……褶皱地质编码语义的标定」正式化）。

机制=先验知识驱动：褶皱码义唯一合法载体=词表登记册
（geosciml_vocab_mapping.json 的 gzce_foldprofile 节——GZCE 01=向斜等
裁定在案，2026-09-29）；褶皱无段级证据通道（无产状点/探针可构成
MLE 回归），故无投票——码义命中即标定，未注册码如实登记待裁定
（同码继承在 build 侧随词表天然成立）。
"""
from __future__ import annotations

import argparse
from collections import Counter

import pandas as pd

from ..convert import mapping as _mp
from ..sheets import get_sheet
from pymapgis.semantics import load_source_layer


def calibrate_folds(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    out_dir = out_dir or sh.root
    from ..convert import config as _cfg
    _cfg.init_sheet(sheet_key)  # 词表按幅切换（与 stylegen_fault._vocab_of 同口径）
    vocab = _mp.load().get("gzce_foldprofile") or {}
    # CONDITIONAL 层缺席守卫（2026-10-03 泛化缺口：缺褶皱层的图幅优雅
    # 跳过——与 gzbd BB002/LDLYAAE002 守卫同构，管线畅通原则）
    try:
        gdf = load_source_layer(str(sh.root), "LDZOFBA005.WL", graphic=False)
    except Exception:
        print(f"   褶皱标定: LDZOFBA005.WL 缺席（{sheet_key}）——优雅跳过")
        return {"rows": 0, "distribution": {}, "pending": [],
                "skipped": "missing fold layer"}
    rows = []
    for i, (_, r) in enumerate(gdf.iterrows()):
        code = str(r.get("GZCE") or "").strip()
        code = code[:-2] if code.endswith(".0") else code
        code = code.zfill(2) if code else ""
        entry = vocab.get(code) or {}
        term = (entry.get("term") or "")
        sem = (entry.get("label") or
               ({"anticline": "背斜", "syncline": "向斜"}.get(term, ""))
               or "")
        rows.append(dict(idx=i, GZCE=code, semantic=sem,
                         profile=term if term in ("anticline", "syncline")
                         else "",
                         verdict=(entry.get("status")
                                  or ("裁定（词表登记册）" if term else
                                      "待裁定（码义未注册）"))))
    out = pd.DataFrame(rows)
    out.to_csv(f"{out_dir}/_fold_calibration_{sh.key}.csv",
               index=False, encoding="utf-8-sig")
    dist = Counter(r["semantic"] for r in rows)
    pending = [r["GZCE"] for r in rows if not r["profile"]]
    if pending:
        print(f"   褶皱码义未注册: {sorted(set(pending))} → 待裁定")
    print(f"   褶皱标定: {len(rows)} 条 → _fold_calibration_{sh.key}.csv"
          f"（{dict(dist)}）")
    return {"rows": len(rows), "distribution": dict(dist),
            "pending": sorted(set(pending))}


def main() -> int:
    ap = argparse.ArgumentParser(prog="calibrate_folds")
    ap.add_argument("--sheet", required=True)
    args = ap.parse_args()
    calibrate_folds(args.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
