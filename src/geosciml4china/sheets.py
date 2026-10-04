"""图幅（sheet）注册表——包内唯一图幅参数源。

一个**图幅项目** = 磁盘上一个目录（sheet root），按约定承载：

```
<root>/
  geojson/L1/                    语义标定 L1 层（转换输入）
  output/geosciml/               转换与渲染产出（GML/lite/style…）
  data/ 或 <root>/               图幅级词表映射/裁定层/登记册
  *.wl/*.wt/*.wp                 MapGIS 矢量（stylegen 直读）
```

解析优先级（高→低）：

1. 环境变量 ``G4C_ROOT_<KEY>``（仅覆盖 root）；
2. 用户配置 ``./geosciml4china.toml`` → ``~/.geosciml4china.toml``
   （``[sheets.<key>]`` 任意 Sheet 字段可覆盖）；
3. 包内注册的开发图幅默认（kurgan/yingjisha，本机路径，可被 1/2 覆盖）。

路径字段分两类：**规则名**按约定候选清单自动发现（存在即取）；
**不规则名**（历史文件名，如 aux 三联体表）在注册条目里显式给相对路径。
所有 Path 绑定不触盘——未安装图幅数据的机器上 import 安全。
"""
from __future__ import annotations

import os
# tomllib 为 3.11+ 标准库；3.10 回退 tomli（2026-10-04 CI 矩阵修复——
# 3.10 job 直接 ImportError 收集失败）
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

# --- 用户配置文件 ------------------------------------------------------------
_USER_CONFIG_CANDIDATES = (
    Path.cwd() / "geosciml4china.toml",
    Path.home() / ".geosciml4china.toml",
)


@dataclass(frozen=True)
class Sheet:
    """一幅 1:25 万（或其他比例尺）建造构造图的全部参数。"""
    key: str                        # 短名："kurgan"
    code: str                       # 图幅号："J43C001002"
    title: str                      # 图名
    root: Path                      # 图幅项目根
    # --- 验收画像 ---
    expected_units: Optional[int] = None            # 色库单元数断言
    expected_polygon_dist: Optional[dict] = None    # 面图层文件分布闸
    lite_expect_counts: Optional[tuple] = None      # 渲染镜像期望 (unit/contact/sds/fol)
    # --- 不规则文件名（相对 root；None=该幅无此项） ---
    aux_pairs_csv: Optional[str] = None
    aux_assoc_csv: Optional[str] = None
    aux_triplets_csv: Optional[str] = None
    calibration_csv: Optional[str] = None
    # --- 命名空间 ---
    base_uri: str = ""              # 空 → f"{NAMESPACE_PLACEHOLDER}/{code}/"

    # ---------- 恒量（图幅无关） ----------
    SCALE_DENOMINATOR: int = 250000

    # ---------- 约定派生路径（规则名，自动发现） ----------
    @property
    def geojson_l1(self) -> Path:
        return self.root / "geojson" / "L1"

    @property
    def out_dir(self) -> Path:
        return self.root / "output" / "geosciml"

    @property
    def lite_out(self) -> Path:
        return self.out_dir / "lite"

    @property
    def gml_out(self) -> Path:
        return self.out_dir / f"{self.key}_geosciml_full.gml"

    @property
    def pending_out(self) -> Path:
        return self.out_dir / "pending_review.md"

    @property
    def report_out(self) -> Path:
        return self.out_dir / "reconciliation_report.md"

    @property
    def style_generated(self) -> Path:
        return self.out_dir / f"{self.key}_style_generated.json"

    @property
    def style_report(self) -> Path:
        return self.out_dir / f"{self.key}_style_report.md"

    @property
    def fault_styles_generated(self) -> Path:
        return self.out_dir / f"{self.key}_fault_styles_generated.json"

    @property
    def render_out(self) -> Path:
        return self.out_dir / f"{self.key}_geosciml_render.pdf"

    def _first(self, *cands: Path) -> Optional[Path]:
        for c in cands:
            if c.exists():
                return c
        return cands[0] if cands else None  # 都不存在→回退首选（报错信息可读）

    # 图幅级数据文件：data/ 优先，root 兜底（两幅历史布局差异即此二分）
    @property
    def vocab_mapping(self) -> Path:
        return self._first(self.root / "data" / "geosciml_vocab_mapping.json",
                           self.root / f"geosciml_vocab_mapping_{self.key}.json",
                           self.root / "geosciml_vocab_mapping.json")

    @property
    def style_overrides(self) -> Path:
        return self._first(self.root / "data" / f"style_overrides_{self.key}.json",
                           self.root / f"style_overrides_{self.key}.json")

    @property
    def fault_style_overrides(self) -> Path:
        return self._first(self.root / "data" / f"fault_style_overrides_{self.key}.json",
                           self.root / f"fault_style_overrides_{self.key}.json")

    @property
    def style_skeleton(self) -> Path:
        return self._first(
            self.root / "data" / f"geological_unit_color_mapping_{self.key}_dzt0179.json",
            self.root / f"geological_unit_color_mapping_{self.key}_dzt0179.json")

    @property
    def handauth_fault_styles(self) -> Path:
        return self._first(self.root / "data" / "fault_rendering_styles.json",
                           self.root / f"fault_rendering_styles_{self.key}.json")

    @property
    def aux_semantics_json(self) -> Path:
        return self._first(self.root / "data" / "fault_aux_code_semantics.json",
                           self.root / "fault_aux_code_semantics.json")

    @property
    def unit_to_ics(self) -> Optional[Path]:
        p = self.root / "data" / "unit_to_ics_candidate.json"
        return p if p.exists() else None

    @property
    def age_table_csv(self) -> Optional[Path]:
        p = self.root / "data" / "stratigraphic_geologic_age_table.csv"
        return p if p.exists() else None

    # 不规则名：显式字段 → 绝对路径
    def _rel(self, rel: Optional[str]) -> Optional[Path]:
        return (self.root / rel) if rel else None

    @property
    def aux_pairs(self) -> Optional[Path]:
        return self._rel(self.aux_pairs_csv)

    @property
    def aux_assoc(self) -> Optional[Path]:
        return self._rel(self.aux_assoc_csv)

    @property
    def aux_triplets(self) -> Optional[Path]:
        return self._rel(self.aux_triplets_csv)

    @property
    def calibration(self) -> Optional[Path]:
        return self._rel(self.calibration_csv)

    @property
    def wp_dir(self) -> Path:
        return self.root


# --- 包内注册的开发图幅（root 可被环境变量/用户配置覆盖） ---------------------
_REGISTRY: dict[str, Sheet] = {}


def _register_defaults() -> None:
    _REGISTRY.setdefault("kurgan", Sheet(
        key="kurgan", code="J43C001002",
        title="库尔干幅(J43C001002)1:250000建造构造图",
        root=Path(r"D:\JWD"),
        expected_units=57,
        expected_polygon_dist={"LDZOFBB001.WP": 608, "LDZOFBB002.WP": 10,
                               "LDZOFBB003.WP": 46, "LDZOFBB004.WP": 49},
        lite_expect_counts=(713, 1316, 310, 305),
        aux_pairs_csv="fault_aux_number_1894_pairs.csv",
        aux_assoc_csv="fault_aux_point_association.csv",
        aux_triplets_csv="_fault_triplets_detail.csv",
        calibration_csv="_gzbd_calibration_report.csv",
    ))
    _REGISTRY.setdefault("yingjisha", Sheet(
        key="yingjisha", code="J43C002003",
        title="英吉沙幅(J43C002003)1:250000建造构造图",
        root=Path(r"D:\J43C002003新疆英吉沙县\J43C002003\MAPGIS\JWD"),
        expected_units=95,
        expected_polygon_dist={"LDZOFBB001.WP": 524, "LDZOFBB002.WP": 1,
                               "LDZOFBB003.WP": 192, "LDZOFBB004.WP": 91},
        lite_expect_counts=(808, 1199, 289, 165),
        aux_pairs_csv="fault_aux_number_1851_pairs.csv",
        aux_assoc_csv="fault_aux_yingjisha.csv",
        aux_triplets_csv="_fault_triplets_yingjisha.csv",
        calibration_csv="_gzbd_calibration_report.csv",
    ))
    # 奥依亚依拉克 J45C004001（2026-09-29 新幅接入）：aux 三表/标定报告待
    # 接入审计建立（当前缺省→相关装配自动降级）；EXPECTED_UNITS=None
    # （首接基线，待 units 实测核定）；面分布=L0 实测（本幅无 LDZOFBB002.WP）
    _REGISTRY.setdefault("aoyiyayilake", Sheet(
        key="aoyiyayilake", code="J45C004001",
        title="奥依亚依拉克幅(J45C004001)1:250000建造构造图",
        root=Path(r"D:\J45C004001新疆奥依亚依拉克\J45C004001\MAPGIS\JWD"),
        expected_units=58,  # 2026-09-29 build 实测核定（60 原码 norm 归一后 58）
        expected_polygon_dist={"LDZOFBB001.WP": 417, "LDZOFBB003.WP": 110,
                               "LDZOFBB004.WP": 16},
        lite_expect_counts=(543, 734, 341, 406),  # 09-29 实测（10/81 skip 后 734）
        aux_pairs_csv="fault_aux_number_1894_pairs.csv",
        aux_assoc_csv="fault_aux_aoyiyayilake.csv",
        aux_triplets_csv="_fault_triplets_aoyiyayilake.csv",
        calibration_csv="_gzbd_calibration_report.csv",
    ))
    # 巴什库尔干 J46C001001（2026-09-29 第二幅新幅）：EXPECTED_*/画像待
    # build 实测核定后回填；aux 无倾角注释类别（断层注记=断层名标签）——
    # pairs 通道空置、倾角走 GZECE 回落；BB002/009 缺、含中文名面层
    _REGISTRY.setdefault("bashkurgan", Sheet(
        key="bashkurgan", code="J46C001001",
        title="巴什库尔干幅(J46C001001)1:250000建造构造图",
        root=Path(r"D:\ts\JWD"),
        expected_units=40,           # 2026-09-29 build 实测核定
        expected_polygon_dist={"LDZOFBB001.WP": 72, "LDZOFBB003.WP": 151,
                               "LDZOFBB004.WP": 180},
        lite_expect_counts=(403, 546, 213, 262),
        aux_pairs_csv="fault_aux_number_1894_pairs.csv",
        aux_assoc_csv="fault_aux_bashkurgan.csv",
        aux_triplets_csv="_fault_triplets_bashkurgan.csv",
        calibration_csv="_gzbd_calibration_report.csv",
    ))


def _apply_user_config(sh: Sheet) -> Sheet:
    """用户 TOML 覆盖（[sheets.<key>] 字段级）。"""
    for cfg in _USER_CONFIG_CANDIDATES:
        if not cfg.exists():
            continue
        try:
            doc = tomllib.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue
        ent = (doc.get("sheets") or {}).get(sh.key) or {}
        if not ent:
            continue
        if "root" in ent:
            ent["root"] = Path(ent["root"])
        if ent.get("lite_expect_counts"):
            ent["lite_expect_counts"] = tuple(ent["lite_expect_counts"])
        sh = replace(sh, **{k: v for k, v in ent.items() if hasattr(sh, k)})
    return sh


def _apply_env(sh: Sheet) -> Sheet:
    v = os.environ.get(f"G4C_ROOT_{sh.key.upper()}")
    return replace(sh, root=Path(v)) if v else sh


_register_defaults()


def get_sheet(key: str = "kurgan") -> Sheet:
    """按短名取图幅参数（用户配置与环境变量已施加；TOML 新增幅可取）。"""
    sh = _REGISTRY.get(key)
    if sh is None:
        sh = _toml_defined_sheets().get(key)
    if sh is None:
        raise KeyError(f"unknown sheet {key!r}（已注册 {list(_REGISTRY)}；"
                       f"新图幅请用 register_sheet 或 geosciml4china.toml）")
    return _apply_env(_apply_user_config(sh))


def _toml_defined_sheets() -> dict:
    """TOML 新增图幅（文档承诺「持久化请写 geosciml4china.toml」的落实，
    2026-10-02 修复：此前 TOML 只能覆盖内置幅、不能新增）。"""
    out = {}
    for cfg in _USER_CONFIG_CANDIDATES:
        if not cfg.exists():
            continue
        try:
            doc = tomllib.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key, ent in (doc.get("sheets") or {}).items():
            if key in _REGISTRY or key in out:
                continue  # 内置注册优先；多配置文件首个优先
            try:
                root = Path(ent["root"])
                code = str(ent.get("code") or "")
            except (KeyError, TypeError):
                continue
            if not code:
                continue
            out[key] = Sheet(
                key=key, code=code,
                title=str(ent.get("title") or code),
                root=root,
                expected_units=ent.get("expected_units"),
                expected_polygon_dist=ent.get("expected_polygon_dist"),
                lite_expect_counts=(tuple(ent["lite_expect_counts"])
                                    if ent.get("lite_expect_counts") else None),
                aux_pairs_csv=ent.get("aux_pairs_csv"),
                aux_assoc_csv=ent.get("aux_assoc_csv"),
                aux_triplets_csv=ent.get("aux_triplets_csv"),
                calibration_csv=ent.get("calibration_csv"),
                base_uri=str(ent.get("base_uri") or ""))
    return out


def register_sheet(sh: Sheet) -> None:
    """注册新图幅（运行时；持久化请写 geosciml4china.toml）。"""
    _REGISTRY[sh.key] = sh


def list_sheets() -> list[Sheet]:
    keys = list(_REGISTRY) + [k for k in _toml_defined_sheets()
                              if k not in _REGISTRY]
    return [get_sheet(k) for k in keys]
