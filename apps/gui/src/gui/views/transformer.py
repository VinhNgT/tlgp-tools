from uuid import UUID

from models import WorkspaceState
from PIL import Image, ImageDraw

CUT_GAP_PX = 20


class ViewportTransformer:
    """Manages display coordinate mapping (including zoom and gap offsets) and segment image composition."""

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
        if not cut_lines:
            self._segments = [(0, self._image_height, 0)]
            return

        segments = []
        prev_y = 0
        for i, cut_y in enumerate(sorted(cut_lines)):
            clamped = max(0, min(self._image_height, cut_y))
            if clamped > prev_y:
                segments.append((prev_y, clamped, i * self.cut_gap_px))
            prev_y = clamped

        if prev_y < self._image_height:
            segments.append(
                (prev_y, self._image_height, len(cut_lines) * self.cut_gap_px)
            )

        self._segments = segments

    def has_active_cuts(self, parent_stack: list[UUID], cut_lines: list[int]) -> bool:
        """Determines if horizontal segment spacing rules are currently visible in the active hierarchy level."""
        return not parent_stack and len(cut_lines) > 0

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
        state: WorkspaceState | None,
    ) -> tuple[int, int]:
        """Returns visual bounding box limits of the active horizontal segment strip containing y coordinate."""
        if not self.has_active_cuts(parent_stack, cut_lines) or not self._segments:
            bx1, by1, bx2, by2 = self.get_boundary(parent_stack, state)
            return by1, by2

        last_idx = len(self._segments) - 1
        for i, (src_start, src_end, _) in enumerate(self._segments):
            if abs_y < src_end:
                bound = src_end if i == last_idx else src_end - 1
                return src_start, bound
        last = self._segments[-1]
        return last[0], last[1]

    def get_boundary(
        self, parent_stack: list[UUID], state: WorkspaceState | None
    ) -> tuple[int, int, int, int]:
        """Calculates active coordinate bounds constraint corresponding to drill down layers."""
        if state and state.image:
            parent_id = parent_stack[-1] if parent_stack else None
            parent = state.components.get(parent_id) if parent_id else None
            if parent:
                b = parent.bounds
                return b.left, b.top, b.right, b.bottom
            return 0, 0, state.image.width, state.image.height
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

    def composite_gapped_image(self, src_img: Image.Image) -> Image.Image:
        """Composes segment strips paste separated by visual gap fills."""
        if not self._segments:
            return src_img

        img_w = src_img.width
        total_gap = self._segments[-1][2]
        total_h = src_img.height + total_gap

        composite = Image.new("RGB", (img_w, total_h), (30, 30, 30))

        for src_start, src_end, display_offset in self._segments:
            seg_h = src_end - src_start
            if seg_h <= 0:
                continue
            seg_strip = src_img.crop((0, src_start, img_w, src_end))
            dest_y = src_start + display_offset
            composite.paste(seg_strip, (0, dest_y))

        draw = ImageDraw.Draw(composite)
        for i in range(1, len(self._segments)):
            _, prev_end, _ = self._segments[i - 1]
            gap_start_y = prev_end + self._segments[i - 1][2]
            gap_mid_y = gap_start_y + self.cut_gap_px // 2

            dash_len = 12
            gap_len = 8
            x = 0
            while x < img_w:
                x_end = min(x + dash_len, img_w)
                draw.line(
                    [(x, gap_mid_y), (x_end, gap_mid_y)],
                    fill=(100, 100, 100),
                    width=2,
                )
                x += dash_len + gap_len

        return composite
