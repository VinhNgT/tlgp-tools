from uuid import UUID

from .viewport_context import ViewportContext

CUT_GAP_PX = 20


class ViewportTransformer:
    """Manages display coordinate mapping (including zoom and gap offsets)."""

    def __init__(self, cut_gap_px: int = CUT_GAP_PX):
        self.cut_gap_px = cut_gap_px
        self._segments: list[tuple[int, int, int]] = []
        self._image_width = 0
        self._image_height = 0

    def update_image_size(self, width: int, height: int):
        self._image_width = width
        self._image_height = height

    def rebuild_segments(self, cut_lines: list[int]):
        """Recomputes segment lists mapping raw Y boundaries to gap-shifted display coordinates."""
        if self._image_height <= 0:
            self._segments = []
            return

        # Filter out edge cuts at the boundaries (0 and image_height) as they are redundant
        active_cuts = [y for y in sorted(cut_lines) if 0 < y < self._image_height]

        if not active_cuts:
            self._segments = [(0, self._image_height, 0)]
            return

        segments = []
        prev_y = 0
        valid_cut_count = 0
        for cut_y in active_cuts:
            if cut_y > prev_y:
                segments.append((prev_y, cut_y, valid_cut_count * self.cut_gap_px))
                valid_cut_count += 1
                prev_y = cut_y

        if prev_y < self._image_height:
            segments.append(
                (prev_y, self._image_height, valid_cut_count * self.cut_gap_px)
            )

        self._segments = segments

    def has_active_cuts(self, parent_stack: list[UUID], cut_lines: list[int]) -> bool:
        """Determines if horizontal segment spacing rules are currently visible in the active hierarchy level."""
        # Cut lines and their visual gaps must remain active and visible
        # at all hierarchy levels, including when drilled down into a component.
        return len(cut_lines) > 0

    def gap_offset_for_y(self, abs_y: int) -> int:
        """Calculates cumulative visual gap shift in pixels located above absolute coordinate abs_y."""
        if not self._segments or len(self._segments) <= 1:
            return 0
        for _src_start, src_end, offset in self._segments:
            if abs_y < src_end:
                return offset
        return self._segments[-1][2]

    def gap_offset_inverse(self, display_y: int) -> int:
        """Reverses display shift mapping relative spacing back to absolute raw screenshot coordinates."""
        if not self._segments or len(self._segments) <= 1:
            return display_y
        for _src_start, src_end, offset in self._segments:
            disp_end = src_end + offset
            if display_y < disp_end:
                return display_y - offset
        return display_y - self._segments[-1][2]

    def get_segment_y_bounds(
        self,
        abs_y: int,
        parent_stack: list[UUID],
        cut_lines: list[int],
        boundary: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        """Returns visual bounding box limits of the active horizontal segment strip containing y coordinate."""
        if not self.has_active_cuts(parent_stack, cut_lines) or not self._segments:
            _, by1, _, by2 = boundary
            return by1, by2

        last_idx = len(self._segments) - 1
        for i, (src_start, src_end, _) in enumerate(self._segments):
            if abs_y < src_end:
                bound = src_end if i == last_idx else src_end - 1
                return src_start, bound
        last = self._segments[-1]
        return last[0], last[1]

    def get_boundary(
        self,
        parent_bounds: tuple[int, int, int, int] | None,
        image_size: tuple[int, int] | None,
    ) -> tuple[int, int, int, int]:
        """Calculates active coordinate bounds constraint corresponding to drill down layers."""
        if parent_bounds:
            return parent_bounds
        if image_size:
            return 0, 0, image_size[0], image_size[1]
        return 0, 0, 99999, 99999

    def to_canvas(
        self,
        abs_x: int,
        abs_y: int,
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
        pan_offset: tuple[float, float] = (0.0, 0.0),
    ) -> tuple[float, float]:
        """Converts absolute raw coordinates to visual canvas space."""
        pan_x, pan_y = pan_offset
        gap_y = (
            self.gap_offset_for_y(abs_y)
            if self.has_active_cuts(parent_stack, cut_lines)
            else 0
        )
        return (
            abs_x * zoom_factor + pan_x,
            (abs_y + gap_y) * zoom_factor + pan_y,
        )

    def to_abs(
        self,
        cx: float,
        cy: float,
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
        pan_offset: tuple[float, float] = (0.0, 0.0),
    ) -> tuple[int, int]:
        """Translates canvas visual coordinates to absolute raw screenshot coordinates."""
        pan_x, pan_y = pan_offset
        raw_x = round((cx - pan_x) / zoom_factor)
        raw_y = round((cy - pan_y) / zoom_factor)
        if self.has_active_cuts(parent_stack, cut_lines):
            raw_y = self.gap_offset_inverse(raw_y)
        return raw_x, raw_y

    # ── ViewportContext convenience methods ──────────────────────────

    def to_canvas_ctx(
        self, abs_x: int, abs_y: int, ctx: ViewportContext
    ) -> tuple[float, float]:
        """Converts absolute raw coordinates to visual canvas space using a ViewportContext."""
        return self.to_canvas(
            abs_x,
            abs_y,
            ctx.zoom_factor,
            list(ctx.parent_stack),
            list(ctx.cut_lines),
            ctx.pan_offset,
        )

    def to_abs_ctx(self, cx: float, cy: float, ctx: ViewportContext) -> tuple[int, int]:
        """Translates canvas visual coordinates to absolute raw coordinates using a ViewportContext."""
        return self.to_abs(
            cx,
            cy,
            ctx.zoom_factor,
            list(ctx.parent_stack),
            list(ctx.cut_lines),
            ctx.pan_offset,
        )

    def has_active_cuts_ctx(self, ctx: ViewportContext) -> bool:
        """Determines if cut-line gap spacing is active using a ViewportContext."""
        return self.has_active_cuts(list(ctx.parent_stack), list(ctx.cut_lines))

    def get_segment_y_bounds_ctx(
        self,
        abs_y: int,
        ctx: ViewportContext,
        boundary: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        """Returns segment Y bounds using a ViewportContext."""
        return self.get_segment_y_bounds(
            abs_y, list(ctx.parent_stack), list(ctx.cut_lines), boundary
        )

    @property
    def segments(self) -> list[tuple[int, int, int]]:
        """Gets the active list of gap-shifted display segments."""
        return self._segments
