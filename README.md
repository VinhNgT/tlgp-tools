# TLGP Tools

uv monorepo containing internal developer tools for TLGP screen specifications.

## Packages

| Package | Description |
|---------|-------------|
| `tlgp-annotation-tool` | Hierarchical screenshot annotator for TLGP screen specs |
| `tlgp-doc-generator` | Generate TLGP screen spec `.docx` from `analysis.json` |

## Setup

```bash
uv sync
```

## Usage

```bash
# Launch the annotation tool
uv run python -m tlgp_annotation_tool

# Generate a spec doc
uv run python -m tlgp_doc_generator analysis.json
```
