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


def get_strict_guidelines_content() -> str:
    """Read the consolidated strict guidelines from markdown."""
    return (_PROMPT_DIR / "strict_guidelines.md").read_text(encoding="utf-8").strip()


def _build_prompt() -> str:
    """Load the prompt markdown containing workflow instructions."""
    workflow = (_PROMPT_DIR / "spec_workflow.md").read_text(encoding="utf-8")
    guidelines = get_strict_guidelines_content()
    return workflow.replace("{strict_guidelines}", guidelines).strip()


def get_spec_workflow_prompt() -> str:
    """Lazy builder to load and assemble the spec workflow prompt template."""
    return _build_prompt()


def get_prompt_section(section_title: str) -> str:
    """Load the standalone files corresponding to each prompt section."""
    if section_title == "analysis.json Schema Reference":
        return (_PROMPT_DIR / "schema_reference.md").read_text(encoding="utf-8").strip()
    elif section_title == "UI Control Type Classification Guide":
        return (_PROMPT_DIR / "classification_guide.md").read_text(encoding="utf-8").strip()
    elif section_title == "Example: Complete Analysis Dict":
        example_json = (_PROMPT_DIR / "example_analysis.json").read_text(encoding="utf-8").strip()
        return f"## Example: Complete Analysis Dict\n\n```json\n{example_json}\n```"
    return ""
