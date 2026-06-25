"""Pydantic models for analysis.json — the contract between agent and script."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator


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
    apis: list[Api] = []

    @model_validator(mode="after")
    def validate_leaf_apis(self) -> Component:
        if self.isLeaf and self.apis:
            raise ValueError(
                f"Component '{self.label}' (id={self.id}) is a leaf component and cannot have API documentation."
            )
        return self


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
    apis: list[Api] = []


class Discrepancy(BaseModel):
    """A conflict between what's visible on-screen and what's in the code."""

    location: str
    imageObservation: str
    codeObservation: str
    resolution: str = ""


class AnalysisData(BaseModel):
    """Root schema for analysis.json."""

    sectionPrefix: str = "1.1"
    imageDir: str
    components: list[Component] = []
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
    def validate_unique_apis(self) -> AnalysisData:
        api_numbers: dict[int, list[str]] = {}
        api_endpoints: dict[tuple[str, str], list[str]] = {}

        def add_api(api: Api, owner: str):
            api_numbers.setdefault(api.number, []).append(owner)
            method_url = (api.method.upper().strip(), api.url.strip())
            api_endpoints.setdefault(method_url, []).append(owner)

        # Screen APIs
        for api in self.screen.apis:
            add_api(api, f"Screen '{self.screen.name}'")

        # Component APIs
        for comp in self.components:
            for api in comp.apis:
                add_api(api, f"Component '{comp.label}' (id={comp.id})")

        errors = []
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
