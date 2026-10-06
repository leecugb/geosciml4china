# -*- coding: utf-8 -*-
"""02 — 标定件检查：断层三维分布、置信带、界线冲突登记册。

    python 02_inspect_calibration.py --root D:/my-sheet --key mykey

只读示例（pandas + geosciml4china.sheets 注册表），无需重跑任何标定；
图幅须已跑过 pipeline（标定 CSV 在 root 下）。
"""
import argparse
from pathlib import Path

import pandas as pd

from geosciml4china.sheets import get_sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="标定件只读检查")
    ap.add_argument("--key", required=True, help="已注册/已标定图幅键")
    args = ap.parse_args()
    sh = get_sheet(args.key)
    root = Path(sh.root)

    fcal = root / f"_gzeeb_calibration_{args.key}.csv"
    if fcal.exists():
        fc = pd.read_csv(fcal, dtype=str)
        print(f"== 断层三维标定 {fcal.name}（{len(fc)} 段）==")
        print("结构类型分布:")
        print(fc["structural_type"].value_counts().to_string())
        print("\n裁决分布:")
        print(fc["verdict"].value_counts().to_string())
        if "conf_band_u" in fc.columns:
            print("\n置信带分布:")
            print(fc["conf_band_u"].value_counts().to_string())

    si = root / "_gzbd_semantic_interpretation.csv"
    if si.exists():
        df = pd.read_csv(si, dtype=str)
        print(f"\n== 界线语义解释 {si.name}（{len(df)} 段）==")
        print("状态分布:")
        print(df["状态"].value_counts().to_string())
        conf = df[df["状态"] == "分歧未裁定"]
        if len(conf):
            print(f"\n分歧未裁定 {len(conf)} 段（编码错误候选，待人工裁定）:")
            print(conf.groupby(["GZBD原码", "标定语义"]).size().to_string())

    pending = root / "output" / "geosciml" / "pending_review.md"
    if pending.exists():
        print(f"\n待裁定清单: {pending}（{len(pending.read_text(encoding='utf-8').splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
