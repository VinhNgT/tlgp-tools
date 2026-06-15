import uuid
import pytest
from engine.state import get_workspace, WorkspaceManager
from engine.exceptions import ComponentNotFoundError, InvalidStateError, ParentNotFoundError, BoundaryViolationError
from models import Bounds, ImageInfo, Style, Visibility

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def workspace() -> WorkspaceManager:
    ws = get_workspace()
    ws.state.image = ImageInfo(filename="test.png", width=800, height=600)
    ws.state.components.clear()
    ws.state.rootComponents.clear()
    ws.state.cutLines.clear()
    ws._history.clear()
    ws._pointer = -1
    ws._save_history_snapshot()
    return ws

@pytest.mark.anyio
async def test_auto_numbering_layout_sort(workspace: WorkspaceManager):
    comp_a_id = uuid.uuid4()
    comp_b_id = uuid.uuid4()
    comp_c_id = uuid.uuid4()
    comp_d_id = uuid.uuid4()

    await workspace.add_component(comp_id=comp_a_id, label="Box A", bounds=Bounds(x=100, y=100, w=50, h=50))
    await workspace.add_component(comp_id=comp_b_id, label="Box B", bounds=Bounds(x=200, y=105, w=50, h=50))
    await workspace.add_component(comp_id=comp_c_id, label="Box C", bounds=Bounds(x=10, y=102, w=50, h=50))
    await workspace.add_component(comp_id=comp_d_id, label="Box D", bounds=Bounds(x=50, y=200, w=50, h=50))

    assert workspace.state.components[comp_c_id].number == "1"
    assert workspace.state.components[comp_a_id].number == "2"
    assert workspace.state.components[comp_b_id].number == "3"
    assert workspace.state.components[comp_d_id].number == "4"

    assert workspace.state.rootComponents == [comp_c_id, comp_a_id, comp_b_id, comp_d_id]

@pytest.mark.anyio
async def test_boundary_violation(workspace: WorkspaceManager):
    parent_id = uuid.uuid4()
    await workspace.add_component(comp_id=parent_id, label="Parent Box", bounds=Bounds(x=100, y=100, w=200, h=200))

    child_id = uuid.uuid4()
    with pytest.raises(BoundaryViolationError) as exc_info:
        await workspace.add_component(
            comp_id=child_id, label="Child", bounds=Bounds(x=50, y=120, w=100, h=50), parent_id=parent_id
        )
    assert "bounds violate parent boundaries" in str(exc_info.value).lower()

    valid_child_id = uuid.uuid4()
    await workspace.add_component(
        comp_id=valid_child_id, label="Valid Child", bounds=Bounds(x=120, y=120, w=50, h=50), parent_id=parent_id
    )

    with pytest.raises(BoundaryViolationError) as exc_info:
        await workspace.move_component(comp_id=parent_id, x=150, y=100)
    assert "bounds violate parent boundaries" in str(exc_info.value).lower()

@pytest.mark.anyio
async def test_child_numbering_single_digit(workspace: WorkspaceManager):
    parent_id = uuid.uuid4()
    await workspace.add_component(comp_id=parent_id, label="Parent Box", bounds=Bounds(x=100, y=100, w=300, h=300))

    child1_id = uuid.uuid4()
    await workspace.add_component(comp_id=child1_id, label="Child Box 1", bounds=Bounds(x=110, y=110, w=100, h=100), parent_id=parent_id)

    child2_id = uuid.uuid4()
    await workspace.add_component(comp_id=child2_id, label="Child Box 2", bounds=Bounds(x=220, y=110, w=50, h=50), parent_id=parent_id)

    grandchild_id = uuid.uuid4()
    await workspace.add_component(comp_id=grandchild_id, label="Grandchild", bounds=Bounds(x=120, y=120, w=50, h=50), parent_id=child1_id)

    assert workspace.state.components[parent_id].number == "1"
    assert workspace.state.components[child1_id].number == "1"
    assert workspace.state.components[child2_id].number == "2"
    assert workspace.state.components[grandchild_id].number == "1"

@pytest.mark.anyio
async def test_move_parent_shifts_descendants(workspace: WorkspaceManager):
    parent_id = uuid.uuid4()
    await workspace.add_component(comp_id=parent_id, label="Parent", bounds=Bounds(x=100, y=100, w=200, h=200))

    child_id = uuid.uuid4()
    await workspace.add_component(comp_id=child_id, label="Child", bounds=Bounds(x=120, y=120, w=50, h=50), parent_id=parent_id)

    await workspace.move_component(comp_id=parent_id, x=150, y=70)

    assert workspace.state.components[parent_id].bounds.x == 150
    assert workspace.state.components[parent_id].bounds.y == 70
    assert workspace.state.components[child_id].bounds.x == 170
    assert workspace.state.components[child_id].bounds.y == 90

@pytest.mark.anyio
async def test_resize_parent_violates_children(workspace: WorkspaceManager):
    parent_id = uuid.uuid4()
    await workspace.add_component(comp_id=parent_id, label="Parent", bounds=Bounds(x=100, y=100, w=200, h=200))

    child_id = uuid.uuid4()
    await workspace.add_component(comp_id=child_id, label="Child", bounds=Bounds(x=150, y=150, w=50, h=50), parent_id=parent_id)

    with pytest.raises(BoundaryViolationError):
        await workspace.update_component(comp_id=parent_id, bounds=Bounds(x=100, y=100, w=40, h=40))

@pytest.mark.anyio
async def test_resize_parent_keeps_children_absolute(workspace: WorkspaceManager):
    parent_id = uuid.uuid4()
    await workspace.add_component(comp_id=parent_id, label="Parent", bounds=Bounds(x=100, y=100, w=200, h=200))

    child_id = uuid.uuid4()
    await workspace.add_component(comp_id=child_id, label="Child", bounds=Bounds(x=120, y=120, w=50, h=50), parent_id=parent_id)

    await workspace.update_component(comp_id=parent_id, bounds=Bounds(x=90, y=80, w=220, h=230))

    assert workspace.state.components[parent_id].bounds.x == 90
    assert workspace.state.components[parent_id].bounds.y == 80
    assert workspace.state.components[child_id].bounds.x == 120
    assert workspace.state.components[child_id].bounds.y == 120

@pytest.mark.anyio
async def test_update_cut_lines_and_history(workspace: WorkspaceManager):
    await workspace.update_cut_lines(lines=[200, 100])
    assert workspace.state.cutLines == [100, 200]

    await workspace.undo()
    assert workspace.state.cutLines == []

    await workspace.redo()
    assert workspace.state.cutLines == [100, 200]

@pytest.mark.anyio
async def test_update_cut_lines_validation(workspace: WorkspaceManager):
    comp_id = uuid.uuid4()
    await workspace.add_component(comp_id=comp_id, label="Test", bounds=Bounds(x=100, y=150, w=100, h=100))

    with pytest.raises(InvalidStateError):
        await workspace.update_cut_lines(lines=[200])
    
    assert workspace.state.cutLines == []

    await workspace.update_cut_lines(lines=[100])
    assert workspace.state.cutLines == [100]

@pytest.mark.anyio
async def test_update_screen_info(workspace: WorkspaceManager):
    await workspace.update_screen_info(name="New Name", description="New Desc")
    assert workspace.state.screen.name == "New Name"
    assert workspace.state.screen.description == "New Desc"

@pytest.mark.anyio
async def test_update_component_visibility(workspace: WorkspaceManager):
    comp_id = uuid.uuid4()
    await workspace.add_component(comp_id=comp_id, label="Test", bounds=Bounds(x=10, y=20, w=100, h=200))

    await workspace.update_component(comp_id=comp_id, visibility=Visibility(visible=False, locked=True))

    comp = workspace.state.components[comp_id]
    assert comp.visibility.visible is False
    assert comp.visibility.locked is True

@pytest.mark.anyio
async def test_visibility_toggling_updates_numbering(workspace: WorkspaceManager):
    comp1 = uuid.uuid4()
    comp2 = uuid.uuid4()
    comp3 = uuid.uuid4()

    await workspace.add_component(comp_id=comp1, label="Comp 1", bounds=Bounds(x=10, y=10, w=50, h=50))
    await workspace.add_component(comp_id=comp2, label="Comp 2", bounds=Bounds(x=10, y=20, w=50, h=50))
    await workspace.add_component(comp_id=comp3, label="Comp 3", bounds=Bounds(x=10, y=30, w=50, h=50))

    assert workspace.state.components[comp1].number == "1"
    assert workspace.state.components[comp2].number == "2"
    assert workspace.state.components[comp3].number == "3"

    await workspace.update_component(comp_id=comp2, visibility=Visibility(visible=False, locked=False))

    assert workspace.state.components[comp1].number == "1"
    assert workspace.state.components[comp2].number == ""
    assert workspace.state.components[comp3].number == "2"
