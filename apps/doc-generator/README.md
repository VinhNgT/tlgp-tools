# TLGP Doc Generator

Generate fully formatted TLGP screen specification `.docx` files from `analysis.json`.

## Usage

```bash
uv run python -m doc_generator analysis.json [-o output.docx] [--dry-run]
```

## Input

The script reads an `analysis.json` file containing the structured screen analysis. See `tlgp://schema/analysis-json` (via the MCP server) for the full field reference.

## Output

A `.docx` file with:
- Component sections with headings, info tables, UI element tables, interaction tables
- Screen overview section
- API documentation with request/response parameter tables
- All formatting applied automatically from `spec_format.toml`

## Formatting

All visual properties (fonts, colors, table widths, borders, cell padding) are defined in [`spec_format.toml`](src/doc_generator/spec_format.toml). Edit this file to change any formatting — no Python code changes needed.
