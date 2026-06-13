"""CLI entry point for the TLGP doc generator."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pydantic import ValidationError

from doc_generator.doc_builder import build_document
from doc_generator.models import AnalysisData


def _load_analysis(path: Path) -> AnalysisData:
    """Load and validate analysis.json."""
    if not path.exists():
        print(f"❌ File not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        return AnalysisData.model_validate(raw)
    except ValidationError as e:
        print(f"❌ Schema validation failed:\n{e}", file=sys.stderr)
        sys.exit(1)


def _print_summary(analysis: AnalysisData):
    """Print a dry-run summary."""
    non_leaf = [c for c in analysis.components if not c.isLeaf]
    leaf = [c for c in analysis.components if c.isLeaf]
    total_children = sum(len(c.children) for c in non_leaf)
    total_interactions = sum(len(c.interactions) for c in non_leaf)
    screen_children = len(analysis.screen.topLevelChildren)
    screen_interactions = len(analysis.screen.interactions)

    print("=" * 50)
    print("  TLGP Doc Generator — Dry Run Summary")
    print("=" * 50)
    print(f"  Section prefix:     {analysis.sectionPrefix}")
    print(f"  Export dir:         {analysis.exportDir}")
    print(f"  Screen:             {analysis.screen.name}")
    print()
    print(f"  Components:         {len(non_leaf)} non-leaf, {len(leaf)} leaf")
    print(
        f"  UI elements:        {total_children} (components) + {screen_children} (screen)"
    )
    print(
        f"  Interactions:       {total_interactions} (components) + {screen_interactions} (screen)"
    )
    print(f"  APIs:               {len(analysis.apis)}")
    print()

    # Count images
    image_count = 0
    missing_images = []
    for c in non_leaf:
        if c.imageFile:
            img = analysis.resolve_image(c.imageFile)
            image_count += 1
            if not img.exists():
                missing_images.append(str(img))
    for img_file in analysis.screen.imageFiles:
        img = analysis.resolve_image(img_file)
        image_count += 1
        if not img.exists():
            missing_images.append(str(img))

    print(f"  Images:             {image_count} referenced")
    if missing_images:
        print(f"  ⚠️  Missing images:  {len(missing_images)}")
        for m in missing_images:
            print(f"     - {m}")
    else:
        print("  ✅ All images found")

    # Estimate tables
    table_count = 0
    table_count += len(non_leaf)  # info tables
    table_count += sum(1 for c in non_leaf if c.children)  # UI tables
    table_count += sum(1 for c in non_leaf if c.interactions)  # interaction tables
    table_count += 2  # screen info + screen general info
    if screen_children:
        table_count += 1
    if screen_interactions:
        table_count += 1
    for api in analysis.apis:
        if api.requestParams:
            table_count += 1
        if api.responseFields:
            table_count += 1
        table_count += sum(1 for s in api.subDtos if s.fields)

    print(f"  Tables:             {table_count} total")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        prog="doc-generator",
        description="Generate TLGP screen spec .docx from analysis.json",
    )
    parser.add_argument(
        "analysis_json",
        nargs="?",
        help="Path to the analysis.json file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .docx file path (default: <screen_name>.docx next to the JSON)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without generating the .docx",
    )

    args = parser.parse_args()

    if args.analysis_json is None:
        parser.print_help()
        sys.exit(0)

    analysis_path = Path(args.analysis_json).resolve()
    analysis = _load_analysis(analysis_path)

    if args.dry_run:
        _print_summary(analysis)
        return

    # Build the document
    print("Building .docx...")
    doc = build_document(analysis)

    # Determine output path
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        # Default: <screen_name>.docx next to the JSON
        safe_name = analysis.screen.name.replace(" ", "_")
        output_path = analysis_path.parent / f"{safe_name}.docx"

    doc.save(str(output_path))

    # Copy analysis.json alongside the .docx for record-keeping
    # (consistent with the MCP tool behavior)
    analysis_dest = output_path.parent / "analysis.json"
    if analysis_path.resolve() != analysis_dest.resolve():
        shutil.copy2(analysis_path, analysis_dest)

    print(f"✅ Saved to: {output_path}")


if __name__ == "__main__":
    main()
