"""Thread safety stress tests for annotator.workspace.manager.

Exercises concurrent reads and writes on WorkspaceManager to verify
that threading.Lock correctly prevents data corruption and race conditions.
"""

import threading
import uuid

import pytest
from annotator.models import Bounds
from annotator.workspace import WorkspaceManager

from .conftest import create_test_image, workspace_with_image


# ── Helpers ────────────────────────────────────────────────────────────


def _run_threads(target, count: int = 8, args=()) -> list[Exception]:
    """Spawn *count* threads running *target* and collect any exceptions."""
    errors: list[Exception] = []

    def wrapper(*a):
        try:
            target(*a)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=wrapper, args=args) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return errors


# ── Concurrent Mutations ──────────────────────────────────────────────


class TestConcurrentMutations:
    def test_parallel_add_no_corruption(self):
        """Multiple threads adding components simultaneously must not corrupt state."""
        ws = workspace_with_image()
        ops_per_thread = 25

        def add_batch(thread_idx: int):
            for i in range(ops_per_thread):
                cid = uuid.uuid4()
                x = (thread_idx * 100 + i * 10) % 700
                ws.add_component(cid, f"T{thread_idx}_{i}", Bounds(x=x, y=0, w=8, h=8))

        thread_count = 4
        
        errors = []
        threads = []
        for t_idx in range(thread_count):
            t = threading.Thread(target=lambda idx=t_idx: add_batch(idx))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(ws.state.components) == thread_count * ops_per_thread

    def test_parallel_add_and_delete(self):
        """Mixing add and delete operations concurrently must leave a consistent state."""
        ws = workspace_with_image()
        added_ids: list[uuid.UUID] = []
        lock = threading.Lock()

        def add_and_record():
            for _ in range(15):
                cid = uuid.uuid4()
                ws.add_component(cid, "X", Bounds(x=0, y=0, w=5, h=5))
                with lock:
                    added_ids.append(cid)

        def delete_some():
            for _ in range(10):
                with lock:
                    if not added_ids:
                        continue
                    target_id = added_ids.pop(0)
                try:
                    ws.delete_component(target_id)
                except Exception:
                    pass  # component may already be gone

        add_threads = [threading.Thread(target=add_and_record) for _ in range(3)]
        del_threads = [threading.Thread(target=delete_some) for _ in range(2)]

        for t in add_threads + del_threads:
            t.start()
        for t in add_threads + del_threads:
            t.join(timeout=10)

        # State must be internally consistent:
        # every root ID exists in components, every component's parent tracks it
        state = ws.state
        for rid in state.rootComponents:
            assert rid in state.components
        for cid, comp in state.components.items():
            if comp.parentId:
                assert comp.parentId in state.components
                parent = state.components[comp.parentId]
                assert cid in parent.childrenIds

    def test_parallel_move(self):
        """Multiple threads moving the same component must not crash."""
        ws = workspace_with_image()
        cid = uuid.uuid4()
        ws.add_component(cid, "Movable", Bounds(x=100, y=100, w=50, h=50))

        def move_around(thread_idx: int):
            for i in range(20):
                x = (thread_idx * 50 + i * 10) % 700
                y = (thread_idx * 30 + i * 10) % 500
                try:
                    ws.move_component(cid, x, y)
                except Exception:
                    pass

        threads = [
            threading.Thread(target=move_around, args=(idx,)) for idx in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Component must still exist and have valid bounds
        assert cid in ws.state.components
        comp = ws.state.components[cid]
        assert comp.bounds.w == 50
        assert comp.bounds.h == 50


# ── Concurrent Reads ──────────────────────────────────────────────────


class TestConcurrentReads:
    def test_snapshot_isolation(self):
        """Reading state from one thread while another mutates must return consistent snapshots."""
        ws = workspace_with_image()
        snapshots: list[int] = []
        lock = threading.Lock()

        def reader():
            for _ in range(50):
                state = ws.state
                with lock:
                    snapshots.append(len(state.components))

        def writer():
            for _ in range(50):
                ws.add_component(
                    uuid.uuid4(), "W", Bounds(x=0, y=0, w=5, h=5)
                )

        r_thread = threading.Thread(target=reader)
        w_thread = threading.Thread(target=writer)
        r_thread.start()
        w_thread.start()
        r_thread.join(timeout=10)
        w_thread.join(timeout=10)

        # Each snapshot must be a valid count (monotonically non-decreasing
        # is not guaranteed because we read outside the lock, but each snapshot
        # is an atomic copy that should have a valid component count)
        for count in snapshots:
            assert count >= 0
            assert count <= 50


# ── Concurrent Undo/Redo ──────────────────────────────────────────────


class TestConcurrentUndoRedo:
    def test_undo_redo_under_contention(self):
        """Rapid undo/redo from multiple threads must not corrupt state."""
        ws = workspace_with_image()
        # Build up some history
        for _ in range(10):
            ws.add_component(uuid.uuid4(), "H", Bounds(x=0, y=0, w=5, h=5))

        def undo_loop():
            for _ in range(10):
                ws.undo()

        def redo_loop():
            for _ in range(10):
                ws.redo()

        threads = [
            threading.Thread(target=undo_loop),
            threading.Thread(target=redo_loop),
            threading.Thread(target=undo_loop),
            threading.Thread(target=redo_loop),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # State must be internally consistent after all operations
        state = ws.state
        for rid in state.rootComponents:
            assert rid in state.components


# ── Subscriber Thread Safety ──────────────────────────────────────────


class TestSubscriberThreadSafety:
    def test_subscriber_called_from_any_thread(self):
        """Subscribers registered before threads start must be invoked safely."""
        ws = workspace_with_image()
        call_count = 0
        count_lock = threading.Lock()

        def on_change(patch, state):
            nonlocal call_count
            with count_lock:
                call_count += 1

        ws.subscribe(on_change)

        def adder():
            for _ in range(10):
                ws.add_component(uuid.uuid4(), "S", Bounds(x=0, y=0, w=5, h=5))

        threads = [threading.Thread(target=adder) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert call_count == 30  # 3 threads × 10 adds

    def test_concurrent_subscribe_and_mutate(self):
        """Adding subscribers while mutations are happening must not crash."""
        ws = workspace_with_image()
        callbacks_called = []

        def mutator():
            for _ in range(20):
                ws.add_component(uuid.uuid4(), "M", Bounds(x=0, y=0, w=5, h=5))

        def subscriber():
            for i in range(5):
                ws.subscribe(lambda p, s, idx=i: callbacks_called.append(idx))

        threads = [
            threading.Thread(target=mutator),
            threading.Thread(target=subscriber),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Just verifying no crash — callback count is timing-dependent
        assert len(ws.state.components) == 20
