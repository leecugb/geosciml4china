# geosciml4china

Full-chain software package for Chinese regional geological map sheets:
**MapGIS project folder → self-supporting geological-semantics calibration → GeoSciML 4.1 conversion → DZ/T 0179-2025 rendering verification**
(scope ruling 2026-09-29: input = the MapGIS project document folder).

- **Calibration** (`geosciml4china.calibrate`, staged migration + pymapgis semantics orchestration): prior-library driven (Xinjiang regional contact-relationship priors = dual-source highest-knowledge base, shipped as package data) + self-supporting discrimination (code-semantics registry / criterion applicability / semantic-dimension review); contradictions go to human adjudication, codes are never auto-changed.
- **Conversion** (`geosciml4china.convert`): six feature classes emitted (GeologicUnit / MappedFeature / Contact / ShearDisplacementStructure / Foliation / Fold + fault attitude measurement points); full document validates against `geoSciMLExtension.xsd`; Lite seven views (GeoJSON, including the GeologicSpecimenView portrayal layer — the GeoSciML 4.1 Sampling package is unpublished, so specimens live in the official portrayal view).
- **Styles** (`geosciml4china.render.stylegen` / `stylegen_fault`): GeoSciML geological semantics + DZ/T 0179-2025 unified color library → rendering style files; sheet-specific adjudications are frozen in an overrides layer (generated defaults < adjudication layer).
- **Rendering** (`geosciml4china.render`): thin adapters reusing the pymapgis rendering pipeline; L1-mirror pixel reconciliation; strike-slip end hooks / fault attitude measurement-point symbols / fold-type symbols / cartographic-contradiction overlays.
- **Verification** (`g4c verify`): XSD + 29 business assertions, empirically locked on four sheets (kurgan J43C001002 / yingjisha J43C002003 / aoyiyayilake J45C004001 / bashkurgan J46C001001).

## Installation

```bash
pip install -e /d/JWD              # mapgis2shp (pymapgis semantics base)
pip install -e /d/geosciml4china   # this package
```

## Test case: jws (Kurgan sheet J43C001002, published L0 dataset)

A public, reproducible test case ships with this repository:
[`data/jws_l0_geojson/`](data/jws_l0_geojson/) — the **L0 GeoJSON of the
11-file preflight contract** (EPSG:4326) converted from a working copy of the
Kurgan sheet (J43C001002) MapGIS project. See
[data/jws_l0_geojson/README.md](data/jws_l0_geojson/README.md) for the file
catalogue and provenance.

To run the pipeline against the test case:

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

## Namespace gate (A19)

Output identifiers currently use the placeholder domain
`geosciml4china.example.org` (`NAMESPACE_FINAL=False`). When the official
domain is decided, change the single constant in `convert/config.py`; the A19
assertion fails the build while the placeholder string remains.

## Package data (shipped with the package, ~4 MB)

GeoSciML 4.1 official XSD tree (72 files, offline validation) · CGI vocabulary
caches · DZ/T 0179-2025 color library and SVG pattern tiles · ICS 2020 time
scale. Sheet data is not bundled in the package (data-ownership avoidance);
the published jws L0 test dataset is an explicit owner-approved exception.

## License

Apache-2.0.
