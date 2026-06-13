"""Pydantic models for analysis.json — the contract between agent and script."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, field_validator


class ChildElement(BaseModel):
    """A leaf UI element inside a component or at the screen level."""

    stt: int
    label: str
    controlType: str
    required: str = ""
    maxLength: str = ""
    editable: str = ""
    description: str = ""


class Interaction(BaseModel):
    """A single user-action / system-reaction pair."""

    action: str
    reaction: str


class Component(BaseModel):
    """A non-leaf or leaf annotated component."""

    id: int
    label: str
    description: str = ""
    isLeaf: bool = False
    imageFile: str | None = None
    children: list[ChildElement] = []
    interactions: list[Interaction] = []


class ApiParam(BaseModel):
    """A single field in a request/response API table."""

    name: str
    meaning: str = ""
    required: str = ""
    dataType: str = ""
    limit: str = ""
    defaultValue: str = ""


class SubDto(BaseModel):
    """A nested DTO table within an API response."""

    name: str
    fieldRef: str = ""
    fields: list[ApiParam] = []


class Api(BaseModel):
    """A single API endpoint's documentation."""

    number: int
    method: str
    title: str
    url: str
    requestParams: list[ApiParam] = []
    requestBodyType: str = ""
    requestDescription: str = ""
    responseType: str = ""
    responseFields: list[ApiParam] = []
    responseDescription: str = ""
    subDtos: list[SubDto] = []


class Screen(BaseModel):
    """Screen-level metadata and top-level children."""

    name: str
    description: str = ""
    imageFiles: list[str] = []
    topLevelChildren: list[ChildElement] = []
    interactions: list[Interaction] = []


class Discrepancy(BaseModel):
    """A conflict between what's visible on-screen and what's in the code."""

    location: str
    imageObservation: str
    codeObservation: str
    resolution: str = ""


class AnalysisData(BaseModel):
    """Root schema for analysis.json."""

    sectionPrefix: str = "1.1"
    exportDir: str
    components: list[Component] = []
    screen: Screen
    apis: list[Api] = []
    discrepancies: list[Discrepancy] = []

    @field_validator("exportDir")
    @classmethod
    def validate_export_dir(cls, v: str) -> str:
        path = Path(v)
        if not path.is_dir():
            raise ValueError(f"exportDir does not exist: {v}")
        return v

    def resolve_image(self, relative_path: str) -> Path:
        """Resolve an image filename relative to exportDir."""
        return Path(self.exportDir) / relative_path
