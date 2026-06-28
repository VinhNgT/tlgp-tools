"""Tests for the scaffold_analysis module."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mcp_server.scaffold import (
    ScaffoldResult,
    _walk_post_order_dfs,
    build_scaffold,
    scaffold_and_save,
)
from tlgp_contracts import (
    Bounds,
    Component,
    ImageInfo,
    ScreenInfo,
    ScreenSpec,
    WorkspaceState,
)


def _make_component(
    component_id: UUID | None = None,
    parent_id: UUID | None = None,
    children_ids: list[UUID] | None = None,
    label: str = "Component",
    number: str = "1",
) -> Component:
    return Component(
        id=component_id or uuid4(),
        number=number,
        label=label,
        parentId=parent_id,
        childrenIds=children_ids or [],
        bounds=Bounds(x=0, y=0, w=100, h=100),
    )


def _make_workspace(
    components: list[Component] | None = None,
    root_ids: list[UUID] | None = None,
    screen_name: str = "",
    screen_desc: str = "",
    image: ImageInfo | None = None,
) -> WorkspaceState:
    comp_dict = {c.id: c for c in (components or [])}
    if image is None:
        image = ImageInfo(filename="root.png", width=375, height=812)
    return WorkspaceState(
        workspaceId=uuid4(),
        screen=ScreenInfo(name=screen_name, description=screen_desc),
        rootComponents=root_ids or [],
        components=comp_dict,
        image=image,
    )


def _write_mapping(export_dir: Path, mapping: dict) -> None:
    (export_dir / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
    )


def _make_annotated_dir(export_dir: Path) -> Path:
    annotated = export_dir / "annotated"
    annotated.mkdir(parents=True, exist_ok=True)
    return annotated


class TestWalkPostOrderDfs:
    def test_empty_workspace(self):
        state = _make_workspace()
        result = _walk_post_order_dfs(state)
        assert result == []

    def test_single_root(self):
        comp = _make_component()
        state = _make_workspace(components=[comp], root_ids=[comp.id])
        result = _walk_post_order_dfs(state)
        assert result == [comp.id]

    def test_children_before_parents(self):
        """Post-order DFS: children should appear before their parent."""
        child = _make_component()
        parent = _make_component(children_ids=[child.id])
        child = child.model_copy(update={"parentId": parent.id})

        state = _make_workspace(
            components=[parent, child],
            root_ids=[parent.id],
        )
        result = _walk_post_order_dfs(state)
        assert result == [child.id, parent.id]

    def test_deep_nesting(self):
        """3-level deep: grandchild → child → parent."""
        grandchild = _make_component()
        child = _make_component(children_ids=[grandchild.id])
        grandchild = grandchild.model_copy(update={"parentId": child.id})
        parent = _make_component(children_ids=[child.id])
        child = child.model_copy(update={"parentId": parent.id})

        state = _make_workspace(
            components=[parent, child, grandchild],
            root_ids=[parent.id],
        )
        result = _walk_post_order_dfs(state)
        assert result == [grandchild.id, child.id, parent.id]

    def test_multiple_roots(self):
        root_a = _make_component()
        root_b = _make_component()
        state = _make_workspace(
            components=[root_a, root_b],
            root_ids=[root_a.id, root_b.id],
        )
        result = _walk_post_order_dfs(state)
        assert result == [root_a.id, root_b.id]


class TestBuildScaffold:
    def test_minimal_scaffold(self, tmp_path):
        """A workspace with one leaf component produces a valid scaffold."""
        comp = _make_component(number="1")
        state = _make_workspace(
            components=[comp],
            root_ids=[comp.id],
            screen_name="Trang chủ",
        )
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {
                "root": ["annotated/root_Trang_chu.png"],
                "components": {str(comp.id): f"annotated/1_Comp_{str(comp.id)[:8]}.png"},
            },
            "raw": {
                "root": ["raw/root_Trang_chu.png"],
                "components": {},
            },
        })

        scaffold = build_scaffold(state, tmp_path)

        assert scaffold["sectionPrefix"] == "1.1"
        assert len(scaffold["nodes"]) == 2  # screen + comp

        # Screen (id=0)
        screen_node = scaffold["nodes"][0]
        assert screen_node["id"] == 0
        assert "Trang chủ" in screen_node["label"]
        assert screen_node["annotatedImages"] == ["annotated/root_Trang_chu.png"]
        assert screen_node["childrenIds"] == [1]
        assert screen_node["absoluteBounds"] == {"x": 0, "y": 0, "w": 375, "h": 812}

        # Leaf component (comp)
        comp_entry = scaffold["nodes"][1]
        assert comp_entry["id"] == 1
        assert comp_entry["absoluteBounds"] == {"x": 0, "y": 0, "w": 100, "h": 100}
        # In the new logic, the leaf gets a default imageFiles with its screenshot if mapped
        assert comp_entry["annotatedImages"] == [f"annotated/1_Comp_{str(comp.id)[:8]}.png"]
        assert comp_entry["childrenIds"] == []

    def test_non_leaf_component_gets_image_file(self, tmp_path):
        """Non-leaf components get imageFile from mapping."""
        child = _make_component(number="1")
        parent = _make_component(number="2", children_ids=[child.id])
        child = child.model_copy(update={"parentId": parent.id})

        state = _make_workspace(
            components=[parent, child],
            root_ids=[parent.id],
        )
        _make_annotated_dir(tmp_path)
        parent_img = f"annotated/2_Comp_{str(parent.id)[:8]}.png"
        child_img = f"annotated/1_Comp_{str(child.id)[:8]}.png"
        _write_mapping(tmp_path, {
            "annotated": {
                "root": ["annotated/root.png"],
                "components": {
                    str(parent.id): parent_img,
                    str(child.id): child_img,
                },
            },
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)

        assert len(scaffold["nodes"]) == 3  # screen + child + parent
        nodes_map = {n["id"]: n for n in scaffold["nodes"]}

        child_entry = nodes_map[1]
        parent_entry = nodes_map[2]

        assert child_entry["annotatedImages"] == [child_img]
        assert parent_entry["annotatedImages"] == [parent_img]

    def test_retains_annotated_prefix_for_image_paths(self, tmp_path):
        """Image paths in the scaffold should retain the 'annotated/' prefix."""
        comp = _make_component(number="1", children_ids=[uuid4()])
        # Add a fake child so comp is non-leaf
        child_id = comp.childrenIds[0]
        child = _make_component(number="2", component_id=child_id)
        child = child.model_copy(update={"parentId": comp.id})

        state = _make_workspace(
            components=[comp, child],
            root_ids=[comp.id],
        )
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {
                "root": ["annotated/root_screen.png"],
                "components": {
                    str(comp.id): "annotated/1_Header_abc12345.png",
                    str(child.id): "annotated/2_Child_def67890.png",
                },
            },
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)

        nodes_map = {n["id"]: n for n in scaffold["nodes"]}
        screen_node = nodes_map[0]
        comp_entry = nodes_map[1]

        # Screen imageFiles should have the prefix
        assert screen_node["annotatedImages"] == ["annotated/root_screen.png"]

        # Non-leaf component imageFile should have the prefix
        assert comp_entry["annotatedImages"] == ["annotated/1_Header_abc12345.png"]

    def test_placeholder_screen_name_when_empty(self, tmp_path):
        """Empty screen name gets a TODO placeholder."""
        state = _make_workspace(screen_name="", screen_desc="")
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": [], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)
        screen_node = scaffold["nodes"][0]
        assert "[TODO" in screen_node["label"]
        assert "[TODO" in screen_node["description"]

    def test_preserves_nonempty_screen_metadata(self, tmp_path):
        """Non-empty screen name/description from workspace is suggested."""
        state = _make_workspace(screen_name="Cài đặt", screen_desc="Màn hình cài đặt")
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": [], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)
        screen_node = scaffold["nodes"][0]
        assert "Cài đặt" in screen_node["label"]
        assert "Màn hình cài đặt" in screen_node["description"]

    def test_custom_section_prefix(self, tmp_path):
        state = _make_workspace()
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": [], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path, section_prefix="2.3")
        assert scaffold["sectionPrefix"] == "2.3"

    def test_missing_mapping_raises(self, tmp_path):
        state = _make_workspace()
        with pytest.raises(FileNotFoundError, match="mapping.json not found"):
            build_scaffold(state, tmp_path)

    def test_scaffold_parses_into_screen_spec(self, tmp_path):
        """Ensure the generated scaffold successfully validates against ScreenSpec schema."""
        child = _make_component(number="1")
        non_leaf_root = _make_component(number="2", children_ids=[child.id])
        child = child.model_copy(update={"parentId": non_leaf_root.id})
        leaf_root = _make_component(number="3")

        state = _make_workspace(
            components=[non_leaf_root, child, leaf_root],
            root_ids=[non_leaf_root.id, leaf_root.id],
        )
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": ["annotated/root.png"], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)
        spec = ScreenSpec.model_validate(scaffold)
        assert len(spec.nodes) == 4  # screen + 3 components
        assert spec.rootId == 0


class TestScaffoldAndSave:
    def test_saves_file_and_returns_result(self, tmp_path):
        comp = _make_component()
        state = _make_workspace(
            components=[comp],
            root_ids=[comp.id],
            screen_name="Trang chủ",
        )
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {
                "root": [],
                "components": {str(comp.id): f"annotated/1_Comp_{str(comp.id)[:8]}.png"},
            },
            "raw": {"root": [], "components": {}},
        })

        result = scaffold_and_save(state, str(tmp_path))

        assert isinstance(result, ScaffoldResult)
        assert result.components == 1
        assert "Trang chủ" in result.screen_name

        # Verify file was written
        saved = json.loads(Path(result.spec_path).read_text(encoding="utf-8"))
        assert saved["sectionPrefix"] == "1.1"
        assert len(saved["nodes"]) == 2

    def test_raises_on_nonexistent_directory(self):
        state = _make_workspace()
        with pytest.raises(FileNotFoundError, match="does not exist"):
            scaffold_and_save(state, "/nonexistent/path")
