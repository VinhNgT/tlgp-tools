"""Tool: list_exports — inspect an output directory and report its state."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


# Filename patterns for recognizing annotation tool exports
_ANNOTATED_IMG_RE = re.compile(r".*_annotated(?:_part\d+)?\.png$", re.IGNORECASE)


def _find_screen_dirs(output_dir: Path) -> list[Path]:
    """Find subdirectories that look like annotation exports.

    The annotation tool creates a subfolder named after the screen
    (e.g., Chi_tiet_san_pham/) containing JSON + images.
    """
    candidates = []
    for child in output_dir.iterdir():
        if child.is_dir():
            # Check if it contains a JSON file with the same name
            json_file = child / f"{child.name}.json"
            if json_file.exists():
                candidates.append(child)
    return candidates


def _inspect_screen_dir(screen_dir: Path) -> dict:
    """Inspect a single screen export directory."""
    name = screen_dir.name
    annotation_json = screen_dir / f"{name}.json"
    analysis_json = screen_dir / "analysis.json"

    # Find annotated images
    annotated_images = sorted(
        f.name
        for f in screen_dir.iterdir()
        if f.is_file() and _ANNOTATED_IMG_RE.match(f.name)
    )

    # Find generated .docx files
    docx_files = sorted(
        f.name for f in screen_dir.iterdir() if f.suffix == ".docx"
    )

    # Check annotation JSON integrity
    issues = []
    components_with_children = 0
    if annotation_json.exists():
        try:
            data = json.loads(annotation_json.read_text(encoding="utf-8"))
            components = data.get("components", [])

            # Count components that should have cropped images
            def _count_parents(comps: list[dict]) -> int:
                count = 0
                for c in comps:
                    children = c.get("children", [])
                    if children:
                        count += 1
                        count += _count_parents(children)
                return count

            components_with_children = _count_parents(components)

            # Check expected images: root image(s) + one per parent component
            cut_lines = data.get("cut_lines", [])
            if cut_lines:
                expected_root = len(cut_lines) + 1
            else:
                expected_root = 1

            expected_total = expected_root + components_with_children

            if len(annotated_images) < expected_total:
                missing_count = expected_total - len(annotated_images)
                issues.append(
                    f"Expected {expected_total} annotated images "
                    f"({expected_root} root + {components_with_children} component), "
                    f"but found {len(annotated_images)} ({missing_count} missing)"
                )
        except (json.JSONDecodeError, KeyError) as e:
            issues.append(f"Failed to parse annotation JSON: {e}")

    # Determine status
    has_annotation = annotation_json.exists()
    has_analysis = analysis_json.exists()
    has_docx = len(docx_files) > 0

    if not has_annotation and not has_analysis:
        status = "empty"
    elif has_annotation and not has_analysis and not issues:
        status = "annotations_only"
    elif has_annotation and not has_analysis and issues:
        status = "malformed"
    elif has_analysis and not has_docx:
        status = "ready"
    elif has_analysis and has_docx:
        status = "complete"
    else:
        status = "malformed"

    return {
        "status": status,
        "screen_name": name,
        "screen_dir": str(screen_dir),
        "annotation_json": str(annotation_json) if has_annotation else None,
        "analysis_json": str(analysis_json) if has_analysis else None,
        "generated_docx": docx_files[0] if has_docx else None,
        "annotated_images": annotated_images,
        "issues": issues,
    }


def list_exports_impl(output_dir: str) -> dict:
    """Inspect the output directory and report folder state."""
    path = Path(output_dir).resolve()

    if not path.exists():
        return {
            "status": "not_found",
            "output_dir": str(path),
            "message": "Directory does not exist. Create it and launch the annotator.",
            "screens": [],
        }

    if not path.is_dir():
        return {
            "status": "malformed",
            "output_dir": str(path),
            "message": "Path exists but is not a directory.",
            "screens": [],
            "issues": [f"{path} is a file, not a directory"],
        }

    screen_dirs = _find_screen_dirs(path)

    if not screen_dirs:
        # Check if the output_dir itself is a screen dir
        json_candidate = path / f"{path.name}.json"
        if json_candidate.exists():
            screen_info = _inspect_screen_dir(path)
            return {
                "status": screen_info["status"],
                "output_dir": str(path),
                "screens": [screen_info],
            }
        return {
            "status": "empty",
            "output_dir": str(path),
            "message": "No annotation exports found. Launch the annotator to create them.",
            "screens": [],
        }

    screens = [_inspect_screen_dir(d) for d in screen_dirs]

    # Overall status: worst status wins
    statuses = [s["status"] for s in screens]
    if "malformed" in statuses:
        overall = "malformed"
    elif all(s == "complete" for s in statuses):
        overall = "complete"
    elif all(s == "ready" for s in statuses):
        overall = "ready"
    elif all(s in ("annotations_only", "ready", "complete") for s in statuses):
        overall = "annotations_only"
    else:
        overall = "malformed"

    return {
        "status": overall,
        "output_dir": str(path),
        "screens": screens,
    }
