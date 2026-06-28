"""Pydantic models for spec.json — the contract between agent and script."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr, field_validator


class Bounds(BaseModel):
    """Bounding box coordinates of the component on the original screen image."""

    x: int
    y: int
    w: int
    h: int


class Interaction(BaseModel):
    """A single user-action / system-reaction pair."""

    action: str = Field(min_length=1)
    reaction: str = Field(min_length=1)


class ApiParam(BaseModel):
    """A single field in a request/response API table."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool
    type: str = Field(min_length=1)
    limit: str | None = Field(default=None, min_length=1)
    defaultValue: str | None = Field(default=None, min_length=1)

    @field_validator("required", mode="before")
    @classmethod
    def _parse_bool(cls, v):
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("Y", "YES", "TRUE", "1", "CÓ", "CO"):
                return True
            if val in ("N", "NO", "FALSE", "0", "KHÔNG", "KHONG", "K"):
                return False
        return bool(v)


class ApiPayload(BaseModel):
    """A single flat DTO payload schema."""

    type: str = Field(min_length=1)  # Unique name/type of the DTO (e.g. "AddToCartRequestDto")
    fields: list[ApiParam] = Field(default_factory=list)


class Api(BaseModel):
    """A single API endpoint's documentation."""

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    requestRootType: str | None = Field(default=None, min_length=1)
    request: list[ApiPayload] = Field(default_factory=list)
    responseRootType: str | None = Field(default=None, min_length=1)
    response: list[ApiPayload] = Field(default_factory=list)


class NodeSpec(BaseModel):
    """A single visual or logical node (Screen, Component, or Element) in the flat tree."""

    id: str
    absoluteBounds: Bounds
    label: str = Field(min_length=1)
    controlType: str = Field(min_length=1)
    required: bool | None = Field(default=None)
    maxLength: int | None = None
    editable: bool | None = Field(default=None)
    description: str = Field(min_length=1)
    rawImage: str = Field(min_length=1)
    annotatedImages: list[str] = Field(default_factory=list)
    childrenIds: list[str] = Field(default_factory=list)  # Sibling order is preserved here
    interactions: list[Interaction] = Field(default_factory=list)
    apis: list[Api] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v):
        if isinstance(v, int):
            return str(v)
        return v

    @field_validator("childrenIds", mode="before")
    @classmethod
    def _coerce_children_ids(cls, v):
        if isinstance(v, list):
            return [str(item) if isinstance(item, int) else item for item in v]
        return v

    @field_validator("required", "editable", mode="before")
    @classmethod
    def _parse_bool(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("Y", "YES", "TRUE", "1", "CÓ", "CO"):
                return True
            if val in ("N", "NO", "FALSE", "0", "KHÔNG", "KHONG", "K"):
                return False
        return bool(v)


class ScreenSpec(BaseModel):
    """Root schema for spec.json representing the normalized flat tree."""

    schema_url: str | None = Field(default=None, alias="$schema")
    sectionPrefix: str = Field(min_length=1)
    rootId: str
    nodes: list[NodeSpec]

    _spec_dir: Path | None = PrivateAttr(default=None)


    @field_validator("rootId", mode="before")
    @classmethod
    def _coerce_root_id(cls, v):
        if isinstance(v, int):
            return str(v)
        return v

    @property
    def nodes_map(self) -> dict[str, NodeSpec]:
        """Helper mapping node ID to node object for O(1) lookups."""
        return {n.id: n for n in self.nodes}

    @property
    def screen(self) -> NodeSpec:
        """Helper to find the root screen component (id == rootId)."""
        nodes = [n for n in self.nodes if n.id == self.rootId]
        if not nodes:
            raise ValueError(f"No component with id == {self.rootId} (screen) defined.")
        return nodes[0]

    @property
    def all_apis(self) -> list[Api]:
        """Combine APIs from the screen and all components in DFS order."""
        dfs_order: list[str] = []
        visited: set[str] = set()
        nodes_dict = self.nodes_map

        def dfs(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)
            node = nodes_dict.get(node_id)
            if not node:
                return
            for child_id in node.childrenIds:
                child = nodes_dict.get(child_id)
                # If a child has nested children, it's a sub-component, so traverse it in DFS
                if child and len(child.childrenIds) > 0:
                    dfs(child_id)
            if node_id != self.rootId:
                dfs_order.append(node_id)

        dfs(self.rootId)

        # Collect APIs starting with Screen, then sub-components in DFS order
        res = list(self.screen.apis)
        for comp_id in dfs_order:
            comp = nodes_dict.get(comp_id)
            if comp:
                res.extend(comp.apis)
        return res

    def resolve_annotated_image(self, path: str) -> Path:
        """Resolve an annotated image path."""
        p = Path(path)
        if p.is_absolute():
            return p
        if self._spec_dir:
            return self._spec_dir / p
        return p

    def resolve_raw_image(self, path: str) -> Path:
        """Resolve a raw image path."""
        p = Path(path)
        if p.is_absolute():
            return p
        if self._spec_dir:
            return self._spec_dir / p
        return p

