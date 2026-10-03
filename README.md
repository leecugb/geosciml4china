# geosciml4china

**Self-supporting geological-semantics calibration and GeoSciML 4.1 interoperability for China's 1:250,000 regional geological map sheets.**

`geosciml4china` turns a legacy MapGIS project folder into trustworthy, confidence-graded geological semantics: **MapGIS → L0 GeoJSON → self-supporting semantic calibration → semantic L1 GeoJSON → GeoSciML 4.1 → semantics-driven rendering**, with every stage machine-verifiable (scope ruling 2026-09-29: input = the MapGIS project document folder).

![Semantics-driven render crop of the jws test case (Kurgan sheet J43C001002)](docs/images/jws_render_crop.svg)

*Render crop of the published [jws test case](data/jws_l0_geojson/README.md): calibrated strata polygons in DZ/T 0179-2025 colors, geological boundaries (incl. GZBD 04/24 unconformity double-lines), fault lines with decorations and fault attitude measurement points (a–b–a composite semantics).*

## The problem

China's 1:250,000 geological map archives (729 map sheets covering the land area; Zuo et al., 2018) were digitized under a unified national code system (DZ/T 0179 symbology, DD2006-06 database specification), yet the *data* systematically deviates from the *specification*, and the dictionary needed to interpret the deviations is not publicly available. We observe four independent dimensions of drift:

- **code values** — sheets introduce undocumented codes (e.g. Yingjisha J43C002003: four new fault codes on 83/289 segments, 29% of that sheet's faults);
- **sub-number double meanings** — sub-type 1894 means *fault dip direction* on Kurgan but *fold auxiliary* on Yingjisha;
- **reversed angle conventions** — 1894 uses a 0° convention, 1851 a 180° convention;
- **category renaming** — the same point class appears under different names across sheets.

The specification layer is uniform, the data layer is divergent, and the dictionary is missing. Schema matching assumes two formal specifications; map QA checks geometry only; conversion implementations assume the codes are already meaningful. To our knowledge, **semantic recovery of legacy map codes without the dictionary** is not addressed by any of these lines of work — including recent knowledge-graph efforts over Chinese vector maps, which all start from known field meanings (Qiu et al., 2024; Duan et al., 2024). Every sheet therefore carries a calibration debt that cannot be discharged by lookup, only by evidence from the map itself.

## The approach: self-supporting semantic calibration

Calibration proceeds from the map's own evidence — geometric invariants, spatial topology, and cross-channel corroboration — under four governing principles:

1. **Generalization** — rule code has zero sheet-specific branches; sheet-specific values (character distances, exemptions, code-semantics registries) live in sheet profiles and registries.
2. **MLE voting** — code semantics are assigned by a maximum-likelihood vote (code prior 3 / name 2 / signature 2 / kinematics 2 / dip 1 / auxiliary points 2 / cover 2; ties go to the prior; <2 votes fall back to the generic class).
3. **Pipeline integrity** — fallback mechanisms keep the chain running (unresolvable codes → general fault + detailed archive).
4. **Contradiction preservation** — evidence conflicts never auto-rewrite codes; they are registered pending human adjudication, and adjudications take effect through an overrides layer while the original vectors remain untouched.

Seven calibration domains each carry an independent verification path: boundary semantics (GZBD, adaptive 40/100/250 m flanking-unit probes), fault kinematics in three dimensions (GZEEB, incl. activity strong-priors via polygon-topology and fault-contact boundary audits), fault aux-point chains (distance bands with median-nearest preference, a–b/a–b–a patterns, strike-slip hook pairs with interval semantics), attitudes (strike⊥dip hard invariant), fossils/mud volcanoes, fault entity grouping, and inferred faults. Every verdict carries a confidence grade from the unified S×I×F framework (source tier × evidence independence × fit; bands: verified / consistent / suspect / conflict), which gates rendering and GeoSciML consumption. Closed-loop adjudication also repairs encoding defects of the data itself — discovered, attributed, ruled, applied via the overrides layer, and re-checked.

## Evidence

- **Full-sheet calibration on Kurgan (J43C001002)**: 2222 boundary segments, 310 fault segments, 299 fault aux points, 305 attitudes, 78=78 annotation pairing — all verified at full scale.
- **External anchor**: the calibrated layer set is 100% consistent with the official 《成矿地质背景研究数据模型》 data-model system (Zuo et al., 2018, *Geology in China* 45(S1):1–26, doi:10.12029/gc2018Z101).
- **Knowledge generation, not only correction**: on Yingjisha, the discriminator generated a testable semantic hypothesis for an unregistered code (code 03 ↔ GZELD=102, a perfect 38:38 one-to-one correspondence, consistent with a normal fault).
- **GeoSciML compliance**: output validates against the official `geoSciMLExtension.xsd` plus 29 business assertions on two sheets; 4733 elements source–target reconciled; Lite seven views emitted.
- **Rendering fidelity**: the semantics-driven render is reconciled against the L1 mirror (pixel-level acceptance 99.99% on Kurgan).
- **Regression suite**: 105 audit tests, each tracing a user adjudication or audit finding, including source-level drift guards.

## Pipeline

`g4c pipeline` runs ⓪ preflight (11-file contract) → ① MapGIS→L0 conversion → ② self-supporting calibration (two-phase materialization) → ③ style generation (semantics + DZ/T 0179-2025 color library → styles, single source) → ④ GeoSciML build (GML + Lite views + pending register) → ⑤ verification (XSD + assertions) → ⑥ semantics-driven rendering with mirror reconciliation.

- **Calibration** (`geosciml4china.calibrate`): prior-library driven (Xinjiang regional contact-relationship priors = dual-source highest-knowledge base, shipped as package data) + the self-supporting domains above.
- **Conversion** (`geosciml4china.convert`): six feature classes (GeologicUnit / MappedFeature / Contact / ShearDisplacementStructure / Foliation / Fold + fault attitude measurement points); specimens live in the official portrayal view because the GeoSciML 4.1 Sampling package is unpublished.
- **Styles** (`geosciml4china.render.stylegen` / `stylegen_fault`): GeoSciML semantics + DZ/T 0179-2025 color library → rendering styles; sheet adjudications frozen in an overrides layer (generated defaults < adjudication layer).
- **Rendering** (`geosciml4china.render`): thin adapters reusing the pymapgis rendering pipeline; strike-slip end hooks, fault attitude symbols, fold symbols, cartographic-contradiction overlays.
- **Verification** (`g4c verify`): XSD + 29 assertions, empirically locked on four sheets (kurgan / yingjisha / aoyiyayilake / bashkurgan).

## Dependencies

geosciml4china depends on the **mapgis2shp** project — the same author's
open-source package ([GitHub](https://github.com/leecugb/mapgis2shp),
[PyPI](https://pypi.org/project/mapgis2shp/)) — which supplies the format
layer: reverse-engineered readers for the closed MapGIS 6.x/67 binary vector
formats, the `pymapgis.semantics` base (sheet profiles, L0 conversion, L1
materialization), and the shared rendering pipeline. geosciml4china adds the
semantic-calibration, GeoSciML, and verification layers on top. The dependency
is structural, not optional — package modules import mapgis2shp throughout and
the installation is made against it (see below).

## Installation

```bash
pip install -e /d/JWD              # mapgis2shp (pymapgis semantics base)
pip install -e /d/geosciml4china   # this package
```

## Reproducible test case: jws (Kurgan sheet J43C001002)

A public, reproducible test case ships with this repository:
[`data/jws_l0_geojson/`](data/jws_l0_geojson/) — the **L0 GeoJSON of the
11-file preflight contract** (EPSG:4326) converted from a working copy of the
Kurgan sheet (J43C001002) MapGIS project. See
[data/jws_l0_geojson/README.md](data/jws_l0_geojson/README.md) for the file
catalogue and provenance.

1. Clone this repository and place the sheet's **MapGIS source folder** at a
   local path (the L0 dataset is the published *conversion product*; the
   upstream MapGIS vectors stay with the data owner).
2. Register the sheet (any of the three methods below), e.g. via
   `~/.geosciml4china.toml`:

   ```toml
   [sheets.jws]
   root = "D:/jws"
   code = "J43C001002"
   title = "Kurgan sheet copy (J43C001002) full-pipeline test"
   expected_units = 57
   expected_polygon_dist = { "LDZOFBB001.WP" = 608, "LDZOFBB002.WP" = 10, "LDZOFBB003.WP" = 46, "LDZOFBB004.WP" = 49 }
   lite_expect_counts = [713, 1316, 310, 305]
   aux_pairs_csv = "fault_aux_number_1894_pairs.csv"
   aux_assoc_csv = "fault_aux_jws.csv"
   aux_triplets_csv = "_fault_triplets_jws.csv"
   calibration_csv = "_gzbd_calibration_report.csv"
   ```

3. Run the chain and expect 29/29 assertions and mirror checks C1–C7:

   ```bash
   g4c check --sheet jws      # preflight: 11-file contract (CORE missing → abort)
   g4c pipeline --sheet jws   # MapGIS → L0 → calibrate → L1 → styles → GML → verify → render
   ```

## Sheet projects

A sheet project is a directory (sheet root) that by convention holds
`geojson/L1/` (semantic calibration layer), `output/geosciml/` (products),
`data/` or root-level sheet vocabulary mappings and adjudication layers, and
the MapGIS vector files. Two development sheets are registered in-package
(kurgan → `D:\JWD`; yingjisha → the Yingjisha JWD folder).

Third-party sheet registration (pick one):

1. Environment variable: `G4C_ROOT_<KEY>=<sheet root>`;
2. User config `./geosciml4china.toml` or `~/.geosciml4china.toml` (any Sheet field can be overridden);
3. Code: `geosciml4china.sheets.register_sheet(Sheet(...))`.

## CLI

```bash
g4c check --sheet kurgan                # sheet preflight: 11-file completeness contract
g4c pipeline --sheet kurgan             # full chain: MapGIS folder → L0 → calibrate → L1 → styles → GML → verify → render
g4c sheets                              # list registered sheets and resolved roots
g4c entities --sheet kurgan             # fault entity grouping (registry + G2 truncation no-merge)
g4c auxchain --sheet kurgan             # fault aux-point entity-chain discrimination (all rulings + optimal 1:1 pairing)
g4c stylegen --sheet kurgan [--diff]    # polygon style generation (semantics → styles, single source)
g4c stylegen-fault --sheet kurgan       # fault style generation
g4c build --sheet kurgan [--only gml|lite|pending] [--sample N]
g4c verify --sheet kurgan               # XSD + business assertions
g4c render --sheet kurgan [--no-overlay] [--check-only]
```

Pipeline order for stepwise debugging: **stylegen → build → verify** (the render
auto-regenerates stale styles via the F3 guard; overlays are the production
default, disable with `--no-overlay`).

## Related work

- **Format layer**: the [mapgis2shp](https://github.com/leecugb/mapgis2shp) package (the same author's project, this project's foundation) reverse-engineers the closed MapGIS 6.x/67 binary formats; its geometry-fidelity paper is under review.
- **Interoperability layer**: Xu et al. (2020, *Journal of Geology* 44(4):337–344) proposed a semantic-fusion mapping from Chinese data models to GeoSciML; the China Geological Survey has operated OneGeology China (64 sheets at 1:1,000,000, three-star service) and publishes GeoSciML 4.1 translations — these assume code meanings are already known.
- **International digitizing standards** (USGS OF 96-291/98-219B/99-438; GeMS; Geoscience Australia GA3362; GSC M183-2-8247-2) document dictionaries, topology rules, and orientation conventions — the very conventions this package recovers from geometry — but take the dictionary's availability for granted.
- **Recent map-semantics research** (Qiu et al., 2024, *Geological Review*; Duan et al., 2024, *Geology in China* 59(2):588–602) builds knowledge graphs and QA systems over vector maps from explicitly mapped dbf fields — again assuming known code semantics.

This package occupies the missing layer between them: dictionary-less semantic recovery of the codes themselves, with every recovered meaning graded by confidence and every contradiction preserved for human adjudication. The recovered invariants are not new to the digitizing standards; their use for semantic recovery without the dictionary is the contribution.

## Boundary

- Calibration outputs are **semantic hypotheses with confidence bands**, not ground truth: the final rulings remain human, and the confidence band gates what rendering and GeoSciML may consume directly.
- The method is validated on two sheets (Kurgan, Yingjisha) and exercised on two more (aoyiyayilake, bashkurgan); the 729-sheet national extrapolation is an inference from a single-sheet 29% calibration-debt measurement and awaits further sheets.
- If the dictionary becomes available, the discriminator does not become obsolete — it degrades gracefully into a deviation-grading engine anchored on the dictionary.
- Sheet data is not bundled (data-ownership avoidance); the published jws L0 test dataset is an explicit owner-approved exception.

## Namespace gate (A19)

Output identifiers currently use the placeholder domain
`geosciml4china.example.org` (`NAMESPACE_FINAL=False`). When the official
domain is decided, change the single constant in `convert/config.py`; the A19
assertion fails the build while the placeholder string remains.

## Package data (shipped with the package, ~4 MB)

GeoSciML 4.1 official XSD tree (72 files, offline validation) · CGI vocabulary
caches · DZ/T 0179-2025 color library and SVG pattern tiles · ICS 2020 time
scale.

## References

- Zuo Qunchao, Ye Tianzhu, Feng Yanfang, Ge Zuo, Wang Yingchao. 2018. 中国陆域1∶25万分幅建造构造图空间数据库 [Spatial database of 1:250,000 map-sheet formation–structure maps covering China's land area]. *Geology in China* 45(S1): 1–26. doi:10.12029/gc2018Z101
- Xu Yafeng, Hua Weihua, Li Yi. 2020. 面向GeoSciML的中国地质数据模型语义融合方法 [Semantic-fusion mapping from Chinese geological data models to GeoSciML]. *Journal of Geology* 44(4): 337–344
- Qiu Qinjun et al. 2024. 多模态数据的地质图关联网络构建及知识服务 [Multi-modal data-driven geological map association networks and knowledge services]. *Geological Review* 70(2)
- Duan Yuxi et al. 2024. Geological map-oriented knowledge graph construction and intelligent Q&A application. *Geology in China* 59(2): 588–602
- USGS Open-File Report 96-291 / 98-219B / 99-438 (digital line-graph attribute dictionaries and look-up tables)
- USGS GeMS (Geologic Map Schema) — ContactsAndFaults topology and digitizing-orientation conventions
- Geoscience Australia GA3362 — composite feature-code decomposition rules
- Geological Survey of Canada M183-2-8247-2 — subtype-controlled domain schema

## License

Apache-2.0.
