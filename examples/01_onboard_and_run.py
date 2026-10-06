# -*- coding: utf-8 -*-
"""01 — 零注入接入：一步式注册 + 全链。

    python 01_onboard_and_run.py --root D:/my-sheet --key mykey [--render]

等价 CLI：g4c probe --root ROOT --key KEY --register && g4c pipeline --sheet KEY
需要 pymapgis 完整栈（profiles/semantics/rendering）在场。
"""
import argparse

from geosciml4china import onboard
from geosciml4china.pipeline import run_pipeline


def main() -> int:
    ap = argparse.ArgumentParser(description="零注入接入 + 全链")
    ap.add_argument("--root", required=True, help="MapGIS 工程文件夹（.WL/.WP/.WT）")
    ap.add_argument("--key", required=True, help="图幅注册键（如 mykey）")
    ap.add_argument("--title", default=None, help="图幅标题（缺省=零注入接入 <key>）")
    ap.add_argument("--code", default=None, help="图幅编号（缺省=J43T00000<末字符>）")
    ap.add_argument("--render", action="store_true", help="含渲染阶段（默认 --skip-render 提速）")
    args = ap.parse_args()

    census = onboard(args.root, args.key, title=args.title, code=args.code)
    print("普查:", {k: census[k] for k in
                   ("lat_mid", "aux_filter", "b_symbol_raw", "n_units_raw",
                    "warnings")})
    return run_pipeline(args.key, skip_render=not args.render)


if __name__ == "__main__":
    raise SystemExit(main())
