"""geosciml4china 处理域契约（2026-09-29 用户裁定，固化入包）：只处理这 11 个 MapGIS 文件。

**这 11 个文件是《中国陆域 1:25 万分幅建造构造图空间数据库》明确指定的图层编号及名称**
（左群超等 2018 表 2 主图图层分层信息 + 图件整饰/标注层惯例）：

| zorder | 源文件 | 官方图层名称 | L1 主题 |
|---|---|---|---|
| 面元 (2) | LDZOFBB001.WP | 沉积岩建造图层（面） | polygons |
| 面元 (2) | LDZOFBB002.WP | 火山岩性岩相图层（面） | polygons |
| 面元 (2) | LDZOFBB003.WP | 侵入岩图层（面） | polygons |
| 面元 (2) | LDZOFBB004.WP | 变质岩建造图层（面） | polygons |
| 水系面 (5) | LDLYAAE002.WP | 主要面状水系图层（面） | waterpoly |
| 水系线 (9) | LDLYAAE001.WL | 主要线状水系图层（线） | waterline |
| 地质界线 (10) | LDZOFBA002.WL | 地质界线图层（线） | boundaries |
| 褶皱轴 (14) | LDZOFBA005.WL | 褶皱图层（线） | fold |
| 断层 (15) | LDZOFBA003.WL | 断裂图层（线） | faults |
| 辅助/化石/泥火山 (16/17) | LDZOFBB099.WT | 各类标注图层（点） | fault_aux/fossil/mudvolcano |
| 产状 (18) | LDZOFBA016.WT | 产状要素图层（点） | attitude |

其余图层文件（推断类 LYGREBA/LZLPGDJ/LHCPGDAC/LHTQGTA、同位素 FBA008、
变形构造 BB009/构造岩浆带 BB010/火山构造 BB011、火山岩性岩相.WP、
LFZY 火山/剖面类、BB008、BB098 等）一律不进入本包处理域。

**完备性分级**（预检语义，2026-09-29 定）：
- CORE（缺即中止）：地质界线/断裂/产状要素/各类标注/沉积岩建造——五层为建造构造图
  语义骨架，缺则管线无意义；
- CONDITIONAL（缺失=声明登记+继续）：火山岩性岩相/侵入岩/变质岩建造（按岩性分区在否）、
  褶皱、水系面/线（干旱区可无）、火山构造——缺失是合法图幅形态，但须显式声明。
"""
from __future__ import annotations

# 面元四文件（契约第 1 行；顺序=绘制序基底）
POLYGON_FILES = ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP", "LDZOFBB004.WP")
WATERPOLY_FILE = "LDLYAAE002.WP"
WATERLINE_FILE = "LDLYAAE001.WL"
BOUNDARY_FILE = "LDZOFBA002.WL"
FOLD_FILE = "LDZOFBA005.WL"
FAULT_FILE = "LDZOFBA003.WL"
ANNOTATION_FILE = "LDZOFBB099.WT"   # fault_aux + fossil + mudvolcano 三主题同源
ATTITUDE_FILE = "LDZOFBA016.WT"

SCOPE_FILES: frozenset = frozenset(
    (*POLYGON_FILES, WATERPOLY_FILE, WATERLINE_FILE, BOUNDARY_FILE,
     FOLD_FILE, FAULT_FILE, ANNOTATION_FILE, ATTITUDE_FILE))
assert len(SCOPE_FILES) == 11

# 图层地质语义（2026-09-29 用户对齐定版——最高级权威；与《中国陆域 1:25 万
# 分幅建造构造图空间数据库》表 2 一致；水系线/面同层同名、扩展名分线面）
OFFICIAL_LAYER_NAMES: dict[str, str] = {
    "LDZOFBB001.WP": "沉积岩建造图层",
    "LDZOFBB002.WP": "火山岩性岩相图层",   # 用户对齐定版（原 ROLES 旧标签
    # "补充沉积地层"废止；生产件更名随下次重生成生效）
    "LDZOFBB003.WP": "侵入岩图层",
    "LDZOFBB004.WP": "变质岩建造图层",
    "LDLYAAE002.WP": "水系图层（面）",
    "LDLYAAE001.WL": "水系图层（线）",
    "LDZOFBA002.WL": "地质界线图层",
    "LDZOFBA005.WL": "褶皱图层",
    "LDZOFBA003.WL": "断裂图层",
    "LDZOFBB099.WT": "注记图层",
    "LDZOFBA016.WT": "产状要素图层",
}

# 完备性分级（CORE 缺即中止；CONDITIONAL 缺失=声明登记+继续）
CORE_FILES: frozenset = frozenset({
    "LDZOFBA002.WL",   # 地质界线
    "LDZOFBA003.WL",   # 断裂
    "LDZOFBA016.WT",   # 产状要素
    "LDZOFBB099.WT",   # 各类标注（aux/化石/注记载体）
    "LDZOFBB001.WP",   # 沉积岩建造（主面层）
})
CONDITIONAL_FILES: frozenset = SCOPE_FILES - CORE_FILES

# L1 主题 → 契约内源文件（材料化溯源断言用）
THEME_SOURCES = {
    "polygons": POLYGON_FILES,
    "waterpoly": (WATERPOLY_FILE,),
    "waterline": (WATERLINE_FILE,),
    "boundaries": (BOUNDARY_FILE,),
    "fold": (FOLD_FILE,),
    "faults": (FAULT_FILE,),
    "fault_aux": (ANNOTATION_FILE,),
    "fossil": (ANNOTATION_FILE,),
    "mudvolcano": (ANNOTATION_FILE,),
    "attitude": (ATTITUDE_FILE,),
}
