from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from uuid import UUID

class Bounds(BaseModel):
    x: int
    y: int
    w: int
    h: int

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
    parentId: Optional[UUID] = None
    childrenIds: List[UUID] = Field(default_factory=list)
    bounds: Bounds
    absoluteBounds: Bounds
    style: Style = Field(default_factory=Style)
    visibility: Visibility = Field(default_factory=Visibility)
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    screen: ScreenInfo = Field(default_factory=ScreenInfo)
    image: Optional[ImageInfo] = None
    cutLines: List[int] = Field(default_factory=list)
    rootComponents: List[UUID] = Field(default_factory=list)
    components: Dict[UUID, Component] = Field(default_factory=dict)
