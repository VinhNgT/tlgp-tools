# TLGP Tools

uv monorepo containing internal developer tools for TLGP screen specifications.

## Packages

| Package | Description |
|---------|-------------|
| `tlgp-annotation-tool` | GUI screenshot annotator with hierarchical component boxing |
| `tlgp-doc-generator` | Generate `.docx` specification documents from `analysis.json` |
| `tlgp-mcp-server` | MCP server exposing the toolchain to AI agents |

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

# Start the MCP server (for AI agent integration)
uv run python -m tlgp_mcp_server
```

## Testing

```bash
uv run pytest -v
```
