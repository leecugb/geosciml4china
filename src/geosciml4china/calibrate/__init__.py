"""标定子系统（渐进迁入中，2026-09-29 全链范围裁定）。

已入包：priors（先验库装载+图幅扩展册合并）。
迁移路线（逐域、影子先行、双幅逐字节复现准入）：
gzbd → gzeeb → attitudes → fossils → aux 链（association/pairs/triplets/entities）。
迁移完成前，编排器经 pymapgis.semantics.calibrate_semantics 跑图幅剖面
l1_stages 列出的既有脚本。
"""
from .priors import load_priors

__all__ = ["load_priors"]
