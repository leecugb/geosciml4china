# -*- coding: utf-8 -*-
"""03 — 修改-再转化回路：编辑编码-语义映射表 → 重跑标定域 → 再物化。

    python 03_modify_reconvert_loop.py --key mykey --code 16 --semantic 走滑断层
       [--note "用户裁定"]

映射表 = code_semantics_map_<key>.csv 的 user_semantic 列（跨轮保留，权威序
在注册表之下、统计票之上）。编辑后须重跑 g4c calibrate-gzeeb 使编辑生效
（pipeline --skip-calibrate-stages 路径带陈旧守卫）。
需要 pymapgis 完整栈在场。
"""
import argparse
from pathlib import Path

import pandas as pd

from geosciml4china.sheets import get_sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="映射表修改-再转化回路")
    ap.add_argument("--key", required=True)
    ap.add_argument("--code", required=True, help="GZEEB 码值（两位字符串）")
    ap.add_argument("--semantic", required=True, help="用户裁定的地质语义")
    ap.add_argument("--note", default="", help="裁定备注（写入 user_note）")
    args = ap.parse_args()

    sh = get_sheet(args.key)
    root = Path(sh.root)
    map_p = root / f"code_semantics_map_{args.key}.csv"
    if not map_p.exists():
        print(f"!! 映射表缺席: {map_p}（先跑 g4c pipeline --sheet {args.key}）")
        return 1

    m = pd.read_csv(map_p, dtype=str)
    code = str(args.code).zfill(2)
    rows = m[m["GZEEB"].astype(str).str.zfill(2) == code]
    if not len(rows):
        print(f"!! 映射表无码 {code}（现有码: {sorted(m['GZEEB'].astype(str).tolist())}）")
        return 1

    # 编辑 user_semantic/user_note 列（不存在则创建）
    if "user_semantic" not in m.columns:
        m["user_semantic"] = ""
    if "user_note" not in m.columns:
        m["user_note"] = ""
    m.loc[m["GZEEB"].astype(str).str.zfill(2) == code,
          "user_semantic"] = args.semantic
    m.loc[m["GZEEB"].astype(str).str.zfill(2) == code,
          "user_note"] = args.note
    m.to_csv(map_p, index=False, encoding="utf-8-sig")
    print(f"已编辑 {map_p.name}: GZEEB={code} → user_semantic={args.semantic}")

    # 再转化：重跑标定域（确定性重放）→ 物化
    from geosciml4china.calibrate.gzeeb import calibrate_faults
    calibrate_faults(args.key)
    from pymapgis.semantics.materialize import materialize_sheet
    materialize_sheet(str(root))
    print(f"重跑 calibrate-gzeeb + 物化完成——编辑已生效，"
          f"可用 g4c build/verify --sheet {args.key} 重建产品")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
