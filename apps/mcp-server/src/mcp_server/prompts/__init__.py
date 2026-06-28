"""MCP prompt content loaders.

Each public function loads a single markdown or JSON reference file
co-located in this package directory. There is exactly one loader per
content file — no indirection maps or template substitution.
"""

from __future__ import annotations

from pathlib import Path

from tlgp_contracts import get_example_spec_json

_PROMPT_DIR = Path(__file__).parent


def _read(filename: str) -> str:
    return (_PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


def get_spec_workflow() -> str:
    """Step-by-step workflow for creating specification documents."""
    return _read("spec_workflow.md")


def get_validation_guide() -> str:
    """Detailed validation rules mapping 1-to-1 to validator checks."""
    return _read("validation_guide.md")


def get_writing_guide() -> str:
    """Semantic writing rules and UI control type classification rules."""
    return _read("writing_guide.md")


def get_example_analysis() -> str:
    """A complete example analysis.json, wrapped in a markdown code fence."""
    raw = get_example_spec_json().strip()
    return f"## Example: Complete Analysis JSON\n\n```json\n{raw}\n```"
