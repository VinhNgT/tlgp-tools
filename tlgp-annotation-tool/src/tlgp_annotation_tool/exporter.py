import os
import json
from typing import List, Tuple
from PIL import Image
from tlgp_annotation_tool.models import ScreenSession, AnnotationBox
from tlgp_annotation_tool.annotation_renderer import draw_annotations_on_image


def _export_level_images(full_img: Image.Image, children: List[AnnotationBox],
                         depth: int, output_dir: str, safe_name: str,
                         parent_box: AnnotationBox = None,
                         parent_path: str = "",
                         cut_lines: List[int] = None):
    """Recursively exports one annotated image per parent that has children.

    Each image shows only the immediate children of that parent.
    Annotation drawing is delegated to the shared annotation_renderer module.

    At root level, if cut_lines are provided, the image is split into
    N+1 segments and exported as separate part files.
    """
    if not children:
        return []

    exported_paths = []

    if parent_box is None:
        # Root level
        if cut_lines:
            # Split into segments and export each as a separate file
            img_h = full_img.height
            boundaries = [0] + sorted(cut_lines) + [img_h]

            for part_idx in range(len(boundaries) - 1):
                seg_y_start = boundaries[part_idx]
                seg_y_end = boundaries[part_idx + 1]

                if seg_y_end <= seg_y_start:
                    continue

                # Crop the segment
                seg_img = full_img.crop((0, seg_y_start, full_img.width, seg_y_end))

                # Filter children whose vertical center falls in this segment
                seg_children = []
                for child in children:
                    center_y = (child.top + child.bottom) / 2
                    if seg_y_start <= center_y < seg_y_end:
                        seg_children.append(child)

                # Draw annotations — offset_y is the segment's start so
                # absolute box coords are correctly translated to segment-local coords.
                # full_img_width stays the ORIGINAL image width for consistent pill sizing.
                draw_annotations_on_image(
                    seg_img, seg_children,
                    offset_x=0, offset_y=seg_y_start,
                    parent_box=None,
                    full_img_width=full_img.width,
                )

                filename = f"{safe_name}_annotated_part{part_idx + 1}.png"
                path = os.path.join(output_dir, filename)
                seg_img.save(path, "PNG")
                exported_paths.append(path)
        else:
            # No cuts — single root image (original behavior)
            img = full_img.copy()
            offset_x, offset_y = 0, 0
            filename = f"{safe_name}_annotated.png"

            draw_annotations_on_image(img, children, offset_x, offset_y, parent_box, full_img.width)
            path = os.path.join(output_dir, filename)
            img.save(path, "PNG")
            exported_paths.append(path)
    else:
        # Crop to the parent box bounds
        crop_box = (parent_box.left, parent_box.top, parent_box.right, parent_box.bottom)
        img = full_img.crop(crop_box)
        offset_x, offset_y = parent_box.left, parent_box.top
        filename = f"{safe_name}_{parent_path}_annotated.png"

        draw_annotations_on_image(img, children, offset_x, offset_y, parent_box, full_img.width)
        img.save(os.path.join(output_dir, filename), "PNG")

    # Recurse for each child that has its own children
    for child in children:
        if child.children:
            child_path = f"{parent_path}_{child.id}" if parent_path else str(child.id)
            _export_level_images(
                full_img, child.children,
                depth + 1, output_dir, safe_name,
                parent_box=child,
                parent_path=child_path,
            )

    return exported_paths


def export_session(session: ScreenSession, output_dir: str):
    """Exports ScreenSession data as JSON and annotated PNG images.

    Generates one annotated image per parent node. The root image shows L1
    components on the full screenshot. Each parent with children gets a
    separate cropped image showing only its immediate children.

    When cut_lines are present, the root-level export produces N+1 separate
    part images instead of a single annotated image.

    Returns (json_path, list_of_root_annotated_paths).
    """
    safe_name = "".join(c for c in session.screen_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    if not safe_name:
        safe_name = "screen_spec"

    # Create subfolder named after the screen
    target_dir = os.path.join(output_dir, safe_name)
    os.makedirs(target_dir, exist_ok=True)

    json_path = os.path.join(target_dir, f"{safe_name}.json")

    # Image export check & load
    if not session.original_image or not os.path.exists(session.original_image):
        raise FileNotFoundError(f"Original image not found: {session.original_image}")

    img = Image.open(session.original_image)

    # JSON export
    data = {
        "screen_name": session.screen_name,
        "description": session.description,
        "original_image": session.original_image,
        "image_width": img.width,
        "image_height": img.height,
        "components": [comp.to_dict() for comp in session.components],
    }
    if session.cut_lines:
        data["cut_lines"] = sorted(session.cut_lines)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    root_paths = _export_level_images(
        full_img=img,
        children=session.components,
        depth=0,
        output_dir=target_dir,
        safe_name=safe_name,
        parent_box=None,
        parent_path="",
        cut_lines=session.cut_lines if session.cut_lines else None,
    )

    return json_path, root_paths
