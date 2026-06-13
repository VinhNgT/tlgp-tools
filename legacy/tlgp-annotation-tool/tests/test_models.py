"""Tests for AnnotationBox model properties and serialization."""

from tlgp_annotation_tool.models import AnnotationBox, ScreenSession

# ── Property Accessors ────────────────────────────────────────────────


class TestAnnotationBoxProperties:
    def test_width_height(self):
        box = AnnotationBox(id=1, label="A", x1=10, y1=20, x2=110, y2=70)
        assert box.width == 100
        assert box.height == 50

    def test_width_height_with_reversed_coords(self):
        """Coords may be reversed (x2 < x1); width/height use abs()."""
        box = AnnotationBox(id=1, label="A", x1=110, y1=70, x2=10, y2=20)
        assert box.width == 100
        assert box.height == 50

    def test_left_top_right_bottom_normalized(self):
        box = AnnotationBox(id=1, label="A", x1=110, y1=70, x2=10, y2=20)
        assert box.left == 10
        assert box.top == 20
        assert box.right == 110
        assert box.bottom == 70

    def test_bounds_dict(self):
        box = AnnotationBox(id=1, label="A", x1=10, y1=20, x2=110, y2=70)
        assert box.bounds == {"x": 10, "y": 20, "w": 100, "h": 50}

    def test_bounds_tuple(self):
        box = AnnotationBox(id=1, label="A", x1=10, y1=20, x2=110, y2=70)
        assert box.bounds_tuple == (10, 20, 110, 70)

    def test_zero_size_box(self):
        box = AnnotationBox(id=1, label="A", x1=50, y1=50, x2=50, y2=50)
        assert box.width == 0
        assert box.height == 0


# ── Serialization ─────────────────────────────────────────────────────


class TestAnnotationBoxSerialization:
    def test_to_dict_simple(self):
        box = AnnotationBox(id=1, label="Test", x1=10, y1=20, x2=110, y2=70)
        d = box.to_dict()
        assert d["id"] == 1
        assert d["label"] == "Test"
        assert d["bounds"] == {"x": 10, "y": 20, "w": 100, "h": 50}
        assert d["pill_corner"] == "top_left"
        assert "children" not in d

    def test_to_dict_with_parent_offset(self):
        """Coordinates in to_dict are relative to parent."""
        box = AnnotationBox(id=1, label="Child", x1=50, y1=60, x2=150, y2=110)
        d = box.to_dict(parent_x=30, parent_y=40)
        assert d["bounds"]["x"] == 20  # 50 - 30
        assert d["bounds"]["y"] == 20  # 60 - 40

    def test_to_dict_with_children(self):
        child = AnnotationBox(id=1, label="C1", x1=20, y1=20, x2=80, y2=80)
        parent = AnnotationBox(
            id=1,
            label="Parent",
            x1=10,
            y1=10,
            x2=100,
            y2=100,
            children=[child],
        )
        d = parent.to_dict()
        assert "children" in d
        assert len(d["children"]) == 1
        # Child coords are relative to parent's left/top
        child_d = d["children"][0]
        assert child_d["bounds"]["x"] == 10  # 20 - 10
        assert child_d["bounds"]["y"] == 10  # 20 - 10

    def test_to_dict_recursive_nesting(self):
        grandchild = AnnotationBox(id=1, label="GC", x1=30, y1=30, x2=50, y2=50)
        child = AnnotationBox(
            id=1,
            label="C",
            x1=20,
            y1=20,
            x2=80,
            y2=80,
            children=[grandchild],
        )
        parent = AnnotationBox(
            id=1,
            label="P",
            x1=10,
            y1=10,
            x2=100,
            y2=100,
            children=[child],
        )
        d = parent.to_dict()
        gc_d = d["children"][0]["children"][0]
        # Grandchild relative to child (left=20, top=20)
        assert gc_d["bounds"]["x"] == 10  # 30 - 20
        assert gc_d["bounds"]["y"] == 10  # 30 - 20


# ── has_descendants ───────────────────────────────────────────────────


class TestHasDescendants:
    def test_no_children(self):
        box = AnnotationBox(id=1, label="A", x1=0, y1=0, x2=100, y2=100)
        assert box.has_descendants() is False

    def test_direct_children(self):
        child = AnnotationBox(id=1, label="C", x1=0, y1=0, x2=50, y2=50)
        parent = AnnotationBox(
            id=1,
            label="P",
            x1=0,
            y1=0,
            x2=100,
            y2=100,
            children=[child],
        )
        assert parent.has_descendants() is True

    def test_pill_corner_default(self):
        box = AnnotationBox(id=1, label="A", x1=0, y1=0, x2=100, y2=100)
        assert box.pill_corner == "top_left"

    def test_custom_pill_corner(self):
        box = AnnotationBox(
            id=1,
            label="A",
            x1=0,
            y1=0,
            x2=100,
            y2=100,
            pill_corner="bottom_right",
        )
        assert box.pill_corner == "bottom_right"


# ── ScreenSession ─────────────────────────────────────────────────────


class TestScreenSession:
    def test_default_values(self):
        session = ScreenSession()
        assert session.screen_name == ""
        assert session.description == ""
        assert session.original_image is None
        assert session.components == []
        assert session.cut_lines == []

    def test_custom_values(self):
        session = ScreenSession(
            screen_name="Product Detail",
            description="A test screen",
            cut_lines=[300, 700],
        )
        assert session.screen_name == "Product Detail"
        assert session.cut_lines == [300, 700]
