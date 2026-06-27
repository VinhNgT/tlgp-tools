"""Pydantic models for analysis.json — the contract between agent and script."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

# ChildElement was removed in favor of the unified NodeSpec


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


class ApiPayload(BaseModel):
    """The structure of an API request or response payload schema."""

    type: str = ""
    parentType: str | None = None
    fields: list[ApiParam] = []


class Api(BaseModel):
    """A single API endpoint's documentation."""

    api: str = Field(min_length=1)
    url: str = Field(min_length=1)
    request: list[ApiPayload] = Field(default_factory=list)
    response: list[ApiPayload] = Field(default_factory=list)


class NodeSpec(BaseModel):
    """A single visual or logical node (Screen, Component, or Element) in the flat tree."""

    id: str  # Globally unique ID (can be UUID string or number string)
    label: str
    controlType: str = ""  # Strictly informational (e.g. "Button", "Text", "Icon"). Omitted for components.
    required: str = ""
    maxLength: str = ""
    editable: str = ""
    description: str = ""
    imageFiles: list[str] = Field(default_factory=list)  # Present for Screens and Components
    childrenIds: list[str] = Field(default_factory=list)  # Sibling order is preserved here
    interactions: list[Interaction] = Field(default_factory=list)
    apis: list[Api] = Field(default_factory=list)


class ScreenSpec(BaseModel):
    """Root schema for spec.json representing the normalized flat tree."""

    sectionPrefix: str = "1.1"
    imageDir: str
    rootId: str = "0"  # Entry point of the tree (always Screen "0" or Screen UUID string)
    nodes: list[NodeSpec] = Field(default_factory=list)

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

    def resolve_image(self, relative_path: str) -> Path:
        """Resolve an image filename relative to imageDir."""
        return Path(self.imageDir) / relative_path
