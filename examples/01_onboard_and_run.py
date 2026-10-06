# -*- coding: utf-8 -*-
"""01 — 零注入接入 + 管线三接口分步（2026-10-06 管线结构）。

    python 01_onboard_and_run.py --root D:/my-sheet --key mykey [--render]

等价 CLI：
    g4c probe --root ROOT --key KEY --register
    g4c prepare --sheet KEY     # 接口一：完整性检验 + 地质语义标定 → codebook
    g4c convert --sheet KEY     # 接口二：按 codebook 转换 GeoSciML
    g4c render  --sheet KEY     # 接口三：GeoSciML 渲染（--render 时执行）
需要 pymapgis 完整栈（profiles/semantics/rendering）在场。
"""
import argparse

from geosciml4china import onboard
from geosciml4china.pipeline import convert, prepare, render_stage


def main() -> int:
    ap = argparse.ArgumentParser(description="零注入接入 + 管线三接口")
    ap.add_argument("--root", required=True, help="MapGIS 工程文件夹（.WL/.WP/.WT）")
    ap.add_argument("--key", required=True, help="图幅注册键（如 mykey）")
    ap.add_argument("--title", default=None, help="图幅标题（缺省=零注入接入 <key>）")
    ap.add_argument("--code", default=None, help="图幅编号（缺省=J43T00000<末字符>）")
    ap.add_argument("--render", action="store_true", help="继续执行接口三（渲染）")
    args = ap.parse_args()

    census = onboard(args.root, args.key, title=args.title, code=args.code)
    print("普查:", {k: census[k] for k in
                   ("lat_mid", "aux_filter", "b_symbol_raw", "n_units_raw",
                    "warnings")})

    # 接口一：完整性检验 + 地质语义标定 → codebook_<key>.json
    rc = prepare(args.key)
    if rc != 0:
        return rc
    # ——此处可人工编辑 codebook_<key>.json（用户裁定通道）——
    # 接口二：按 codebook 转换 GeoSciML（stylegen → build → verify）
    rc = convert(args.key)
    if rc != 0 or not args.render:
        return rc
    # 接口三：GeoSciML 渲染 + C1-C7 镜像核验
    return render_stage(args.key)


if __name__ == "__main__":
    raise SystemExit(main())
