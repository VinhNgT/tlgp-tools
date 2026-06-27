"""Pydantic models for analysis.json — the contract between agent and script."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class PrimitiveElement(BaseModel):
    """A leaf UI element that is a primitive control (e.g., Button, Text)."""

    type: Literal["primitive"] = "primitive"
    label: str
    controlType: str
    required: str = ""
    maxLength: str = ""
    editable: str = ""
    description: str = ""


class ComponentReferenceElement(BaseModel):
    """A leaf UI element that references another component."""

    type: Literal["component"] = "component"
    componentId: int
    label: str = ""
    description: str = ""

    @property
    def controlType(self) -> str:
        return "Component"


ChildElement = Annotated[
    PrimitiveElement | ComponentReferenceElement, Field(discriminator="type")
]


class Interaction(BaseModel):
    """A single user-action / system-reaction pair."""

    action: str
    reaction: str


class ApiParam(BaseModel):
    """A single field in a request/response API table."""

    name: str = Field(min_length=1)
    meaning: str = ""
    required: str = ""
    dataType: str = ""
    limit: str = ""
    defaultValue: str = ""


class ApiSchema(BaseModel):
    """A nested schema table within an API request or response."""

    name: str = Field(min_length=1)
    fieldRef: str = ""
    fields: list[ApiParam] = []


class ApiMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    WS = "WS"
    GRPC = "GRPC"
    SSE = "SSE"


class Api(BaseModel):
    """A single API endpoint's documentation."""

    method: ApiMethod
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    requestParams: list[ApiParam] = []
    requestBodyType: str = ""
    requestDescription: str = ""
    responseType: str = ""
    responseFields: list[ApiParam] = []
    responseDescription: str = ""
    schemas: dict[str, ApiSchema] = Field(default_factory=dict)


class AnalysisComponent(BaseModel):
    """A non-leaf or leaf annotated component."""

    id: int
    label: str
    description: str = ""
    isLeaf: bool = False
    imageFile: str | None = None
    children: list[ChildElement] = []
    interactions: list[Interaction] = []
    apis: list[Api] = []

    @model_validator(mode="after")
    def validate_leaf_constraints(self) -> AnalysisComponent:
        if self.isLeaf:
            if self.apis:
                raise ValueError(
                    f"Component '{self.label}' (id={self.id}) is a leaf component and cannot have API documentation."
                )
            if self.children:
                raise ValueError(
                    f"Component '{self.label}' (id={self.id}) is a leaf component and cannot have children."
                )
        return self


class Screen(BaseModel):
    """Screen-level metadata and top-level children."""

    name: str = Field(min_length=1)
    description: str = ""
    imageFiles: list[str] = []
    topLevelChildren: list[ChildElement] = []
    interactions: list[Interaction] = []
    apis: list[Api] = []


class Discrepancy(BaseModel):
    """A confirmed conflict between the screenshot and the source code."""

    location: str
    imageObservation: str
    codeObservation: str
    expectedBehavior: str = ""


class AnalysisData(BaseModel):
    """Root schema for analysis.json."""

    sectionPrefix: str = "1.1"
    imageDir: str
    components: dict[int, AnalysisComponent] = Field(default_factory=dict)
    screen: Screen
    discrepancies: list[Discrepancy] = []

    @property
    def all_apis(self) -> list[Api]:
        """Combine APIs from the screen and all components in order."""
        res = list(self.screen.apis)
        for c in self.components.values():
            res.extend(c.apis)
        return res

    def resolve_image(self, relative_path: str) -> Path:
        """Resolve an image filename relative to imageDir."""
        return Path(self.imageDir) / relative_path
