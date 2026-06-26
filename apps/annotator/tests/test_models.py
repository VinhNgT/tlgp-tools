"""Tests for annotator.models (Bounds, Component, WorkspaceState, TreeUtils)."""

import uuid

import pydantic
import pytest
from annotator.models import Bounds, Component, Style, WorkspaceState
from tlgp_contracts import TreeUtils

# ── Bounds ─────────────────────────────────────────────────────────────


class TestBounds:
    def test_left_top_right_bottom(self):
        b = Bounds(x=10, y=20, w=100, h=50)
        assert b.left == 10
        assert b.top == 20
        assert b.right == 110
        assert b.bottom == 70

    def test_minimum_size_constraint(self):
        with pytest.raises(pydantic.ValidationError):
            Bounds(**{"x": 0, "y": 0, "w": 3, "h": 10})
        with pytest.raises(pydantic.ValidationError):
            Bounds(**{"x": 0, "y": 0, "w": 10, "h": 3})

    def test_serialization_roundtrip(self):
        b = Bounds(x=5, y=10, w=100, h=200)
        data = b.model_dump()
        restored = Bounds.model_validate(data)
        assert restored.x == b.x
        assert restored.w == b.w


# ── Component ──────────────────────────────────────────────────────────


class TestComponent:
    def test_default_fields(self):
        comp = Component(
            id=uuid.uuid4(),
            number="1",
            label="Test",
            bounds=Bounds(x=0, y=0, w=100, h=100),
        )
        assert comp.parentId is None
        assert comp.childrenIds == []
        assert comp.style.pillCorner == "top_left"

    def test_custom_style(self):
        comp = Component(
            id=uuid.uuid4(),
            number="2",
            label="Styled",
            bounds=Bounds(x=0, y=0, w=50, h=50),
            style=Style(pillCorner="bottom_right"),
        )
        assert comp.style.pillCorner == "bottom_right"


# ── WorkspaceState ─────────────────────────────────────────────────────


class TestWorkspaceState:
    def test_default_state(self):
        sid = uuid.uuid4()
        state = WorkspaceState(workspaceId=sid)
        assert state.version == 1
        assert state.revision == 0
        assert state.readOnly is False
        assert state.image is None
        assert state.cutLines == []
        assert state.rootComponents == []
        assert state.components == {}

    def test_serialization_roundtrip(self):
        sid = uuid.uuid4()
        comp_id = uuid.uuid4()
        state = WorkspaceState(
            workspaceId=sid,
            components={
                comp_id: Component(
                    id=comp_id,
                    number="1",
                    label="Root",
                    bounds=Bounds(x=0, y=0, w=100, h=100),
                )
            },
            rootComponents=[comp_id],
        )
        data = state.model_dump(mode="json")
        restored = WorkspaceState.model_validate(data)
        assert restored.workspaceId == sid
        assert comp_id in restored.components
        assert restored.components[comp_id].label == "Root"


# ── TreeUtils ──────────────────────────────────────────────────────────


class TestTreeUtils:
    def _make_state_with_tree(self):
        """Create a state with root → child → grandchild structure."""
        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        grandchild_id = uuid.uuid4()

        grandchild = Component(
            id=grandchild_id,
            number="",
            label="Grandchild",
            parentId=child_id,
            bounds=Bounds(x=30, y=30, w=20, h=20),
        )
        child = Component(
            id=child_id,
            number="",
            label="Child",
            parentId=root_id,
            childrenIds=[grandchild_id],
            bounds=Bounds(x=10, y=10, w=80, h=80),
        )
        root = Component(
            id=root_id,
            number="",
            label="Root",
            childrenIds=[child_id],
            bounds=Bounds(x=0, y=0, w=200, h=200),
        )

        state = WorkspaceState(
            workspaceId=uuid.uuid4(),
            components={root_id: root, child_id: child, grandchild_id: grandchild},
            rootComponents=[root_id],
        )
        return state, root_id, child_id, grandchild_id

    def test_get_children_root_level(self):
        state, root_id, _, _ = self._make_state_with_tree()
        children = TreeUtils.get_children(state, None)
        assert len(children) == 1
        assert children[0].id == root_id

    def test_get_children_of_parent(self):
        state, root_id, child_id, _ = self._make_state_with_tree()
        children = TreeUtils.get_children(state, root_id)
        assert len(children) == 1
        assert children[0].id == child_id

    def test_get_children_missing_parent(self):
        state, _, _, _ = self._make_state_with_tree()
        children = TreeUtils.get_children(state, uuid.uuid4())
        assert children == []

    def test_walk_dfs(self):
        state, root_id, child_id, grandchild_id = self._make_state_with_tree()
        walked = list(TreeUtils.walk_dfs(state))
        assert len(walked) == 3
        ids = [c.id for c in walked]
        assert ids == [root_id, child_id, grandchild_id]

    def test_has_children(self):
        state, root_id, child_id, grandchild_id = self._make_state_with_tree()
        assert TreeUtils.has_children(state, root_id) is True
        assert TreeUtils.has_children(state, child_id) is True
        assert TreeUtils.has_children(state, grandchild_id) is False

    def test_has_children_missing_component(self):
        state, _, _, _ = self._make_state_with_tree()
        assert TreeUtils.has_children(state, uuid.uuid4()) is False
