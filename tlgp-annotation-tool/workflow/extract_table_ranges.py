"""
extract_table_ranges.py

Parse readDocument(format='json') output to extract table metadata for styling.
Classifies tables by type and extracts text ranges needed for bold styling.

Usage:
    $env:PYTHONUTF8=1; uv run python scripts/extract_table_ranges.py <json_file_path>

Output: Compact JSON to stdout with table classifications and text ranges.
"""
import json
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Known Row 0 Col 0 text patterns for 2-col table classification
INFO_HEADER = "Tên chức năng"
SCREEN_LEVEL_INFO_HEADER = "Tên màn hình"  # Screen-level variant of info table
SCREEN_INFO_HEADER = "Mô tả chức năng"
INTERACTION_HEADER = "Hành động của tác nhân"


def get_cell_text(cell: dict) -> str:
    """Extract text content from a table cell."""
    text = ""
    for content in cell.get('content', []):
        if 'paragraph' in content:
            for elem in content['paragraph'].get('elements', []):
                text += elem.get('textRun', {}).get('content', '')
    return text.strip()


def get_cell_text_range(cell: dict) -> dict | None:
    """Get the startIndex and endIndex of text within a cell."""
    ranges = []
    for content in cell.get('content', []):
        if 'paragraph' in content:
            for elem in content['paragraph'].get('elements', []):
                tr = elem.get('textRun', {})
                text = tr.get('content', '').strip()
                if text:
                    ranges.append({
                        'startIndex': elem['startIndex'],
                        'endIndex': elem['endIndex'],
                    })
    if not ranges:
        return None
    # Merge into a single range spanning all text
    return {
        'startIndex': ranges[0]['startIndex'],
        'endIndex': ranges[-1]['endIndex'],
    }


def classify_table(cols: int, row0_col0_text: str) -> str:
    """Classify a table by column count and Row 0 Col 0 text.
    
    Classification rules (deterministic, content-based for 2-col):
    - 7 cols → uiElements
    - 6 cols → api
    - 2 cols → check Row 0 Col 0 text:
      - "Tên chức năng" → info
      - "Mô tả chức năng" → screenInfo
      - "Hành động của tác nhân" → interaction
    """
    if cols == 7:
        return "uiElements"
    elif cols == 6:
        return "api"
    elif cols == 2:
        if row0_col0_text == INFO_HEADER:
            return "info"
        elif row0_col0_text == SCREEN_LEVEL_INFO_HEADER:
            return "info"  # Same styling as component info tables
        elif row0_col0_text == SCREEN_INFO_HEADER:
            return "screenInfo"
        elif row0_col0_text == INTERACTION_HEADER:
            return "interaction"
        else:
            return "unknown_2col"
    else:
        return "unknown"


def extract_table_ranges(doc_json: dict) -> dict:
    """Extract all table metadata needed for styling steps 4D.3–4D.6."""
    body = doc_json['body']['content']
    
    # Get document end index
    end_index = body[-1].get('endIndex', 0) if body else 0

    tables = []
    table_idx = 0

    for elem in body:
        if 'table' not in elem:
            continue
        
        table = elem['table']
        cols = table.get('columns', 0)
        rows_count = table.get('rows', 0)
        table_rows = table.get('tableRows', [])

        # Get Row 0 Col 0 text for classification
        row0_col0_text = ""
        if table_rows and table_rows[0].get('tableCells'):
            row0_col0_text = get_cell_text(table_rows[0]['tableCells'][0])

        ttype = classify_table(cols, row0_col0_text)

        table_info = {
            'tableId': f'table:body:{table_idx}',
            'type': ttype,
            'rows': rows_count,
            'cols': cols,
            'startIndex': elem.get('startIndex', 0),
            'endIndex': elem.get('endIndex', 0),
        }

        # All tables have a standard header Row 0 (no column-header concept).
        # Extract the entire Row 0 text span for verification purposes.
        if table_rows:
            first_row = table_rows[0]
            cells = first_row.get('tableCells', [])
            if cells:
                first_cell_range = get_cell_text_range(cells[0])
                last_cell_range = get_cell_text_range(cells[-1])
                if first_cell_range and last_cell_range:
                    table_info['headerRowRange'] = {
                        'startIndex': first_cell_range['startIndex'],
                        'endIndex': last_cell_range['endIndex'],
                    }
                else:
                    table_info['headerRowRange'] = None
            else:
                table_info['headerRowRange'] = None
        else:
            table_info['headerRowRange'] = None

        tables.append(table_info)
        table_idx += 1

    # Build type registry
    registry = {
        'info': [],
        'screenInfo': [],
        'uiElements': [],
        'interaction': [],
        'api': [],
        'unknown': [],
    }
    for t in tables:
        key = t['type'] if t['type'] in registry else 'unknown'
        registry[key].append(t['tableId'])

    return {
        'endIndex': end_index,
        'tableCount': len(tables),
        'registry': registry,
        'tables': tables,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_table_ranges.py <json_file_path>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, 'r', encoding='utf-8') as f:
        doc_json = json.load(f)

    result = extract_table_ranges(doc_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
