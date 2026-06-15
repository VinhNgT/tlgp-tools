import asyncio
import uuid
import pytest
import httpx
from engine.app import app
from engine.state import get_workspace
from models import ImageInfo

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def setup_workspace():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=2000, height=2000)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()
    workspace._history.clear()
    workspace._pointer = -1
    workspace._save_history_snapshot()
    return workspace

@pytest.mark.anyio
async def test_concurrent_mutations_maintain_history():
    """
    Tests that firing many concurrent mutation requests accurately locks,
    serializes, and preserves the history stack sequentially without
    losing any patches or writes.
    """
    workspace = get_workspace()
    
    # Pre-create a component
    comp_id = uuid.uuid4()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/components",
            json={
                "id": str(comp_id),
                "label": "Concurrent Target",
                "bounds": {"x": 100, "y": 100, "w": 100, "h": 100},
            },
        )
        assert res.status_code == 200

    # Start 100 concurrent move requests, each moving it by (1, 1)
    async def move_task(client: httpx.AsyncClient, i: int):
        await client.put(
            f"/components/{comp_id}/move",
            json={"x": 100 + i, "y": 100 + i}
        )

    # Note: Using AsyncClient(app=app) bypasses network and hits the ASGI app directly
    # Wait, passing app directly to AsyncClient requires 'transport=httpx.ASGITransport(app=app)' in modern httpx
    # To be safe against httpx versions:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # The first request above created 1 snapshot.
        # Now we fire 100 move requests concurrently.
        tasks = [move_task(client, i) for i in range(1, 101)]
        await asyncio.gather(*tasks)

    # If the lock worked, there should be exactly 102 snapshots in history
    # (1 empty init, 1 component add, 100 moves)
    assert len(workspace._history) == 102
    assert workspace._pointer == 101

@pytest.mark.anyio
async def test_concurrent_tree_recalculations():
    """
    Tests that simultaneous updates to bounds on siblings/children don't 
    corrupt the recalculate_tree boundaries.
    """
    workspace = get_workspace()
    
    parent_id = uuid.uuid4()
    child_ids = [uuid.uuid4() for _ in range(50)]
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create parent
        await client.post(
            "/components",
            json={
                "id": str(parent_id),
                "label": "Parent",
                "bounds": {"x": 0, "y": 0, "w": 1000, "h": 1000},
            },
        )
        
        # Create 50 children linearly
        for i, cid in enumerate(child_ids):
            await client.post(
                "/components",
                json={
                    "id": str(cid),
                    "label": f"Child {i}",
                    "parentId": str(parent_id),
                    "bounds": {"x": 10, "y": 10, "w": 50, "h": 50},
                },
            )
            
        # Concurrently resize all children
        async def resize_child(cid: uuid.UUID, i: int):
            await client.put(
                f"/components/{cid}",
                json={"bounds": {"x": 10, "y": 10, "w": 60 + i, "h": 60 + i}}
            )
            
        tasks = [resize_child(cid, i) for i, cid in enumerate(child_ids)]
        await asyncio.gather(*tasks)
        
    # Check that children resized
    # And tree math was run (all children should have assigned numbers instead of empty string)
    for cid in child_ids:
        comp = workspace.state.components[cid]
        assert comp.number != ""
        assert comp.bounds.w >= 60

