from annotator.models import Bounds, Component
from annotator.workspace.errors import InvalidStateError

MIN_CUT_GAP = 50


class BoundsValidator:
    """Pure domain service encapsulating component coordinate boundary validation and clamping math."""

    @staticmethod
    def clamp_val(val: float, lo: float, hi: float) -> float:
        """Clamps a value within lower and upper bounds."""
        return max(lo, min(hi, val))

    @staticmethod
    def clamp_box_position(
        ox1: float,
        oy1: float,
        w: float,
        h: float,
        dx: float,
        dy: float,
        bx1: float,
        by1: float,
        bx2: float,
        by2: float,
    ) -> tuple[float, float]:
        """Calculates and clamps the new top-left coordinates for a box of width w and height h moving by (dx, dy)."""
        rx1 = max(bx1, min(bx2 - w, ox1 + dx))
        ry1 = max(by1, min(by2 - h, oy1 + dy))
        return rx1, ry1

    @staticmethod
    def clamp_resize(
        ox1: float,
        oy1: float,
        ox2: float,
        oy2: float,
        dx: float,
        dy: float,
        handle: str,
        bx1: float,
        by1: float,
        bx2: float,
        by2: float,
        min_size: float = 4,
        children_union: tuple[float, float, float, float] | None = None,
    ) -> tuple[float, float, float, float]:
        """Calculates and clamps the new coordinates (rx1, ry1, rx2, ry2) during resizing."""
        rx1, ry1, rx2, ry2 = ox1, oy1, ox2, oy2

        if "w" in handle:
            rx1 = max(bx1, min(bx2, ox1 + dx))
        if "e" in handle:
            rx2 = max(bx1, min(bx2, ox2 + dx))
        if "n" in handle:
            ry1 = max(by1, min(by2, oy1 + dy))
        if "s" in handle:
            ry2 = max(by1, min(by2, oy2 + dy))

        # Enforce minimum size constraint
        if rx2 - rx1 < min_size:
            if "w" in handle:
                rx1 = rx2 - min_size
            else:
                rx2 = rx1 + min_size
        if ry2 - ry1 < min_size:
            if "n" in handle:
                ry1 = ry2 - min_size
            else:
                ry2 = ry1 + min_size

        # Enforce children bounds union constraint (box cannot shrink past its children's union)
        if children_union:
            cx1, cy1, cx2, cy2 = children_union
            if rx1 > cx1:
                rx1 = cx1
            if rx2 < cx2:
                rx2 = cx2
            if ry1 > cy1:
                ry1 = cy1
            if ry2 < cy2:
                ry2 = cy2

        # Final safety clamp to guarantee coordinates never violate the boundary box
        rx1 = max(bx1, min(bx2, rx1))
        rx2 = max(bx1, min(bx2, rx2))
        ry1 = max(by1, min(by2, ry1))
        ry2 = max(by1, min(by2, ry2))

        return rx1, ry1, rx2, ry2


class CutValidator:
    """Pure domain service encapsulating cut line coordinate constraints and collision checks."""

    @staticmethod
    def get_intersecting_component(
        img_y: int, components: list[Component]
    ) -> Component | None:
        """Determines if a horizontal coordinate intersects with any component bounds."""
        for comp in components:
            if comp.bounds.top <= img_y <= comp.bounds.bottom:
                return comp
        return None

    @staticmethod
    def is_valid_position(
        img_y: int, image_height: int, cut_lines: list[int], min_gap: int
    ) -> bool:
        """Verifies if a coordinate satisfies top/bottom margins and gap constraints."""
        if img_y < min_gap or img_y > image_height - min_gap:
            return False
        for existing_y in cut_lines:
            if abs(img_y - existing_y) < min_gap:
                return False
        return True

    @staticmethod
    def is_valid_position_for_drag(
        img_y: int,
        image_height: int,
        cut_lines: list[int],
        exclude_index: int,
        min_gap: int,
    ) -> bool:
        """Verifies if a coordinate satisfies gap constraints excluding a specific cut line index."""
        if img_y < min_gap or img_y > image_height - min_gap:
            return False
        for i, existing_y in enumerate(cut_lines):
            if i == exclude_index:
                continue
            if abs(img_y - existing_y) < min_gap:
                return False
        return True

    @staticmethod
    def validate_cut_lines(
        cut_lines: list[int], image_height: int, min_gap: int
    ) -> None:
        """Validates a list of cut lines against image boundaries and mutual spacing constraints."""
        sorted_cuts = sorted(cut_lines)
        for i, cut in enumerate(sorted_cuts):
            if cut < min_gap or cut > image_height - min_gap:
                raise InvalidStateError(
                    f"Cut line at Y={cut} violates top/bottom margin constraint of {min_gap}px",
                    cut_y=cut,
                )
            if i > 0 and (cut - sorted_cuts[i - 1]) < min_gap:
                raise InvalidStateError(
                    f"Cut line at Y={cut} is too close to adjacent cut line at Y={sorted_cuts[i - 1]} (minimum gap is {min_gap}px)",
                    cut_y=cut,
                )

    @staticmethod
    def get_intersecting_cut(bounds: Bounds, cut_lines: list[int]) -> int | None:
        """Determines if any cut line intersects with the component bounds."""
        for cut in cut_lines:
            if bounds.top <= cut <= bounds.bottom:
                return cut
        return None
