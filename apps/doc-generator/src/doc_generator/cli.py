"""CLI entry point for the TLGP doc generator."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from pydantic import ValidationError
from tlgp_logger import get_logger, setup_logging

from doc_generator.doc_builder import build_document
from doc_generator.models import AnalysisData
from doc_generator.validation import DocGenResult, validate_analysis

logger = get_logger(__name__)


def _load_analysis_raw(path: Path) -> dict:
    """Load raw JSON dict from the analysis file path.

    Returns the parsed dict on success. On failure, returns None after
    logging the error and (in non-JSON mode) exiting.
    """
    if not path.exists():
        logger.error(f"File not found: {path}")
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON", error=str(e))
        return None


def _load_analysis(path: Path) -> AnalysisData:
    """Load and validate analysis.json, exiting on error (for human-readable mode)."""
    raw = _load_analysis_raw(path)
    if raw is None:
        sys.exit(1)

    try:
        return AnalysisData.model_validate(raw)
    except ValidationError as e:
        logger.error("Schema validation failed", error=str(e))
        sys.exit(1)


def _parse_analysis(raw: dict) -> AnalysisData | list[str]:
    """Parse raw dict into AnalysisData, returning error list on failure."""
    try:
        return AnalysisData.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(loc) for loc in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return errors


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
    print(f"  Export dir:         {analysis.imageDir}")
    print(f"  Screen:             {analysis.screen.name}")
    print()
    print(f"  Components:         {len(non_leaf)} non-leaf, {len(leaf)} leaf")
    print(
        f"  UI elements:        {total_children} (components) + {screen_children} (screen)"
    )
    print(
        f"  Interactions:       {total_interactions} (components) + {screen_interactions} (screen)"
    )
    print(f"  APIs:               {len(analysis.all_apis)}")
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
    for api in analysis.all_apis:
        if api.requestParams:
            table_count += 1
        if api.responseFields:
            table_count += 1
        table_count += sum(1 for s in api.subDtos if s.fields)

    print(f"  Tables:             {table_count} total")
    print("=" * 50)


def _run_json_mode(
    analysis_path: Path,
    output_path: str | None,
    validate_only: bool,
) -> int:
    """Execute in JSON mode: all output is a single JSON object on stdout.

    Returns the process exit code (0 for success, 1 for failure).
    """
    raw = _load_analysis_raw(analysis_path)
    if raw is None:
        result = DocGenResult(valid=False, errors=[f"Failed to read {analysis_path}"])
        sys.stdout.write(result.model_dump_json())
        return 1

    parsed = _parse_analysis(raw)
    if isinstance(parsed, list):
        result = DocGenResult(valid=False, errors=parsed)
        sys.stdout.write(result.model_dump_json())
        return 1

    data: AnalysisData = parsed

    # Run validation
    vr = validate_analysis(data)

    if not vr.valid:
        result = DocGenResult.from_validation(vr)
        sys.stdout.write(result.model_dump_json())
        return 1

    if validate_only:
        result = DocGenResult.from_validation(vr)
        sys.stdout.write(result.model_dump_json())
        return 0

    # Build document
    doc = build_document(data)

    if output_path:
        out = Path(output_path).resolve()
    else:
        safe_name = (
            "".join(
                c for c in data.screen.name if c.isalnum() or c in (" ", "_", "-")
            )
            .strip()
            .replace(" ", "_")
        )
        out = Path(data.imageDir) / f"{safe_name}.docx"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))

    # Save analysis JSON alongside the docx
    analysis_json_dest = out.parent / "analysis.json"
    if analysis_path.resolve() != analysis_json_dest.resolve():
        shutil.copy2(analysis_path, analysis_json_dest)

    result = DocGenResult.from_validation(vr, output_path=str(out), tables=len(doc.tables))
    sys.stdout.write(result.model_dump_json())
    return 0


def main():
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))

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
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output a single JSON result object to stdout (machine-readable mode)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate analysis data without generating the .docx (implies --json)",
    )

    args = parser.parse_args()

    if args.analysis_json is None:
        parser.print_help()
        sys.exit(0)

    analysis_path = Path(args.analysis_json).resolve()

    # --validate-only implies --json
    if args.validate_only:
        args.json_mode = True

    # JSON mode: structured output for machine consumption
    if args.json_mode:
        exit_code = _run_json_mode(analysis_path, args.output, args.validate_only)
        sys.exit(exit_code)

    # Human-readable mode
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
    analysis_dest = output_path.parent / "analysis.json"
    if analysis_path.resolve() != analysis_dest.resolve():
        shutil.copy2(analysis_path, analysis_dest)

    print(f"✅ Saved to: {output_path}")


if __name__ == "__main__":
    main()
