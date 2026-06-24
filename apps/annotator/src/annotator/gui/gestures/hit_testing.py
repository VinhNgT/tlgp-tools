"""Hit testing utilities for components and handles."""

from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Component


class HitTester:
    """Pure functions for collision detection."""

    @staticmethod
    def get_hit_boxes(
        cx: float,
        cy: float,
        components: list[Component],
        ctx: ViewportContext,
        transformer: ViewportTransformer,
    ) -> list[Component]:
        """Calculates a list of all visible components intersected by absolute coordinates."""
        hit = []
        for box in components:
            bx1, by1 = transformer.to_canvas_ctx(box.bounds.left, box.bounds.top, ctx)
            bx2, by2 = transformer.to_canvas_ctx(
                box.bounds.right, box.bounds.bottom, ctx
            )
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                hit.append(box)
        return hit

    @staticmethod
    def hit_box(
        cx: float,
        cy: float,
        components: list[Component],
        selected_boxes: list[Component],
        ctx: ViewportContext,
        transformer: ViewportTransformer,
    ) -> Component | None:
        """Identifies intersected component, sorting with selected box priorities for cycling."""
        boxes = HitTester.get_hit_boxes(cx, cy, components, ctx, transformer)
        if not boxes:
            return None
        selected = [b for b in boxes if b in selected_boxes]
        non_selected = [b for b in boxes if b not in selected_boxes]
        ordered = non_selected + selected
        return ordered[-1] if ordered else None

    @staticmethod
    def hit_handle(
        cx: float,
        cy: float,
        selected_boxes: list[Component],
        ctx: ViewportContext,
        transformer: ViewportTransformer,
        border_width: float = 0,
    ) -> str | None:
        """Hit tests resize handles of the currently selected component."""
        if len(selected_boxes) != 1:
            return None

        box = selected_boxes[0]
        bx1, by1 = transformer.to_canvas_ctx(box.bounds.left, box.bounds.top, ctx)
        bx2, by2 = transformer.to_canvas_ctx(box.bounds.right, box.bounds.bottom, ctx)

        half_lw = border_width / 2.0
        bx1 += half_lw
        by1 += half_lw
        bx2 -= half_lw
        by2 -= half_lw

        mx = (bx1 + bx2) / 2
        my = (by1 + by2) / 2
        hs = 5

        handles = {
            "nw": (bx1, by1),
            "n": (mx, by1),
            "ne": (bx2, by1),
            "w": (bx1, my),
            "e": (bx2, my),
            "sw": (bx1, by2),
            "s": (mx, by2),
            "se": (bx2, by2),
        }

        for name, (hx, hy) in handles.items():
            if hx - hs <= cx <= hx + hs and hy - hs <= cy <= hy + hs:
                return name
        return None
