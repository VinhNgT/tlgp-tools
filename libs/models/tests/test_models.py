from uuid import uuid4

import pytest
from models import (
    Bounds,
    Component,
    ScreenInfo,
    Style,
    TreeUtils,
    Visibility,
    WorkspaceState,
)
from pydantic import ValidationError


def test_bounds_validation():
    # Valid bounds
    b = Bounds(x=10, y=20, w=100, h=150)
    assert b.x == 10
    assert b.y == 20
    assert b.w == 100
    assert b.h == 150
    assert b.left == 10
    assert b.right == 110
    assert b.top == 20
    assert b.bottom == 170

    # Width too small
    with pytest.raises(ValidationError):
        Bounds(x=10, y=20, w=3, h=150)

    # Height too small
    with pytest.raises(ValidationError):
        Bounds(x=10, y=20, w=100, h=3)


def test_visibility_defaults():
    v = Visibility()
    assert v.visible is True
    assert v.locked is False


def test_component_defaults():
    cid = uuid4()
    bounds = Bounds(x=0, y=0, w=50, h=50)
    comp = Component(id=cid, number="1", label="Button", bounds=bounds)

    assert comp.id == cid
    assert comp.number == "1"
    assert comp.label == "Button"
    assert comp.parentId is None
    assert comp.childrenIds == []
    assert comp.bounds == bounds
    assert isinstance(comp.style, Style)
    assert comp.style.pillCorner == "top_left"
    assert isinstance(comp.visibility, Visibility)
    assert comp.visibility.visible is True
    assert comp.visibility.locked is False
    assert comp.metadata == {}


def test_workspace_state_defaults():
    sid = uuid4()
    state = WorkspaceState(sessionId=sid)
    assert state.version == 1
    assert state.sessionId == sid
    assert state.revision == 0
    assert state.readOnly is False
    assert isinstance(state.screen, ScreenInfo)
    assert state.image is None
    assert state.cutLines == []
    assert state.rootComponents == []
    assert state.components == {}


def test_tree_utils_get_children():
    sid = uuid4()
    root_id = uuid4()
    child_id = uuid4()

    root_comp = Component(
        id=root_id,
        number="1",
        label="Root",
        bounds=Bounds(x=0, y=0, w=100, h=100),
        childrenIds=[child_id],
    )
    child_comp = Component(
        id=child_id,
        number="1.1",
        label="Child",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        parentId=root_id,
    )

    state = WorkspaceState(
        sessionId=sid,
        rootComponents=[root_id],
        components={root_id: root_comp, child_id: child_comp},
    )

    # Test root components retrieval
    roots = TreeUtils.get_children(state, None)
    assert len(roots) == 1
    assert roots[0].id == root_id

    # Test child components retrieval
    children = TreeUtils.get_children(state, root_id)
    assert len(children) == 1
    assert children[0].id == child_id

    # Test non-existent parent ID
    assert TreeUtils.get_children(state, uuid4()) == []


def test_tree_utils_walk_dfs():
    sid = uuid4()
    c1 = uuid4()
    c2 = uuid4()
    c3 = uuid4()

    comp1 = Component(
        id=c1,
        number="1",
        label="C1",
        bounds=Bounds(x=0, y=0, w=100, h=100),
        childrenIds=[c2, c3],
    )
    comp2 = Component(
        id=c2,
        number="1.1",
        label="C2",
        bounds=Bounds(x=10, y=10, w=40, h=40),
        parentId=c1,
    )
    comp3 = Component(
        id=c3,
        number="1.2",
        label="C3",
        bounds=Bounds(x=50, y=50, w=40, h=40),
        parentId=c1,
    )

    state = WorkspaceState(
        sessionId=sid,
        rootComponents=[c1],
        components={c1: comp1, c2: comp2, c3: comp3},
    )

    # Walk from root
    walked = list(TreeUtils.walk_dfs(state))
    assert len(walked) == 3
    assert walked[0].id == c1
    assert walked[1].id == c2
    assert walked[2].id == c3


def test_tree_utils_has_descendants():
    sid = uuid4()
    c1 = uuid4()
    c2 = uuid4()

    comp1 = Component(
        id=c1,
        number="1",
        label="C1",
        bounds=Bounds(x=0, y=0, w=100, h=100),
        childrenIds=[c2],
    )
    comp2 = Component(
        id=c2,
        number="1.1",
        label="C2",
        bounds=Bounds(x=10, y=10, w=40, h=40),
        parentId=c1,
    )

    state = WorkspaceState(
        sessionId=sid,
        rootComponents=[c1],
        components={c1: comp1, c2: comp2},
    )

    assert TreeUtils.has_descendants(state, c1) is True
    assert TreeUtils.has_descendants(state, c2) is False
    assert TreeUtils.has_descendants(state, uuid4()) is False
