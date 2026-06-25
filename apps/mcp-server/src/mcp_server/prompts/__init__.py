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


def get_prompt_section(section_title: str) -> str:
    """Load the standalone files corresponding to each prompt section."""
    if section_title == "analysis.json Schema Reference":
        return (_PROMPT_DIR / "schema_reference.md").read_text(encoding="utf-8").strip()
    elif section_title == "UI Control Type Classification Guide":
        return (
            (_PROMPT_DIR / "classification_guide.md")
            .read_text(encoding="utf-8")
            .strip()
        )
    elif section_title == "Example: Complete Analysis Dict":
        example_json = (
            (_PROMPT_DIR / "example_analysis.json").read_text(encoding="utf-8").strip()
        )
        return f"## Example: Complete Analysis Dict\n\n```json\n{example_json}\n```"
    return ""
