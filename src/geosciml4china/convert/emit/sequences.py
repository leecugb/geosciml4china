"""XSD slot sequences — single source of truth for property ordering.

Every list is checked against geoSciMLBasic.xsd / geoSciMLExtension.xsd.
SlotWriter enforces these at build time; the full-document XSD validation
is the second, independent gate.
"""

GML_HEAD = ["description", "identifier", "name"]

MAPPED_FEATURE = [
    "observationMethod",
    "positionalAccuracy",
    "resolutionRepresentativeFraction",
    "mappingFrame",
    "exposure",
    "specification",
    "shape",
]

GEOLOGIC_FEATURE = [
    "observationMethod",
    "occurrence",
    "purpose",
    "relatedFeature",
    "classifier",
    "geologicHistory",
]

GEOLOGIC_UNIT = GEOLOGIC_FEATURE + [
    "geologicUnitType",
    "rank",
    "composition",
    "hierarchyLink",
    "gbMaterialDescription",
    "gbUnitDescription",
]

GEOLOGIC_EVENT = [
    "eventProcess",
    "numericAge",
    "olderNamedAge",
    "youngerNamedAge",
    "eventEnvironment",
]

CONTACT = GEOLOGIC_FEATURE + ["contactType", "stContactDescription"]
FOLD = GEOLOGIC_FEATURE + ["profileType", "stFoldDescription"]
FOLIATION = GEOLOGIC_FEATURE + ["foliationType", "stFoliationDescription"]
SDS = GEOLOGIC_FEATURE + ["faultType", "stStructureDescription"]

PLANAR_ORIENTATION = [
    "determinationMethod",
    "convention",
    "azimuth",
    "dip",
    "polarity",
]

SDS_DESCRIPTION = ["stPhysicalProperty", "deformationStyle", "planeOrientation"]
DISPLACEMENT_VALUE = [
    "hangingWallDirection",
    "movementSense",
    "movementType",
    "displacementEvent",
]
LINEAR_ORIENTATION = ["directed", "plunge", "trend"]
# GeologicFeatureRelation（Extension）：base AbstractFeatureRelationType 的
# relatedFeature 在前，扩展 relationship/sourceRole/targetRole 在后
FEATURE_RELATION = ["relatedFeature", "relationship", "sourceRole", "targetRole"]
FOLIATION_DESCRIPTION = [
    "definingElement",
    "continuity",
    "intensity",
    "mineralElement",
    "orientation",
    "spacing",
]

COMPOSITION_PART = ["role", "material", "proportion"]
GEOLOGIC_UNIT_HIERARCHY = ["role", "proportion", "targetUnit"]

# Slots allowed to repeat (0..* / 1..*) per complex type.
_FEATURE_REPEATABLE = {
    "observationMethod",
    "occurrence",
    "geologicHistory",
    "relatedFeature",
    "classifier",
}
REPEATABLE = {
    "GEOLOGIC_FEATURE": _FEATURE_REPEATABLE,
    "GEOLOGIC_UNIT": _FEATURE_REPEATABLE | {"composition", "hierarchyLink"},
    "GEOLOGIC_EVENT": {"eventProcess", "eventEnvironment"},
    "MAPPED_FEATURE": {"observationMethod"},
    "SDS": _FEATURE_REPEATABLE | {"stStructureDescription"},
}
