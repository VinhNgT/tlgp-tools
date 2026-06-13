"""MCP prompt — loaded from spec_workflow.md at import time.

The prompt file uses two template variables:
- {section_prefix} — replaced at invocation time in server.py
- {annotation_json_example} — replaced at build time (below)
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent

# Inline annotation JSON example — embedded into the prompt at the
# {annotation_json_example} placeholder so the agent sees a concrete
# reference for the annotation export format.
_ANNOTATION_JSON_EXAMPLE = """\
{
  "screen_name": "Screen Name",
  "description": "Screen description",
  "original_image": "/path/to/original.png",
  "image_width": 1080,
  "image_height": 1920,
  "imageFiles": ["Screen_Name_annotated.png"],
  "components": [
    {
      "id": 1,
      "label": "Component Label",
      "bounds": {"x": 0, "y": 0, "w": 1080, "h": 200},
      "pill_corner": "top_left",
      "imageFile": "Screen_Name_1_annotated.png",
      "children": [
        {
          "id": 1,
          "label": "Child Label",
          "bounds": {"x": 10, "y": 10, "w": 40, "h": 40},
          "pill_corner": "top_left",
          "imageFile": null
        }
      ]
    }
  ],
  "cut_lines": [960]
}"""


def _build_prompt() -> str:
    """Load the prompt markdown and inject the annotation JSON example."""
    md_path = _PROMPT_DIR / "spec_workflow.md"
    template = md_path.read_text(encoding="utf-8")
    return template.replace("{annotation_json_example}", _ANNOTATION_JSON_EXAMPLE)


SPEC_WORKFLOW_PROMPT = _build_prompt()
