"""MCP prompt content loaders.

Loads markdown-based reference guides and workflow instructions from files
co-located in this package directory.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def get_strict_guidelines_content() -> str:
    """Read the consolidated strict guidelines from markdown."""
    return (_PROMPT_DIR / "strict_guidelines.md").read_text(encoding="utf-8").strip()


def get_spec_workflow_content() -> str:
    """Load the spec workflow instructions for agent reference."""
    workflow = (_PROMPT_DIR / "spec_workflow.md").read_text(encoding="utf-8")
    guidelines = get_strict_guidelines_content()
    return workflow.replace("{strict_guidelines}", guidelines).strip()


_PROMPT_MAP = {
    "analysis.json Schema Reference": "schema_reference.md",
    "UI Control Type Classification Guide": "classification_guide.md",
    "Example: Complete Analysis Dict": "example_analysis.json",
}


def get_prompt_section(section_title: str) -> str:
    """Load the standalone files corresponding to each prompt section."""
    filename = _PROMPT_MAP.get(section_title)
    if not filename:
        return ""

    content = (_PROMPT_DIR / filename).read_text(encoding="utf-8").strip()

    if section_title == "Example: Complete Analysis Dict":
        return f"## Example: Complete Analysis Dict\n\n```json\n{content}\n```"

    return content
