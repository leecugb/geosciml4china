# jws GeoSciML products — Kurgan sheet (J43C001002) test-case outputs

This directory holds the **GeoSciML conversion products** of the *jws* test
sheet, built from the L1 semantic layer (`data/jws_l1_geojson`) by
`g4c build` / `g4c stylegen` / `g4c stylegen-fault`.

## Contents

| File | Description |
|---|---|
| `jws_geosciml_full.gml` | Full GeoSciML 4.1 document (4733 members; validates against `geoSciMLExtension.xsd`) |
| `lite/` | Seven Lite views (GeoJSON): geologic_unit / contact / shear_displacement_structure / fault_attitude_point / site_observation / fossil_specimen / fold / waterline / waterpoly |
| `jws_style_generated.json` | Polygon & line style mapping (DZ/T 0179-2025 color library driven) |
| `jws_fault_styles_generated.json` | Fault styles (GZEEB semantics + adjudicated decorations) |
| `pending_review.md` | Adjudication queue (never auto-changed codes) |
| `reconciliation_report.md` | Verification report (29 assertions, XSD + business checks) |

## Reproducibility

The full test case now forms a closed loop in this repository:

```
data/jws_l0_geojson   (conversion input: 11-file contract)
  → g4c pipeline …
  → data/jws_l1_geojson   (semantic calibration layer)
  → g4c stylegen / build
  → data/jws_geosciml     (this directory: GML + Lite + styles + reports)
```

Expected verification results: `g4c verify --sheet jws` → **29/29 PASS**;
render mirror checks C1–C7 → **all PASS**. Identifier namespace is the
placeholder domain (A19 gate) until the official domain is decided.
