"""
extract_heading_ranges.py

Parse readDocument(format='json') output to extract all HEADING_3 and HEADING_4
text ranges and content for styling (Step 4D.2).

Usage:
    $env:PYTHONUTF8=1; uv run python scripts/extract_heading_ranges.py <json_file_path>

Output: Compact JSON to stdout with heading indices and types.
"""
import json
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def extract_headings(doc_json: dict) -> dict:
    """Extract character ranges and text for HEADING_3 and HEADING_4 paragraphs."""
    body = doc_json['body']['content']
    headings = []

    for elem in body:
        if 'paragraph' not in elem:
            continue
        paragraph = elem['paragraph']
        style = paragraph.get('paragraphStyle', {})
        named_style = style.get('namedStyleType')

        if named_style in ('HEADING_3', 'HEADING_4'):
            text = ""
            for pe in paragraph.get('elements', []):
                text += pe.get('textRun', {}).get('content', '')
            
            headings.append({
                'type': named_style,
                'startIndex': elem.get('startIndex', 0),
                'endIndex': elem.get('endIndex', 0),
                'text': text.strip()
            })

    return {
        'headingCount': len(headings),
        'headings': headings
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_heading_ranges.py <json_file_path>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, 'r', encoding='utf-8') as f:
        doc_json = json.load(f)

    result = extract_headings(doc_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
