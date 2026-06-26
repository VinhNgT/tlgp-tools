"""MCP prompt content loaders.

Each public function loads a single markdown or JSON reference file
co-located in this package directory. There is exactly one loader per
content file — no indirection maps or template substitution.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def _read(filename: str) -> str:
    return (_PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


def get_spec_workflow() -> str:
    """Step-by-step workflow for creating specification documents."""
    return _read("spec_workflow.md")


def get_classification_guide() -> str:
    """Rules for categorizing UI elements into control types."""
    return _read("classification_guide.md")


def get_example_analysis() -> str:
    """A complete example analysis.json, wrapped in a markdown code fence."""
    raw = _read("example_analysis.json")
    return f"## Example: Complete Analysis JSON\n\n```json\n{raw}\n```"
