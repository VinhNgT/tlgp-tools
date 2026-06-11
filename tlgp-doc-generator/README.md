# TLGP Doc Generator

Generate fully formatted TLGP screen specification `.docx` files from `analysis.json`.

## Usage

```bash
uv run python -m tlgp_doc_generator analysis.json [-o output.docx] [--dry-run]
```

## Input

The script reads an `analysis.json` file produced by the agent during Phase 3 (screen analysis). See the schema in the implementation plan.

## Output

A `.docx` file with:
- Component sections with headings, info tables, UI element tables, interaction tables
- Screen overview section
- API documentation with request/response parameter tables
- All formatting matching the TLGP reference document exactly

## Copy-Paste Workflow

1. Upload the generated `.docx` to Google Drive
2. Open the auto-converted Google Doc
3. Select All → Copy
4. Paste into the target Google Doc at the desired position
