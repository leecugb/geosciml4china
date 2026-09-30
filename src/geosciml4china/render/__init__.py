"""geosciml_render —— GeoSciML 产物渲染引擎（薄适配器+全量复用）。

公共 API：build_geosciml_map / check_consistency / render（CLI 见 render.py）。
"""
from .map_builder import build_geosciml_map
from .mirror import check_consistency

__all__ = ["build_geosciml_map", "check_consistency"]
