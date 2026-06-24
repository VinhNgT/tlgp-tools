"""Canvas rendering pipeline extraction."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen

from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Component
from annotator.rendering import (
    compute_border_widths,
    compute_pill_font_size,
    compute_pill_padding,
    get_pill_coords,
)


@dataclass(frozen=True)
class CanvasRenderState:
    """Parameters required for a single frame render."""

    viewport_ctx: ViewportContext
    active_comps: list[Component]
    selected_ids: list[UUID]
    active_interaction: dict[UUID, Any] | None
    is_dragging: bool
    resize_handle: str | None
    show_labels: bool
    temp_rect: Any | None
    parent_comp: Component | None
    full_img_width: int
    children_bounds_union: tuple[float, float, float, float] | None


class CanvasRenderer:
    """Stateless rendering pipeline for the canvas."""

    def __init__(self, transformer: ViewportTransformer):
        self.transformer = transformer

    def paint_parent_mask(
        self, p: QPainter, state: CanvasRenderState, base_pixmap: Any
    ):
        """Paints the dark overlay masking out non-parent components."""
        if not state.parent_comp or not base_pixmap:
            return

        ctx = state.viewport_ctx
        zoom = ctx.zoom_factor
        pan_x, pan_y = ctx.pan_offset

        src_w = base_pixmap.width()
        src_h = base_pixmap.height()
        target_rect = QRectF(pan_x, pan_y, src_w * zoom, src_h * zoom)
        source_rect = QRectF(0, 0, src_w, src_h)

        # Draw the full image darkened
        p.setOpacity(0.4)
        p.drawPixmap(target_rect, base_pixmap, source_rect)
        p.setOpacity(1.0)

        # Compute parent region in canvas coordinates
        gap = (
            self.transformer.gap_offset_for_y(state.parent_comp.bounds.top)
            if self.transformer.has_active_cuts_ctx(ctx)
            else 0
        )
        px1 = state.parent_comp.bounds.left
        py1 = state.parent_comp.bounds.top + gap
        px2 = state.parent_comp.bounds.right
        py2 = state.parent_comp.bounds.bottom + gap

        # Redraw the parent region at full brightness
        parent_target = QRectF(
            pan_x + px1 * zoom,
            pan_y + py1 * zoom,
            (px2 - px1) * zoom,
            (py2 - py1) * zoom,
        )
        parent_source = QRectF(px1, py1, px2 - px1, py2 - py1)
        p.drawPixmap(parent_target, base_pixmap, parent_source)

    def paint_annotations(self, p: QPainter, state: CanvasRenderState, font: QFont):
        """Paints annotation boxes, pills, labels, and interaction overlays."""
        if not state.active_comps:
            return

        ctx = state.viewport_ctx
        zoom = ctx.zoom_factor

        font_size = compute_pill_font_size(state.parent_comp, state.full_img_width)
        abs_box_border, abs_pill_outline = compute_border_widths(
            state.parent_comp, state.full_img_width
        )

        pill_font_size = max(4, round(font_size * zoom))
        qfont = QFont(font)
        qfont.setPixelSize(pill_font_size)
        qfont.setBold(True)
        fm = QFontMetrics(qfont)

        scaled_pad_x, scaled_pad_y = compute_pill_padding(pill_font_size)
        border_width = max(1, round(abs_box_border * zoom))
        pill_outline_width = max(1, round(abs_pill_outline * zoom))

        inactive_color = Qt.GlobalColor.darkGray
        box_pen = QPen(inactive_color, border_width)
        box_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pill_outline_pen = QPen(inactive_color, pill_outline_width)
        pill_outline_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pill_text_pen = QPen(inactive_color)

        non_selected = [c for c in state.active_comps if c.id not in state.selected_ids]
        selected = [c for c in state.active_comps if c.id in state.selected_ids]
        ordered_comps = non_selected + selected

        # Draw child bounds union overlay if resizing
        if len(selected) == 1 and state.resize_handle and state.is_dragging:
            union = state.children_bounds_union
            if union:
                cx1, cy1, cx2, cy2 = union
                gcx1, gcy1 = self.transformer.to_canvas_ctx(cx1, cy1, ctx)
                gcx2, gcy2 = self.transformer.to_canvas_ctx(cx2, cy2, ctx)
                overlay_color = Qt.GlobalColor.darkGray
                dash_pen = QPen(overlay_color, 2)
                dash_pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(dash_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)

                lw = border_width + 1
                inset = float(lw)
                max_w_inset = max(0.0, (gcx2 - gcx1 - 2.0) / 2.0)
                max_h_inset = max(0.0, (gcy2 - gcy1 - 2.0) / 2.0)
                actual_inset = min(inset, max_w_inset, max_h_inset)

                p.drawRect(
                    QRectF(
                        gcx1 + actual_inset + 1.0,
                        gcy1 + actual_inset + 1.0,
                        gcx2 - gcx1 - 2 * actual_inset - 2.0,
                        gcy2 - gcy1 - 2 * actual_inset - 2.0,
                    )
                )

                overlay_font = QFont(font)
                overlay_font.setBold(True)
                overlay_font.setItalic(True)
                p.setFont(overlay_font)
                p.setPen(QPen(overlay_color))
                p.drawText(
                    QPointF(gcx1 + actual_inset + 4, gcy1 + actual_inset + 13),
                    "Child Bounds",
                )

        for comp in ordered_comps:
            is_selected = comp.id in state.selected_ids
            comp_color = QColor("#0c8ce9") if is_selected else QColor("#ff4444")
            pill_fill_col = QColor("#FFFFFF")

            lw = border_width + 1 if is_selected else border_width
            box_pen.setColor(comp_color)
            box_pen.setWidth(lw)
            box_pen.setStyle(Qt.PenStyle.SolidLine)

            pill_outline_pen.setColor(comp_color)
            pill_text_pen.setColor(comp_color)

            bounds = comp.bounds
            if state.active_interaction and comp.id in state.active_interaction:
                bounds = state.active_interaction[comp.id]

            cx1, cy1 = self.transformer.to_canvas_ctx(bounds.left, bounds.top, ctx)
            cx2, cy2 = self.transformer.to_canvas_ctx(bounds.right, bounds.bottom, ctx)

            # Box border
            p.setPen(box_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            half_lw = lw / 2.0
            p.drawRect(
                QRectF(cx1 + half_lw, cy1 + half_lw, cx2 - cx1 - lw, cy2 - cy1 - lw)
            )

            # Number pill
            num_str = comp.number
            ref_tw = fm.horizontalAdvance("99")
            ref_th = fm.height()
            pill_size = max(ref_tw + scaled_pad_x, ref_th + scaled_pad_y)
            pill_w = pill_h = pill_size

            pill_corner = comp.style.pillCorner
            pill_x, pill_y = get_pill_coords(
                cx1, cy1, cx2, cy2, pill_w, pill_h, pill_corner
            )

            p.setPen(pill_outline_pen)
            p.setBrush(QBrush(pill_fill_col))
            half_pow = pill_outline_width / 2.0
            p.drawRect(
                QRectF(
                    pill_x + half_pow,
                    pill_y + half_pow,
                    pill_w - pill_outline_width,
                    pill_h - pill_outline_width,
                )
            )

            # Pill text
            p.setFont(qfont)
            p.setPen(pill_text_pen)
            p.drawText(
                QRectF(pill_x, pill_y, pill_w, pill_h),
                Qt.AlignmentFlag.AlignCenter,
                num_str,
            )

            if state.show_labels and comp.label:
                lbl_font = QFont(font)
                p.setFont(lbl_font)
                p.setPen(QPen(comp_color))
                p.drawText(QPointF(cx1, cy2 + 13), comp.label)

            # Selection handles
            if is_selected:
                self._paint_handles(
                    p, cx1 + half_lw, cy1 + half_lw, cx2 - half_lw, cy2 - half_lw
                )

    def _paint_handles(
        self, p: QPainter, cx1: float, cy1: float, cx2: float, cy2: float
    ):
        mx = (cx1 + cx2) / 2
        my = (cy1 + cy2) / 2
        hs = 5
        handles = [
            (cx1, cy1),
            (mx, cy1),
            (cx2, cy1),
            (cx1, my),
            (cx2, my),
            (cx1, cy2),
            (mx, cy2),
            (cx2, cy2),
        ]

        # We hardcode highlight color here to avoid passing palette, it's roughly this Qt role
        p.setPen(QPen(QColor(0, 120, 215), 1))  # standard highlight
        p.setBrush(QBrush(QColor("#FFFFFF")))
        for hx, hy in handles:
            p.drawRect(QRectF(hx - hs, hy - hs, hs * 2, hs * 2))

    def paint_temp_rect(self, p: QPainter, temp_rect: Any):
        """Paints the drag selection or draw marquee."""
        if not temp_rect:
            return
        w = temp_rect.width
        pen = QPen(QColor(temp_rect.color), w)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        if temp_rect.dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        x1 = min(temp_rect.x1, temp_rect.x2)
        x2 = max(temp_rect.x1, temp_rect.x2)
        y1 = min(temp_rect.y1, temp_rect.y2)
        y2 = max(temp_rect.y1, temp_rect.y2)
        half_w = w / 2.0
        p.drawRect(
            QRectF(
                x1 + half_w,
                y1 + half_w,
                (x2 - x1) - w,
                (y2 - y1) - w,
            )
        )
