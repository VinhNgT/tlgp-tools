import uuid

import pytest
from pydantic import ValidationError
from tlgp_contracts.workspace import Bounds, Component, WorkspaceState


def test_bounds_computed_properties():
    bounds = Bounds(x=10, y=20, w=100, h=50)
    assert bounds.left == 10
    assert bounds.top == 20
    assert bounds.right == 110
    assert bounds.bottom == 70


def test_bounds_minimum_size_validation():
    # Valid bounds
    Bounds(x=0, y=0, w=4, h=4)

    # Invalid width
    with pytest.raises(ValidationError) as exc:
        Bounds(x=0, y=0, w=3, h=10)  # type: ignore
    assert "Input should be greater than or equal to 4" in str(exc.value)

    # Invalid height
    with pytest.raises(ValidationError) as exc:
        Bounds(x=0, y=0, w=10, h=3)  # type: ignore
    assert "Input should be greater than or equal to 4" in str(exc.value)

    # Invalid x, y
    with pytest.raises(ValidationError):
        Bounds(x=-1, y=0, w=10, h=10)  # type: ignore


def test_component_uuid_relationships():
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()

    comp = Component(
        id=child_id,
        number="1",
        label="Test",
        parentId=parent_id,
        bounds=Bounds(x=0, y=0, w=10, h=10),
    )

    assert comp.id == child_id
    assert comp.parentId == parent_id
    assert comp.childrenIds == []

    # Defaults
    assert comp.style.pillCorner == "top_left"


def test_component_number_digit_validation():
    # Valid numeric numbers and empty string are allowed
    Component(
        id=uuid.uuid4(),
        number="123",
        label="Test",
        bounds=Bounds(x=0, y=0, w=10, h=10),
    )
    Component(
        id=uuid.uuid4(),
        number="",
        label="Test",
        bounds=Bounds(x=0, y=0, w=10, h=10),
    )

    # Invalid non-digit characters should raise ValidationError
    with pytest.raises(ValidationError, match="Component number must contain only digits"):
        Component(
            id=uuid.uuid4(),
            number="abc",
            label="Test",
            bounds=Bounds(x=0, y=0, w=10, h=10),
        )
    with pytest.raises(ValidationError, match="Component number must contain only digits"):
        Component(
            id=uuid.uuid4(),
            number="1.2",
            label="Test",
            bounds=Bounds(x=0, y=0, w=10, h=10),
        )


def test_workspace_state_defaults_and_serialization():
    ws_id = uuid.uuid4()
    state = WorkspaceState(workspaceId=ws_id)

    assert state.version == 1
    assert state.revision == 0
    assert not state.readOnly
    assert state.screen.name == ""
    assert state.image is None
    assert state.cutLines == []
    assert state.rootComponents == []
    assert state.components == {}

    # Serialization roundtrip
    data = state.model_dump(mode="json")
    state_loaded = WorkspaceState.model_validate(data)

    assert state_loaded.workspaceId == ws_id
    assert state_loaded.version == 1
