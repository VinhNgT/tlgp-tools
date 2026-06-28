"""TLGP Contracts — shared Pydantic schemas defining module boundaries."""

from .docgen import DocGenResult
from .tree import TreeUtils
from .unit_limit import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
)
from .workspace import (
    Bounds,
    Component,
    ImageExportManifest,
    ImageExportManifestBoth,
    ImageInfo,
    PillCorner,
    ScreenInfo,
    Style,
    WorkspaceState,
)
from .spec import (
    Interaction,
    ApiParam,
    ApiPayload,
    Api,
    NodeSpec,
    ScreenSpec,
)

import importlib.resources

def get_example_spec_json() -> str:
    """Retrieve the canonical example spec JSON string."""
    ref = importlib.resources.files("tlgp_contracts") / "example_spec.json"
    return ref.read_text(encoding="utf-8")

__all__ = [
    "DEFAULT_UNIT_COST_ANNOTATION",
    "DEFAULT_UNIT_COST_API",
    "DEFAULT_UNIT_LIMIT",
    "Bounds",
    "Component",
    "DocGenResult",
    "ImageExportManifest",
    "ImageExportManifestBoth",
    "ImageInfo",
    "PillCorner",
    "ScreenInfo",
    "Style",
    "TreeUtils",
    "WorkspaceState",
    "get_example_spec_json",
    "Interaction",
    "ApiParam",
    "ApiPayload",
    "Api",
    "NodeSpec",
    "ScreenSpec",
]

