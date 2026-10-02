"""语义标识派生（2026-10-02 用户裁定「geosciml 完全基于地质语义建模，不应
保留原 mapgis 中的图元 id 信息」）——build（发射）与 verify（重算）同源。

id 方案（用户裁定）：
  · 断层段：sds.F085.1 / mf.F085.1（fault_id + 实体段序，seg_idx 升序）
  · 测量点：fp.F085.2（fault_id + 沿弧序，arc_s 排序；标签 F085测点②）
  · 接触：c.04.3（GZBD_eff 类型码 + 类内序）
  · 面元：mf.{norm}.{ord}；产状：fol.{host}.{ord}；标本：sp.{host}.{ord}
  · 褶皱：fold.{n}（全局行序）；水系：{_src_file}.{n}（弃 _src_id）

序号规则全部确定性与 L1 行序绑定（L1 物化确定性 + build 时效守卫）；
分支实体（F001/F002/F005/F013/F026）段序以 seg_idx 升序为准——本序号是
稳定标签而非链坐标（几何链遍历序对分支实体无良定义）。
"""
from __future__ import annotations

import re
from collections import Counter

from .model import _safe_ncname

RESERVED_NC_PREFIXES = ("c.", "fp.", "fold.", "fol.", "sds.", "gu.", "sp.",
                        "rel.", "rock.", "ge.", "mf.")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CONTACT_CODES = ("01", "02", "04", "11", "16", "24", "43", "60")  # 10/81 由 build 跳过

_NORM_RE = re.compile(r"^(?:c|fp|fold|fol|sds|gu|sp|rel|rock|ge|mf)\.|^F\d+|^\d\d")


def circled(n: int) -> str:
    """1..20 → ①..⑳；超限回退普通数字（断言级兜底，现幅最大 7/断层）。"""
    if 1 <= n <= len(_CIRCLED):
        return _CIRCLED[n - 1]
    return str(n)


def assert_no_norm_collisions(norms) -> None:
    """装载期守卫：单元 norm 撞保留前缀（c./fp./F\d+/纯数字）即 FAIL——
    否则语义 id 会与产品内其他类 id 冲突。四幅实测零冲突。"""
    for nm in norms:
        if nm and _NORM_RE.match(nm):
            raise AssertionError(
                f"单元 norm {nm!r} 与语义 id 保留前缀冲突（ids.RESERVED_NC_PREFIXES）")


def fault_seg_ordinals(faults_gdf) -> dict:
    """段行位（== _src_id）→ (fault_id, 1 基段序)。同 fault_id 按 seg_idx
    升序编号——与 fault_entities.csv 组内行序一致。"""
    out = {}
    for fid, sub in faults_gdf.groupby("fault_id", sort=False):
        for i, (_, row) in enumerate(sub.iterrows(), 1):
            out[int(row["_src_id"])] = (str(fid), i)
    return out


def sds_id(fault_id: str, seg_ord: int) -> str:
    return f"{fault_id}.{seg_ord}"


def measure_point_ids(fault_aux_gdf, auxchain_df, faults_gdf) -> dict:
    """aux_idx → {mp_id, fault_id, ord, label}。产品 b 点（kind=symbol、
    sub_no=1894、status normal、有 dip_az）按（段序，arc_s，dist_m，aux_idx）
    在实体域内排序编号；arc_s 取 fault_aux_<key>.csv（缺失回落
    seg_geom.project 弧位）。"""
    seg_of = fault_seg_ordinals(faults_gdf)
    arcs = {}
    if auxchain_df is not None and len(auxchain_df):
        for _, r in auxchain_df.iterrows():
            try:
                arcs[int(r["aux_idx"])] = float(r["arc_s"])
            except (TypeError, ValueError, KeyError):
                continue
    rows = []
    for _, r in fault_aux_gdf.iterrows():
        if (str(r.get("kind")) != "symbol"
                or int(float(r.get("sub_no") or 0)) != 1894
                or str(r.get("status") or "normal") not in ("normal", "")
                or r.get("dip_az") is None):
            continue
        aux = int(r["_src_id"])
        fid, sord = seg_of.get(int(r["seg_idx"]), (str(r.get("fault_id")), 0))
        arc = arcs.get(aux)
        if arc is None:
            seg_geom = faults_gdf.geometry.iloc[int(r["seg_idx"])]
            arc = seg_geom.project(r.geometry)
        rows.append((fid, sord, arc, float(r.get("dist_m") or 0.0), aux))
    out = {}
    by_fault: dict[str, list] = {}
    for row in rows:
        by_fault.setdefault(row[0], []).append(row)
    for fid, rs in by_fault.items():
        rs.sort(key=lambda x: (x[1], x[2], x[3], x[4]))
        for i, (f, sord, arc, dm, aux) in enumerate(rs, 1):
            out[aux] = {"mp_id": f"fp.{f}.{i}", "fault_id": f, "ord": i,
                        "label": f"{f}测点{circled(i)}"}
    return out


def contact_ids(boundaries_gdf) -> dict:
    """boundaries _src_id → "GZBD_eff.类内序"（L1 行序逐类计数；
    10/81/excluded 不占号——与 build 跳过口径一致）。"""
    out = {}
    cnt = Counter()
    for _, r in boundaries_gdf.iterrows():
        code = str(r.get("GZBD_eff") or "")
        if code not in CONTACT_CODES or str(r.get("status") or "normal") == "excluded":
            continue
        cnt[code] += 1
        out[int(r["_src_id"])] = f"{code}.{cnt[code]}"
    return out


def _norm_of(raw2norm, code: str) -> str:
    """raw2norm 为 dict（unit_mod.raw_to_norm_map() 返回映射）或可调用；
    未命中回落原码（build 侧另有 KeyError 闸，helper 不重复抛错）。"""
    try:
        v = raw2norm.get(code)
    except AttributeError:
        v = raw2norm(code)
    return v if v else code


def polygon_mf_ids(polygons_gdf, raw2norm) -> list:
    """与 gdf 行对齐的面元 MF feature_id（"norm.ord"；按 (norm, src_file)
    组内行序计数）。raw2norm: QDUECC 原码 → 单元 norm。"""
    out = [None] * len(polygons_gdf)
    cnt = Counter()
    for i, (_, r) in enumerate(polygons_gdf.iterrows()):
        norm = _norm_of(raw2norm, str(r.get("QDUECC") or ""))
        key = (norm, str(r.get("_src_file") or ""))
        cnt[key] += 1
        out[i] = f"{norm}.{cnt[key]}"
    return out


def foliation_ids(attitude_gdf, raw2norm) -> dict:
    """attitude _src_id → {host_norm, ord}（按 host 组内行序；host_code 不
    解析时回落 GZBBGA 原码）。"""
    out = {}
    cnt = Counter()
    for _, r in attitude_gdf.iterrows():
        host = (_norm_of(raw2norm, str(r.get("host_code") or ""))
                or str(r.get("GZBBGA") or ""))
        cnt[host] += 1
        out[int(r["_src_id"])] = {"host_norm": host, "ord": cnt[host]}
    return out


def fold_ids(fold_gdf) -> list:
    return [str(i) for i in range(1, len(fold_gdf) + 1)]


def specimen_ids(frames, raw2norm) -> dict:
    """(kind, 行位) → {host_norm, ord}。跨 fossil/mudvolcano 连续计数
    （共享宿主不撞号），build 顺序 = 化石在前。"""
    out = {}
    cnt = Counter()
    for kind, gdf in frames:
        for i, (_, r) in enumerate(gdf.iterrows()):
            host = _norm_of(raw2norm, str(r.get("host_code") or "")) or "sp"
            cnt[host] += 1
            out[(kind, i)] = {"host_norm": host, "ord": cnt[host]}
    return out


def water_ids(water_gdf, src_file_col="_src_file") -> list:
    """与 gdf 行对齐的水系透传 id（"_src_file.ord"，弃 _src_id）。"""
    out = [None] * len(water_gdf)
    cnt = Counter()
    for i, (_, r) in enumerate(water_gdf.iterrows()):
        src = str(r.get(src_file_col) or "water")
        cnt[src] += 1
        out[i] = f"{src}.{cnt[src]}"
    return out


def a_designation(a_ids: str) -> str:
    """"1675/1676" → "a①②"；"1675" → "a①"；空 → ""。"""
    parts = [p for p in str(a_ids).split("/") if p.strip()]
    if not parts:
        return ""
    return "a" + "".join(circled(i) for i in range(1, len(parts) + 1))
