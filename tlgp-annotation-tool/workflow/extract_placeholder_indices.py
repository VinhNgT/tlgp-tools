"""
extract_placeholder_indices.py

Parse readDocument(format='json') output to find exact character indices of
[TABLE_*] and [IMAGE_*] placeholder markers in the document.

Usage:
    $env:PYTHONUTF8=1; uv run python scripts/extract_placeholder_indices.py <json_file_path>

Output: Compact JSON to stdout with placeholder indices sorted descending.
"""
import json
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def extract_placeholders(doc_json: dict) -> dict:
    """Extract all [TABLE_*] and [IMAGE_*] placeholders with their character indices."""
    body = doc_json['body']['content']
    tables = []
    images = []

    # Regex patterns for placeholder markers
    table_pattern = re.compile(r'\[TABLE_\w+\]')
    image_pattern = re.compile(r'\[IMAGE_\w+\]')

    for elem in body:
        if 'paragraph' not in elem:
            continue
        paragraph = elem['paragraph']
        for pe in paragraph.get('elements', []):
            text_run = pe.get('textRun', {})
            content = text_run.get('content', '')
            start_index = pe.get('startIndex', 0)

            # Find table placeholders
            for match in table_pattern.finditer(content):
                placeholder = match.group()
                abs_start = start_index + match.start()
                abs_end = start_index + match.end()
                tables.append({
                    'placeholder': placeholder,
                    'startIndex': abs_start,
                    'endIndex': abs_end,
                })

            # Find image placeholders
            for match in image_pattern.finditer(content):
                placeholder = match.group()
                abs_start = start_index + match.start()
                abs_end = start_index + match.end()
                images.append({
                    'placeholder': placeholder,
                    'startIndex': abs_start,
                    'endIndex': abs_end,
                })

    # Sort descending by startIndex (for bottom-to-top insertion)
    tables.sort(key=lambda x: x['startIndex'], reverse=True)
    images.sort(key=lambda x: x['startIndex'], reverse=True)

    return {
        'tables': tables,
        'images': images,
        'totalPlaceholders': len(tables) + len(images),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_placeholder_indices.py <json_file_path>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, 'r', encoding='utf-8') as f:
        doc_json = json.load(f)

    result = extract_placeholders(doc_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
