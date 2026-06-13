from dataclasses import dataclass, field


@dataclass
class AnnotationBox:
    """A rectangular annotation region that can contain nested child annotations.

    Supports arbitrary recursive nesting. Coordinates are always
    stored in absolute image space regardless of nesting depth.
    """

    id: int  # 1-based sequential number within its sibling list
    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    children: list["AnnotationBox"] = field(default_factory=list)
    pill_corner: str = "top_left"

    @property
    def width(self) -> int:
        return abs(self.x2 - self.x1)

    @property
    def height(self) -> int:
        return abs(self.y2 - self.y1)

    @property
    def left(self) -> int:
        return min(self.x1, self.x2)

    @property
    def top(self) -> int:
        return min(self.y1, self.y2)

    @property
    def right(self) -> int:
        return max(self.x1, self.x2)

    @property
    def bottom(self) -> int:
        return max(self.y1, self.y2)

    @property
    def bounds(self) -> dict:
        return {"x": self.left, "y": self.top, "w": self.width, "h": self.height}

    @property
    def bounds_tuple(self) -> tuple:
        """Returns (left, top, right, bottom) — always normalised."""
        return self.left, self.top, self.right, self.bottom

    def to_dict(self, parent_x: int = 0, parent_y: int = 0) -> dict:
        """Recursively serialize to dict. Coordinates are relative to the parent."""
        result = {
            "id": self.id,
            "label": self.label,
            "bounds": {
                "x": self.left - parent_x,
                "y": self.top - parent_y,
                "w": self.width,
                "h": self.height,
            },
            "pill_corner": self.pill_corner,
        }
        if self.children:
            result["children"] = [
                child.to_dict(parent_x=self.left, parent_y=self.top)
                for child in self.children
            ]
        return result

    def has_descendants(self) -> bool:
        """Returns True if this box or any descendant has children."""
        if self.children:
            return True
        return any(child.has_descendants() for child in self.children)


@dataclass
class ScreenSession:
    screen_name: str = ""
    description: str = ""
    original_image: str | None = None
    components: list[AnnotationBox] = field(default_factory=list)
    # Sorted list of Y-coordinates (absolute image space) for horizontal cuts.
    # Only supported at root level.
    cut_lines: list[int] = field(default_factory=list)
