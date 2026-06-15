from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Bounds(BaseModel):
    x: int
    y: int
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
    pillCorner: str = "top_left"


class Visibility(BaseModel):
    visible: bool = True
    locked: bool = False


class Component(BaseModel):
    id: UUID
    number: str
    label: str
    parentId: UUID | None = None
    childrenIds: list[UUID] = Field(default_factory=list)
    bounds: Bounds
    style: Style = Field(default_factory=Style)
    visibility: Visibility = Field(default_factory=Visibility)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScreenInfo(BaseModel):
    name: str = ""
    description: str = ""


class ImageInfo(BaseModel):
    filename: str
    width: int
    height: int


class WorkspaceState(BaseModel):
    version: int = 1
    sessionId: UUID
    revision: int = 0
    readOnly: bool = False
    screen: ScreenInfo = Field(default_factory=ScreenInfo)
    image: ImageInfo | None = None
    cutLines: list[int] = Field(default_factory=list)
    rootComponents: list[UUID] = Field(default_factory=list)
    components: dict[UUID, Component] = Field(default_factory=dict)

