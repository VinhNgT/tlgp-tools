"""Pydantic models for analysis.json — the contract between agent and script."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from tlgp_contracts import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
)


class UnitLimitConfig(BaseModel):
    """Configurable unit cost parameters for complexity validation.

    Each component and screen has a complexity budget measured in units.
    Annotations (child elements) and APIs each consume a configurable
    number of units, and the total per scope must not exceed maxUnits.
    """

    annotationCost: int = DEFAULT_UNIT_COST_ANNOTATION
    apiCost: int = DEFAULT_UNIT_COST_API
    maxUnits: int = DEFAULT_UNIT_LIMIT


class ChildElement(BaseModel):
    """A leaf UI element inside a component or at the screen level."""

    stt: int
    componentId: int | None = None
    label: str = ""
    controlType: str = ""
    required: str = ""
    maxLength: str = ""
    editable: str = ""
    description: str = ""


class Interaction(BaseModel):
    """A single user-action / system-reaction pair."""

    action: str
    reaction: str


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

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"API number must be >= 1, got {v}")
        return v

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        v = v.strip().upper()
        allowed = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        if v not in allowed:
            raise ValueError(f"API method must be one of {allowed}, got '{v}'")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"API url must start with '/', got '{v}'")
        return v


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

    name: str
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
    unitLimit: UnitLimitConfig = Field(default_factory=UnitLimitConfig)
    components: list[AnalysisComponent] = []
    screen: Screen
    discrepancies: list[Discrepancy] = []

    @property
    def all_apis(self) -> list[Api]:
        """Combine APIs from the screen and all components in order."""
        res = list(self.screen.apis)
        for c in self.components:
            res.extend(c.apis)
        return res

    @model_validator(mode="after")
    def resolve_component_references(self) -> AnalysisData:
        comp_dict = {c.id: c for c in self.components}

        def _resolve_children(children: list[ChildElement], owner_name: str):
            for child in children:
                if child.componentId is not None:
                    if child.componentId in comp_dict:
                        comp = comp_dict[child.componentId]
                        if not child.label:
                            child.label = comp.label
                        if not child.description:
                            child.description = comp.description
                        if not child.controlType:
                            child.controlType = "Component"
                    else:
                        raise ValueError(
                            f"Child element in {owner_name} references non-existent componentId: {child.componentId}"
                        )

        _resolve_children(self.screen.topLevelChildren, f"Screen '{self.screen.name}'")
        for comp in self.components:
            _resolve_children(comp.children, f"Component '{comp.label}' (id={comp.id})")

        return self

    @model_validator(mode="after")
    def validate_uniqueness_constraints(self) -> AnalysisData:
        api_numbers: dict[int, list[str]] = {}
        api_endpoints: dict[tuple[str, str], list[str]] = {}
        component_ids: dict[int, list[str]] = {}

        def add_api(api: Api, owner: str):
            api_numbers.setdefault(api.number, []).append(owner)
            method_url = (api.method.upper().strip(), api.url.strip())
            api_endpoints.setdefault(method_url, []).append(owner)

        # Screen APIs
        for api in self.screen.apis:
            add_api(api, f"Screen '{self.screen.name}'")

        # Component APIs and IDs
        for comp in self.components:
            component_ids.setdefault(comp.id, []).append(comp.label)
            for api in comp.apis:
                add_api(api, f"Component '{comp.label}' (id={comp.id})")

        errors = []
        for comp_id, labels in component_ids.items():
            if len(labels) > 1:
                errors.append(
                    f"Component ID {comp_id} is duplicated across components: {', '.join(labels)}"
                )

        for num, owners in api_numbers.items():
            if len(owners) > 1:
                errors.append(
                    f"API number {num} is defined in multiple places: {', '.join(owners)}"
                )

        for (method, url), owners in api_endpoints.items():
            if len(owners) > 1:
                errors.append(
                    f"API {method} {url} is defined in multiple places: {', '.join(owners)}"
                )

        if errors:
            raise ValueError("; ".join(errors))

        return self

    @field_validator("imageDir")
    @classmethod
    def validate_image_dir(cls, v: str) -> str:
        path = Path(v)
        if not path.is_dir():
            raise ValueError(f"imageDir does not exist: {v}")
        return v

    def resolve_image(self, relative_path: str) -> Path:
        """Resolve an image filename relative to imageDir."""
        return Path(self.imageDir) / relative_path
