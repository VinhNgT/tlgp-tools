"""Geometry-aware layout sorting for auto-numbering annotation boxes.

This module provides a scale-independent algorithm that sorts boxes into
natural reading order (top-to-bottom rows, left-to-right within rows)
using vertical overlap ratios and connected-component clustering.

Key design properties:
- Zero rendering dependencies — does not import annotation_renderer.
- Scale-consistent — overlap ratios are dimensionless, producing identical
  grouping at any nesting depth. This mirrors how the font/border scaling
  system produces visually identical results after cropping + upscaling.
- Mixed-height aware — correctly groups boxes of different heights in the
  same visual row.
- Transitive — if A overlaps B and B overlaps C, all three are grouped
  even if A doesn't directly overlap C.
"""

from typing import List
from tlgp_annotation_tool.models import AnnotationBox

# Minimum vertical overlap ratio (relative to the smaller box's height)
# for two boxes to be considered on the same row.
ROW_OVERLAP_THRESHOLD = 0.5


# ── Overlap Ratio ──────────────────────────────────────────────────────

def _compute_overlap_ratio(a: AnnotationBox, b: AnnotationBox) -> float:
    """Compute the vertical overlap between two boxes as a ratio.

    Returns the overlap distance divided by the smaller box's height.
    Returns 0.0 if there is no overlap or either box has zero height.
    """
    overlap = min(a.bottom, b.bottom) - max(a.top, b.top)
    if overlap <= 0:
        return 0.0

    min_height = min(a.height, b.height)
    if min_height <= 0:
        return 0.0

    return overlap / min_height


# ── Union-Find ─────────────────────────────────────────────────────────

class _UnionFind:
    """Lightweight union-find (disjoint set) data structure."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Union by rank
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ── Row Grouping ──────────────────────────────────────────────────────

def _build_row_groups(
    boxes: List[AnnotationBox],
    threshold: float = ROW_OVERLAP_THRESHOLD,
) -> List[List[AnnotationBox]]:
    """Group boxes into rows using vertical overlap and connected components.

    Two boxes are considered to be on the same row if their vertical overlap
    ratio (relative to the smaller box's height) is >= threshold.

    Returns a list of row groups. Each group is sorted left-to-right.
    The row list itself is sorted top-to-bottom by median vertical center.
    """
    n = len(boxes)
    if n == 0:
        return []
    if n == 1:
        return [list(boxes)]

    # Build adjacency via union-find
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            ratio = _compute_overlap_ratio(boxes[i], boxes[j])
            if ratio >= threshold:
                uf.union(i, j)

    # Collect connected components
    groups: dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)

    # Build row groups with actual box references
    row_groups: List[List[AnnotationBox]] = []
    for indices in groups.values():
        row = [boxes[i] for i in indices]
        # Sort within each row left-to-right
        row.sort(key=lambda b: b.left)
        row_groups.append(row)

    # Sort rows top-to-bottom by median vertical center
    def row_median_center(row: List[AnnotationBox]) -> float:
        centers = sorted((b.top + b.bottom) / 2 for b in row)
        mid = len(centers) // 2
        if len(centers) % 2 == 0:
            return (centers[mid - 1] + centers[mid]) / 2
        return centers[mid]

    row_groups.sort(key=row_median_center)
    return row_groups


# ── Public API ─────────────────────────────────────────────────────────

def sort_boxes_reading_order(boxes: List[AnnotationBox]) -> List[AnnotationBox]:
    """Sort boxes into natural reading order (row-major).

    Returns a new flat list sorted top-to-bottom by row, left-to-right
    within each row. The original list is not modified.
    """
    if len(boxes) <= 1:
        return list(boxes)

    row_groups = _build_row_groups(boxes)
    result: List[AnnotationBox] = []
    for row in row_groups:
        result.extend(row)
    return result


def sort_and_renumber_recursive(boxes: List[AnnotationBox]) -> None:
    """Sort boxes in-place using reading order, renumber 1..N, and recurse.

    This mirrors the recursive structure of the export pipeline
    (_export_level_images) and the rendering pipeline
    (draw_annotations_on_image), ensuring that the numbering order
    is consistent with what appears in the exported images.
    """
    if not boxes:
        return

    sorted_boxes = sort_boxes_reading_order(boxes)

    # Update the input list in-place
    boxes.clear()
    boxes.extend(sorted_boxes)

    # Renumber and recurse into children
    for i, box in enumerate(boxes):
        box.id = i + 1
        if box.children:
            sort_and_renumber_recursive(box.children)
