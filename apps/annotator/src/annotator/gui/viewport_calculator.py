"""Viewport calculator for determining zoom and pan values to fit components."""


from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Component


class ViewportCalculator:
    """Pure static logic for calculating viewport fits without mutating state."""

    @staticmethod
    def calculate_fit(
        vw: int,
        vh: int,
        target_comp: Component | None,
        img_w: int,
        img_h: int,
        ctx: ViewportContext,
        transformer: ViewportTransformer,
    ) -> tuple[float, float, float]:
        """Calculates new zoom and pan_offset to fit the target or image."""
        if target_comp:
            bw = target_comp.bounds.w
            has_cuts = transformer.has_active_cuts_ctx(ctx)
            gap_top = transformer.gap_offset_for_y(target_comp.bounds.top) if has_cuts else 0
            gap_bottom = transformer.gap_offset_for_y(target_comp.bounds.bottom) if has_cuts else 0

            visual_top = target_comp.bounds.top + gap_top
            visual_bottom = target_comp.bounds.bottom + gap_bottom
            visual_h = visual_bottom - visual_top

            zoom_x = (vw - 120) / bw if bw > 0 else 1.0
            zoom_y = (vh - 120) / visual_h if visual_h > 0 else 1.0
            new_zoom = max(0.1, min(4.0, min(zoom_x, zoom_y)))
            pad_x = (vw / 2) - (target_comp.bounds.left + bw / 2) * new_zoom
            pad_y = (vh / 2) - ((visual_top + visual_bottom) / 2) * new_zoom
            return new_zoom, pad_x, pad_y
        else:
            has_cuts = transformer.has_active_cuts_ctx(ctx)
            num_cuts = len(ctx.cut_lines)
            total_h = img_h + num_cuts * transformer.cut_gap_px if has_cuts else img_h

            zoom_x = (vw - 40) / img_w if img_w > 0 else 1.0
            zoom_y = (vh - 40) / total_h if total_h > 0 else 1.0
            new_zoom = max(0.1, min(1.0, min(zoom_x, zoom_y)))
            pad_x = (vw - img_w * new_zoom) / 2
            pad_y = (vh - total_h * new_zoom) / 2
            return new_zoom, pad_x, pad_y

