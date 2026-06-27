"""Workspace state contracts.

These Pydantic models define the canonical schema for the annotator's workspace
state and export formats. They are the single source of truth for the REST API
contract between the annotator and any consumer (e.g. the MCP server).
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

PillCorner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


class Bounds(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    # Minimum renderable annotation size in the UI to ensure pills remain selectable
    w: int = Field(..., ge=4)
    h: int = Field(..., ge=4)

    @property
    def left(self) -> int:
        return self.x

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def top(self) -> int:
        return self.y

    @property
    def bottom(self) -> int:
        return self.y + self.h


class Style(BaseModel):
    pillCorner: PillCorner = "top_left"


class Component(BaseModel):
    id: UUID
    number: str
    label: str
    parentId: UUID | None = None
    childrenIds: list[UUID] = Field(default_factory=list)
    bounds: Bounds
    style: Style = Field(default_factory=Style)

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: str) -> str:
        if v != "" and not v.isdigit():
            raise ValueError("Component number must contain only digits")
        return v


class ScreenInfo(BaseModel):
    name: str = ""
    description: str = ""


class ImageInfo(BaseModel):
    filename: str
    width: int
    height: int


class WorkspaceState(BaseModel):
    version: int = 1
    workspaceId: UUID
    revision: int = 0
    readOnly: bool = False
    screen: ScreenInfo = Field(default_factory=ScreenInfo)
    image: ImageInfo | None = None
    cutLines: list[int] = Field(default_factory=list)
    rootComponents: list[UUID] = Field(default_factory=list)
    components: dict[UUID, Component] = Field(default_factory=dict)
    autoNumbering: bool = True


# ── Export Manifest ────────────────────────────────────────────


class ImageExportManifest(BaseModel):
    """Schema for the mapping.json file inside workspace image export ZIPs.

    This represents the 'annotated' or 'raw' mode export mapping, where:
        root: path to the root image (or None)
        components: dict mapping component UUID string → archive path
    """

    root: list[str] = Field(default_factory=list)
    components: dict[str, str] = Field(default_factory=dict)


class ImageExportManifestBoth(BaseModel):
    """Schema for mapping.json when export mode is 'both'."""

    annotated: ImageExportManifest = Field(default_factory=ImageExportManifest)
    raw: ImageExportManifest = Field(default_factory=ImageExportManifest)
