# TLGP Doc Generator

Generate fully formatted TLGP screen specification `.docx` files from `analysis.json`.

## Usage

```bash
uv run doc-gen analysis.json [-o output.docx] [--dry-run] [--validate-only] [--json]
```

- `--dry-run`: Print a summary without generating the document.
- `--validate-only`: Validate the analysis data without generating the `.docx`.
- `--json`: Output a single JSON result object to stdout (machine-readable mode used by the MCP server).

## Input

The script reads an `analysis.json` file containing the structured screen analysis. See the Pydantic model definitions in [`models.py`](src/doc_generator/models.py) for the canonical schema.

## Output

- A `.docx` file with:
  - Component sections with headings, info tables, UI element tables, interaction tables
  - Screen overview section
  - API documentation with request/response parameter tables
  - All formatting applied automatically from `spec_format.toml`
- An `analysis.json` file copied/saved in the same directory as the `.docx` file for record-keeping.

## Formatting

All visual properties (fonts, colors, table widths, borders, cell padding) are defined in [`spec_format.toml`](src/doc_generator/spec_format.toml). Edit this file to change any formatting — no Python code changes needed.

## Testing

```bash
uv run pytest apps/doc-generator/
```
