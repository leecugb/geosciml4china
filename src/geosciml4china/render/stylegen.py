# -*- coding: utf-8 -*-
"""样式生成器（2026-09-27 用户裁定：泛化渲染架构）。

GeoSciML 地质语义 + 统一标准色库（data/dzt0179_color_library.json，
DZ/T 0179-2025）→ 渲染映射文件（polygon_layers schema）。

架构定位：取代两幅各自手写的 _build_color_mapping_<sheet>_dzt0179.py
（44/52 条手写 RULES）——同一份规则代码按单元语义（norm 码/名称/图层
角色）从色库派生 rgb 与 pattern_ref；图幅特有裁定（EK 喀什群、HtA 滹沱系、
无接触分区组间分色等）经 **overrides 裁定层** 固化（adjudicated > 生成默认，
与项目权威分级一致）；层序证据不足的组间分色给**确定性占位 + pending**
（矛盾交人工裁定，绝不猜）。

默认组间分色规则（文档化、确定性；与 2026-09-19 两幅裁定值的关系见 diff）：
- 同统 1 组 → 统色；
- 同统 2 组（老→新）→ [统色, 该统最高阶色]；
- 同统 n≥3 组 → 该统阶色序列等距取 n 槽（含两端；阶不足时深端垫统色）。
段间分色（自动探测同组多段）：下段 ×0.90、中段=组色、上段 +(255-c)×0.30。

CLI:
    python -m geosciml_render.stylegen --sheet kurgan [--diff]
        [--seed-overrides] [--out PATH]
    --diff           与骨架文件（现生产映射）逐单元对账
    --seed-overrides 把 diff 中"生成≠骨架"的单元以骨架值播种进 overrides
                     （骨架=已裁定生产映射，播种=basis adjudicated 转录）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..data import DZT0179_COLOR_LIBRARY
from ..sheets import get_sheet, list_sheets

LIB_PATH = DZT0179_COLOR_LIBRARY

ROLES = {
    # 官方图层名（2026-09-29 用户对齐定版；原「正式/补充沉积地层」废止）
    "LDZOFBB001.WP": "沉积岩建造",
    "LDZOFBB002.WP": "火山岩性岩相",
    "LDZOFBB003.WP": "侵入岩",
    "LDZOFBB004.WP": "变质岩建造",
}
POLY_FILES = list(ROLES)
# 空载占位层（用户样式件已含；与生产口径一致——无 units、官方角色名）
_PLACEHOLDER_LAYERS = {
    "LDZOFBB009.WP": "深部断裂",
    "LDZOFBB010.WP": "构造岩浆岩带",
    "LDLYAAE002.WP": "冰川/常年积雪面",
}


def _sheet_cfg(key: str) -> dict:
    """注册表图幅 → stylegen 配置（历史键名保持，函数体零改动）。"""
    sh = get_sheet(key)
    return {
        "wp_dir": sh.wp_dir,
        "lite_dir": sh.lite_out,
        "skeleton": sh.style_skeleton,
        "overrides": sh.style_overrides,
        "out": sh.style_generated,
        "report": sh.style_report,
        "sheet_title": sh.title.split("1:250000")[0] if "1:250000" in sh.title else sh.title,
    }


class _SheetCfgDict(dict):
    """惰性 SHEETS 映射：SHEETS["kurgan"] → _sheet_cfg(...)；兼容旧消费方式。"""

    def __getitem__(self, key):
        return _sheet_cfg(key)

    def __contains__(self, key):
        try:
            get_sheet(key)
            return True
        except KeyError:
            return False


SHEETS = _SheetCfgDict()


def norm_code(raw: str) -> str:
    """原始 mathtext 码 → 归一码（与两个旧生成器同一规则）。"""
    return re.sub(r"[→↓↑.]", "", raw).strip()


# ---------------------------------------------------------------------------
# 色库访问
# ---------------------------------------------------------------------------

# 标准界线线样式（DZ/T 0179 表22 地质界线用色——图幅无关标准资产；
# 骨架缺失时（独立项目泛化接入）作为 line_layers 默认）。
# 2026-10-03 渲染完全基于地质语义：line_styles 由 GZBD 码键改为标定
# 语义标签键（sem_label 规范形）；渲染器对「角度不整合界线」等变体
# 与「（先验建议→xx）」后缀做规范化后查表
STANDARD_LINE_LAYERS = {
    "LDZOFBA002.WL": {
        "role": "地质界线（标定语义）",
        "type_field": "sem_label",
        "line_styles": {
            "实测地质界线": {"name": "实测地质界线", "rgb": [51, 51, 51],
                         "width": 0.45, "style": "solid"},
            "第四系界线": {"name": "第四系界线", "rgb": [51, 51, 51],
                       "width": 0.3, "style": "solid"},
            "角度不整合": {"name": "角度不整合", "rgb": [51, 51, 51],
                       "width": 0.5, "style": "solid",
                       "note": "双线：实线+平行点线，点线在年轻地层一侧"},
            "侵入接触": {"name": "侵入接触", "rgb": [51, 51, 51],
                     "width": 0.45, "style": "solid"},
            "推测界线": {"name": "推测界线", "rgb": [100, 100, 100],
                     "width": 0.4, "style": "dashed", "dash_pattern": [11.1, 3.2]},
            "平行不整合": {"name": "平行不整合", "rgb": [51, 51, 51],
                       "width": 0.5, "style": "solid",
                       "note": "双线：实线+平行断线，断线在年轻地层一侧"},
            "不整合接触": {"name": "不整合接触（待裁定方向）", "rgb": [51, 51, 51],
                       "width": 0.5, "style": "solid"},
            "岩性过渡渐变界线": {"name": "岩性过渡渐变界线", "rgb": [100, 100, 100],
                         "width": 0.6, "style": "dotted",
                         "dash_pattern": [0.01, 3.3], "capstyle": "round"},
            "脉动接触界线": {"name": "脉动接触界线", "rgb": [51, 51, 51],
                         "width": 0.45, "style": "dashdot"},
            "整合接触": {"name": "整合接触", "rgb": [51, 51, 51],
                     "width": 0.45, "style": "solid"},
            "冰雪区界线": {"name": "冰雪区界线", "rgb": [0, 255, 255],
                       "width": 0.5, "style": "solid"},
        },
    },
}


class Lib:
    def __init__(self, path: Path = LIB_PATH):
        self.doc = json.loads(Path(path).read_text(encoding="utf-8"))
        self.fs = self.doc["formal_strata"]
        self.sys_base = {k: v["rgb"] for k, v in self.doc["system_base"].items()}
        self.cross = {e["code"]: e for e in self.doc["cross_era"]}
        self.qg = {e["code"]: e for e in self.doc["quat_genetic"]}
        intr = self.doc["intrusive"]
        self.t6_ep = {e["epoch"]: e["rgb"] for e in intr["acid_intermediate_t6"]["epochs"]}
        self.t6_base = intr["acid_intermediate_t6"]["era_base"]
        self.t7_ep = {e["epoch"]: e["rgb"] for e in intr["acid_pt_t7"]["epochs"]}
        self.t9 = {e["era"]: e["rgb"] for e in intr["neutral_t9"]["eras"]}
        self.t10 = {e["era"]: e["rgb"] for e in intr["basic_t10"]["eras"]}
        self.t11 = {e["era"]: e["rgb"] for e in intr["ultrabasic_t11"]["eras"]}
        self.t12 = {e["era"]: e["rgb"] for e in intr["alkaline_t12"]["eras"]}
        self.t13 = {e["era"]: e["rgb"] for e in intr["lamprophyre_t13"]["eras"]}
        self.t14 = {e["type"]: e["rgb"] for e in self.doc["dike_types_t14"]}
        self.order_records = self.doc["stratigraphic_contacts"]["records"]
        self.group_composition = self.doc["group_composition"]["groups"]

    def ts_rgb(self, path: str):
        node = self.doc["timescale"]
        for seg in path.split("/"):
            node = node[seg] if seg in node else node["children"][seg]
        return node.get("rgb") or (node.get("base") or {})["rgb"]

    def stage_children(self, tong: str) -> list[str]:
        """该统的阶码（升序，如 ['N1_1','N1_3','N1_5']）。"""
        def _num(code: str) -> int:
            return int(code.rsplit("_", 1)[-1])
        return sorted((k for k, v in self.fs.items() if v.get("parent") == tong),
                      key=_num)


# ---------------------------------------------------------------------------
# 单元输入
# ---------------------------------------------------------------------------

@dataclass
class UnitInput:
    raw_code: str
    norm: str
    name: str
    role: str
    src_file: str


def read_lite_units(sheet: str) -> list[UnitInput]:
    """读 GeoSciML Lite 单元视图（geologic_unit_view.geojson）的单元清单——
    **样式生成的语义源（2026-09-28 F1 解耦）**：norm/名称/角色/原码/源图层
    全部来自 GeoSciML 工件，不再回读 MapGIS WP（原则：与 MapGIS→GeoSciML
    转换解耦，GML 持有者即可复算样式）。
    同名单元跨多面元去重（首现）；bootstrap 回退见 read_sheet_units（--from-wp）。
    """
    p = SHEETS[sheet]["lite_dir"] / "geologic_unit_view.geojson"
    doc = json.loads(p.read_text(encoding="utf-8"))
    feats = doc.get("features") or []
    assert feats, f"lite geologic_unit_view empty: {p}（须先 build lite；或 --from-wp 引导）"
    seen: dict[tuple[str, str], UnitInput] = {}
    for f in feats:
        pr = f.get("properties") or {}
        key = (str(pr.get("src_file") or ""), str(pr.get("map_code") or ""))
        if key in seen or not key[1]:
            continue
        seen[key] = UnitInput(raw_code=key[1], norm=str(pr.get("unit_norm") or ""),
                              name=str(pr.get("name") or ""),
                              role=str(pr.get("layer_role") or ""), src_file=key[0])
    return list(seen.values())


def read_sheet_units(sheet: str) -> list[UnitInput]:
    """读图幅 WP 面层单元清单（raw 码+名称+角色），与旧生成器同输入。"""
    import os
    from pymapgis import Reader
    cfg = SHEETS[sheet]
    out: list[UnitInput] = []
    cwd = os.getcwd()
    os.chdir(cfg["wp_dir"])
    try:
        for f in POLY_FILES:
            if not Path(f).exists():
                continue  # 缺面层文件（如本幅无 LDZOFBB002.WP）——跳过不崩
            with Reader(f) as r:
                g = r.geodataframe
            seen: dict[str, str] = {}
            for c, n in zip(g["QDUECC"].astype(str), g["QDUECD"].astype(str)):
                seen.setdefault(c, n.strip())
            for raw, name in seen.items():
                out.append(UnitInput(raw_code=raw, norm=norm_code(raw),
                                     name=name, role=ROLES[f], src_file=f))
    finally:
        os.chdir(cwd)
    return out


# ---------------------------------------------------------------------------
# 分类与取色规则
# ---------------------------------------------------------------------------

# 第四系成因码别名（复合/异形码 → quat_genetic 键；gl 无独立条目借 g）
_QG_ALIAS = {"gl": "g", "al+pl": "alp", "pal": "alp", "eld": "el", "alm": "mr"}

# 侵入岩希腊字母前缀 → (色表, 花纹族, 花纹码)；最长前缀优先匹配
# 色表: t6=表6显生宙酸性-中酸性 / t7=表7前寒武酸性 / t9=中性 / t10=基性 /
#       t11=超基性 / t12=碱性 / t13=煌斑岩 / dike_*=表14 脉岩（时代不明）
_INTR_PREFIX = [
    ("γδο", ("t6", "custom", "gammaDeltaO")),
    ("γδ", ("t6", "t15_intrusive", "gdT2")),
    ("γο", ("t6", "custom", "gammaO")),
    ("γπ", ("t6", "custom", "gammaPi")),
    ("ηδο", ("t9", "custom", "deltaO")),
    ("ηγ", ("t6", "t15_intrusive", "etagJ1")),
    ("ξγ", ("t6", "custom", "xiGamma")),
    ("δο", ("t9", "custom", "deltaO")),
    ("δ", ("t9", "t15_intrusive", "dK2")),
    ("ν", ("t10", "t15_intrusive", "nD3")),
    ("σ", ("t11", "t15_intrusive", "sS")),
    ("οφ", ("t11", "custom", "omicronPhi")),
    ("κξο", ("t12", "t15_intrusive", "ksoC2")),
    ("κc", ("t13", "t15_intrusive", "kcK1")),
    ("χ", ("t13", "t15_intrusive", "cO1")),
    ("γρ", ("dike_acid", None, None)),      # 伟晶岩脉
    ("βμ", ("dike_basic", None, None)),
    ("τα", ("dike_alkaline", None, None)),
    ("υ", ("dike_basic", None, None)),
    ("ρ", ("dike_acid", None, None)),       # 伟晶岩脉
    ("q", ("dike_quartz", None, None)),
    ("γ", ("t6", "custom", "gamma")),
]
# 时代不明脉岩：色表类 → 表14 类型名
_DIKE_BY_CLASS = {"t6": "酸性岩脉", "t7": "酸性岩脉", "t9": "中性岩脉",
                  "t10": "基性岩脉", "t11": "超基性岩脉", "t12": "碱性岩脉",
                  "t13": "碱性岩脉", "dike_acid": "酸性岩脉",
                  "dike_basic": "基性岩脉", "dike_alkaline": "碱性岩脉",
                  "dike_quartz": "石英脉"}
# 中性/基性/超基性/碱性：时代后缀 → 代群（表9/10/11/12/13 eras 键）
_ERA_GROUP = {e: "Pz1" for e in ("Cm", "∈")}
_ERA_GROUP.update({e: "Pz2" for e in ("S", "O", "D", "C", "P")})
_ERA_GROUP.update({e: "Mz" for e in ("T", "J", "K")})
_ERA_GROUP.update({e: "Cz" for e in ("E", "N", "Q")})

# 变质岩特殊宿主（表19：以所属年代地层单位颜色表达）→ timescale 路径
_META_HOST = {"ChA": "Pt/Pt2/Ch", "ChSt": "Pt/Pt2/Ch", "Jxb": "Pt/Pt2/Jx",
              "Pt1K": "Pt/Pt1", "Pt2K": "Pt/Pt2", "Pt3K": "Pt/Pt3",
              # 滹沱纪 Ht 与古元古代 Pt1 同时代（2026-09-29 用户裁定）——
              # HtA 埃连卡特岩群取 Pt1 色（灰占位消解）
              "HtA": "Pt/Pt1"}

_ERA_RE = re.compile(r"^(Qh|Qp|Q|N|E|K|J|T|P|C|D|S|O|Cm|∈|Z|Nh|Qb|Jx|Ch|Pt\d?)"
                     r"(\d(?:-\d)?)?(.*)$")
_CROSS_SYS_RE = re.compile(r"^([A-Z])(\d(?:-\d)?)([A-Z])(\d(?:-\d)?)(.*)$")
_CROSS_CODES = {"CP", "SD", "DC", "OS", "JK", "TJ", "PT", "KE", "EN", "NQ",
                "CmO", "ZCm"}

# 界级/系级基色回落映射（2026-10-02 Pt1K 案）：元古界岩群（Pt1K）、长城系
# 岩群（ChA/ChSt）无统级编码——按时代前缀取表2 system_base 基色。
# 注意：_ERA_RE 交替序短码遮蔽长码（"P" 先于 "Pt\d?" 命中、C 先于 Ch），
# 回落层须按**长前缀优先**自扫，不得复用 _ERA_RE 的 group(1)。
_ERA_TO_BASE = {"Pt1": "Pt1", "Pt2": "Pt2", "Pt3": "Pt3",
                "Ht": "Pt2",  # 滹沱纪（2026-10-02 用户裁定：中元古代）
                "Ch": "Pt2", "Jx": "Pt2", "Qb": "Pt3",
                "Nh": "Nh", "Z": "Z", "∈": "Cm",
                "Qh": "Q", "Qp": "Q", "Q": "Q",
                "N": "N", "E": "E", "K": "K", "J": "J", "T": "T",
                "P": "P", "C": "Pz2", "D": "Pz2", "S": "Pz1", "O": "Pz1",
                "Cm": "Cm"}
_ERA_PREFIX_ORDER = tuple(sorted(_ERA_TO_BASE, key=len, reverse=True))


def _era_base_spec(norm: str, lib: Lib) -> StyleSpec | None:
    """界级基色回落：时代前缀（长优先）→ system_base 基色；
    未命中 None（保持未分类占位链）。"""
    for p in _ERA_PREFIX_ORDER:
        if not norm.startswith(p):
            continue
        key = _ERA_TO_BASE[p]
        if key not in lib.sys_base:
            return None
        return StyleSpec(rgb=list(lib.sys_base[key]), cls="strata_base",
                         src=f"表2 界级基色 {key}")
    return None


@dataclass
class StyleSpec:
    rgb: list | None = None
    pattern_ref: dict | None = None
    src: str = ""
    pending: str = ""          # 非空 → 入 pending 登记
    cls: str = ""              # quat/strata/intrusive/metamorphic/unknown


def _quat_spec(norm: str, lib: Lib) -> StyleSpec:
    """第四系：年代底色 + 成因花纹（群/复合未定 → 仅底色）。"""
    m = re.match(r"^(Qh|Qp|Q)(\d)?(.*)$", norm)
    if not m:
        return None  # 非第四系码（如 Qbbg/Qbl 以外的异形）交后续规则
    if m.group(1) == "Qh":
        age_key = "Qh"
    elif m.group(1) == "Q":
        age_key = "Q"  # 未定世第四系（2026-09-29 巴什库尔干 Qbbg/Qbl 首遇）
    else:
        age_key = f"Qp_{m.group(2)}" if m.group(2) else "Qp"
    rest = m.group(3) or ""
    spec = StyleSpec(cls="quat")
    if age_key not in lib.fs:
        spec.pending = f"年代统 {age_key} 不在 formal_strata"
        return spec
    spec.rgb = list(lib.fs[age_key]["rgb"])
    spec.src = f"表2 {age_key} 年代底色"
    # 成因码解析：exact → alias → 首段（'+'复合）→ 首段 alias
    genetic = None
    cands = [rest, _QG_ALIAS.get(rest)]
    if "+" in rest:
        first = rest.split("+")[0]
        cands += [first, _QG_ALIAS.get(first)]
    for c in cands:
        if c and c in lib.qg:
            genetic = c
            break
    if genetic:
        g = lib.qg[genetic]
        spec.pattern_ref = {"family": "t05_quat", "code": g["pattern_ref"]["code"]}
        spec.src += f" + 表5 {genetic} 成因花纹"
        if g["pattern_ref"].get("status") != "authoritative":
            spec.pending = f"成因花纹 {genetic} 瓦片 draft（待校核）"
    elif rest and rest not in ("X", "W") and not rest.startswith("-"):
        spec.pending = f"成因码 {rest!r} 未命中 quat_genetic（仅底色）"
    return spec


def _intr_spec(norm: str, lib: Lib) -> StyleSpec | None:
    for prefix, (table, fam, code) in _INTR_PREFIX:
        if not norm.startswith(prefix):
            continue
        suffix = norm[len(prefix):]
        spec = StyleSpec(cls="intrusive")
        if not suffix:  # 时代不明脉岩 → 表14
            tname = _DIKE_BY_CLASS[table]
            spec.rgb = list(lib.t14[tname])
            spec.src = f"表14 {tname}（时代不明）"
            return spec
        # 时代可定脉岩（如 βμC/υO-D2，2026-09-29 奥依亚依拉克新幅首遇）：
        # 伪表 dike_* → 岩族真表按时代群取色（DZ/T 表6/10/12 时代色）；
        # 原仅 t9-t13 查表致 KeyError——库尔干/英吉沙脉岩全为时代不明
        # （裸码走表14）或 overrides 短路，本分支此前未被 exercised。
        table = {"dike_basic": "t10", "dike_acid": "t6",
                 "dike_alkaline": "t12"}.get(table, table)
        # 时代后缀：t6 先世色、次前寒武 t7、后代基色；其余按代群
        s = "Cm" if suffix == "∈" else suffix
        if table == "t6":
            if s in lib.t6_ep:
                spec.rgb, spec.src = list(lib.t6_ep[s]), f"表6 {suffix}世"
            elif s in lib.t7_ep:
                spec.rgb, spec.src = list(lib.t7_ep[s]), f"表7 {suffix}纪"
            elif s in lib.t6_base:
                spec.rgb, spec.src = list(lib.t6_base[s]), f"表6 {suffix}代基色"
            else:
                spec.pending = f"时代后缀 {suffix!r} 未命中表6/表7"
                return spec
        else:
            grp = None
            for era, g in _ERA_GROUP.items():
                if g and s.startswith(era):
                    grp = g
                    break
            tbl = {"t9": lib.t9, "t10": lib.t10, "t11": lib.t11,
                   "t12": lib.t12, "t13": lib.t13}[table]
            if grp in tbl:
                tname = {"t9": "表9 中性", "t10": "表10 基性", "t11": "表11 超基性",
                         "t12": "表12 碱性", "t13": "表13 煌斑岩"}[table]
                spec.rgb, spec.src = list(tbl[grp]), f"{tname} {grp}"
            else:
                spec.pending = f"时代后缀 {suffix!r} 未命中{table}代群"
                return spec
        if fam and code:
            spec.pattern_ref = {"family": fam, "code": code}
        return spec
    return None


def _meta_spec(norm: str, lib: Lib) -> StyleSpec | None:
    if norm in _META_HOST:
        path = _META_HOST[norm]
        return StyleSpec(rgb=list(lib.ts_rgb(path)), cls="metamorphic",
                         src=f"表19 规则：宿主 {path} 色")
    m = _ERA_RE.match(norm)
    if m and m.group(2):  # 可解析为地层码（如 S2-3d1）→ 表19 同地层取色
        tong = f"{m.group(1)}{m.group(2)}"
        if tong in lib.fs:
            return StyleSpec(rgb=list(lib.fs[tong]["rgb"]), cls="metamorphic",
                             src=f"表19 规则：所属 {tong} 色")
    return None


def _order_groups(tong: str, groups: list[str], lib: Lib) -> list[str] | None:
    """同统多组的老→新排序（组码级）。

    证据：stratigraphic_contacts 中 superposed/conformable 记录（单元码序列）
    ∪ group_composition 群组成（成员码序列）——均先按统过滤再折算组码比对
    （组码跨统不唯一：w 见于 C1w/K2w/E2w，必须统域内匹配）；
    simultaneous/no_contact 不给方向（交 pending/overrides）。
    """
    cands = [rec.get("units", []) for rec in lib.order_records
             if rec.get("type") in ("superposed", "conformable")]
    cands += [[m["code"] for m in g["members"]] for g in lib.group_composition]
    for seq in cands:
        fg = []
        for x in seq:
            if not isinstance(x, str):
                continue
            parsed = _strata_parse(x)
            if parsed and parsed[0] == tong:
                fg.append(parsed[1])
        sub = [c for c in fg if c in groups]
        if len(sub) > 1 and set(sub) == set(groups):
            return sub
    return None


def _shade_slots(tong: str, n: int, lib: Lib) -> list[list[int]]:
    """默认组间分色槽：1 组统色；2 组 [统色, 最高阶]；n≥3 阶序列等距含两端。"""
    base = list(lib.fs[tong]["rgb"])
    stages = lib.stage_children(tong)
    if n == 1 or not stages:
        return [base] * n
    if n == 2:
        return [base, list(lib.fs[stages[-1]]["rgb"])]
    if n <= len(stages):
        idx = [round(i * (len(stages) - 1) / (n - 1)) for i in range(n)]
        return [list(lib.fs[stages[i]]["rgb"]) for i in idx]
    slots = [base] + [list(lib.fs[s]["rgb"]) for s in stages]
    return (slots + [slots[-1]] * n)[:n]


def _seg_shade(rgb, seg: int, n_seg: int):
    """段间分色（2026-10-03 泛化）：同组不同段赋色必须互异——按段序
    在 下段深(×0.90)↔上段浅(+30% 趋白) 间线性插值；n=2/3 与原
    dark/base/light 三档逐值一致（回归兼容）。"""
    if n_seg <= 1:
        return list(rgb)
    t = (seg - 1) / (n_seg - 1)
    if t < 0.5:
        k = 0.90 + t * 2 * 0.10
        return [round(c * k) for c in rgb]
    k = (t - 0.5) * 2 * 0.30
    return [round(c + (255 - c) * k) for c in rgb]


def _strata_parse(norm: str):
    """→ (统键, 组码, 段号|None, 跨系键|None)；不可解析 None。"""
    m = _CROSS_SYS_RE.match(norm)
    if m and f"{m.group(1)}{m.group(3)}" in _CROSS_CODES:
        return None, m.group(5), None, f"{m.group(1)}{m.group(3)}"
    m = _ERA_RE.match(norm)
    if not m or not m.group(2):
        return None
    tong = f"{m.group(1)}{m.group(2)}"
    rest = m.group(3) or ""
    fm = re.match(r"^(.*?)(\d+)$", rest)
    if fm and fm.group(1):
        return tong, fm.group(1), int(fm.group(2)), None
    return tong, rest, None, None


def generate(sheet: str, lib: Lib | None = None,
             overrides: dict | None = None,
             source: str = "lite") -> tuple[dict, list[dict], list[dict]]:
    """生成映射 + 逐单元报告行 + pending 行。overrides={norm: {rgb?, pattern_ref?}}。
    source: "lite"=GeoSciML 视图语义源（默认，F1 解耦）；"wp"=MapGIS 引导回退。"""
    lib = lib or Lib()
    cfg = SHEETS[sheet]
    units = read_lite_units(sheet) if source == "lite" else read_sheet_units(sheet)
    overrides = overrides or {}

    # ① 逐单元基础取色
    specs: dict[str, StyleSpec] = {}
    for u in units:
        nm = u.norm
        spec = StyleSpec(cls="unknown")
        if nm.startswith("Q"):
            spec = _quat_spec(nm, lib)
        else:
            intr = _intr_spec(nm, lib) if u.role == "侵入岩" else None
            if intr is not None:
                spec = intr
            elif u.role == "变质岩":
                meta = _meta_spec(nm, lib)
                if meta is not None:
                    spec = meta
        if spec.rgb is None:
            parsed = _strata_parse(nm)
            if parsed and parsed[3]:  # 跨系
                code = parsed[3]
                e = lib.cross.get(code)
                if e:
                    spec = StyleSpec(rgb=list(e["base_rgb"]), cls="strata",
                                     src=f"表3 跨系 {code} 底色（网纹 draft 不上图）")
            elif parsed and parsed[0] and parsed[0] in lib.fs:
                spec = StyleSpec(rgb=list(lib.fs[parsed[0]]["rgb"]), cls="strata",
                                 src=f"统色 {parsed[0]}")
            if spec.rgb is None:
                # 界级基色回落（2026-10-02 Pt1K 案）：元古界/长城系岩群
                # 无统级编码——时代前缀 → 表2 system_base 基色
                spec = _era_base_spec(nm, lib) or spec
        specs[nm] = spec

    # ② 组间分色（同统多组）
    by_tong: dict[str, list[UnitInput]] = {}
    for u in units:
        # 沉积地层角色判定（2026-10-03 J2t/J2y 案）：角色分类体系含
        # 「沉积地层」（库尔干）与「沉积岩建造」（125万数据库）两系——
        # 原 endswith('沉积地层') 为死过滤致组间分色整体旁路
        if specs[u.norm].cls != "strata" or not (u.role and "沉积" in u.role):
            continue
        parsed = _strata_parse(u.norm)
        if parsed and parsed[0] and not parsed[3]:
            by_tong.setdefault(parsed[0], []).append(u)
    for tong, us in by_tong.items():
        groups = sorted({(_strata_parse(u.norm)[1] or "") for u in us})
        if len(groups) <= 1:
            continue
        norms_by_group = {g: sorted(u.norm for u in us
                                    if (_strata_parse(u.norm)[1] or "") == g)
                          for g in groups}
        order = _order_groups(tong, groups, lib)
        if order is None:
            slot_order = sorted(groups)  # 确定性占位（码序），交 pending
            slots = _shade_slots(tong, len(groups), lib)
            for g, rgb in zip(slot_order, slots):
                for nm in norms_by_group[g]:
                    specs[nm].rgb = list(rgb)
                    specs[nm].pending = (f"{tong} 组间层序证据不足：占位分色"
                                         f"（码序 {slot_order}，方向未定）")
                    specs[nm].src += f"；{tong} 组间分色·占位（层序 pending）"
        else:
            slots = _shade_slots(tong, len(order), lib)
            for g, rgb in zip(order, slots):
                for nm in norms_by_group[g]:
                    specs[nm].rgb = list(rgb)
                    specs[nm].src += f"；{tong} 组间分色（{'>'.join(order)}，老深新浅）"

    # ③ 段间分色（自动探测同组多段）
    by_formation: dict[str, list[tuple[str, int]]] = {}
    for u in units:
        if specs[u.norm].cls != "strata":
            continue
        parsed = _strata_parse(u.norm)
        if parsed and parsed[2] is not None and not parsed[3]:
            by_formation.setdefault(f"{parsed[0]}{parsed[1]}", []).append(
                (u.norm, parsed[2]))
    for fm, mems in by_formation.items():
        if len(mems) < 2:
            continue
        n_seg = max(s for _, s in mems)
        for nm, seg in mems:
            specs[nm].rgb = _seg_shade(specs[nm].rgb, seg, n_seg)
            specs[nm].src += f"；段间分色 {seg}/{n_seg} 段（下段深、上段浅）"

    # ③b 界级基色多单元分色（2026-10-02 用户裁定：相同地质年代号的不同
    # 地层赋色要有区别——ChA/ChSt 型同界基色碰撞须分色；层序未定时
    # 码序占位（下段深上段浅同构 _seg_shade，占位标注待裁定）
    era_groups: dict[str, list[str]] = {}
    for u in units:
        if specs[u.norm].cls != "strata_base":
            continue
        _key = specs[u.norm].src.rsplit(" ", 1)[-1]
        era_groups.setdefault(_key, []).append(u.norm)
    for _ek, _norms in era_groups.items():
        if len(_norms) < 2:
            continue
        for i, _nm in enumerate(sorted(_norms), 1):
            specs[_nm].rgb = _seg_shade(specs[_nm].rgb, i, len(_norms))
            specs[_nm].src += (f"；同界分色 {i}/{len(_norms)}"
                               f"（码序占位，层序待裁定）")
            specs[_nm].pending = specs[_nm].pending or (
                f"同界基色多单元（{_ek}）——码序占位分色，层序待裁定")

    # ④ overrides 裁定层（应用即登记）
    from dataclasses import replace as _dc_replace

    from pymapgis.semantics.confidence import evaluate

    def _style_conf(nm, spec, overridden):
        """统一框架影子评价（T7 映射；report 侧三列，mapping JSON 不动）。"""
        if overridden:
            return evaluate("adjudicated", adjudicated=True,
                            reasons=("override 裁定",))
        if spec.rgb is None:
            bd = evaluate("code_read", "single", 1.0, counterexample_open=True,
                          reasons=(spec.pending or "未分类",))
            return _dc_replace(bd, band="pending")
        if spec.pending:  # 占位分色/draft 花纹/成因未命中
            bd = evaluate("code_read", "single", 1.0, counterexample_open=True,
                          reasons=(spec.pending,))
            return _dc_replace(bd, band="pending")
        return evaluate("verified", "multi_root", 1.0,
                        reasons=(spec.src,))  # D3：色库查表断言 I=1.0

    report: list[dict] = []
    pending: list[dict] = []
    for u in units:
        nm = u.norm
        spec = specs[nm]
        src = spec.src or "!! 未分类"
        flags = []
        if nm in overrides:
            ov = overrides[nm]
            if ov.get("rgb"):
                spec.rgb = list(ov["rgb"])
            if "pattern_ref" in ov:
                spec.pattern_ref = ov["pattern_ref"]
            flags.append(f"override（{ov.get('basis', 'adjudicated')}）")
            src = f"override：{ov.get('note', '')}" or src
            # 裁定消解型 pending：占位/层序/未分类 由 override 给出定论→清除
            if any(k in spec.pending for k in ("占位", "层序", "未分类")):
                spec.pending = ""
        if spec.rgb is None:
            spec.pending = spec.pending or "未分类（无规则命中）"
            # 新幅首接教训（2026-09-29 奥依亚依拉克）：未分类单元被丢弃致
            # build 断链——改确定性占位灰 + pending（与组间占位同哲学：
            # 占位=明确标记的临时态，非猜色；裁定经 overrides/pending 闭环；
            # 库尔干/英吉沙 0 未分类单元，本分支不触发→逐字节一致保持）
            spec.rgb = [235, 235, 235]
        if spec.pending:
            flags.append("pending")
            pending.append({"norm": nm, "name": u.name, "src_file": u.src_file,
                            "reason": spec.pending})
        report.append({"raw": u.raw_code, "norm": nm, "name": u.name,
                       "src_file": u.src_file, "rgb": spec.rgb,
                       "pattern_ref": spec.pattern_ref, "src": src,
                       "flags": flags, "cls": spec.cls,
                       "conf": _style_conf(nm, spec, nm in overrides)})

    # ⑤ 组装映射文件（骨架深拷贝，units 替换）；新幅首接无骨架→最小模板
    skel_p = Path(cfg["skeleton"])
    # 无骨架回退（2026-10-02 jwss 泛化测试）：界线线样式属 DZ/T 0179 标准
    # （地质界线 GZBD 色/宽/线型——图幅无关），并入包标准默认；骨架存在时
    # 以骨架为准（图幅裁定层优先）
    skel = (json.loads(skel_p.read_text(encoding="utf-8")) if skel_p.exists()
            else {"polygon_layers": {}, "line_layers": STANDARD_LINE_LAYERS,
                  "_meta": {}})
    out = json.loads(json.dumps(skel))
    for f in POLY_FILES:
        layer_units = {}
        for r in report:
            if r["src_file"] != f or r["rgb"] is None:
                continue
            e = {"norm": r["norm"], "name": r["name"], "rgb": r["rgb"]}
            if r["pattern_ref"]:
                e["pattern_ref"] = r["pattern_ref"]
            layer_units[r["raw"]] = e
        out["polygon_layers"][f] = {
            "role": ROLES[f], "code_field": "QDUECC", "name_field": "QDUECD",
            "units": layer_units,
        }
    for _pf, _prole in _PLACEHOLDER_LAYERS.items():
        out["polygon_layers"].setdefault(_pf, {
            "role": _prole, "code_field": "QDUECC", "name_field": "QDUECD",
            "units": {},
        })
    out["_meta"] = {
        "title": f"{cfg['sheet_title']}地质单元配色映射（语义生成 · DZ/T 0179-2025 色库）",
        "scale": "1:250000",
        "standard": "DZ/T 0179-2025",
        "color_source": "data/dzt0179_color_library.json + geosciml_render/stylegen.py",
        "created": "2026-09-27",
        "generator": "geosciml_render.stylegen（语义→样式；overrides 裁定层见 "
                     f"{cfg['overrides'].name}）",
        "supersedes": (Path(cfg['skeleton']).name + "（手写规则版，保留供对账）")
                      if skel_p.exists() else "（新幅首接，无骨架）",
    }
    return out, report, pending


def load_overrides(sheet: str) -> dict:
    p = SHEETS[sheet]["overrides"]
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return doc.get("overrides", {})


def diff_styles(generated: dict, reference: dict) -> list[dict]:
    """生成 vs 参照（生产映射）逐单元对账：rgb / pattern_ref 差异。"""
    rows = []
    for f in POLY_FILES:
        gu = (generated["polygon_layers"].get(f) or {}).get("units", {})
        ru = (reference["polygon_layers"].get(f) or {}).get("units", {})
        for raw in sorted(set(gu) | set(ru)):
            g, r = gu.get(raw), ru.get(raw)
            if g is None:
                rows.append({"raw": raw, "src_file": f, "kind": "生成缺失",
                             "norm": (r or {}).get("norm")})
                continue
            if r is None:
                rows.append({"raw": raw, "src_file": f, "kind": "生成多余",
                             "norm": g.get("norm")})
                continue
            diffs = []
            if g.get("rgb") != r.get("rgb"):
                diffs.append(f"rgb {r.get('rgb')}→{g.get('rgb')}")
            gp = g.get("pattern_ref") or {}
            rp = r.get("pattern_ref") or {}
            if (gp.get("family"), gp.get("code")) != (rp.get("family"), rp.get("code")):
                diffs.append(f"pattern_ref {rp or None}→{gp or None}")
            if diffs:
                rows.append({"raw": raw, "src_file": f, "kind": "差异",
                             "norm": g.get("norm"), "diff": "；".join(diffs)})
    return rows


def write_outputs(sheet: str, mapping: dict, report: list[dict],
                  pending: list[dict]) -> None:
    cfg = SHEETS[sheet]
    cfg["out"].parent.mkdir(parents=True, exist_ok=True)
    cfg["out"].write_text(json.dumps(mapping, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    lines = [f"# {cfg['sheet_title']}语义生成样式报告（stylegen 2026-09-27）",
             "",
             f"单元 {len(report)}；pending {len(pending)}；"
             f"override {sum(1 for r in report if any('override' in f for f in r['flags']))}",
             "",
             "| 文件 | 码 | norm | 名称 | rgb | 花纹 | 规则来源 | C | band | 标记 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(report, key=lambda x: (x["src_file"], x["raw"])):
        pat = (f"{r['pattern_ref']['family']}.{r['pattern_ref']['code']}"
               if r["pattern_ref"] else "")
        lines.append(f"| {r['src_file']} | {r['raw']} | {r['norm']} | {r['name']} "
                     f"| {r['rgb']} | {pat} | {r['src']} | {r['conf'].C:.2f} "
                     f"| {r['conf'].band} | {'；'.join(r['flags'])} |")
    if pending:
        lines += ["", "## pending（交人工裁定）", ""]
        for p in pending:
            lines.append(f"- **{p['norm']}**（{p['name']}，{p['src_file']}）：{p['reason']}")
    cfg["report"].write_text("\n".join(lines), encoding="utf-8")


def seed_overrides(sheet: str, diffs: list[dict], reference: dict) -> Path:
    """把 diff 单元以骨架（生产映射）值播种进 overrides（basis=裁定转录）。"""
    cfg = SHEETS[sheet]
    doc = {"_meta": {"title": f"{cfg['sheet_title']}样式 overrides 裁定层",
                     "created": "2026-09-27",
                     "note": "stylegen 生成默认值之上的裁定覆盖；播种自生产映射"
                             "（2026-09-19 用户裁定），后续裁定追加于此后"},
           "overrides": {}}
    p = cfg["overrides"]
    if p.exists():
        doc = json.loads(p.read_text(encoding="utf-8"))
    ref_units = {}
    for f in POLY_FILES:
        for raw, u in (reference["polygon_layers"].get(f, {}).get("units", {}) or {}).items():
            ref_units[u.get("norm")] = u
    n = 0
    for d in diffs:
        nm = d.get("norm")
        if not nm or nm not in ref_units:
            continue
        ru = ref_units[nm]
        ov = doc["overrides"].get(nm, {})
        ov["rgb"] = ru.get("rgb")
        if ru.get("pattern_ref"):
            ov["pattern_ref"] = ru["pattern_ref"]
        ov.setdefault("note", "播种自生产映射（2026-09-19 裁定版）")
        ov.setdefault("basis", "adjudicated 2026-09-19")
        doc["overrides"][nm] = ov
        n += 1
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"overrides 播种 {n} 单元 → {p}")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(prog="geosciml_render.stylegen")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()], required=True)
    ap.add_argument("--from-wp", action="store_true",
                    help="引导回退：语义源改读 MapGIS WP（新幅冷启动，lite 未建时）")
    ap.add_argument("--diff", action="store_true", help="与骨架（生产映射）对账")
    ap.add_argument("--seed-overrides", action="store_true",
                    help="先 diff，差异单元以骨架值播种 overrides 后重新生成")
    args = ap.parse_args()
    cfg = SHEETS[args.sheet]
    lib = Lib()
    src = "wp" if args.from_wp else "lite"

    overrides = load_overrides(args.sheet)
    mapping, report, pending = generate(args.sheet, lib, overrides, source=src)
    write_outputs(args.sheet, mapping, report, pending)
    print(f"生成: {cfg['out']}（源={src}，单元 {len(report)}，pending {len(pending)}，"
          f"override {sum(1 for r in report if any('override' in f for f in r['flags']))}）")

    if args.diff or args.seed_overrides:
        skel = json.loads(Path(cfg["skeleton"]).read_text(encoding="utf-8"))
        diffs = diff_styles(mapping, skel)
        print(f"对账 vs {Path(cfg['skeleton']).name}: 差异 {len(diffs)} 单元")
        for d in diffs:
            print(f"  [{d['kind']}] {d.get('norm')} ({d['src_file']}): {d.get('diff', '')}")
        if args.seed_overrides and diffs:
            seed_overrides(args.sheet, diffs, skel)
            overrides = load_overrides(args.sheet)
            mapping, report, pending = generate(args.sheet, lib, overrides,
                                                source=src)
            write_outputs(args.sheet, mapping, report, pending)
            diffs2 = diff_styles(mapping, skel)
            print(f"播种后重生成: 差异 {len(diffs2)} 单元"
                  + (f"（残余: {[d.get('norm') for d in diffs2]}）" if diffs2 else "（归零）"))
    if pending:
        print("pending:")
        for p in pending:
            print(f"  {p['norm']}（{p['name']}）: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
