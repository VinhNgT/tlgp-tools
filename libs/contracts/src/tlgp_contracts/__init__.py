"""TLGP Contracts — shared Pydantic schemas defining module boundaries."""

import importlib.resources

from .docgen import DocGenResult
from .spec import (
    Api,
    ApiParam,
    ApiPayload,
    Interaction,
    NodeSpec,
    ScreenSpec,
)
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


def get_example_spec_json() -> str:
    """Retrieve the canonical example spec JSON string."""
    ref = importlib.resources.files("tlgp_contracts") / "example_spec.json"
    return ref.read_text(encoding="utf-8")

__all__ = [
    "DEFAULT_UNIT_COST_ANNOTATION",
    "DEFAULT_UNIT_COST_API",
    "DEFAULT_UNIT_LIMIT",
    "Api",
    "ApiParam",
    "ApiPayload",
    "Bounds",
    "Component",
    "DocGenResult",
    "ImageExportManifest",
    "ImageExportManifestBoth",
    "ImageInfo",
    "Interaction",
    "NodeSpec",
    "PillCorner",
    "ScreenInfo",
    "ScreenSpec",
    "Style",
    "TreeUtils",
    "WorkspaceState",
    "get_example_spec_json",
]

