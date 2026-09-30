"""Data classes shared by the GML emitters and the Lite view builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from . import config as _cfg

_NCNAME_BAD = __import__("re").compile(r"[^\w.-]", __import__("re").UNICODE)


def _safe_ncname(s: str) -> str:
    """gml:id NCName 化：非法字符（+/∈ 等数学符号）转 _x{码点大写hex}_。

    英吉沙复合/侵入单元码含 '+' 与 '∈'（Qhal+pl、ηγ∈ 等，XSD NCName 校验实测）。"""
    return _NCNAME_BAD.sub(lambda m: f"_x{ord(m.group(0)):X}_", str(s))


def config_base() -> str:
    return _cfg.BASE_URI


@dataclass
class EventRec:
    eventprocess_term: Optional[str] = None  # deposition/intrusion/metamorphic_process
    eventprocess_label: str = ""
    older_era: Optional[str] = None  # ICS CamelCase id
    younger_era: Optional[str] = None
    older_ma: Optional[float] = None
    younger_ma: Optional[float] = None
    numeric_pair: Optional[Tuple[float, float]] = None  # regional dual-track (older, younger) Ma


@dataclass
class CompositionRec:
    lithology_term: str = ""
    lithology_label: str = ""
    lithology_uri: str = ""
    role: str = "dominant"


@dataclass
class UnitRec:
    norm: str
    name: str
    layer_role: str  # 正式沉积地层/侵入岩/变质岩/补充沉积地层
    unittype_term: str = ""
    rank_term: str = ""
    description: str = ""
    event: Optional[EventRec] = None
    compositions: List[CompositionRec] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)  # {target_norm, term, note}（单元对接地关系 v2.1）
    rgb: Optional[List[int]] = None

    @property
    def uri(self) -> str:
        return f"{config_base()}geologicunit/{quote(self.norm, safe='')}"

    @property
    def gml_id(self) -> str:
        return f"gu.{_safe_ncname(self.norm)}"


@dataclass
class MappedFeatureRec:
    feature_id: str  # FEATUREID or generated id
    specification_uri: str
    specification_title: str
    geometry: Dict[str, Any]
    observation_term: Optional[str] = None
    observation_label: str = ""
    purpose: Optional[str] = None
    description: Optional[str] = None  # 非空则入 gml:description（测量点位 MF 用）
    map_code: str = ""      # MapGIS 原码（QDUECC_eff，GeoSciML 侧溯源）
    src_file: str = ""      # 源图层（LDZOFBB00X.WP，portrayal 分层语义）

    @property
    def uri(self) -> str:
        return f"{config_base()}mappedfeature/{self.feature_id}"

    @property
    def gml_id(self) -> str:
        return f"mf.{self.feature_id}"


@dataclass
class ContactRec:
    src_id: int
    code: str  # GZBD_eff
    sem_label: str
    verdict: str
    younger_side: Optional[str]
    geometry: Dict[str, Any]
    decided: bool
    contacttype_term: Optional[str] = None
    contacttype_label: str = ""
    observation_term: Optional[str] = None
    observation_label: str = ""
    pending_ref: Optional[str] = None

    @property
    def uri(self) -> str:
        return f"{config_base()}contact/{self.src_id}"

    @property
    def gml_id(self) -> str:
        return f"c.{self.src_id}"


@dataclass
class FaultAuxPlane:
    azimuth: float
    dip: Optional[float]
    aux_idx: Optional[int] = None   # 1894 箭头 aux 索引（溯源）
    mode: str = ""                  # 六类模式标签（a-b-a·逆断层产状点 等，09-26 定版）
    dip_source: str = ""            # 倾角来源：配对注释 / 配对待裁定 / 无（留空）——GZECE 回落已废止（09-29 裁定）
    movement_sense: str = ""        # faultmovementsense 词：normal/reverse/no_movement_sense
    foot: Optional[dict] = None     # 测量点位=b 到所属段的垂足（GeoJSON Point；09-27 用户裁定保留）


@dataclass
class FaultRec:
    feature_id: str
    fault_id: str
    fault_name: Optional[str]
    gzeeb_eff: str
    structural_type: str
    evidence_class: str
    faulttype_term: str = ""
    faulttype_label: str = ""
    observation_term: str = ""
    observation_label: str = ""
    description_append: str = ""
    gzehg: str = ""
    gzece: float = 0.0
    attitude_note: str = ""         # 产状点逐平面模式行+争议/矛盾横幅（进 GML/Lite 描述）
    slip_sense: str = ""            # 238/239 钩旋向：dextral/sinistral（走滑段）
    planes: List[FaultAuxPlane] = field(default_factory=list)
    geometry: Dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"{config_base()}fault/{self.feature_id}"

    @property
    def gml_id(self) -> str:
        return f"sds.{self.feature_id}"


@dataclass
class AttitudeRec:
    src_id: int
    gzbbga: str
    sem_type: str
    azimuth: float
    dip: Optional[float]  # None=空倾角（如实缺省，dip 槽不发射）
    foliation_term: Optional[str] = None
    foliation_label: str = ""
    overturned: bool = False
    host_norm: Optional[str] = None
    host_name: Optional[str] = None
    note: str = ""   # B3：违反（待裁定）verdict 声明（如实标记，2026-09-28）
    geometry: Dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"{config_base()}foliation/{self.src_id}"

    @property
    def gml_id(self) -> str:
        return f"fol.{self.src_id}"


@dataclass
class FoldRec:
    feature_id: str
    name: str
    gzce: str
    profile_term: str  # anticline / syncline
    geometry: Dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"{config_base()}fold/{self.feature_id}"

    @property
    def gml_id(self) -> str:
        return f"fold.{self.feature_id}"


@dataclass
class SpecimenRec:
    """化石/泥火山产地（GeoSciML Lite GeologicSpecimenView，2026-09-28 转入）。

    主 GML 无 GeologicSpecimen 槽（GeoSciML 4.1 未发布 Sampling 包——
    离线树+gml 3.1.1 不可得已实证）；标本以官方 portrayal 层
    GeologicSpecimenView 承载（lite 第六视图）。"""

    src_id: int
    kind: str                 # 化石 / 泥火山（图层类别）
    sem_type: str             # 动物化石/植物化石/孢粉化石/泥火山
    sub_no: str               # MapGIS 子图码（genericSymbolizer）
    height: str = "2.0"       # 图形参数：符号高（mm）——render_fossil_layer 契约
    angle: str = "0.0"        # 图形参数：旋转角（rad）
    verdict: str = ""
    host_norm: Optional[str] = None
    host_name: Optional[str] = None
    note: str = ""            # 违反（待裁定）verdict 声明（B3 同构）
    geometry: Dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"{config_base()}specimen/{self.src_id}"

    @property
    def gml_id(self) -> str:
        return f"sp.{self.src_id}"
