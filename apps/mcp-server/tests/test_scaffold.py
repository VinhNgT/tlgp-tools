"""Tests for the scaffold_analysis module."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from doc_generator.models import AnalysisData
from mcp_server.scaffold import (
    ScaffoldResult,
    _walk_post_order_dfs,
    build_scaffold,
    scaffold_and_save,
)
from tlgp_contracts import Bounds, Component, ScreenInfo, WorkspaceState


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
) -> WorkspaceState:
    comp_dict = {c.id: c for c in (components or [])}
    return WorkspaceState(
        workspaceId=uuid4(),
        screen=ScreenInfo(name=screen_name, description=screen_desc),
        rootComponents=root_ids or [],
        components=comp_dict,
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
        comp = _make_component()
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
        assert scaffold["imageDir"] == str(tmp_path.resolve())
        assert len(scaffold["components"]) == 1

        # Leaf component: imageFile is None
        comp_entry = scaffold["components"][1]
        assert comp_entry["id"] == 1
        assert comp_entry["isLeaf"] is True
        assert comp_entry["imageFile"] is None

        # Screen
        assert "Trang chủ" in scaffold["screen"]["name"]
        assert scaffold["screen"]["imageFiles"] == ["annotated/root_Trang_chu.png"]
        assert len(scaffold["screen"]["topLevelChildren"]) == 1

    def test_non_leaf_component_gets_image_file(self, tmp_path):
        """Non-leaf components get imageFile from mapping."""
        child = _make_component()
        parent = _make_component(children_ids=[child.id])
        child = child.model_copy(update={"parentId": parent.id})

        state = _make_workspace(
            components=[parent, child],
            root_ids=[parent.id],
        )
        _make_annotated_dir(tmp_path)
        parent_img = f"annotated/1_Comp_{str(parent.id)[:8]}.png"
        _write_mapping(tmp_path, {
            "annotated": {
                "root": ["annotated/root.png"],
                "components": {
                    str(parent.id): parent_img,
                    str(child.id): f"annotated/2_Comp_{str(child.id)[:8]}.png",
                },
            },
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)

        assert len(scaffold["components"]) == 2
        # Post-order: child (id=1) then parent (id=2)
        child_entry = scaffold["components"][1]
        parent_entry = scaffold["components"][2]

        assert child_entry["isLeaf"] is True
        assert child_entry["imageFile"] is None

        assert parent_entry["isLeaf"] is False
        assert parent_entry["imageFile"] == f"annotated/1_Comp_{str(parent.id)[:8]}.png"

    def test_retains_annotated_prefix_for_image_paths(self, tmp_path):
        """Image paths in the scaffold should retain the 'annotated/' prefix."""
        comp = _make_component(children_ids=[uuid4()])
        # Add a fake child so comp is non-leaf
        child_id = comp.childrenIds[0]
        child = _make_component(component_id=child_id)
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

        # Screen imageFiles should have the prefix
        assert scaffold["screen"]["imageFiles"] == ["annotated/root_screen.png"]

        # Non-leaf component imageFile should have the prefix
        parent_entry = scaffold["components"][2]  # post-order: child first
        assert parent_entry["imageFile"] == "annotated/1_Header_abc12345.png"

    def test_placeholder_screen_name_when_empty(self, tmp_path):
        """Empty screen name gets a TODO placeholder."""
        state = _make_workspace(screen_name="", screen_desc="")
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": [], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)
        assert "[TODO" in scaffold["screen"]["name"]
        assert "[TODO" in scaffold["screen"]["description"]

    def test_preserves_nonempty_screen_metadata(self, tmp_path):
        """Non-empty screen name/description from workspace is suggested."""
        state = _make_workspace(screen_name="Cài đặt", screen_desc="Màn hình cài đặt")
        _make_annotated_dir(tmp_path)
        _write_mapping(tmp_path, {
            "annotated": {"root": [], "components": {}},
            "raw": {"root": [], "components": {}},
        })

        scaffold = build_scaffold(state, tmp_path)
        assert "Cài đặt" in scaffold["screen"]["name"]
        assert "Màn hình cài đặt" in scaffold["screen"]["description"]

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

    def test_top_level_children_control_type(self, tmp_path):
        """Non-leaf root components and leaf root components resolve correctly under AnalysisData."""
        child = _make_component()
        non_leaf_root = _make_component(children_ids=[child.id])
        child = child.model_copy(update={"parentId": non_leaf_root.id})
        leaf_root = _make_component()

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
        # Manually verify componentId is mapped in raw dict
        top_children_raw = scaffold["screen"]["topLevelChildren"]
        assert len(top_children_raw) == 2
        assert top_children_raw[0]["componentId"] is not None
        assert top_children_raw[1]["componentId"] is not None

        # Parse into AnalysisData to resolve controlType references
        analysis = AnalysisData.model_validate(scaffold)
        top_children = analysis.screen.topLevelChildren
        assert len(top_children) == 2
        assert top_children[0].controlType == "Component"
        assert top_children[1].controlType == "Component"


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
        saved = json.loads(Path(result.analysis_path).read_text(encoding="utf-8"))
        assert saved["sectionPrefix"] == "1.1"
        assert len(saved["components"]) == 1

    def test_raises_on_nonexistent_directory(self):
        state = _make_workspace()
        with pytest.raises(FileNotFoundError, match="does not exist"):
            scaffold_and_save(state, "/nonexistent/path")

    def test_saved_file_does_not_include_unit_limit(self, tmp_path):
        """The saved analysis.json does not include unitLimit config."""
        comp = _make_component()
        state = _make_workspace(
            components=[comp],
            root_ids=[comp.id],
            screen_name="Test",
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
        saved = json.loads(Path(result.analysis_path).read_text(encoding="utf-8"))

        assert "unitLimit" not in saved

